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
