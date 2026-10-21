"""On-demand recovery of only a known, approved instance."""
import threading
import time
import uuid
from .contracts import canonical, digest, load_json
from .lmstudio import ActivityWatch, Runtime, final_text, select_loaded
from .profiles import authorize_job, verify_runtime_binding
from .store import Store, atomic_json
from .worker import ownership, launch


def update_instance(store, key, fields, state="recovering"):
    with store.db(write=True) as db:
        row = db.execute("SELECT data FROM instances WHERE instance_key=?", (key,)).fetchone()
        data = {**load_json(row["data"]), **fields}
        db.execute("UPDATE instances SET state=?,data=? WHERE instance_key=?", (state, canonical(data), key))


def close_instance(store, key):
    current = store.instance(key)
    if current["data"].get("recovery_phase") == "retired": return
    if current["state"] == "ready":
        update_instance(store, key, {"recovery_phase": "unload"}, "closed")


def request_recovery(state_dir, instance_key):
    store = Store(state_dir)
    current = store.instance(instance_key)
    if (current["state"] == "ready" or current["data"].get("recovery_phase") == "retired"
            or current["data"].get("recovery_blocked")
            or current["data"].get("next_recovery_at", 0) > time.time()): return
    with ownership(store, "recovery-" + digest([current["data"]["endpoint"], current["data"]["model_id"]])) as available:
        if available:
            launch(state_dir, "recover", instance_key)


def current_loaded(runtime, profile):
    snapshot = runtime.list_models()
    loaded = select_loaded(snapshot, profile)
    matches = [m for m in snapshot.get("models", []) if m.get("key") == profile["model_id"]]
    if len(matches) != 1 or len(matches[0].get("loaded_instances", [])) > 1:
        raise ValueError("unaccounted_instances")
    verify_runtime_binding(profile, matches[0])
    if not matches[0].get("loaded_instances"): return None
    if loaded is None: raise ValueError("invalid_loaded_configuration")
    return loaded


def probe(runtime, profile, instance_id):
    watch = ActivityWatch(profile["stale_tolerance_seconds"], time.monotonic())
    stop, stale = threading.Event(), threading.Event()
    def watchdog():
        while not stop.wait(.25):
            if watch.is_stale(time.monotonic()):
                stale.set()
                runtime.abort()
    thread = threading.Thread(target=watchdog, daemon=True)
    thread.start()
    answer, started = [], False
    try:
        body = {"model": instance_id, "input": "Return exactly PROBE_OK", "stream": True, "store": False,
                **profile["request_settings"], "max_output_tokens": 512}
        for event, data in runtime.stream(body):
            if stale.is_set(): raise ValueError("probe_stale")
            if event == "chat.start":
                if started or data.get("model_instance_id") != instance_id:
                    raise ValueError("probe_instance_changed")
                started = True
            if event == "error" or event.startswith(("tool_call.", "model_load.")):
                raise ValueError("probe_error")
            watch.observe(event, data, time.monotonic())
            if event == "message.delta":
                answer.append(data.get("content", ""))
                if sum(map(len, answer)) > 1024: raise ValueError("invalid_probe")
            if event == "chat.end":
                if not started or "".join(answer) != "PROBE_OK" or final_text(data.get("result")) != "PROBE_OK":
                    raise ValueError("invalid_probe")
                watch.done = True
                return
        raise ValueError("incomplete_probe")
    finally:
        stop.set()
        runtime.abort()
        thread.join(2)


def recover_once(store, key, runtime):
    instance = store.instance(key)
    if instance["state"] == "ready" or instance["data"].get("recovery_phase") == "retired": return True
    profile = instance["data"]["profile"]
    approved = authorize_job(store, {"profile": profile, "brief": {"capability": profile["capabilities"][0]}})
    if approved["approval"] != profile["approval"] or approved["model_id"] != profile["model_id"]:
        raise ValueError("approval_changed")
    with store.db() as db:
        peers = [load_json(row["data"]) for row in db.execute(
            "SELECT DISTINCT i.data FROM instances i JOIN attempts a USING(instance_key) WHERE a.state IN ('reserved','submitting','streaming')")]
    healthy = any(p["endpoint"] == profile["endpoint"] and p["model_id"] == profile["model_id"] for p in peers)
    if healthy: return False
    phase = instance["data"].get("recovery_phase", "unload")
    loaded = current_loaded(runtime, profile)
    if phase == "load" and loaded:
        loaded_key = digest([loaded["endpoint"], loaded["model_id"], loaded["instance_id"]])
        with store.db() as db:
            tracked = db.execute("SELECT 1 FROM instances WHERE instance_key=?", (loaded_key,)).fetchone()
        # A different record may already own an uncertain probe on this replacement.
        if loaded_key != key and tracked: raise ValueError("unaccounted_instances")
    if phase in ("probe_submitting", "probe_uncertain"):
        update_instance(store, key, {"recovery_phase": "unload"})
        phase = "unload"
    if phase == "unload":
        if loaded:
            if loaded["instance_id"] != instance["data"].get("loaded", instance["data"])["instance_id"]:
                raise ValueError("unaccounted_instances")
            try: runtime.unload(loaded["instance_id"])
            except (OSError, ValueError): pass
            if current_loaded(runtime, profile) is not None:
                raise ValueError("unload_not_confirmed")
        update_instance(store, key, {"recovery_phase": "load"})
        phase, loaded = "load", None
    if phase == "load":
        if loaded is None:
            try:
                runtime.load({"model": profile["model_id"], "context_length": instance["data"]["config"]["context_length"]})
            except (OSError, ValueError): pass
            loaded = current_loaded(runtime, profile)
        if loaded is None: raise ValueError("load_not_confirmed")
        update_instance(store, key, {"recovery_phase": "probe", "loaded": loaded})
    else:
        if loaded is None: raise ValueError("probe_instance_lost")
        if loaded["instance_id"] != instance["data"]["loaded"]["instance_id"]:
            raise ValueError("unaccounted_instances")
    probe_id = uuid.uuid4().hex
    receipt = store.root / "probes" / key / (probe_id + ".json")
    atomic_json(receipt, {"generation": instance["generation"], "state": "submitting", "time": time.time()})
    update_instance(store, key, {"recovery_phase": "probe_submitting", "probe_id": probe_id, "loaded": loaded})
    try:
        probe(runtime, profile, loaded["instance_id"])
    except BaseException:
        update_instance(store, key, {"recovery_phase": "probe_uncertain"}, "closed")
        atomic_json(receipt, {"generation": instance["generation"], "state": "uncertain", "time": time.time()})
        raise
    approved = authorize_job(store, {"profile": profile, "brief": {"capability": profile["capabilities"][0]}})
    if approved["approval"] != profile["approval"]: raise ValueError("approval_changed")
    after = current_loaded(runtime, profile)
    if after is None or after["instance_id"] != loaded["instance_id"]:
        raise ValueError("probe_instance_changed")
    new_key = digest([after["endpoint"], after["model_id"], after["instance_id"]])
    data = {**instance["data"], **after, "binding_verified": True, "loaded": after, "recovery_phase": "ready", "recovery_error": None, "recovery_blocked": False, "next_recovery_at": 0}
    with store.db(write=True) as db:
        generation = instance["generation"] + 1
        db.execute("UPDATE attempts SET state='released' WHERE instance_key=? AND state='uncertain'", (key,))
        if new_key == key:
            db.execute("UPDATE instances SET generation=?,state='ready',data=? WHERE instance_key=?", (generation, canonical(data), key))
        else:
            db.execute("UPDATE instances SET generation=?,state='closed',data=? WHERE instance_key=?", (generation, canonical({**data, "recovery_phase": "retired", "replacement_key": new_key}), key))
            db.execute("INSERT OR REPLACE INTO instances VALUES (?,?,'ready',?)", (new_key, generation, canonical(data)))
    atomic_json(receipt, {"generation": generation, "state": "complete", "time": time.time()})
    return True


def recover_instance(state_dir, instance_key):
    store = Store(state_dir)
    instance = store.instance(instance_key)
    # A reload can change the instance ID while another caller discovers it.
    with ownership(store, "recovery-" + digest([instance["data"]["endpoint"], instance["data"]["model_id"]])) as owned:
        if not owned: return 0
        delay = 1
        while True:
            instance = store.instance(instance_key)
            if instance["state"] == "ready" or instance["data"].get("recovery_phase") == "retired": return 0
            try:
                # Reconcile dead observers, but never infer that a live peer is free.
                from .worker import reconcile_attempts
                reconcile_attempts(state_dir)
                if recover_once(store, instance_key, Runtime(instance["data"]["endpoint"])): return 0
                time.sleep(.25)
            except (OSError, ValueError) as error:
                if str(error) in ("approval_changed", "model_not_approved", "routing_disabled", "invalid_profile", "unaccounted_instances", "runtime_binding_unavailable", "runtime_binding_mismatch"):
                    update_instance(store, instance_key, {"recovery_error": str(error), "recovery_blocked": True}, "closed")
                    return 2
                update_instance(store, instance_key, {"next_recovery_at": time.time() + delay, "recovery_error": type(error).__name__}, "closed")
                time.sleep(delay)
                delay = min(delay * 2, 30)
