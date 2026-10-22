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

    def test_external_instance_never_loads_unloads_or_probes(self):
        server, store, job, key = self.prepare()
        for _ in range(2):
            with self.assertRaisesRegex(ValueError,'instance_not_owned'):
                recover_once(store,key,Runtime(server.endpoint))
        self.assertEqual(server.calls,[])
        self.assertEqual(store.attempt(job['attempt_id'])['state'],'uncertain')
        self.assertEqual(store.instance(key)['state'],'closed')

    def test_owned_instance_still_requires_lifecycle_qualification(self):
        server, store, job, key = self.prepare()
        with patch('local_model_delegation.capacity.owned_operation',return_value=True):
            with self.assertRaisesRegex(ValueError,'lifecycle_unqualified'):
                recover_once(store,key,Runtime(server.endpoint))
        self.assertEqual(server.calls,[])
        self.assertEqual(store.attempt(job['attempt_id'])['state'],'uncertain')

    def test_recovery_records_blocker_without_releasing_slots(self):
        server,store,job,key=self.prepare()
        self.assertEqual(recover_instance(self.state,key),2)
        self.assertEqual(store.instance(key)['data']['recovery_error'],'instance_not_owned')
        self.assertEqual(store.attempt(job['attempt_id'])['state'],'uncertain')
        self.assertEqual(server.calls,[])

    def test_stale_closes_admission_and_falls_back_once(self):
        server = FakeRuntime(delay=.6)
        self.addCleanup(server.close)
        profile = self.profile(); profile["endpoint"] = server.endpoint
        profile["stale_tolerance_seconds"] = .1
        self.write_config(profile)
        store = Store(self.state)
        job = store.reserve(self.brief(), profile, {**self.loaded(), "endpoint": server.endpoint})
        with patch("local_model_delegation.recovery.request_recovery"):
            run_local_attempt(self.state, job["attempt_id"])
        self.assertEqual(store.job(job["job_id"])["status"], "fallback_required")
        key = store.attempt(job["attempt_id"])["instance_key"]
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
