import copy
import time
from unittest.mock import patch

from tests import test_scheduler
from tests.support import Fixture


class PracticalAdmission(Fixture):
    setup_queue = test_scheduler.Scheduler.setup_queue
    generic = test_scheduler.Scheduler.generic
    resources = test_scheduler.Scheduler.resources

    def test_idle_assessment_instance_accepts_fresh_project_approval(self):
        from local_model_delegation.store import Store
        profile = self.profile(); previous = copy.deepcopy(profile); previous['approval'] = None
        store = Store(self.state)
        old = store.reserve(self.brief(), previous, self.loaded())
        with store.db(write=True) as db:
            db.execute("UPDATE attempts SET state='complete'")
            db.execute("UPDATE jobs SET status='accepted'")
            # Older helpers closed policy-only changes without a recovery marker.
            db.execute("UPDATE instances SET state='closed'")
        result = store.reserve(self.brief('new-approval'), profile, self.loaded())
        self.assertEqual(result['status'], 'reserved')
        self.assertEqual(store.instance(store.attempt(old['attempt_id'])['instance_key'])['data']['profile']['approval'], profile['approval'])

    def test_approval_refresh_never_closes_or_reuses_an_occupied_slot(self):
        from local_model_delegation.store import Store
        profile = self.profile(); store = Store(self.state)
        old = store.reserve(self.brief(), profile, self.loaded())
        changed = copy.deepcopy(profile); changed['approval']['owner_reference'] = 'renewed-consent'
        for state in ('reserved','submitting','streaming','uncertain'):
            with store.db(write=True) as db: db.execute('UPDATE attempts SET state=?',(state,))
            result = store.reserve(self.brief('approval-'+state), changed, self.loaded())
            self.assertIsNone(result['attempt_id'])
            self.assertEqual(store.instance(store.attempt(old['attempt_id'])['instance_key'])['state'], 'ready')

    def test_approval_refresh_does_not_clear_recovery_or_changed_identity(self):
        from local_model_delegation.store import Store
        from local_model_delegation.recovery import close_instance
        profile = self.profile(); store = Store(self.state)
        old = store.reserve(self.brief(), profile, self.loaded())
        key = store.attempt(old['attempt_id'])['instance_key']
        with store.db(write=True) as db: db.execute("UPDATE attempts SET state='complete'")
        close_instance(store, key)
        changed = copy.deepcopy(profile); changed['approval']['owner_reference'] = 'renewed-consent'
        self.assertIsNone(store.reserve(self.brief('recovery'),changed,self.loaded())['attempt_id'])
        self.assertEqual(store.instance(key)['data']['recovery_phase'], 'unload')

    def test_approval_refresh_requires_identical_runtime_binding_and_no_lifecycle_work(self):
        from local_model_delegation.store import Store
        from local_model_delegation.contracts import digest
        profile = self.profile(); store = Store(self.state)
        old = store.reserve(self.brief(), profile, self.loaded())
        with store.db(write=True) as db: db.execute("UPDATE attempts SET state='complete'")
        changed = copy.deepcopy(profile); changed['approval']['owner_reference'] = 'renewed-consent'
        changed['request_settings']['max_output_tokens'] += 1
        self.assertIsNone(store.reserve(self.brief('settings'),changed,self.loaded())['attempt_id'])
        changed = copy.deepcopy(profile); changed['approval']['owner_reference'] = 'renewed-consent'
        loaded = self.loaded(); loaded['config']['context_length'] *= 2
        self.assertIsNone(store.reserve(self.brief('context'),changed,loaded)['attempt_id'])
        with store.db(write=True) as db:
            db.execute("INSERT INTO model_operations VALUES ('uncertain-op',?,'uncertain','{}')",(digest([profile['endpoint'],profile['model_id']]),))
        self.assertIsNone(store.reserve(self.brief('operation'),changed,self.loaded())['attempt_id'])

    def test_loaded_single_slot_needs_no_memory_calibration(self):
        from local_model_delegation.capacity import qualified_limit
        store, brief, profile = self.setup_queue()
        profile.pop('capacity_evidence')
        observation = {'pressure': 'warning', 'observed_at': time.time()}
        self.assertEqual(qualified_limit(profile, self.loaded(4), observation), 1)
        for pressure in ('critical', 'unknown'):
            self.assertEqual(qualified_limit(profile, self.loaded(), {**observation, 'pressure': pressure}), 0)
        self.assertEqual(qualified_limit(profile, self.loaded(), {**observation, 'observed_at': 1}), 0)

    def test_warning_swap_and_free_memory_do_not_veto_loaded_work(self):
        store, brief, profile = self.setup_queue()
        job = store.enqueue(brief, brief['fallback'])
        resources = {**self.resources(), 'pressure': 'warning', 'available_bytes': 0, 'swapout_delta_bytes': 4096}
        self.assertEqual(store.admit(job['job_id'], profile, self.loaded(), resources)['status'], 'reserved')

    def test_full_prompt_and_output_must_fit_runtime_before_reservation(self):
        store, brief, profile = self.setup_queue()
        job = store.enqueue(brief, brief['fallback'])
        loaded = self.loaded()
        loaded['config']['context_length'] = profile['request_settings']['max_output_tokens']
        result = store.admit(job['job_id'], profile, loaded, self.resources())
        self.assertEqual(result['reason'], 'context_budget_exceeded')
        self.assertIsNone(store.job(job['job_id'])['attempt_id'])

    def test_explicit_operating_budget_is_separate_from_observed_evidence(self):
        from local_model_delegation.onboarding import approve_scope
        from local_model_delegation.profiles import read_profiles
        store, brief, profile = self.setup_queue()
        evidence = copy.deepcopy(profile.get('assessment'))
        scope = [{**profile['scope'][0], 'max_input_bytes': 65536}]
        with self.assertRaisesRegex(ValueError, 'owner_confirmation_required'):
            approve_scope(self.state, profile['profile_id'], '', scope)
        approve_scope(self.state, profile['profile_id'], 'fixture-owner-practical-pilot', scope)
        current = read_profiles(self.state)[0]
        self.assertEqual(current['approval']['scope'], scope)
        self.assertEqual(current.get('assessment'), evidence)
        self.assertNotIn('benefit_evidence', current['approval'])
        for value in (True, 0, -1, 800001):
            with self.assertRaisesRegex(ValueError, 'invalid_scope'):
                approve_scope(self.state, profile['profile_id'], 'fixture-owner', [{**scope[0], 'max_input_bytes': value}])

    def test_worker_uses_lightweight_fresh_gate(self):
        store, brief, profile = self.setup_queue()
        job = store.enqueue(brief, brief['fallback'])
        store.admit(job['job_id'], profile, self.loaded(), self.resources())
        with patch('local_model_delegation.capacity.pressure_snapshot', return_value={'pressure':'warning','observed_at':time.time()}), \
             patch('local_model_delegation.capacity.machine_snapshot', side_effect=AssertionError('heavy sample')):
            self.assertTrue(store.submission_resources_available(store.job(job['job_id'])))

    def test_context_screen_counts_unicode_system_prompt_and_output(self):
        from local_model_delegation.worker import build_model_request, context_fits
        store, brief, profile = self.setup_queue()
        brief['behavior_contract'] = 'Explain café 🙂'
        loaded = self.loaded()
        body = build_model_request(brief, profile, loaded['instance_id'])
        bound = len((body['system_prompt'] + body['input']).encode()) + 2048 + body['max_output_tokens']
        loaded['config']['context_length'] = bound
        self.assertTrue(context_fits(brief, profile, loaded))
        loaded['config']['context_length'] -= 1
        self.assertFalse(context_fits(brief, profile, loaded))

    def test_new_synthetic_assessment_does_not_automatically_expand_concurrency(self):
        from tests.test_onboarding import Onboarding
        from local_model_delegation.onboarding import begin_assessment
        from local_model_delegation.store import atomic_json
        profile = Onboarding.setup_policy(self)
        profile['capacity_evidence'] = {'qualified': True, 'limit': 4}
        atomic_json(self.state/'profiles/fictional.json', profile)
        assessment = begin_assessment(self.state, 'fictional', 'fixture-standing-consent')
        self.assertEqual(assessment['capacity_target'], 1)
