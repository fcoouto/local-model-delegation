"""Frozen project campaigns use the existing fake runtime and native receipts."""
import copy
import json
import sys
from pathlib import Path
from unittest.mock import patch

from . import test_project_assessment as preparation
from .support import Fixture, FakeRuntime, FIXED, BUGGY
from local_model_delegation import project_runs as runs
from local_model_delegation import onboarding
from local_model_delegation.contracts import load_json
from local_model_delegation.store import atomic_json


class ProjectRuns(Fixture):
    pack = preparation.ProjectPreparation.pack
    def setUp(self):
        super().setUp()
        recovery = patch('local_model_delegation.recovery.request_recovery')
        recovery.start()
        self.addCleanup(recovery.stop)
        self.server = FakeRuntime(model_format='gguf')
        self.addCleanup(self.server.close)
        self.profile_data = self.profile()
        catalog_path = Path(self.profile_data['runtime_catalog'])
        catalog = load_json(catalog_path.read_text())
        catalog['models'][0]['format'] = 'gguf'
        atomic_json(catalog_path, catalog)
        self.profile_data.update(endpoint=self.server.endpoint, capabilities=['code_change', 'test_writing', 'file_summary'])
        self.write_config(self.profile_data, enabled=False)

    def executable_pack(self):
        pack = self.pack()
        executable = str(Path(sys.executable).resolve())
        for task in pack['domains'][0]['assignments']:
            task['execution'] = {
                'files': {'helper.py': BUGGY}, 'editable_paths': ['helper.py'],
                'criteria': ['Whitespace is stripped at both ends.'],
                'public_checks': [{'id': 'syntax', 'argv': [executable, '-m', 'py_compile', 'helper.py'],
                                   'cwd': '.', 'timeout_seconds': 5}],
                'private_files': {'oracle.py': 'from helper import normalize\nassert normalize(" a ") == "a"\n'},
                'private_checks': [{'id': 'behavior', 'argv': [executable, 'oracle.py'], 'cwd': '.', 'timeout_seconds': 5}],
                'reference_files': {'helper.py': FIXED}, 'review_reference': 'independent-fixture-review',
                'max_cycles': 3,
                'budget': {'context_length': 8192, 'output_ceiling': 2048, 'prefill_seconds': 1,
                           'decode_tokens_per_second': 100, 'measurement_reference': 'fictional-runtime-qualification'}}
        return pack

    def prepare_run(self):
        with patch('local_model_delegation.project_runs.verify_references', return_value={'verified': True}):
            return runs.prepare_project_run(self.state, 'fictional', self.project, self.executable_pack(), 'owner-project')

    def test_project_run_freezes_scope_without_inference_or_approval_change(self):
        before = (self.state / 'profiles/fictional.json').read_bytes()
        prepared = self.prepare_run()
        record = onboarding._assessment(self.state, prepared['assessment_id'])
        self.assertEqual(record['schema_version'], 2)
        self.assertEqual(prepared['preview']['max_submissions'], 24)
        self.assertEqual(len(record['trials']), 8)
        self.assertEqual(record['preview']['project'], self.pack()['project'])
        self.assertIsNone(record['profile_snapshot']['approval'])
        self.assertEqual((self.state / 'profiles/fictional.json').read_bytes(), before)
        self.assertFalse(any(method == 'POST' for method, _ in self.server.calls))

    def test_draft_authorization_rejects_before_submission(self):
        prepared = self.prepare_run()
        record = onboarding._assessment(self.state, prepared['assessment_id'])
        with self.assertRaisesRegex(ValueError, 'assessment_consent_required'):
            onboarding.authorize_assessment(self.state, record['trials'][0]['brief'],
                                            {k: record[k] for k in ('assessment_id', 'permit_token')})

    def test_consent_binds_pack_and_model(self):
        prepared = self.prepare_run()
        with self.assertRaisesRegex(ValueError, 'assessment_preview_mismatch'):
            onboarding.consent_assessment(self.state, prepared['assessment_id'], '0' * 64, 'owner-run')
        result = onboarding.consent_assessment(self.state, prepared['assessment_id'], prepared['preview_digest'], 'owner-run')
        self.assertEqual(result['state'], 'authorized')
        record = onboarding._assessment(self.state, prepared['assessment_id'])
        (self.project / 'helper.py').write_text('changed source')
        with self.assertRaisesRegex(ValueError, 'project_source_changed'):
            onboarding.authorize_assessment(self.state, record['trials'][0]['brief'],
                                            {k: record[k] for k in ('assessment_id', 'permit_token')})

    def test_missing_execution_or_reference_never_prepares_a_run(self):
        pack = self.executable_pack()
        pack['domains'][0]['assignments'][0]['execution'] = None
        with self.assertRaisesRegex(ValueError, 'project_execution_required'):
            runs.prepare_project_run(self.state, 'fictional', self.project, pack, 'owner')
        pack = self.executable_pack()
        pack['domains'][0]['assignments'][0]['execution']['reference_files'] = {'../escape.py': FIXED}
        with self.assertRaises(ValueError):
            runs.prepare_project_run(self.state, 'fictional', self.project, pack, 'owner')

    def test_output_budget_and_deadline_are_measured_and_hidden_checks_not_in_prompt(self):
        from local_model_delegation.worker import build_model_request
        prepared = self.prepare_run()
        record = onboarding._assessment(self.state, prepared['assessment_id'])
        trial = record['trials'][0]
        self.assertEqual(trial['brief']['task_requirements']['max_output_tokens'], 2048)
        self.assertGreater(trial['deadline_seconds'], 40)
        request = build_model_request(trial['brief'], record['profile_snapshot'], 'instance')
        self.assertNotIn('oracle.py', request['input'])
        self.assertNotIn('reference_files', request['input'])

    def test_record_tampering_and_offline_report(self):
        prepared = self.prepare_run()
        report = onboarding.assessment_report(self.state, prepared['assessment_id'])
        self.assertEqual(report['counts']['planned'], 8)
        self.assertEqual(report['counts']['not_run'], 8)
        path = self.state / 'assessments' / prepared['assessment_id'] / 'assessment.json'
        record = load_json(path.read_text())
        record['trials'][0]['brief']['behavior_contract'] = 'Changed after preview'
        atomic_json(path, record)
        with self.assertRaisesRegex(ValueError, 'invalid_assessment_record'):
            onboarding._assessment(self.state, prepared['assessment_id'])

    def test_real_reference_checks_distinguish_base_and_reference(self):
        task = self.executable_pack()['domains'][0]['assignments'][0]
        result = runs.verify_references(self.state, task)
        self.assertTrue(result['verified'])
        task['execution']['reference_files']['helper.py'] = BUGGY
        with self.assertRaisesRegex(ValueError, 'project_reference_failed'):
            runs.verify_references(self.state, task)

    def generated(self, prepared=None, trial_id=None, answer=None):
        from local_model_delegation.store import Store
        from local_model_delegation.worker import run_local_attempt
        prepared = prepared or self.prepare_run()
        record = onboarding._assessment(self.state, prepared['assessment_id'])
        if record['authorization']['state'] == 'draft':
            onboarding.consent_assessment(self.state, prepared['assessment_id'], prepared['preview_digest'], 'owner-run')
        trial_id = trial_id or record['trials'][0]['trial_id']
        with patch('local_model_delegation.worker.launch'):
            envelope = onboarding.submit_trial(self.state, prepared['assessment_id'], trial_id)
        store = Store(self.state)
        from local_model_delegation.capacity import pressure_snapshot
        saved = store.admit(envelope['job_id'], record['profile_snapshot'],
                            {**self.loaded(), 'endpoint': self.server.endpoint}, pressure_snapshot())
        self.server.answer = answer if answer is not None else json.dumps({'files': {'helper.py': FIXED}, 'summary': 'Trim whitespace'})
        with patch('local_model_delegation.worker.launch'):
            run_local_attempt(self.state, saved['attempt_id'])
        return prepared, store, store.job(saved['job_id'])

    def test_public_cycles_bind_parent_and_stop_after_three(self):
        prepared, store, job = self.generated()
        result = runs.advance_cycle(self.state, prepared['assessment_id'], job['job_id'])
        record = onboarding._assessment(self.state, prepared['assessment_id'])
        child = record['trials'][-1]
        self.assertEqual(child['cycle'], 2)
        self.assertEqual(child['parent_job_id'], job['job_id'])
        self.assertNotIn('oracle.py', child['brief']['behavior_contract'])
        self.assertEqual(runs.advance_cycle(self.state, prepared['assessment_id'], job['job_id']), result)
        prepared, store, job = self.generated(prepared, child['trial_id'])
        runs.advance_cycle(self.state, prepared['assessment_id'], job['job_id'])
        third = onboarding._assessment(self.state, prepared['assessment_id'])['trials'][-1]
        prepared, store, job = self.generated(prepared, third['trial_id'])
        with self.assertRaisesRegex(ValueError, 'assessment_cycle_limit'):
            runs.advance_cycle(self.state, prepared['assessment_id'], job['job_id'])
        self.assertEqual(sum(method == 'POST' for method, _ in self.server.calls), 3)

    def test_hidden_checks_finalize_and_cannot_become_feedback(self):
        from local_model_delegation.validation import prepare_verification, run_native_checks, record_verification
        prepared, store, job = self.generated()
        session = prepare_verification(self.state, job['job_id'])
        observed = run_native_checks(self.state, job['job_id'])
        self.assertTrue(all(observed['checks'].values()))
        with self.assertRaisesRegex(ValueError, 'assessment_already_finalizing'):
            runs.advance_cycle(self.state, prepared['assessment_id'], job['job_id'])
        receipt = {k: session[k] for k in ('session_token', 'job_id', 'attempt_id', 'native_task_id',
                                          'candidate_hash', 'source_hash', 'acceptance_hash')}
        receipt.update(criteria=[True], claims=[], checks=observed['checks'])
        record_verification(self.state, job['job_id'], receipt)
        result = onboarding.record_trial(self.state, prepared['assessment_id'],
                                          {'trial_id': job['brief']['task_key'], 'job_id': job['job_id']})
        self.assertEqual(result['counts']['passed'], 1)

    def test_pause_and_duplicate_submit_preserve_existing_job(self):
        prepared, store, job = self.generated()
        result = onboarding.submit_trial(self.state, prepared['assessment_id'], job['brief']['task_key'])
        self.assertEqual(result['job_id'], job['job_id'])
        onboarding.control_assessment(self.state, prepared['assessment_id'], 'pause')
        with self.assertRaisesRegex(ValueError, 'assessment_paused'):
            runs.advance_cycle(self.state, prepared['assessment_id'], job['job_id'])

    def test_deadline_keeps_uncertain_slot_and_never_grades_inability(self):
        self.server.delay = .1
        with patch('local_model_delegation.project_runs.execution_deadline', return_value=.01):
            prepared, store, job = self.generated()
        self.assertEqual(store.attempt(job['attempt_id'])['state'], 'uncertain')
        self.assertEqual(job['reason'], 'assessment_deadline_exceeded')
        result = onboarding.assessment_report(self.state, prepared['assessment_id'])
        self.assertEqual(result['counts']['failed'], 0)
        with self.assertRaises(ValueError):
            runs.advance_cycle(self.state, prepared['assessment_id'], job['job_id'])

    def test_exhausted_terminal_is_unfinished_not_failed(self):
        self.server.output_tokens = 2048
        prepared, store, job = self.generated()
        self.assertEqual(store.attempt(job['attempt_id'])['state'], 'complete')
        result = onboarding.record_trial(self.state, prepared['assessment_id'],
                                          {'trial_id': job['brief']['task_key'], 'job_id': job['job_id']})
        self.assertEqual(result['counts']['unfinished'], 1)
        self.assertEqual(result['counts']['failed'], 0)

    def test_invalid_proposal_consumes_cycle_without_changing_snapshot(self):
        prepared, store, job = self.generated(answer='not JSON')
        runs.advance_cycle(self.state, prepared['assessment_id'], job['job_id'])
        child = onboarding._assessment(self.state, prepared['assessment_id'])['trials'][-1]
        self.assertEqual(child['brief']['files'], job['brief']['files'])
        self.assertIn('invalid_proposal', child['brief']['behavior_contract'])

    def test_revised_parent_cannot_be_accepted_later(self):
        prepared, store, job = self.generated()
        runs.advance_cycle(self.state, prepared['assessment_id'], job['job_id'])
        record = onboarding._assessment(self.state, prepared['assessment_id'])
        with self.assertRaisesRegex(ValueError, 'assessment_cycle_revised'):
            onboarding.authorize_assessment(self.state, job['brief'],
                {k: record[k] for k in ('assessment_id', 'permit_token')}, purpose='verify', job=store.job(job['job_id']))

    def test_cycle_lineage_and_consent_metadata_cannot_be_detached(self):
        prepared, store, job = self.generated()
        runs.advance_cycle(self.state, prepared['assessment_id'], job['job_id'])
        record = onboarding._assessment(self.state, prepared['assessment_id'])
        for field, value in (('cycle', 4), ('parent_candidate_hash', '0' * 64), ('deadline_seconds', 99999)):
            changed = copy.deepcopy(record)
            changed['trials'][-1][field] = value
            with self.assertRaisesRegex(ValueError, 'invalid_assessment_record'):
                runs.validate_record(changed, prepared['assessment_id'])
        record['authorization']['owner_reference'] = None
        with self.assertRaisesRegex(ValueError, 'invalid_assessment_record'):
            runs.validate_record(record, prepared['assessment_id'])

    def test_offline_verification_rechecks_verifier_identity(self):
        prepared, store, job = self.generated()
        record = onboarding._assessment(self.state, prepared['assessment_id'])
        with patch('local_model_delegation.onboarding._verification_snapshot', return_value={}):
            with self.assertRaisesRegex(ValueError, 'assessment_checker_changed'):
                runs.authorize(self.state, record, job['brief'],
                    {k: record[k] for k in ('assessment_id', 'permit_token')}, purpose='verify', job=job)
