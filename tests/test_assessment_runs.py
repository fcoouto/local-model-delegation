"""Standalone assessments use disposable, unapproved profiles and fake inference."""
import copy
import json
import shutil
import threading
import time
from pathlib import Path
from unittest.mock import patch

from .support import Fixture, FakeRuntime
from local_model_delegation import onboarding as assessment
from local_model_delegation.contracts import load_json
from local_model_delegation.store import atomic_json


class AssessmentRuns(Fixture):
    group = {'capability': 'test_writing', 'language': 'python',
             'complexity': 'simple', 'context_bucket': 'small'}

    def setUp(self):
        super().setUp()
        self.server = FakeRuntime(model_format='gguf')
        self.addCleanup(self.server.close)
        self.candidate = self.profile()
        catalog_path = Path(self.candidate['runtime_catalog'])
        catalog = load_json(catalog_path.read_text())
        catalog['models'][0]['format'] = 'gguf'
        atomic_json(catalog_path, catalog)
        self.candidate.update(endpoint=self.server.endpoint, approval=None, scope=[],
                              qualification_status='needs_assessment',
                              capabilities=['file_summary', 'code_change', 'python_code_change', 'test_writing'])
        self.write_config(self.candidate, enabled=False)

    def prepare(self, selection=None, **kwargs):
        self.assertTrue(hasattr(assessment, 'prepare_assessment'), 'prepare_assessment must exist')
        return assessment.prepare_assessment(self.state, 'fictional',
                                             selection or {'groups': [self.group]}, **kwargs)

    def test_focused_preview_has_six_trials_without_inference(self):
        before = (self.state / 'config.json').read_bytes()
        run = self.prepare()
        self.assertEqual(run['state'], 'draft')
        self.assertEqual(run['preview']['distinct_cases'], 3)
        self.assertEqual(run['preview']['max_submissions'], 6)
        self.assertNotIn('permit_token', run)
        self.assertFalse(any(method == 'POST' for method, _ in self.server.calls))
        self.assertEqual((self.state / 'config.json').read_bytes(), before)

    def test_all_preview_preserves_six_distinct_groups(self):
        run = self.prepare({'all': True})
        self.assertEqual(len(run['preview']['groups']), 6)
        self.assertEqual(run['preview']['max_submissions'], 36)

    def test_choices_do_not_initialize_state_or_contact_runtime(self):
        self.assertTrue(hasattr(assessment, 'assessment_choices'))
        choices = assessment.assessment_choices()
        self.assertEqual(choices['total_trials'], 36)
        self.assertEqual(len(choices['groups']), 6)
        self.assertFalse((self.state / 'state.sqlite3').exists())
        self.assertEqual(self.server.calls, [])

    def test_invalid_selections_rejected(self):
        self.assertTrue(hasattr(assessment, 'prepare_assessment'))
        for selection in ({}, {'all': False}, {'all': 1}, {'groups': []},
                          {'groups': [self.group, self.group]}, {'all': True, 'groups': [self.group]},
                          {'groups': [{**self.group, 'language': 'unknown'}]}):
            with self.subTest(selection=selection), self.assertRaisesRegex(ValueError, 'invalid_assessment_selection'):
                assessment.prepare_assessment(self.state, 'fictional', selection)
        self.assertEqual(self.server.calls, [])

    def test_selected_capability_is_required(self):
        self.candidate['capabilities'] = ['file_summary']
        self.write_config(self.candidate, enabled=False)
        with self.assertRaisesRegex(ValueError, 'assessment_scope_unsupported'):
            self.prepare()

    def test_approved_input_is_preserved_and_rejected(self):
        profile = self.profile()
        self.write_config(profile, enabled=False)
        path = self.state / 'profiles/fictional.json'
        before = path.read_bytes()
        with self.assertRaisesRegex(ValueError, 'assessment_requires_unapproved_profile'):
            self.prepare()
        self.assertEqual(path.read_bytes(), before)

    def test_missing_prerequisites_do_not_save_a_draft(self):
        for target, value, error in (
                ('shutil.which', None, 'assessment_checker_unavailable'),
                ('local_model_delegation.validation._qualified_isolation', False, 'isolation_unsupported'),
                ('local_model_delegation.lmstudio.select_loaded', None, 'assessment_model_unavailable'),
                ('local_model_delegation.worker.context_fits', False, 'assessment_context_unfit')):
            with self.subTest(target=target), patch(target, return_value=value):
                with self.assertRaisesRegex(ValueError, error):
                    self.prepare({'all': True})
                self.assertEqual(list((self.state / 'assessments').glob('*/assessment.json')), [])
        self.assertFalse(any(method == 'POST' for method, _ in self.server.calls))

    def test_explicit_source_profile_provenance_preserves_approval(self):
        source = copy.deepcopy(self.candidate)
        source.update(profile_id='approved-source', approval={'owner_reference': 'fictional-owner'})
        source['request_settings']['temperature'] = 0.5
        path = self.state / 'profiles/approved-source.json'
        atomic_json(path, source)
        twin = {**source, 'profile_id': 'another-source'}
        atomic_json(self.state / 'profiles/another-source.json', twin)
        before = path.read_bytes()
        run = self.prepare(source_profile_id='approved-source')
        self.assertEqual(run['preview']['source_profile']['profile_id'], 'approved-source')
        self.assertEqual(run['preview']['source_profile']['approval_at_preparation'], source['approval'])
        self.assertEqual(path.read_bytes(), before)
        source['model_id'] = 'unrelated-model'
        atomic_json(path, source)
        with self.assertRaises(ValueError):
            self.prepare(source_profile_id='approved-source')

    def test_structural_validation_does_not_grant_approval(self):
        from local_model_delegation import profiles
        self.assertTrue(hasattr(profiles, 'validate_profile_fields'))
        self.assertEqual(profiles.validate_profile_fields(self.candidate, 'test_writing'), self.candidate)
        with self.assertRaisesRegex(ValueError, 'model_not_approved'):
            profiles.validate_profile(self.candidate, 'test_writing')

    def saved_run(self, selection=None):
        prepared = self.prepare(selection)
        record = assessment._assessment(self.state, prepared['assessment_id'])
        permit = {k: record[k] for k in ('assessment_id', 'permit_token')}
        return prepared, record, permit

    def consent(self, prepared):
        self.assertTrue(hasattr(assessment, 'consent_assessment'), 'consent_assessment must exist')
        return assessment.consent_assessment(self.state, prepared['assessment_id'],
                                             prepared['preview_digest'], 'fixture-run-consent')

    def test_run_consent_is_required_even_with_standing_permission(self):
        prepared, record, permit = self.saved_run()
        config = load_json((self.state / 'config.json').read_text())
        config['assessment_policy'] = {'enabled': True, 'owner_reference': 'standing'}
        atomic_json(self.state / 'config.json', config)
        before = (self.state / 'config.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'assessment_consent_required'):
            assessment.authorize_assessment(self.state, record['trials'][0]['brief'], permit)
        self.assertEqual(self.consent(prepared), self.consent(prepared))
        self.assertEqual(assessment.authorize_assessment(self.state, record['trials'][0]['brief'], permit), self.candidate)
        self.assertEqual((self.state / 'config.json').read_bytes(), before)

    def test_consent_rejects_wrong_digest_reference_and_terminal_state(self):
        prepared, record, _ = self.saved_run()
        self.assertTrue(hasattr(assessment, 'consent_assessment'))
        for digest, reference in [('wrong', 'owner'), (prepared['preview_digest'], '')]:
            with self.assertRaises(ValueError):
                assessment.consent_assessment(self.state, prepared['assessment_id'], digest, reference)
        self.consent(prepared)
        with self.assertRaisesRegex(ValueError, 'assessment_consent_conflict'):
            assessment.consent_assessment(self.state, prepared['assessment_id'], prepared['preview_digest'], 'another')
        record = assessment._assessment(self.state, prepared['assessment_id'])
        record['authorization']['state'] = 'stopped'
        atomic_json(self.state / 'assessments' / prepared['assessment_id'] / 'assessment.json', record)
        with self.assertRaisesRegex(ValueError, 'assessment_stopped'):
            self.consent(prepared)

    def test_changed_profile_and_checkers_reject_submission(self):
        prepared, record, permit = self.saved_run()
        self.consent(prepared)
        self.candidate['request_settings']['temperature'] = .5
        atomic_json(self.state / 'profiles/fictional.json', self.candidate)
        with self.assertRaisesRegex(ValueError, 'assessment_identity_changed'):
            assessment.authorize_assessment(self.state, record['trials'][0]['brief'], permit)
        atomic_json(self.state / 'profiles/fictional.json', record['profile_snapshot'])
        with patch.object(assessment, '_verification_snapshot', return_value={}):
            with self.assertRaisesRegex(ValueError, 'assessment_checker_changed'):
                assessment.authorize_assessment(self.state, record['trials'][0]['brief'], permit)

    def test_frozen_scope_and_permit_cannot_be_substituted(self):
        prepared, record, permit = self.saved_run()
        self.consent(prepared)
        brief = record['trials'][0]['brief']
        for changed_brief, changed_permit in (({**brief, 'behavior_contract': 'different'}, permit),
                                              (brief, {**permit, 'permit_token': 'wrong'})):
            with self.assertRaisesRegex(ValueError, 'assessment_scope_mismatch'):
                assessment.authorize_assessment(self.state, changed_brief, changed_permit)
        fixture = self.root / 'changed-fixture.json'
        atomic_json(fixture, {'cases': []})
        with patch.object(assessment, 'fixtures_path', return_value=fixture):
            with self.assertRaisesRegex(ValueError, 'assessment_scope_mismatch'):
                assessment.authorize_assessment(self.state, brief, permit)

    def test_standalone_runs_reject_legacy_approval_and_capacity(self):
        prepared = self.prepare()
        with self.assertRaisesRegex(ValueError, 'explicit_setup_onboarding_required'):
            assessment.approve_assessment(self.state, prepared['assessment_id'], 'owner', [])
        with self.assertRaisesRegex(ValueError, 'assessment_single_slot_only'):
            assessment.record_capacity(self.state, prepared['assessment_id'], {})

    def test_unknown_malformed_and_downgraded_records_fail_closed(self):
        prepared, record, _ = self.saved_run()
        path = self.state / 'assessments' / prepared['assessment_id'] / 'assessment.json'
        for change in ({'schema_version': 2}, {'schema_version': True}, {'authorization': {}},
                       {'preview_digest': 'forged'}, {'trials': []}):
            atomic_json(path, {**record, **change})
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'invalid_assessment_record'):
                assessment._assessment(self.state, prepared['assessment_id'])
        del record['schema_version']
        atomic_json(path, record)
        with self.assertRaisesRegex(ValueError, 'invalid_assessment_record'):
            assessment._assessment(self.state, prepared['assessment_id'])

    def test_revoked_run_can_verify_only_its_submitted_candidate(self):
        from local_model_delegation.store import Store
        from local_model_delegation.contracts import canonical
        from local_model_delegation.worker import run_local_attempt
        from local_model_delegation.validation import verify_candidate
        prepared, record, permit = self.saved_run({'groups': [{**self.group, 'capability': 'python_code_change'}]})
        self.consent(prepared)
        trial = record['trials'][0]
        files = {n: item['content'] for n, item in trial['brief']['files'].items()}
        files['helper.py'] = 'def transform(text):\n    return text.strip()\n'
        files['test_helper.py'] += '\n    def test_regression(self):\n        self.assertEqual(transform(" a "), "a")\n'
        self.server.answer = json.dumps({'files': files, 'summary': 'Strip both ends'})
        store = Store(self.state)
        saved = store.reserve(trial['brief'], self.candidate, {**self.loaded(), 'endpoint': self.server.endpoint})
        with store.db(write=True) as db:
            db.execute('UPDATE jobs SET route_data=? WHERE job_id=?', (canonical({'assessment': permit}), saved['job_id']))
        self.assertEqual(run_local_attempt(self.state, saved['attempt_id']), 0)
        record = assessment._assessment(self.state, prepared['assessment_id'])
        record['authorization']['state'] = 'stopped'
        atomic_json(self.state / 'assessments' / prepared['assessment_id'] / 'assessment.json', record)
        (self.state / 'profiles/fictional.json').unlink()
        self.assertEqual(verify_candidate(self.state, saved['job_id'])['status'], 'accepted')
        job = store.job(saved['job_id'])
        with self.assertRaisesRegex(ValueError, 'assessment_scope_mismatch'):
            assessment.authorize_assessment(self.state, record['trials'][1]['brief'], permit, purpose='verify', job=job)
        with self.assertRaisesRegex(ValueError, 'assessment_scope_mismatch'):
            assessment.authorize_assessment(self.state, trial['brief'], permit, purpose='verify', job={**job, 'attempt_id': None})

    def queued_run(self):
        from local_model_delegation.store import Store
        prepared, record, _ = self.saved_run()
        self.consent(prepared)
        with patch('local_model_delegation.worker.launch'):
            job = assessment.submit_trial(self.state, prepared['assessment_id'], record['trials'][0]['trial_id'])
        return prepared, record, Store(self.state), job

    def admit(self, store, job):
        from tests.test_scheduler import Scheduler
        return store.admit(job['job_id'], self.candidate,
                           {**self.loaded(), 'endpoint': self.server.endpoint}, Scheduler.resources(self))

    def control(self, prepared, action):
        self.assertTrue(hasattr(assessment, 'control_assessment'), 'control_assessment must exist')
        return assessment.control_assessment(self.state, prepared['assessment_id'], action)

    def test_submission_is_idempotent_and_second_trial_waits(self):
        prepared, record, store, job = self.queued_run()
        with patch('local_model_delegation.worker.launch') as launch:
            repeated = assessment.submit_trial(self.state, prepared['assessment_id'], record['trials'][0]['trial_id'])
            self.assertEqual(repeated['job_id'], job['job_id'])
            launch.assert_not_called()
            with self.assertRaisesRegex(ValueError, 'assessment_trial_pending'):
                assessment.submit_trial(self.state, prepared['assessment_id'], record['trials'][1]['trial_id'])
        reserved = self.admit(store, job)
        from local_model_delegation.worker import run_local_attempt
        run_local_attempt(self.state, reserved['attempt_id'])
        run_local_attempt(self.state, reserved['attempt_id'])
        self.assertEqual(self.server.calls.count(('POST', '/api/v1/chat')), 1)
        with self.assertRaisesRegex(ValueError, 'assessment_has_no_native_fallback'):
            store.claim_fallback(job['job_id'])

    def test_pause_defers_reservation_and_explicit_resume_reuses_job(self):
        from local_model_delegation.scheduler import schedule_once
        prepared, record, store, job = self.queued_run()
        reserved = self.admit(store, job)
        self.assertEqual(self.control(prepared, 'pause')['state'], 'paused')
        self.assertEqual(store.attempt(reserved['attempt_id'])['state'], 'released')
        self.assertEqual(store.job(job['job_id'])['status'], 'waiting')
        with patch('local_model_delegation.worker.start_worker') as start:
            schedule_once(self.state)
            start.assert_not_called()
        with patch('local_model_delegation.worker.launch'):
            self.assertEqual(self.control(prepared, 'resume')['state'], 'authorized')
        self.assertEqual(self.admit(store, job)['job_id'], job['job_id'])

    def test_stop_is_terminal_and_cannot_be_renewed(self):
        prepared = self.prepare()
        self.assertEqual(self.control(prepared, 'stop')['state'], 'stopped')
        with self.assertRaisesRegex(ValueError, 'assessment_stopped'):
            self.control(prepared, 'resume')
        with self.assertRaisesRegex(ValueError, 'assessment_stopped'):
            self.consent(prepared)

    def test_stop_before_commitment_prevents_post(self):
        from local_model_delegation.worker import run_local_attempt
        prepared, _, store, job = self.queued_run()
        reserved = self.admit(store, job)
        entered, release = threading.Event(), threading.Event()
        def barrier(*args):
            entered.set()
            if not release.wait(5): raise RuntimeError('test barrier timeout')
            return True
        with patch('local_model_delegation.store.Store.submission_resources_available', side_effect=barrier):
            thread = threading.Thread(target=run_local_attempt, args=(self.state, reserved['attempt_id']))
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                self.assertEqual(self.control(prepared, 'stop')['state'], 'stopped')
            finally:
                release.set(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertFalse(any(method == 'POST' for method, _ in self.server.calls))

    def test_stop_after_commitment_preserves_attempt_and_allows_observation(self):
        from local_model_delegation.worker import run_local_attempt
        prepared, _, store, job = self.queued_run()
        reserved = self.admit(store, job)
        entered, release = threading.Event(), threading.Event()
        def barrier(*args):
            entered.set()
            if not release.wait(5): raise RuntimeError('test barrier timeout')
        with patch('local_model_delegation.habblaud.ensure_observer', side_effect=barrier):
            thread = threading.Thread(target=run_local_attempt, args=(self.state, reserved['attempt_id']))
            thread.start()
            try:
                self.assertTrue(entered.wait(5))
                self.control(prepared, 'stop')
                self.assertEqual(store.attempt(reserved['attempt_id'])['state'], 'submitting')
            finally:
                release.set(); thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.server.calls.count(('POST', '/api/v1/chat')), 1)
        self.assertEqual(store.attempt(reserved['attempt_id'])['state'], 'complete')

    def test_lost_worker_never_replays_committed_attempt(self):
        prepared, _, store, job = self.queued_run()
        reserved = self.admit(store, job)
        attempt = store.attempt(reserved['attempt_id'])
        store.transition(attempt['attempt_id'], attempt['generation'], 'reserved', 'submitting',
                         {'submitted_at': time.time(), 'request_settings': self.candidate['request_settings']})
        with patch('local_model_delegation.recovery.request_recovery'), patch('local_model_delegation.worker.start_worker') as start:
            first = self.control(prepared, 'resume')
            second = self.control(prepared, 'resume')
            self.assertEqual(first['state'], 'paused')
            self.assertIsNone(second['next_trial_id'])
            self.assertEqual(store.attempt(attempt['attempt_id'])['state'], 'uncertain')
            start.assert_not_called()
        self.assertFalse(any(method == 'POST' for method, _ in self.server.calls))

    def test_active_run_permission_blocks_maintenance_without_jobs(self):
        from local_model_delegation.updates import _disabled
        from local_model_delegation.package import prepare_uninstall
        prepared = self.prepare()
        self.consent(prepared)
        for check in (_disabled, prepare_uninstall):
            with self.assertRaisesRegex(ValueError, 'assessments_must_be_paused'):
                check(self.state)
        self.control(prepared, 'pause')
        _disabled(self.state)

    def test_changed_identity_invalidates_new_work(self):
        prepared, record, _ = self.saved_run()
        self.consent(prepared)
        self.candidate['request_settings']['temperature'] = .2
        atomic_json(self.state / 'profiles/fictional.json', self.candidate)
        with self.assertRaisesRegex(ValueError, 'assessment_identity_changed'):
            assessment.submit_trial(self.state, prepared['assessment_id'], record['trials'][0]['trial_id'])
        self.assertEqual(assessment._assessment(self.state, prepared['assessment_id'])['authorization']['state'], 'invalidated')
        self.assertFalse(any(method == 'POST' for method, _ in self.server.calls))

    def test_worker_run_lock_contention_is_retryable(self):
        from local_model_delegation.worker import ownership, run_local_attempt
        prepared, _, store, job = self.queued_run()
        reserved = self.admit(store, job)
        with ownership(store, 'assessment-' + prepared['assessment_id']):
            self.assertEqual(run_local_attempt(self.state, reserved['attempt_id']), 0)
        self.assertEqual(store.attempt(reserved['attempt_id'])['state'], 'reserved')
        self.assertEqual(store.job(job['job_id'])['status'], 'reserved')
        self.assertFalse(any(method == 'POST' for method, _ in self.server.calls))

    def test_terminal_model_failure_allows_next_trial_but_never_repeats(self):
        from local_model_delegation.worker import run_local_attempt
        prepared, record, store, job = self.queued_run()
        reserved = self.admit(store, job)
        self.server.output_tokens = self.candidate['request_settings']['max_output_tokens']
        run_local_attempt(self.state, reserved['attempt_id'])
        with patch('local_model_delegation.worker.launch'):
            progress = self.control(prepared, 'resume')
            repeated = assessment.submit_trial(self.state, prepared['assessment_id'], record['trials'][0]['trial_id'])
        self.assertEqual(progress['next_trial_id'], record['trials'][1]['trial_id'])
        self.assertEqual(repeated['job_id'], job['job_id'])
        self.assertEqual(self.server.calls.count(('POST', '/api/v1/chat')), 1)

    def test_offline_report_survives_profile_artifact_and_database_removal(self):
        from local_model_delegation.worker import run_local_attempt
        prepared, record, store, job = self.queued_run()
        reserved = self.admit(store, job)
        self.server.output_tokens = self.candidate['request_settings']['max_output_tokens']
        run_local_attempt(self.state, reserved['attempt_id'])
        assessment.record_trial(self.state, prepared['assessment_id'], {'trial_id': record['trials'][0]['trial_id'], 'job_id': job['job_id']})
        (self.state / 'profiles/fictional.json').unlink()
        shutil.rmtree(self.artifact)
        (self.state / 'state.sqlite3').unlink()
        before = {p: p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        before_calls = list(self.server.calls)
        report = assessment.assessment_report(self.state, prepared['assessment_id'])
        self.assertEqual(report['counts']['planned'], 6)
        self.assertEqual(report['counts']['submitted'], 1)
        self.assertEqual(report['counts']['failed'], 1)
        self.assertEqual(report['counts']['not_run'], 5)
        self.assertEqual(report['freshness'], 'unverified')
        self.assertIsNone(report['profile']['approval'])
        self.assertEqual(self.server.calls, before_calls)
        self.assertEqual({p: p.read_bytes() for p in self.state.rglob('*') if p.is_file()}, before)

    def test_report_distinguishes_pending_verification_from_failure(self):
        from local_model_delegation.worker import run_local_attempt
        prepared, _, store, job = self.queued_run()
        reserved = self.admit(store, job)
        run_local_attempt(self.state, reserved['attempt_id'])
        report = assessment.assessment_report(self.state, prepared['assessment_id'])
        self.assertEqual(report['counts']['awaiting_verification'], 1)
        self.assertEqual(report['counts']['evaluated'], 0)
        self.assertEqual(report['counts']['not_run'], 5)
        self.assertEqual(report['trials'][0]['total_output_tokens'], 50)
        self.assertNotIn('recommendation', report)

    def test_reassessment_retains_source_profile_when_changed_or_deleted(self):
        source = {**self.candidate, 'profile_id': 'source', 'approval': {'owner_reference': 'owner'}}
        path = self.state / 'profiles/source.json'
        atomic_json(path, source)
        prepared = self.prepare(source_profile_id='source')
        source['approval'] = None
        atomic_json(path, source)
        report = assessment.assessment_report(self.state, prepared['assessment_id'])
        self.assertEqual(report['source_profile']['profile_id'], 'source')
        self.assertEqual(report['source_profile']['approval_at_preparation'], {'owner_reference': 'owner'})
        self.assertEqual(report['operating_state']['source_profile']['status'], 'changed')
        path.unlink()
        report = assessment.assessment_report(self.state, prepared['assessment_id'])
        self.assertEqual(report['operating_state']['source_profile']['status'], 'unavailable')

    def test_report_with_current_check_is_read_only_and_detects_stale_identity(self):
        prepared = self.prepare()
        report = assessment.assessment_report(self.state, prepared['assessment_id'], check_current=True)
        self.assertEqual(report['freshness'], 'current')
        self.candidate['request_settings']['temperature'] = .1
        atomic_json(self.state / 'profiles/fictional.json', self.candidate)
        report = assessment.assessment_report(self.state, prepared['assessment_id'], check_current=True)
        self.assertEqual(report['freshness'], 'stale')
        self.assertEqual(report['profile']['request_settings']['temperature'], 0)

    def test_read_only_store_never_creates_state_or_permits_writes(self):
        from local_model_delegation.store import Store
        missing = self.root / 'missing'
        with self.assertRaises(FileNotFoundError): Store(missing, read_only=True)
        self.assertFalse(missing.exists())
        prepared = self.prepare()
        before = {p: p.read_bytes() for p in self.state.rglob('*') if p.is_file()}
        store = Store(self.state, read_only=True)
        with self.assertRaisesRegex(ValueError, 'read_only_state'):
            with store.db(write=True): pass
        assessment.assessment_report(self.state, prepared['assessment_id'])
        self.assertEqual({p: p.read_bytes() for p in self.state.rglob('*') if p.is_file()}, before)

    def test_report_uses_exact_jobs_beyond_recent_visibility_limit(self):
        from local_model_delegation.worker import run_local_attempt
        prepared, _, store, job = self.queued_run()
        reserved = self.admit(store, job)
        run_local_attempt(self.state, reserved['attempt_id'])
        for number in range(105):
            unrelated = store.reserve(self.brief('unrelated-' + str(number)), self.candidate, None)
            with store.db(write=True) as db:
                db.execute("UPDATE jobs SET status='failed' WHERE job_id=?", (unrelated['job_id'],))
        report = assessment.assessment_report(self.state, prepared['assessment_id'])
        self.assertEqual(report['counts']['submitted'], 1)
        self.assertEqual(report['trials'][0]['job_id'], job['job_id'])

    def test_unavailable_checks_are_not_recorded_as_model_failure(self):
        from local_model_delegation.worker import run_local_attempt
        prepared, record, store, job = self.queued_run()
        reserved = self.admit(store, job)
        run_local_attempt(self.state, reserved['attempt_id'])
        store.select_fallback(job['job_id'], 'verification_unsupported')
        with self.assertRaisesRegex(ValueError, 'trial_unresolved'):
            assessment.record_trial(self.state, prepared['assessment_id'], {'trial_id': record['trials'][0]['trial_id'], 'job_id': job['job_id']})
        report = assessment.assessment_report(self.state, prepared['assessment_id'])
        self.assertEqual(report['counts']['failed'], 0)
        self.assertEqual(report['counts']['unresolved'], 1)
        self.assertEqual(report['trials'][0]['infrastructure_blocker'], 'verification_unsupported')

    def test_assessment_outcome_cannot_change_model_global_evidence(self):
        from local_model_delegation.worker import run_local_attempt
        prepared, _, store, job = self.queued_run()
        reserved = self.admit(store, job)
        run_local_attempt(self.state, reserved['attempt_id'])
        with store.db(write=True) as db:
            db.execute("UPDATE jobs SET status='failed' WHERE job_id=?", (job['job_id'],))
        before = (self.state / 'profiles/fictional.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'assessment_has_no_global_outcome'):
            assessment.record_outcome(self.state, job['job_id'], {
                'native_usage': {'kind': 'unknown', 'value': None}, 'coordination_tokens': None,
                'checking_tokens': None, 'fallback_tokens': None, 'native_baseline_tokens': None,
                'onboarding_tokens': None, 'latency_seconds': 1, 'provenance': 'fictional test'})
        self.assertEqual((self.state / 'profiles/fictional.json').read_bytes(), before)

    def test_cli_prepare_consent_report_and_stop_share_the_run(self):
        from tests.test_cli import CLI
        selection = self.root / 'selection.json'
        atomic_json(selection, {'groups': [self.group]})
        prepared = CLI.invoke(self, 'assessment', 'prepare', '--profile-id', 'fictional', '--selection', str(selection))
        identifier = prepared['assessment_id']
        result = CLI.invoke(self, 'assessment', 'consent', '--assessment-id', identifier,
                            '--preview-digest', prepared['preview_digest'], '--owner-reference', 'fixture-cli-consent')
        self.assertEqual(result['state'], 'authorized')
        self.assertEqual(CLI.invoke(self, 'assessment', 'pause', '--assessment-id', identifier)['state'], 'paused')
        self.assertEqual(CLI.invoke(self, 'assessment', 'stop', '--assessment-id', identifier)['state'], 'stopped')
        before_calls = list(self.server.calls)
        report = CLI.invoke(self, 'assessment', 'report', '--assessment-id', identifier)
        self.assertEqual(report['counts']['not_run'], 6)
        self.assertEqual(before_calls, self.server.calls)
        self.assertFalse(any(method == 'POST' for method, _ in self.server.calls))

    def test_focused_run_completes_through_existing_native_verification(self):
        from local_model_delegation.store import Store
        from local_model_delegation.worker import run_local_attempt, wait_job
        from local_model_delegation.validation import prepare_verification, run_native_checks, record_verification
        prepared, record, _ = self.saved_run()
        self.consent(prepared)
        store = Store(self.state)
        before = (self.state / 'profiles/fictional.json').read_bytes()
        cases = [(' a ', 'a'), ('a', 'A'), ('a-b-c', 'abc')]
        for trial in record['trials']:
            argument, expected = cases[int(trial['case_id'][-1])]
            test_source = ('import unittest\nfrom helper import transform\nclass Tests(unittest.TestCase):\n'
                           f'    def test_contract(self):\n        self.assertEqual(transform({argument!r}), {expected!r})\n')
            self.server.answer = json.dumps({'files': {'test_helper.py': test_source}, 'summary': 'Expose the stated difference'})
            with patch('local_model_delegation.worker.launch'):
                job = assessment.submit_trial(self.state, prepared['assessment_id'], trial['trial_id'])
            reserved = self.admit(store, job)
            self.assertEqual(run_local_attempt(self.state, reserved['attempt_id']), 0)
            self.assertEqual(wait_job(self.state, job['job_id'], 0)['status'], 'candidate_ready')
            session = prepare_verification(self.state, job['job_id'])
            checks = run_native_checks(self.state, job['job_id'])
            self.assertEqual(checks['checks'], {'syntax': True})
            receipt = {k: session[k] for k in ('job_id', 'attempt_id', 'native_task_id', 'candidate_hash',
                                              'source_hash', 'acceptance_hash', 'session_token')}
            # The native fixture reviewer checks the exact expected boundary case, independently of syntax.
            self.assertIn(f'transform({argument!r}), {expected!r}', test_source)
            receipt.update(criteria=[True], checks=checks['checks'], claims=[])
            self.assertEqual(record_verification(self.state, job['job_id'], receipt)['status'], 'accepted')
            final = assessment.record_trial(self.state, prepared['assessment_id'], {'trial_id': trial['trial_id'], 'job_id': job['job_id']})
        self.assertEqual(final['state'], 'complete')
        self.assertEqual(final['counts']['passed'], 6)
        self.assertEqual(final['counts']['evaluated'], 6)
        self.assertEqual(final['counts']['not_run'], 0)
        self.assertTrue(final['groups'][0]['provisional_synthetic_evidence'])
        self.assertEqual(self.server.calls.count(('POST', '/api/v1/chat')), 6)
        self.assertEqual((self.state / 'profiles/fictional.json').read_bytes(), before)
        last_receipt = {'trial_id': trial['trial_id'], 'job_id': job['job_id']}
        self.assertEqual(assessment.record_trial(self.state, prepared['assessment_id'], last_receipt), final)

    def test_full_run_records_36_terminal_failures_without_retries(self):
        from local_model_delegation.store import Store
        from local_model_delegation.worker import run_local_attempt
        prepared, record, _ = self.saved_run({'all': True})
        self.consent(prepared)
        store = Store(self.state)
        self.server.output_tokens = self.candidate['request_settings']['max_output_tokens']
        for trial in record['trials']:
            with patch('local_model_delegation.worker.launch'):
                job = assessment.submit_trial(self.state, prepared['assessment_id'], trial['trial_id'])
            reserved = self.admit(store, job)
            run_local_attempt(self.state, reserved['attempt_id'])
            report = assessment.record_trial(self.state, prepared['assessment_id'], {'trial_id': trial['trial_id'], 'job_id': job['job_id']})
        self.assertEqual(report['state'], 'complete')
        self.assertEqual(report['counts']['failed'], 36)
        self.assertEqual(report['counts']['submitted'], 36)
        self.assertEqual(len(report['groups']), 6)
        self.assertEqual(self.server.calls.count(('POST', '/api/v1/chat')), 36)
        self.assertTrue(all(t['reason'] == 'output_budget_exhausted' for t in report['trials']))

    def test_pause_uses_current_reservation_when_waiting_snapshot_is_stale(self):
        from local_model_delegation.worker import ownership
        prepared, _, store, job = self.queued_run()
        stale = store.job(job['job_id'])
        reserved = self.admit(store, job)
        with ownership(store, 'assessment-' + prepared['assessment_id']):
            assessment._defer_run_job(store, stale, 'paused')
        self.assertEqual(store.attempt(reserved['attempt_id'])['state'], 'released')
        self.assertEqual(store.job(job['job_id'])['status'], 'waiting')
        self.assertIsNone(store.job(job['job_id'])['attempt_id'])

    def test_pause_during_scheduler_authorization_keeps_job_resumable(self):
        from local_model_delegation.scheduler import schedule_once
        prepared, _, store, job = self.queued_run()
        authorize = assessment.authorize_assessment
        paused = False
        def pause_then_authorize(*args, **kwargs):
            nonlocal paused
            if not paused:
                paused = True
                self.control(prepared, 'pause')
            return authorize(*args, **kwargs)
        with patch.object(assessment, 'authorize_assessment', side_effect=pause_then_authorize):
            schedule_once(self.state)
        self.assertEqual(store.job(job['job_id'])['status'], 'waiting')
        with patch('local_model_delegation.worker.launch'):
            self.assertEqual(self.control(prepared, 'resume')['state'], 'authorized')
        self.assertEqual(self.admit(store, job)['status'], 'reserved')

    def test_pressure_is_sampled_again_after_slow_final_binding_checks(self):
        from local_model_delegation.worker import run_local_attempt
        prepared, _, store, job = self.queued_run()
        reserved = self.admit(store, job)
        check = assessment._check_run_bindings
        critical = False
        def changed_pressure(*args, **kwargs):
            nonlocal critical
            result = check(*args, **kwargs)
            critical = True
            return result
        with patch.object(assessment, '_check_run_bindings', side_effect=changed_pressure), \
                patch('local_model_delegation.store.Store.submission_resources_available', side_effect=lambda job: not critical):
            run_local_attempt(self.state, reserved['attempt_id'])
        self.assertFalse(any(method == 'POST' for method, _ in self.server.calls))
        self.assertFalse(store.attempt(reserved['attempt_id'])['data'].get('submitted_at'))

    def test_pause_during_scheduler_admission_keeps_job_resumable(self):
        from local_model_delegation.scheduler import schedule_once
        from local_model_delegation.store import Store
        prepared, _, store, job = self.queued_run()
        admit = Store.admit
        def pause_then_admit(current, *args, **kwargs):
            self.control(prepared, 'pause')
            return admit(current, *args, **kwargs)
        with patch.object(Store, 'admit', autospec=True, side_effect=pause_then_admit):
            schedule_once(self.state)
        self.assertEqual(store.job(job['job_id'])['status'], 'waiting')
        with patch('local_model_delegation.worker.launch'):
            self.assertEqual(self.control(prepared, 'resume')['state'], 'authorized')
        self.assertEqual(self.admit(store, job)['status'], 'reserved')

    def test_pause_during_early_worker_rejection_keeps_job_resumable(self):
        from local_model_delegation.worker import run_local_attempt
        for target in ('local_model_delegation.store.Store.submission_resources_available',
                       'local_model_delegation.worker.context_fits'):
            with self.subTest(target=target):
                prepared, _, store, job = self.queued_run()
                reserved = self.admit(store, job)
                def pause_then_reject(*args, **kwargs):
                    self.control(prepared, 'pause')
                    return False
                with patch(target, side_effect=pause_then_reject):
                    run_local_attempt(self.state, reserved['attempt_id'])
                self.assertEqual(store.job(job['job_id'])['status'], 'waiting')
                self.assertEqual(store.attempt(reserved['attempt_id'])['state'], 'released')
                with patch('local_model_delegation.worker.launch'):
                    self.assertEqual(self.control(prepared, 'resume')['state'], 'authorized')
                self.assertEqual(self.admit(store, job)['status'], 'reserved')
                self.control(prepared, 'stop')
        self.assertFalse(any(method == 'POST' for method, _ in self.server.calls))

    def test_native_checker_change_stays_unresolved_after_checker_returns(self):
        from local_model_delegation.worker import run_local_attempt
        from local_model_delegation.validation import prepare_verification
        prepared, _, store, job = self.queued_run()
        reserved = self.admit(store, job)
        run_local_attempt(self.state, reserved['attempt_id'])
        with patch.object(assessment, '_verification_snapshot', return_value={}):
            with self.assertRaisesRegex(ValueError, 'assessment_checker_changed'):
                prepare_verification(self.state, job['job_id'])
        with patch('local_model_delegation.worker.launch'):
            progress = self.control(prepared, 'resume')
        report = assessment.assessment_report(self.state, prepared['assessment_id'])
        self.assertEqual(progress['state'], 'paused')
        self.assertIsNone(progress['next_trial_id'])
        self.assertEqual(report['counts']['failed'], 0)
        self.assertEqual(report['counts']['evaluated'], 0)
        self.assertEqual(report['counts']['unresolved'], 1)

    def test_invalid_model_proposals_are_evaluated_failures(self):
        from local_model_delegation.worker import run_local_attempt
        from local_model_delegation.validation import prepare_verification
        for answer in ('not JSON', '{"summary":"first","summary":"second","files":{}}',
                       '{"summary":"proposal","files":NaN}',
                       json.dumps({'summary': 'proposal', 'files': {'outside.txt': 'wrong path'}})):
            with self.subTest(answer=answer):
                prepared, _, store, job = self.queued_run()
                self.server.answer = answer
                reserved = self.admit(store, job)
                run_local_attempt(self.state, reserved['attempt_id'])
                with self.assertRaises(ValueError): prepare_verification(self.state, job['job_id'])
                with patch('local_model_delegation.worker.launch'): self.control(prepared, 'resume')
                report = assessment.assessment_report(self.state, prepared['assessment_id'])
                self.assertEqual(report['counts']['failed'], 1)
                self.assertEqual(report['counts']['evaluated'], 1)
                self.assertEqual(report['counts']['unresolved'], 0)

    def test_corrupt_saved_candidate_is_not_a_model_failure(self):
        from local_model_delegation.worker import run_local_attempt
        from local_model_delegation.validation import prepare_verification
        for content in ('{', '{"text":"first","text":"second","sha256":"invalid"}'):
            with self.subTest(content=content):
                prepared, _, store, job = self.queued_run()
                reserved = self.admit(store, job)
                run_local_attempt(self.state, reserved['attempt_id'])
                Path(store.job(job['job_id'])['result_path']).write_text(content)
                with self.assertRaises(ValueError): prepare_verification(self.state, job['job_id'])
                with patch('local_model_delegation.worker.launch'):
                    self.assertEqual(self.control(prepared, 'resume')['state'], 'paused')
                report = assessment.assessment_report(self.state, prepared['assessment_id'])
                self.assertEqual(report['counts']['evaluated'], 0)
                self.assertEqual(report['counts']['unresolved'], 1)
