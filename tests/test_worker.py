import os
import signal
import subprocess
import sys
import time
from unittest.mock import patch
from local_model_delegation.store import Store
from local_model_delegation.worker import run_local_attempt, start_worker, wait_job, reconcile_attempts
from tests.support import Fixture, FakeRuntime, REPO_ROOT


class Worker(Fixture):
    def setUp(self):
        super().setUp()
        recovery = patch("local_model_delegation.recovery.request_recovery")
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
        run_local_attempt(self.state, job["attempt_id"])
        self.assertEqual(store.job(job["job_id"])["status"], "fallback_required")
        self.assertEqual(store.attempt(job["attempt_id"])["state"], "uncertain")

    def test_mismatched_final_result(self):
        server, store, job = self.prepare(mismatch=True)
        run_local_attempt(self.state, job["attempt_id"])
        self.assertEqual(store.job(job["job_id"])["status"], "fallback_required")

    def test_parent_exit_does_not_stop_observer(self):
        server, store, job = self.prepare(delay=.3)
        code = f'import sys;sys.path.insert(0,{str(REPO_ROOT)!r});from local_model_delegation.worker import start_worker;from pathlib import Path;print(start_worker(Path({str(self.state)!r}),{job["attempt_id"]!r}))'
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
        run_local_attempt(self.state, job["attempt_id"])
        self.assertEqual(server.calls.count(("POST", "/api/v1/chat")), 1)

    def test_recover_reserved_without_post_intent(self):
        server, store, job = self.prepare()
        reconcile_attempts(self.state)
        result = wait_job(self.state, job["job_id"], 3)
        self.assertEqual(result["status"], "candidate_ready")
        self.assertEqual(server.calls.count(("POST", "/api/v1/chat")), 1)

    def test_review_status_restarts_lost_recovery_owner(self):
        from local_model_delegation.recovery import close_instance
        server, store, job = self.prepare()
        store.transition(job["attempt_id"], 0, "reserved", "uncertain", {})
        store.select_fallback(job["job_id"], "observer_lost")
        key = store.attempt(job["attempt_id"])["instance_key"]
        close_instance(store, key)
        self.recovery_patch.stop()
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and not store.instance(key)["data"].get("recovery_blocked"):
            wait_job(self.state, job["job_id"], 0)
            time.sleep(.05)
        self.assertEqual(store.instance(key)["state"], "closed")
        self.assertEqual(store.instance(key)["data"]["recovery_error"], "instance_not_owned")
        self.assertEqual(server.calls.count(("POST", "/api/v1/models/unload")), 0)

    def test_cache_refresh_keeps_detached_worker_alive(self):
        import shutil
        server,store,job=self.prepare(delay=.3)
        cache=self.root/'cache';scripts=cache
        scripts.mkdir()
        shutil.copytree(REPO_ROOT/'local_model_delegation',scripts/'local_model_delegation')
        shutil.copyfile(REPO_ROOT/'delegate.py',scripts/'delegate.py')
        fixtures=cache/'skills/setup/fixtures';fixtures.mkdir(parents=True)
        shutil.copyfile(REPO_ROOT/'skills/setup/fixtures/assessment-cases.json',fixtures/'assessment-cases.json')
        code=f'import sys;sys.path.insert(0,{str(scripts)!r});from pathlib import Path;from local_model_delegation.worker import start_worker;print(start_worker(Path({str(self.state)!r}),{job["attempt_id"]!r}))'
        parent=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True)
        self.assertEqual(parent.returncode,0,parent.stderr)
        shutil.rmtree(cache)
        self.assertEqual(wait_job(self.state,job['job_id'],5)['status'],'candidate_ready')
        self.assertEqual(server.calls.count(('POST','/api/v1/chat')),1)
        instance=store.instance(store.attempt(job['attempt_id'])['instance_key'])
        self.assertTrue((self.state/'runtimes'/instance['data']['runtime_bundle']/'delegate.py').is_file())
