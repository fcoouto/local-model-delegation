"""Standalone assessments use disposable, unapproved profiles and fake inference."""
import copy
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
