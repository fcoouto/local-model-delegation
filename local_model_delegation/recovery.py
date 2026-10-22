"""On-demand recovery of only a known, approved instance."""
import time
from .contracts import canonical, digest, load_json
from .lmstudio import Runtime
from .store import Store
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



def recover_once(store, key, runtime):
    instance = store.instance(key)
    if instance["state"] == "ready" or instance["data"].get("recovery_phase") == "retired": return True
    from .capacity import owned_operation
    if not owned_operation(store, instance): raise ValueError("instance_not_owned")
    raise ValueError("lifecycle_unqualified")


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
                if recover_once(store, instance_key, Runtime(instance["data"]["endpoint"], token_env=instance["data"]["profile"].get("token_env"))): return 0
                time.sleep(.25)
            except (OSError, ValueError) as error:
                if str(error) in ("instance_not_owned", "lifecycle_unqualified", "approval_changed", "model_not_approved", "routing_disabled", "invalid_profile", "unaccounted_instances", "runtime_binding_unavailable", "runtime_binding_mismatch"):
                    update_instance(store, instance_key, {"recovery_error": str(error), "recovery_blocked": True}, "closed")
                    return 2
                update_instance(store, instance_key, {"next_recovery_at": time.time() + delay, "recovery_error": type(error).__name__}, "closed")
                time.sleep(delay)
                delay = min(delay * 2, 30)
