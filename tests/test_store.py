import copy
import multiprocessing
import time
from local_model_delegation.store import Store, atomic_json
from tests.support import Fixture


def compete(state, brief, profile, loaded, queue):
    try:
        queue.put(Store(state).reserve(brief, profile, loaded)["status"])
    except Exception as exc:
        queue.put(type(exc).__name__)


class Slots(Fixture):
    def setUp(self):
        super().setUp()
        self.store = Store(self.state)

    def test_cross_project_capacity_one(self):
        p, loaded = self.profile(), self.loaded()
        context = multiprocessing.get_context("fork")
        queue = context.Queue()
        processes = [context.Process(target=compete, args=(self.state, self.brief(str(i)), p, loaded, queue)) for i in range(2)]
        for process in processes: process.start()
        for process in processes:
            process.join(10)
            self.assertEqual(process.exitcode, 0)
        self.assertCountEqual([queue.get(timeout=2), queue.get(timeout=2)], ["reserved", "fallback_required"])
        queue.close()

    def test_capacity_two_and_changes(self):
        p = self.profile()
        first = self.store.reserve(self.brief("a"), p, self.loaded(2))
        second = self.store.reserve(self.brief("b"), p, self.loaded(2))
        self.assertEqual(first["status"], "reserved")
        self.assertEqual(second["status"], "reserved")
        self.assertEqual(self.store.reserve(self.brief("c"), p, self.loaded(2))["status"], "fallback_required")
        self.assertEqual(self.store.reserve(self.brief("d"), p, self.loaded(1))["status"], "fallback_required")
        for attempt in (first, second):
            self.assertTrue(self.store.transition(attempt["attempt_id"], 0, "reserved", "released", {}))
        self.assertEqual(self.store.reserve(self.brief("e"), p, self.loaded(1))["status"], "reserved")

    def test_recovery_reservations_do_not_expire(self):
        first = self.store.reserve(self.brief(), self.profile(), self.loaded())
        self.store.transition(first["attempt_id"], 0, "reserved", "uncertain", {"heartbeat": 0})
        self.assertEqual(self.store.reserve(self.brief("next"), self.profile(), self.loaded())["status"], "fallback_required")

    def test_repeated_submit_recovers_same_job(self):
        first = self.store.reserve(self.brief(), self.profile(), self.loaded())
        again = self.store.reserve(self.brief(), self.profile(), self.loaded())
        self.assertEqual(first, again)
        self.assertEqual(self.store.lookup("fixture-chat", "change-one")["job_id"], first["job_id"])
        changed = self.brief()
        changed["behavior_contract"] = "different task"
        with self.assertRaisesRegex(ValueError, "job_conflict"):
            self.store.reserve(changed, self.profile(), self.loaded())

    def test_single_fallback_transition(self):
        first = self.store.reserve(self.brief(), self.profile(), None)
        a = self.store.select_fallback(first["job_id"], "unavailable")
        b = self.store.select_fallback(first["job_id"], "duplicate")
        self.assertEqual(a, b)
        self.assertEqual(a["fallback"], {"model": "gpt-6.1-sol", "reasoning_effort": "medium"})

    def test_profile_change_preserves_attempt_snapshot(self):
        p = self.profile()
        first = self.store.reserve(self.brief(), p, self.loaded())
        p["fallback"]["model"] = "changed-future-model"
        self.assertEqual(self.store.job(first["job_id"])["profile"]["fallback"]["model"], "gpt-6.1-sol")

    def test_generation_and_terminal_fencing(self):
        first = self.store.reserve(self.brief(), self.profile(), self.loaded())
        self.assertFalse(self.store.transition(first["attempt_id"], 99, "reserved", "streaming", {}))
        self.assertTrue(self.store.transition(first["attempt_id"], 0, "reserved", "submitting", {}))
        self.assertFalse(self.store.transition(first["attempt_id"], 0, "reserved", "submitting", {}))
        self.store.select_fallback(first["job_id"], "stale")
        self.assertFalse(self.store.publish_candidate(first["attempt_id"], 0, "answer.json"))

    def test_private_state_and_symlink_rejection(self):
        self.assertEqual(self.state.stat().st_mode & 0o777, 0o700)
        self.assertEqual((self.state / "state.sqlite3").stat().st_mode & 0o777, 0o600)
        bad = self.root / "bad"
        bad.symlink_to(self.state, target_is_directory=True)
        with self.assertRaises(ValueError): Store(bad)

    def test_submission_cannot_start_after_fallback_or_recovery(self):
        first = self.store.reserve(self.brief(), self.profile(), self.loaded())
        self.store.select_fallback(first["job_id"], "cancel_before_send")
        self.assertFalse(self.store.transition(first["attempt_id"], 0, "reserved", "submitting", {}))

    def test_private_state_rejects_parent_symlink(self):
        outside = self.root / "outside"
        outside.mkdir()
        (self.state / "jobs").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError): atomic_json(self.state / "jobs/child/result.json", {"data": "private"})
        self.assertFalse((outside / "child").exists())

    def test_disappearing_sqlite_sidecar_does_not_break_open(self):
        from pathlib import Path
        from unittest.mock import patch
        sidecar=Path(str(self.store.path)+'-shm');sidecar.write_bytes(b'fixture');sidecar.chmod(0o600)
        original=Path.stat; calls=[]
        def race(path,*args,**kwargs):
            if path==sidecar and kwargs.get('follow_symlinks',True):
                calls.append(path)
                if len(calls)==2: sidecar.unlink()
            return original(path,*args,**kwargs)
        with patch.object(Path,'stat',race): reopened=Store(self.state)
        self.assertEqual(reopened.path,self.store.path)
