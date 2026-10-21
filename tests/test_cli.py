import json
import subprocess
import sys
from unittest.mock import patch
from pathlib import Path
from local_repair.cli import reconcile_native
from local_repair.store import Store
from tests.support import Fixture, FakeRuntime, SCRIPTS, FIXED, SUPPLIED, ADDED


class CLI(Fixture):
    def invoke(self, *args):
        result = subprocess.run([sys.executable, "-B", str(SCRIPTS / "repair.py"), "--state-dir", str(self.state), *args], capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 2), result.stderr)
        return json.loads(result.stdout)

    def busy(self, fallback=None):
        server = FakeRuntime()
        self.addCleanup(server.close)
        p = self.profile()
        p["endpoint"] = server.endpoint
        if fallback: p["fallback"] = fallback
        self.write_config(p)
        store = Store(self.state)
        store.reserve(self.brief("occupier"), p, {**self.loaded(), "endpoint": server.endpoint})
        path = self.root / "brief.json"
        path.write_text(json.dumps(self.brief("request")))
        return server, store, path

    def test_busy_emits_fallback_without_local_post(self):
        server, store, path = self.busy()
        result = self.invoke("submit", "--brief", str(path))
        self.assertEqual(result["status"], "fallback_required")
        self.assertEqual(result["reason"], "model_busy")
        self.assertEqual(result["fallback"], {"model": "gpt-6.1-sol", "reasoning_effort": "medium"})
        self.assertFalse(any(method == "POST" for method, _ in server.calls))

    def test_native_fallback_is_not_qwen_default(self):
        fallback = {"model": "owner-other-model", "reasoning_effort": "high"}
        server, store, path = self.busy(fallback)
        result = self.invoke("submit", "--brief", str(path))
        self.assertEqual(result["fallback"], fallback)

    def test_claim_attach_is_idempotent(self):
        store = Store(self.state)
        job = store.reserve(self.brief(), self.profile(), None)
        first, second = store.claim_fallback(job["job_id"]), store.claim_fallback(job["job_id"])
        self.assertEqual(first["dispatch_token"], second["dispatch_token"])
        self.assertTrue(first["may_dispatch"])
        self.assertFalse(second["may_dispatch"])
        native_id = "/root/" + first["task_name"]
        self.assertTrue(store.attach_fallback(job["job_id"], first["dispatch_token"], native_id))
        self.assertTrue(store.attach_fallback(job["job_id"], first["dispatch_token"], native_id))
        self.assertFalse(store.attach_fallback(job["job_id"], "wrong-token", native_id))

    def test_spawn_ack_lost_does_not_respawn(self):
        store = Store(self.state)
        job = store.reserve(self.brief(), self.profile(), None)
        first = store.claim_fallback(job["job_id"])
        listing = [{"task_name": "/root/" + first["task_name"]}]
        result = reconcile_native(store, job["job_id"], listing)
        self.assertEqual(result["native_task_id"], listing[0]["task_name"])
        self.assertFalse(store.claim_fallback(job["job_id"])["may_dispatch"])
        other = store.reserve(self.brief("uncertain"), self.profile(), None)
        store.claim_fallback(other["job_id"])
        result = reconcile_native(store, other["job_id"], [])
        self.assertEqual(result["status"], "dispatch_uncertain")

    def test_compaction_resume_uses_lookup(self):
        server, store, path = self.busy()
        first = self.invoke("submit", "--brief", str(path))
        recovered = self.invoke("lookup", "--chat", "fixture-chat", "--task-key", "request")
        self.assertEqual(first["job_id"], recovered["job_id"])
        self.assertEqual(first["attempt_id"], recovered["attempt_id"])
        self.assertFalse(any(method == "POST" for method, _ in server.calls))

    def test_disabled_does_not_create_state(self):
        path = self.root / "brief.json"
        path.write_text(json.dumps(self.brief()))
        result = self.invoke("submit", "--brief", str(path))
        self.assertEqual(result["reason"], "routing_disabled")
        self.assertFalse(self.state.exists())

    def test_fallback_candidate_uses_independent_checks(self):
        self.write_config()
        store = Store(self.state)
        job = store.reserve(self.brief(), self.profile(), None)
        claim = store.claim_fallback(job["job_id"])
        native_id = "/root/" + claim["task_name"]
        store.attach_fallback(job["job_id"], claim["dispatch_token"], native_id)
        candidate = self.root / "cloud-result.json"
        candidate.write_text(json.dumps({"files": {"helper.py": FIXED, "test_helper.py": SUPPLIED + ADDED}, "summary": "fix"}))
        result = store.record_fallback_candidate(job["job_id"], native_id, candidate)
        self.assertEqual(result["status"], "candidate_ready")
        self.assertEqual(self.invoke("check", "--job", job["job_id"])["status"], "accepted")

    def test_invalid_native_output_is_terminal(self):
        self.write_config()
        store = Store(self.state)
        job = store.reserve(self.brief(), self.profile(), None)
        claim = store.claim_fallback(job["job_id"])
        native_id = "/root/" + claim["task_name"]
        store.attach_fallback(job["job_id"], claim["dispatch_token"], native_id)
        candidate = self.root / "invalid.json"
        candidate.write_text("not valid output")
        store.record_fallback_candidate(job["job_id"], native_id, candidate)
        self.assertEqual(self.invoke("check", "--job", job["job_id"])["status"], "failed")

    def test_invalid_model_list_is_unavailable(self):
        from local_repair.cli import submit
        server, store, path = self.busy()
        with patch("local_repair.cli.Runtime.list_models", return_value={"models": [None]}):
            self.assertEqual(submit(self.state, path)["status"], "fallback_required")

