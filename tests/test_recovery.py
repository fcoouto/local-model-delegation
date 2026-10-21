import threading
import time
from unittest.mock import patch
from local_model_delegation.recovery import close_instance, recover_once, recover_instance
from local_model_delegation.lmstudio import Runtime
from local_model_delegation.store import Store
from local_model_delegation.worker import run_local_attempt, start_worker, wait_job
from tests.support import Fixture, FakeRuntime


class Recovery(Fixture):
    def prepare(self, **kwargs):
        server = FakeRuntime(**kwargs)
        self.addCleanup(server.close)
        p = self.profile()
        p["endpoint"] = server.endpoint
        self.write_config(p)
        store = Store(self.state)
        job = store.reserve(self.brief(), p, {**self.loaded(2), "endpoint": server.endpoint})
        attempt = store.attempt(job["attempt_id"])
        store.transition(attempt["attempt_id"], 0, "reserved", "uncertain", {})
        store.select_fallback(job["job_id"], "test_silence")
        close_instance(store, attempt["instance_key"])
        return server, store, job, attempt["instance_key"]

    def test_lost_load_ack_reconciles_before_retry(self):
        server, store, job, key = self.prepare()
        server.drop_load_ack = True
        self.assertTrue(recover_once(store, key, Runtime(server.endpoint)))
        self.assertEqual(server.calls.count(("POST", "/api/v1/models/load")), 1)
        self.assertIn(("GET", "/api/v1/models"), server.calls)
        self.assertEqual(store.instance(key)["state"], "ready")
        self.assertEqual(store.instance(key)["generation"], 1)

    def test_lost_unload_ack_reconciles_before_retry(self):
        server, store, job, key = self.prepare()
        server.drop_unload_ack = True
        self.assertTrue(recover_once(store, key, Runtime(server.endpoint)))
        self.assertEqual(server.calls.count(("POST", "/api/v1/models/unload")), 1)

    def test_healthy_peer_defers_unload(self):
        server, store, job, key = self.prepare(delay=.35)
        # The closed instance blocks admission; create the healthy peer before re-closing it.
        with store.db(write=True) as db: db.execute("UPDATE instances SET state='ready' WHERE instance_key=?", (key,))
        healthy = store.reserve(self.brief("healthy"), self.profile_for(server), {**self.loaded(2), "endpoint": server.endpoint})
        start_worker(self.state, healthy["attempt_id"])
        deadline = time.monotonic() + 2
        while not server.calls and time.monotonic() < deadline: time.sleep(.01)
        close_instance(store, key)
        self.assertFalse(recover_once(store, key, Runtime(server.endpoint)))
        self.assertNotIn(("POST", "/api/v1/models/unload"), server.calls)
        self.assertEqual(wait_job(self.state, healthy["job_id"], 3)["status"], "candidate_ready")
        self.assertTrue(recover_once(store, key, Runtime(server.endpoint)))

    def profile_for(self, server):
        p = self.profile()
        p["endpoint"] = server.endpoint
        from local_model_delegation.profiles import model_identity
        p["approval"]["model_identity"] = model_identity(p)
        return p

    def test_two_recovery_owners(self):
        server, store, job, key = self.prepare()
        threads = [threading.Thread(target=recover_instance, args=(self.state, key)) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(5)
        self.assertFalse(any(t.is_alive() for t in threads))
        self.assertEqual(server.calls.count(("POST", "/api/v1/models/unload")), 1)

    def test_old_generation_and_late_output(self):
        server, store, job, key = self.prepare()
        self.assertTrue(recover_once(store, key, Runtime(server.endpoint)))
        self.assertFalse(store.publish_candidate(job["attempt_id"], 0, "late.json"))
        self.assertEqual(store.job(job["job_id"])["status"], "fallback_required")

    def test_incomplete_probe_stays_closed(self):
        server, store, job, key = self.prepare(incomplete=True)
        with self.assertRaises(ValueError): recover_once(store, key, Runtime(server.endpoint))
        self.assertNotEqual(store.instance(key)["state"], "ready")

    def test_stale_closes_admission_and_falls_back_once(self):
        server = FakeRuntime(delay=.6)
        self.addCleanup(server.close)
        profile = self.profile_for(server)
        profile["stale_tolerance_seconds"] = .1
        self.write_config(profile)
        store = Store(self.state)
        job = store.reserve(self.brief(), profile, {**self.loaded(), "endpoint": server.endpoint})
        with patch("local_model_delegation.recovery.request_recovery"):
            run_local_attempt(self.state, job["attempt_id"])
        self.assertEqual(store.job(job["job_id"])["status"], "fallback_required")
        key = store.attempt(job["attempt_id"])["instance_key"]
        self.assertNotEqual(store.instance(key)["state"], "ready")

    def test_recovery_restart_after_ack_loss(self):
        server, store, job, key = self.prepare()
        runtime = Runtime(server.endpoint)
        original = runtime.load
        def successful_then_crash(body):
            original(body)
            raise KeyboardInterrupt("simulate process death")
        with patch.object(runtime, "load", successful_then_crash), self.assertRaises(KeyboardInterrupt):
            recover_once(store, key, runtime)
        self.assertTrue(recover_once(store, key, Runtime(server.endpoint)))
        self.assertEqual(server.calls.count(("POST", "/api/v1/models/load")), 1)

    def test_review_uncertain_probe_requires_new_reset(self):
        server, store, job, key = self.prepare(incomplete=True)
        for _ in range(2):
            with self.assertRaises(ValueError): recover_once(store, key, Runtime(server.endpoint))
        self.assertEqual(server.calls.count(("POST", "/api/v1/chat")), 2)
        self.assertEqual(server.calls.count(("POST", "/api/v1/models/unload")), 2)
        self.assertNotEqual(store.instance(key)["state"], "ready")

    def test_review_missing_runtime_binding_stays_closed(self):
        server, store, job, key = self.prepare()
        profile = self.profile_for(server)
        profile.pop("runtime_catalog", None)
        self.write_config(profile)
        with self.assertRaises(ValueError): recover_once(store, key, Runtime(server.endpoint))
        self.assertNotEqual(store.instance(key)["state"], "ready")
        self.assertFalse(any(method == "POST" for method, _ in server.calls))

    def test_probe_owner_death_requires_reset(self):
        server, store, job, key = self.prepare()
        runtime = Runtime(server.endpoint)
        original = runtime.stream
        def starts_then_dies(body):
            for event in original(body):
                yield event
                raise KeyboardInterrupt("simulate probe owner death")
        with patch.object(runtime, "stream", starts_then_dies), self.assertRaises(KeyboardInterrupt):
            recover_once(store, key, runtime)
        # SIGKILL cannot run exception handlers; its durable intent still fences retry.
        from local_model_delegation.recovery import update_instance
        update_instance(store, key, {"recovery_phase": "probe_submitting"}, "closed")
        self.assertTrue(recover_once(store, key, Runtime(server.endpoint)))
        self.assertEqual(server.calls.count(("POST", "/api/v1/models/unload")), 2)
        self.assertEqual(server.calls.count(("POST", "/api/v1/chat")), 2)
        from local_model_delegation.contracts import load_json
        receipts = [load_json(p.read_text()) for p in (store.root / "probes" / key).glob("*.json")]
        self.assertEqual(sorted(r["state"] for r in receipts), ["complete", "uncertain"])

    def test_runtime_metadata_mismatch_cannot_load_or_probe(self):
        server, store, job, key = self.prepare()
        runtime = Runtime(server.endpoint)
        snapshot = runtime.list_models()
        snapshot["models"][0]["architecture"] = "different"
        with patch.object(runtime, "list_models", return_value=snapshot), self.assertRaisesRegex(ValueError, "runtime_binding_mismatch"):
            recover_once(store, key, runtime)
        self.assertFalse(any(method == "POST" for method, _ in server.calls))
        self.assertNotEqual(store.instance(key)["state"], "ready")

    def test_recovery_restart_respects_owner_backoff_and_permanent_error(self):
        from local_model_delegation.contracts import digest
        from local_model_delegation.recovery import request_recovery, update_instance
        from local_model_delegation.worker import ownership
        server, store, job, key = self.prepare()
        with patch("local_model_delegation.recovery.launch") as launch:
            with ownership(store, "recovery-" + digest([server.endpoint, "fictional-model"])):
                request_recovery(self.state, key)
            launch.assert_not_called()
            update_instance(store, key, {"next_recovery_at": time.time() + 30}, "closed")
            request_recovery(self.state, key)
            launch.assert_not_called()
            update_instance(store, key, {"next_recovery_at": 0, "recovery_blocked": True}, "closed")
            request_recovery(self.state, key)
            launch.assert_not_called()
            update_instance(store, key, {"recovery_blocked": False}, "closed")
            request_recovery(self.state, key)
            launch.assert_called_once()

    def test_repeated_recovery_tracks_replacement_instance(self):
        from local_model_delegation.contracts import digest
        server, store, job, key = self.prepare()
        server.change_instance_on_load = True
        for _ in range(2):
            self.assertTrue(recover_once(store, key, Runtime(server.endpoint)))
            self.assertEqual(store.instance(key)["data"]["recovery_phase"], "retired")
            key = digest([server.endpoint, "fictional-model", server.instance_id])
            self.assertEqual(store.instance(key)["state"], "ready")
            self.assertEqual(store.instance(key)["data"]["loaded"]["instance_id"], server.instance_id)
            close_instance(store, key)
        self.assertEqual(server.calls.count(("POST", "/api/v1/models/unload")), 2)

    def test_probe_requires_one_matching_start(self):
        from local_model_delegation.recovery import probe
        server, store, job, key = self.prepare()
        runtime = Runtime(server.endpoint)
        stream = runtime.stream
        for duplicate in (False, True):
            def malformed(body):
                for event, data in stream(body):
                    if event != "chat.start":
                        yield event, data
                    elif duplicate:
                        yield event, data
                        yield event, data
            with self.subTest(duplicate=duplicate), patch.object(runtime, "stream", malformed):
                with self.assertRaises(ValueError): probe(runtime, self.profile_for(server), server.instance_id)

    def test_resumed_probe_rejects_unverified_replacement(self):
        from local_model_delegation.recovery import update_instance
        server, store, job, key = self.prepare()
        update_instance(store, key, {"recovery_phase": "probe", "loaded": {
            **self.loaded(), "endpoint": server.endpoint}})
        server.instance_id = "unverified-replacement"
        with self.assertRaisesRegex(ValueError, "unaccounted_instances"):
            recover_once(store, key, Runtime(server.endpoint))
        self.assertFalse(any(method == "POST" for method, _ in server.calls))
        self.assertEqual(store.attempt(job["attempt_id"])["state"], "uncertain")

    def test_changed_approval_during_probe_cannot_reopen(self):
        from local_model_delegation.recovery import probe
        server, store, job, key = self.prepare()
        def probe_then_change(runtime, profile, instance_id):
            probe(runtime, profile, instance_id)
            replacement = self.profile_for(server)
            replacement["approval"]["owner_reference"] = "fictional-new-confirmation"
            self.write_config(replacement)
        with patch("local_model_delegation.recovery.probe", side_effect=probe_then_change):
            with self.assertRaisesRegex(ValueError, "approval_changed"):
                recover_once(store, key, Runtime(server.endpoint))
        self.assertNotEqual(store.instance(key)["state"], "ready")
        self.assertEqual(store.attempt(job["attempt_id"])["state"], "uncertain")

    def test_recovery_defers_to_healthy_replacement_peer(self):
        from local_model_delegation.recovery import update_instance
        server, store, job, key = self.prepare()
        update_instance(store, key, {"recovery_phase": "load"})
        server.instance_id = "replacement-with-healthy-work"
        profile = self.profile_for(server)
        peer = store.reserve(self.brief("healthy-replacement"), profile, {
            **self.loaded(), "endpoint": server.endpoint, "instance_id": server.instance_id})
        self.assertEqual(peer["status"], "reserved")
        self.assertFalse(recover_once(store, key, Runtime(server.endpoint)))
        self.assertFalse(any(method == "POST" for method, _ in server.calls))
        self.assertEqual(store.attempt(peer["attempt_id"])["state"], "reserved")

    def test_old_load_phase_cannot_probe_another_uncertain_instance(self):
        from local_model_delegation.contracts import digest
        from local_model_delegation.recovery import update_instance
        server, store, job, key = self.prepare()
        update_instance(store, key, {"recovery_phase": "load"})
        server.instance_id = "replacement-with-uncertain-probe"
        profile = self.profile_for(server)
        loaded = {**self.loaded(), "endpoint": server.endpoint,
                  "instance_id": server.instance_id, "binding_verified": False}
        store.reserve(self.brief("replacement"), profile, loaded)
        replacement = digest([server.endpoint, profile["model_id"], server.instance_id])
        update_instance(store, replacement, {"recovery_phase": "probe_uncertain", "loaded": loaded}, "closed")
        with self.assertRaisesRegex(ValueError, "unaccounted_instances"):
            recover_once(store, key, Runtime(server.endpoint))
        self.assertFalse(any(method == "POST" for method, _ in server.calls))
        self.assertEqual(store.attempt(job["attempt_id"])["state"], "uncertain")

    def test_replacement_discovery_cannot_start_competing_recovery(self):
        from local_model_delegation.contracts import digest
        from local_model_delegation.lmstudio import select_loaded
        from local_model_delegation.recovery import probe
        server, store, job, key = self.prepare()
        server.change_instance_on_load = True
        entered, release = threading.Event(), threading.Event()
        def paused_probe(runtime, profile, instance_id):
            if instance_id == "fixture-instance-1":
                entered.set()
                if not release.wait(5): raise ValueError("test_probe_release_timeout")
            return probe(runtime, profile, instance_id)
        with patch("local_model_delegation.recovery.probe", side_effect=paused_probe), patch("local_model_delegation.recovery.request_recovery"):
            owner = threading.Thread(target=recover_instance, args=(self.state, key))
            owner.start()
            try:
                self.assertTrue(entered.wait(3))
                profile = self.profile_for(server)
                loaded = select_loaded(Runtime(server.endpoint).list_models(), profile)
                other = store.reserve(self.brief("competing-project"), profile, loaded)
                self.assertEqual(other["reason"], "instance_closed")
                replacement = digest([server.endpoint, profile["model_id"], loaded["instance_id"]])
                recover_instance(self.state, replacement)
                self.assertEqual(server.calls.count(("POST", "/api/v1/models/unload")), 1)
            finally:
                release.set()
                owner.join(5)
            self.assertFalse(owner.is_alive())
            self.assertEqual(store.instance(replacement)["state"], "ready")
