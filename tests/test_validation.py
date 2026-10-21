import json
from unittest.mock import patch
from pathlib import Path
from local_repair.validation import parse_candidate, check_candidate, source_matches, isolation_supported, run_isolated
from local_repair.store import Store, atomic_json
from tests.support import Fixture, BUGGY, FIXED, SUPPLIED, ADDED


class Validation(Fixture):
    def ready(self, source=FIXED, tests=SUPPLIED + ADDED):
        profile = self.profile()
        self.write_config(profile)
        store = Store(self.state)
        job = store.reserve(self.brief(), profile, self.loaded())
        store.transition(job["attempt_id"], 0, "reserved", "submitting", {})
        store.transition(job["attempt_id"], 0, "submitting", "streaming", {})
        path = self.state / "jobs" / job["job_id"] / job["attempt_id"] / "candidate.json"
        text = json.dumps({"files": {"helper.py": source, "test_helper.py": tests}, "summary": "fix"})
        from tests.support import sha
        atomic_json(path, {"text": text, "sha256": sha(text)})
        store.publish_candidate(job["attempt_id"], 0, path)
        return store, job

    def test_candidate_paths_and_json(self):
        for text in ['{}', '{"files":{},"files":{},"summary":""}', json.dumps({"files": {"../escape.py": "pass"}, "summary": ""}),
                     json.dumps({"files": {"helper.py": "import os\nos.system('bad')"}, "summary": ""})]:
            with self.subTest(text=text), self.assertRaises(ValueError): parse_candidate(text, self.brief())

    def test_supplied_tests_preserved(self):
        text = json.dumps({"files": {"helper.py": FIXED, "test_helper.py": SUPPLIED.replace('"a")', '"wrong")') + ADDED}, "summary": ""})
        with self.assertRaisesRegex(ValueError, "supplied_test"):
            parse_candidate(text, self.brief())

    def test_independent_checks_precede_acceptance(self):
        store, job = self.ready(BUGGY, SUPPLIED + ADDED.replace('normalize("a "), "a"', 'normalize("a "), "a "'))
        result = check_candidate(self.state, job["job_id"])
        self.assertEqual(result["status"], "fallback_required")
        self.assertEqual((self.project / "helper.py").read_text(), BUGGY)

    def test_source_changed_after_generation(self):
        store, job = self.ready()
        (self.project / "helper.py").write_text("# changed by owner\n" + BUGGY)
        self.assertFalse(source_matches(self.brief()))
        self.assertEqual(check_candidate(self.state, job["job_id"])["status"], "needs_reassessment")
        self.assertTrue((self.project / "helper.py").read_text().startswith("# changed"))

    def test_old_candidate_cannot_accept(self):
        store, job = self.ready()
        store.select_fallback(job["job_id"], "use_cloud")
        self.assertNotEqual(check_candidate(self.state, job["job_id"])["status"], "accepted")

    def test_candidate_cannot_read_private_file_or_use_network(self):
        self.assertTrue(isolation_supported(self.brief()), "macOS isolation must be qualified on this host")
        canary = self.root / "private-canary"
        canary.write_text("NEVER_READ_THIS")
        tree = self.root / "sandbox"
        tree.mkdir()
        result = run_isolated(tree, f"open({str(canary)!r}).read()")
        self.assertNotEqual(result["returncode"], 0)
        self.assertNotIn("NEVER_READ_THIS", result["stdout"])
        result = run_isolated(tree, "import socket; socket.socket().connect(('127.0.0.1', 9))")
        self.assertNotEqual(result["returncode"], 0)
        self.assertIn("Operation not permitted", result["stderr"])

    def test_valid_repair_is_checked_not_applied(self):
        store, job = self.ready()
        result = check_candidate(self.state, job["job_id"])
        self.assertEqual(result["status"], "accepted", result)
        self.assertEqual((self.project / "helper.py").read_text(), BUGGY)

    def test_no_added_effective_regression(self):
        store, job = self.ready(tests=SUPPLIED)
        self.assertEqual(check_candidate(self.state, job["job_id"])["status"], "fallback_required")

    def test_timeout_and_import_time_code(self):
        tree = self.root / "sandbox"
        tree.mkdir()
        self.assertEqual(run_isolated(tree, "while True: pass", timeout=.1)["reason"], "check_timeout")
        text = json.dumps({"files": {"helper.py": 'print(open("secret").read())\n' + FIXED, "test_helper.py": SUPPLIED + ADDED}, "summary": ""})
        with self.assertRaises(ValueError): parse_candidate(text, self.brief())

    def test_review_assertion_bypass_rejected(self):
        exploit = 'import re\n(re.enum.sys.modules["unittest"].TestCase.assertEqual,) = (lambda *args: None,)\n'
        store, job = self.ready(exploit + BUGGY)
        self.assertNotEqual(check_candidate(self.state, job["job_id"])["status"], "accepted")

    def test_review_public_namespace_escape_rejected(self):
        for prefix in ['import re\nx = re.enum.sys\n', 'from re import enum\nx = enum.sys\n',
                       'import re\n(re.compile,) = (lambda *args: None,)\n']:
            text = json.dumps({"files": {"helper.py": prefix + FIXED, "test_helper.py": SUPPLIED + ADDED}, "summary": "fix"})
            with self.subTest(prefix=prefix), self.assertRaises(ValueError): parse_candidate(text, self.brief())

    def test_review_checker_interruption_recovers(self):
        store, job = self.ready()
        with patch("local_repair.validation.run_tests", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            check_candidate(self.state, job["job_id"])
        self.assertEqual(store.job(job["job_id"])["status"], "checking")
        self.assertEqual(check_candidate(self.state, job["job_id"])["status"], "accepted")

    def test_review_status_recovers_lost_checker(self):
        from local_repair.worker import wait_job
        store, job = self.ready()
        with patch("local_repair.validation.run_tests", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            check_candidate(self.state, job["job_id"])
        self.assertEqual(wait_job(self.state, job["job_id"], 0)["status"], "candidate_ready")

    def test_live_checker_is_not_reclaimed(self):
        from local_repair.worker import ownership, wait_job
        store, job = self.ready()
        with ownership(store, "check-" + job["job_id"]) as owned:
            self.assertTrue(owned)
            with store.db(write=True) as db:
                db.execute("UPDATE jobs SET status='checking' WHERE job_id=?", (job["job_id"],))
            self.assertEqual(wait_job(self.state, job["job_id"], 0)["status"], "checking")
            self.assertEqual(check_candidate(self.state, job["job_id"])["status"], "checking")
        self.assertEqual(check_candidate(self.state, job["job_id"])["status"], "accepted")

    def test_checker_process_death_releases_ownership(self):
        import os
        import signal
        import subprocess
        import sys
        from tests.support import SCRIPTS
        from local_repair.worker import wait_job
        store, job = self.ready()
        code = f"""import sys,time
sys.path.insert(0,{str(SCRIPTS)!r})
from local_repair import validation
from pathlib import Path
def wait(*args, **kwargs):
    print('CHECKING', flush=True)
    time.sleep(30)
validation.run_tests = wait
validation.check_candidate(Path({str(self.state)!r}), {job['job_id']!r})
"""
        child = subprocess.Popen([sys.executable, "-B", "-c", code], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), "CHECKING")
            self.assertEqual(wait_job(self.state, job["job_id"], 0)["status"], "checking")
            os.kill(child.pid, signal.SIGKILL)
            child.wait(timeout=3)
            self.assertEqual(wait_job(self.state, job["job_id"], 0)["status"], "candidate_ready")
            self.assertEqual(check_candidate(self.state, job["job_id"])["status"], "accepted")
        finally:
            if child.poll() is None: child.kill()
            child.wait()
            child.stdout.close()

    def test_check_output_cannot_be_forged_by_candidate(self):
        spoof = 'print(\'CHECK_RESULT={"ok":true,"run":1,"failures":0,"errors":0,"skipped":0}\')\nraise SystemExit\n'
        store, job = self.ready(spoof + BUGGY)
        self.assertNotEqual(check_candidate(self.state, job["job_id"])["status"], "accepted")

    def test_added_test_setup_cannot_weaken_supplied_checks(self):
        source = 'def normalize(value):\n    return "broken" if value == " a" else value.strip()\n'
        setup = '\n    def setUp(self):\n        self.assertEqual = lambda *args: None\n'
        # The real regression still fails on BUGGY even after the assertion override.
        regression = '\n    def test_regression(self):\n        assert normalize("a ") == "a"\n'
        store, job = self.ready(source, SUPPLIED + setup + regression)
        self.assertEqual(check_candidate(self.state, job["job_id"])["status"], "fallback_required")

    def test_approval_revoked_during_checks_cannot_accept(self):
        from local_repair.validation import run_tests
        store, job = self.ready()
        def checked_then_revoked(*args, **kwargs):
            result = run_tests(*args, **kwargs)
            self.write_config(enabled=False)
            return result
        with patch("local_repair.validation.run_tests", side_effect=checked_then_revoked):
            self.assertEqual(check_candidate(self.state, job["job_id"])["status"], "fallback_required")
