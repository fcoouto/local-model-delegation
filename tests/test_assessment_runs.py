"""Standalone assessments use disposable, unapproved profiles and fake inference."""
import copy
import json
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
