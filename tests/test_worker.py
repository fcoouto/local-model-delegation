import os
import signal
import subprocess
import sys
import time
from unittest.mock import patch
from local_repair.store import Store
from local_repair.worker import run_attempt, start_worker, wait_job, reconcile_attempts
from tests.support import Fixture, FakeRuntime, SCRIPTS


class Worker(Fixture):
    def setUp(self):
        super().setUp()
        recovery = patch("local_repair.recovery.request_recovery")
        self.recovery_patch = recovery
        recovery.start()
        self.addCleanup(recovery.stop)

    def prepare(self, **kwargs):
        server = FakeRuntime(**kwargs)
        self.addCleanup(server.close)
        profile = self.profile()
        profile["endpoint"] = server.endpoint
        self.write_config(profile)
        loaded = {**self.loaded(), "endpoint": server.endpoint}
        store = Store(self.state)
        job = store.reserve(self.brief(), profile, loaded)
        return server, store, job

    def test_eof_without_chat_end(self):
        server, store, job = self.prepare(incomplete=True)
        run_attempt(self.state, job["attempt_id"])
        self.assertEqual(store.job(job["job_id"])["status"], "fallback_required")
        self.assertEqual(store.attempt(job["attempt_id"])["state"], "uncertain")

    def test_mismatched_final_result(self):
        server, store, job = self.prepare(mismatch=True)
        run_attempt(self.state, job["attempt_id"])
        self.assertEqual(store.job(job["job_id"])["status"], "fallback_required")

    def test_parent_exit_does_not_stop_observer(self):
        server, store, job = self.prepare(delay=.3)
        code = f'import sys;sys.path.insert(0,{str(SCRIPTS)!r});from local_repair.worker import start_worker;from pathlib import Path;print(start_worker(Path({str(self.state)!r}),{job["attempt_id"]!r}))'
        parent = subprocess.run([sys.executable, "-B", "-c", code], capture_output=True, text=True)
        self.assertEqual(parent.returncode, 0, parent.stderr)
        result = wait_job(self.state, job["job_id"], 5)
        self.assertEqual(result["status"], "candidate_ready")
        self.assertEqual(server.calls.count(("POST", "/api/v1/chat")), 1)

    def test_two_observers_one_submit(self):
        server, store, job = self.prepare(delay=.1)
        pids = [start_worker(self.state, job["attempt_id"]) for _ in range(2)]
        result = wait_job(self.state, job["job_id"], 5)
        self.assertEqual(result["status"], "candidate_ready")
        self.assertEqual(server.calls.count(("POST", "/api/v1/chat")), 1)
        for pid in pids:
            try: os.waitpid(pid, 0)
            except ChildProcessError: pass

    def test_death_after_submission_intent(self):
        server, store, job = self.prepare(delay=1)
        pid = start_worker(self.state, job["attempt_id"])
        deadline = time.monotonic() + 3
        while not server.calls and time.monotonic() < deadline: time.sleep(.02)
        os.kill(pid, signal.SIGKILL)
        os.waitpid(pid, 0)
        reconcile_attempts(self.state)
        self.assertEqual(store.attempt(job["attempt_id"])["state"], "uncertain")
        run_attempt(self.state, job["attempt_id"])
        self.assertEqual(server.calls.count(("POST", "/api/v1/chat")), 1)

    def test_recover_reserved_without_post_intent(self):
        server, store, job = self.prepare()
        reconcile_attempts(self.state)
        result = wait_job(self.state, job["job_id"], 3)
        self.assertEqual(result["status"], "candidate_ready")
        self.assertEqual(server.calls.count(("POST", "/api/v1/chat")), 1)

    def test_review_status_restarts_lost_recovery_owner(self):
        from local_repair.recovery import close_instance
        server, store, job = self.prepare()
        store.transition(job["attempt_id"], 0, "reserved", "uncertain", {})
        store.select_fallback(job["job_id"], "observer_lost")
        key = store.attempt(job["attempt_id"])["instance_key"]
        close_instance(store, key)
        self.recovery_patch.stop()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and store.instance(key)["state"] != "ready":
            wait_job(self.state, job["job_id"], 0)
            time.sleep(.05)
        self.assertEqual(store.instance(key)["state"], "ready")
        self.assertEqual(server.calls.count(("POST", "/api/v1/models/unload")), 1)
