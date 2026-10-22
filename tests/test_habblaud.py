import json
import time
from unittest.mock import patch
from local_model_delegation.store import Store, atomic_json
from local_model_delegation.contracts import digest
from tests.support import Fixture
from tests.habblaud_support import Receiver, PARENT, OTHER_PARENT, CONTEXT


class Habblaud(Fixture):
    def receiver(self):
        receiver = Receiver(); self.addCleanup(receiver.close)
        return receiver

    def queued(self, context=None):
        self.write_config()
        store = Store(self.state); brief = self.brief()
        job = store.enqueue(brief, brief['fallback'], visibility=context)
        return store, brief, job

    def test_disabled_status_has_no_state_or_network_side_effect(self):
        from local_model_delegation.habblaud import status
        self.assertFalse(status(self.state)['enabled'])
        self.assertFalse(self.state.exists())

    def test_context_validation_and_independently_optional_labels(self):
        from local_model_delegation.habblaud import validate_context
        for context in ({'coordinator_chat_id': PARENT}, CONTEXT,
                        {'coordinator_chat_id': PARENT, 'specialty': 'Security'},
                        {'coordinator_chat_id': PARENT, 'role': 'Tester'}):
            self.assertEqual(validate_context(context), context)
        for extra in ({'role': 'reviewer'}, {'role': 'Unknown'}, {'specialty': ''},
                      {'specialty': ' '*4}, {'specialty': 'x'*4097}, {'model': 'fake'},
                      {'coordinator_chat_id': 'not-a-thread'}, {'role': None}):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                validate_context({**CONTEXT, **extra})

    def test_context_does_not_change_brief_identity_or_legacy_submission(self):
        store, brief, job = self.queued(CONTEXT)
        saved = store.job(job['job_id'])
        self.assertEqual(saved['brief'], brief)
        self.assertEqual(saved['brief_hash'], digest(brief))
        self.assertEqual(saved['route_data']['habblaud']['context'], CONTEXT)
        self.assertEqual(store.enqueue(brief, brief['fallback'], visibility=CONTEXT)['job_id'], job['job_id'])
        self.assertEqual(store.enqueue(brief, brief['fallback'])['job_id'], job['job_id'])
        other = self.brief('legacy')
        legacy = store.enqueue(other, other['fallback'])
        self.assertNotIn('habblaud', store.job(legacy['job_id'])['route_data'])

    def test_bad_context_rolls_back_enqueue(self):
        self.write_config(); store = Store(self.state); brief = self.brief()
        with self.assertRaises(ValueError):
            store.enqueue(brief, brief['fallback'], visibility={**CONTEXT, 'role': 'typo'})
        self.assertIsNone(store.lookup(brief['origin_chat_id'], brief['task_key']))

    def test_enable_requires_exact_codex_account_and_preserves_routing(self):
        from local_model_delegation.habblaud import configure, status
        receiver = self.receiver()
        with self.assertRaisesRegex(ValueError, 'account'):
            configure(self.state, receiver.endpoint, 'wrong')
        self.assertFalse(self.state.exists())
        configure(self.state, receiver.endpoint, '.codex')
        self.assertTrue(status(self.state)['enabled'])
        self.assertFalse(json.loads((self.state/'config.json').read_text())['routing_enabled'])
        receiver.accounts = [{'id': '.codex', 'provider': 'claude'}]
        with self.assertRaisesRegex(ValueError, 'account'):
            configure(self.state, receiver.endpoint, '.codex')

    def test_transport_rejects_nonlocal_credentials_paths_redirects_and_oversize(self):
        from local_model_delegation.habblaud import Client
        for url in ('https://127.0.0.1', 'http://example.com', 'http://localhost',
                    'http://user:secret@127.0.0.1', 'http://127.0.0.1/path',
                    'http://127.0.0.1?query', 'http://127.0.0.1#fragment'):
            with self.subTest(url=url), self.assertRaises(ValueError): Client(url)
        receiver = self.receiver(); client = Client(receiver.endpoint)
        receiver.get_status = 302
        with self.assertRaises(ValueError): client.snapshot('.codex')
        receiver.get_status = 200; receiver.raw = b'x' * (2*1024*1024+1)
        with self.assertRaises(ValueError): client.snapshot('.codex')
        receiver.raw = b'{malformed'
        with self.assertRaises(ValueError): client.snapshot('.codex')

    def test_hook_false_acknowledgment_is_failure(self):
        from local_model_delegation.habblaud import Client
        receiver = self.receiver(); receiver.reject = True
        with self.assertRaisesRegex(ValueError, 'rejected'):
            Client(receiver.endpoint).event('.codex', {'hook_event_name':'SubagentStart',
                'session_id':PARENT, 'agent_id':OTHER_PARENT, 'agent_type':'LOCAL · fixture'})

    def test_explicit_rebind_preserves_execution_identity(self):
        from local_model_delegation.habblaud import bind
        store, brief, job = self.queued(CONTEXT)
        before = store.job(job['job_id'])
        bind(self.state, job['job_id'], {**CONTEXT, 'coordinator_chat_id':OTHER_PARENT})
        after = store.job(job['job_id'])
        self.assertEqual(after['brief_hash'], before['brief_hash'])
        self.assertEqual(after['status'], before['status'])
        self.assertEqual(after['route_data']['observed_at'], before['route_data']['observed_at'])
        self.assertEqual(after['route_data']['habblaud']['context']['coordinator_chat_id'], OTHER_PARENT)

    def active(self):
        from local_model_delegation.habblaud import configure, bind_context
        receiver = self.receiver(); profile = self.profile(); self.write_config(profile)
        store = Store(self.state); brief = self.brief(); brief['origin_chat_id'] = PARENT
        job = store.reserve(brief, profile, self.loaded())
        with store.db(write=True) as db: bind_context(db, job['job_id'], CONTEXT)
        configure(self.state, receiver.endpoint, '.codex')
        now = time.time()
        store.transition(job['attempt_id'], 0, 'reserved', 'submitting', {'submitted_at': now, 'last_event_at': now})
        return receiver, store, job, now

    def job_phase(self, store, job, status, attempt='complete', native=None):
        with store.db(write=True) as db:
            db.execute('UPDATE attempts SET state=? WHERE attempt_id=?', (attempt, job['attempt_id']))
            db.execute('UPDATE jobs SET status=?,native_task_id=? WHERE job_id=?', (status, native, job['job_id']))

    def test_observer_labels_actual_model_and_sends_only_changed_activity(self):
        from local_model_delegation.habblaud import Observer
        receiver, store, job, now = self.active(); observer = Observer(self.state, job['job_id'])
        self.assertTrue(observer.step(now))
        events = [e['event'] for e in receiver.events]
        self.assertEqual([e['hook_event_name'] for e in events], ['SubagentStart', 'PreToolUse'])
        self.assertEqual(events[0]['agent_type'], 'LOCAL · Reviewer · fictional-model · Security')
        self.assertEqual(events[0]['session_id'], PARENT)
        self.assertEqual(events[1]['tool_name'], 'LOCAL: Starting')
        observer.step(now+1); self.assertEqual(len(receiver.events), 2)
        observer.step(now+21)
        self.assertEqual(receiver.events[-1]['event']['hook_event_name'], 'SessionStart')
        self.assertEqual(len(receiver.agents), 1)
        payload = json.dumps(receiver.events)
        self.assertNotIn('strip both ends', payload); self.assertNotIn('lstrip', payload)
        self.assertNotIn('approval', payload); self.assertNotIn('token_env', payload)

    def test_candidate_verification_then_stop_never_closes_parent(self):
        from local_model_delegation.habblaud import Observer
        receiver, store, job, now = self.active(); observer = Observer(self.state, job['job_id'])
        observer.step(now)
        self.job_phase(store, job, 'candidate_ready'); observer.step(now+1)
        self.assertEqual(receiver.events[-1]['event']['tool_name'], 'LOCAL: Awaiting verification')
        self.job_phase(store, job, 'accepted'); self.assertFalse(observer.step(now+2))
        self.assertEqual(receiver.events[-2]['event']['tool_name'], 'LOCAL: Verified')
        self.assertEqual(receiver.events[-1]['event']['hook_event_name'], 'SubagentStop')
        self.assertNotIn('SessionEnd', [e['event']['hook_event_name'] for e in receiver.events])
        count = len(receiver.events); self.assertFalse(Observer(self.state, job['job_id']).step(now+3))
        self.assertEqual(len(receiver.events), count)

    def test_native_acceptance_keeps_local_uncertainty_and_model(self):
        from local_model_delegation.habblaud import Observer
        receiver, store, job, now = self.active(); observer = Observer(self.state, job['job_id'])
        observer.step(now)
        self.job_phase(store, job, 'accepted', 'uncertain', '/root/native')
        self.assertFalse(observer.step(now+1))
        self.assertEqual(receiver.events[-2]['event']['tool_name'], 'LOCAL: Execution status unknown')
        self.assertIn('fictional-model', receiver.events[-1]['event']['agent_type'])
        self.assertNotIn('Verified', json.dumps(receiver.events))
        self.assertEqual(store.attempt(job['attempt_id'])['state'], 'uncertain')

    def test_stale_attempt_is_retired_without_refreshing_progress(self):
        from local_model_delegation.habblaud import Observer
        receiver, store, job, now = self.active(); observer = Observer(self.state, job['job_id'])
        observer.step(now); before = store.attempt(job['attempt_id'])
        self.assertFalse(observer.step(now+121))
        self.assertEqual(store.attempt(job['attempt_id']), before)
        self.assertEqual(receiver.events[-1]['event']['hook_event_name'], 'SubagentStop')

    def test_queue_reservation_and_historical_terminal_work_create_no_character(self):
        from local_model_delegation.habblaud import Observer
        receiver, store, job, now = self.active()
        for state, attempt in [('waiting','reserved'), ('reserved','reserved'), ('accepted','complete')]:
            self.job_phase(store, job, state, attempt)
            self.assertFalse(Observer(self.state, job['job_id']).step(now))
        self.assertEqual(receiver.events, [])

    def test_restart_and_lost_ack_keep_one_stable_child(self):
        from local_model_delegation.habblaud import Observer
        receiver, store, job, now = self.active(); receiver.drop_ack = True
        observer = Observer(self.state, job['job_id']); self.assertTrue(observer.step(now))
        identity = next(iter(receiver.agents))
        observer = Observer(self.state, job['job_id']); observer.step(now+21)
        self.assertEqual(list(receiver.agents), [identity])
        self.assertEqual(sum(e['event']['hook_event_name']=='SubagentStart' for e in receiver.events), 1)
        receiver.agents.clear(); observer.step(now+42)
        self.assertEqual(list(receiver.agents), [identity])
        self.assertEqual(receiver.events[-1]['event']['tool_name'], 'LOCAL: Starting')

    def test_rebind_retires_old_child_and_label_freeze_rejects_conflict(self):
        from local_model_delegation.habblaud import Observer, bind_context
        receiver, store, job, now = self.active(); observer = Observer(self.state, job['job_id'])
        observer.step(now); original = next(iter(receiver.agents))
        with self.assertRaisesRegex(ValueError, 'conflict'), store.db(write=True) as db:
            bind_context(db, job['job_id'], {**CONTEXT, 'role':'Builder'}, rebind=True)
        with store.db(write=True) as db:
            bind_context(db, job['job_id'], {**CONTEXT, 'coordinator_chat_id':OTHER_PARENT}, rebind=True)
        observer.step(now+1)
        self.assertEqual(receiver.agents[original]['status'], 'done')
        live = [a for a in receiver.agents.values() if a['status']=='working']
        self.assertEqual(len(live), 1); self.assertNotEqual(live[0]['id'], original)
        self.assertEqual(live[0]['parentId'], '.codex:'+OTHER_PARENT)

    def test_account_disappearing_and_rejected_events_do_not_change_execution(self):
        from local_model_delegation.habblaud import Observer, status
        receiver, store, job, now = self.active(); observer = Observer(self.state, job['job_id'])
        observer.step(now); before = store.job(job['job_id']); attempt = store.attempt(job['attempt_id'])
        receiver.accounts = []
        self.assertTrue(observer.step(now+21)); self.assertEqual(len(receiver.events), 2)
        self.assertEqual(status(self.state, job['job_id'])['observation']['error'], 'habblaud_account_unavailable')
        receiver.accounts = [{'id':'.codex','provider':'codex'}]; receiver.reject = True
        self.assertTrue(observer.step(now+42))
        self.assertEqual(store.job(job['job_id']), before)
        self.assertEqual(store.attempt(job['attempt_id']), attempt)

    def test_global_disable_retires_only_display_and_preserves_reservation(self):
        from local_model_delegation.habblaud import Observer
        from local_model_delegation.visibility import set_visibility
        receiver, store, job, now = self.active(); observer = Observer(self.state, job['job_id'])
        observer.step(now); before = store.attempt(job['attempt_id'])
        set_visibility(self.state, False); self.assertFalse(observer.step(now+1))
        self.assertEqual(receiver.events[-1]['event']['hook_event_name'], 'SubagentStop')
        self.assertEqual(store.attempt(job['attempt_id']), before)

    def test_unsupported_label_reports_error_and_does_not_emit(self):
        from local_model_delegation.habblaud import Observer, bind_context, status
        receiver, store, job, now = self.active()
        with store.db(write=True) as db:
            bind_context(db, job['job_id'], {**CONTEXT, 'specialty':'Guardian'}, rebind=True)
        self.assertFalse(Observer(self.state, job['job_id']).step(now))
        self.assertEqual(receiver.events, [])
        self.assertEqual(status(self.state, job['job_id'])['observation']['error'], 'unsupported_habblaud_label')

    def test_transport_timeout_is_bounded(self):
        from local_model_delegation.habblaud import Client
        receiver = self.receiver(); receiver.delay = 3
        start = time.monotonic()
        with self.assertRaises(ValueError): Client(receiver.endpoint).snapshot('.codex')
        self.assertLess(time.monotonic()-start, 2.8)

    def test_initial_delivery_failure_can_recover_and_stop(self):
        from local_model_delegation.habblaud import Observer
        receiver, store, job, now = self.active()
        receiver.accounts = []; observer = Observer(self.state, job['job_id'])
        observer.step(now)
        receiver.accounts = [{'id':'.codex','provider':'codex'}]
        observer.step(now+21)
        self.assertEqual(len(receiver.agents), 1)
        self.job_phase(store, job, 'accepted'); observer.step(now+22)
        self.assertEqual(next(iter(receiver.agents.values()))['status'], 'done')

    def test_detached_observer_uses_runtime_bundle_and_single_owner(self):
        import os
        from local_model_delegation.habblaud import ensure_observer, quiesce
        receiver, store, job, now = self.active()
        starts = [ensure_observer(self.state, job['job_id']) for _ in range(2)]
        try:
            deadline = time.monotonic()+5
            while not receiver.agents and time.monotonic()<deadline: time.sleep(.05)
            self.assertEqual(len(receiver.agents), 1)
            self.assertEqual(sum(e['event']['hook_event_name']=='SubagentStart' for e in receiver.events), 1)
            self.assertTrue(list((self.state/'runtimes').glob('*/local_model_delegation/habblaud.py')))
        finally:
            quiesce(self.state)
            for start in starts:
                if start.get('pid'):
                    try: os.waitpid(start['pid'], 0)
                    except ChildProcessError: pass
        self.assertEqual(next(iter(receiver.agents.values()))['status'], 'done')
        self.assertEqual(store.attempt(job['attempt_id'])['state'], 'submitting')

    def test_worker_executes_when_hook_receiver_rejects_events(self):
        from local_model_delegation.habblaud import configure, bind_context, quiesce
        from local_model_delegation.worker import run_local_attempt
        from tests.support import FakeRuntime
        receiver = self.receiver(); receiver.reject = True
        runtime = FakeRuntime(delay=.2); self.addCleanup(runtime.close)
        profile = self.profile(); profile['endpoint'] = runtime.endpoint; self.write_config(profile)
        store = Store(self.state); job = store.reserve(self.brief(), profile, {**self.loaded(), 'endpoint':runtime.endpoint})
        with store.db(write=True) as db: bind_context(db, job['job_id'], CONTEXT)
        configure(self.state, receiver.endpoint, '.codex')
        try:
            self.assertEqual(run_local_attempt(self.state, job['attempt_id']), 0)
            deadline = time.monotonic()+4
            while not receiver.events and time.monotonic()<deadline: time.sleep(.05)
            self.assertTrue(receiver.events)
            self.assertEqual(store.job(job['job_id'])['status'], 'candidate_ready')
            self.assertEqual(runtime.calls.count(('POST','/api/v1/chat')), 1)
        finally: quiesce(self.state)

    def test_disable_and_prepare_uninstall_leave_jobs_and_model_state_intact(self):
        from local_model_delegation.habblaud import disable, status
        from local_model_delegation.package import prepare_uninstall
        receiver, store, job, now = self.active()
        before = store.attempt(job['attempt_id'])
        disable(self.state)
        self.assertFalse(status(self.state)['enabled'])
        self.assertEqual(store.attempt(job['attempt_id']), before)
        self.job_phase(store, job, 'accepted')
        prepare_uninstall(self.state)
        self.assertFalse(status(self.state)['enabled'])
        self.assertEqual(store.job(job['job_id'])['status'], 'accepted')

    def test_missing_coordinator_can_be_bound_after_observation_error(self):
        from local_model_delegation.habblaud import Observer, bind_context
        receiver, store, job, now = self.active()
        with store.db(write=True) as db:
            saved = store.job(job['job_id'])
            route = saved['route_data']; route.pop('habblaud')
            brief = saved['brief']; brief['origin_chat_id'] = 'legacy-chat'
            db.execute('UPDATE jobs SET brief=?,route_data=? WHERE job_id=?', (json.dumps(brief),json.dumps(route),job['job_id']))
        observer = Observer(self.state, job['job_id']); self.assertFalse(observer.step(now))
        with store.db(write=True) as db: bind_context(db, job['job_id'], CONTEXT, rebind=True)
        observer.step(now+21)
        self.job_phase(store, job, 'accepted'); observer.step(now+22)
        self.assertEqual(next(iter(receiver.agents.values()))['status'], 'done')

    def test_numeric_ok_is_not_a_boolean_acknowledgment(self):
        from local_model_delegation.habblaud import Client
        receiver = self.receiver(); receiver.raw = b'{"ok":1}'
        with self.assertRaisesRegex(ValueError, 'rejected'):
            Client(receiver.endpoint).event('.codex', {'hook_event_name':'SubagentStart',
                'session_id':PARENT,'agent_id':OTHER_PARENT,'agent_type':'LOCAL'})

    def test_actual_model_stays_full_while_specialty_is_shortened(self):
        from local_model_delegation.habblaud import Observer, bind_context
        receiver, store, job, now = self.active()
        with store.db(write=True) as db:
            bind_context(db,job['job_id'],{'coordinator_chat_id':PARENT,'specialty':'x'*100},rebind=True)
        Observer(self.state,job['job_id']).step(now)
        self.assertEqual(receiver.events[0]['event']['agent_type'], 'LOCAL · fictional-model · '+'x'*48)
        self.assertEqual(store.job(job['job_id'])['route_data']['habblaud']['context']['specialty'], 'x'*100)

    def test_update_quiesces_observer_before_preservation_snapshot(self):
        import os
        from pathlib import Path
        from tests.test_updates import Updates
        from local_model_delegation.habblaud import configure, ensure_observer, status, bind_context
        from local_model_delegation.updates import prepare_update, verify_update
        old, target = Updates.packages(self)
        receiver = self.receiver(); store = Store(self.state)
        job = store.reserve(self.brief(), self.profile(), self.loaded())
        with store.db(write=True) as db: bind_context(db, job['job_id'], CONTEXT)
        store.transition(job['attempt_id'], 0, 'reserved', 'submitting', {'submitted_at':time.time()})
        configure(self.state,receiver.endpoint,'.codex'); start = ensure_observer(self.state,job['job_id'])
        try:
            deadline = time.monotonic()+4
            while not receiver.agents and time.monotonic()<deadline: time.sleep(.05)
            self.assertTrue(receiver.agents)
            self.job_phase(store,job,'accepted')
            prepared = prepare_update(self.state,target,old)
            self.assertEqual(verify_update(self.state,Path(prepared['receipt']),target)['status'],'verified')
            self.assertFalse(status(self.state)['enabled'])
            self.assertEqual(next(iter(receiver.agents.values()))['status'],'done')
        finally:
            from local_model_delegation.habblaud import quiesce
            quiesce(self.state)
            if start.get('pid'):
                try: os.waitpid(start['pid'],0)
                except ChildProcessError: pass
