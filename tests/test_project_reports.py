import copy
from unittest.mock import patch
from tests import test_project_assessment_runs as campaigns
from tests.support import Fixture
from local_model_delegation import project_runs as runs, onboarding
from local_model_delegation.store import atomic_json


class ProjectReports(Fixture):
    setUp = campaigns.ProjectRuns.setUp
    pack = campaigns.ProjectRuns.pack
    executable_pack = campaigns.ProjectRuns.executable_pack
    prepare_run = campaigns.ProjectRuns.prepare_run
    generated = campaigns.ProjectRuns.generated

    def report_fixture(self, passed=2, weights=False):
        prepared = self.prepare_run()
        record = onboarding._assessment(self.state, prepared['assessment_id'])
        for trial in record['trials'][:passed]:
            record['receipts'][trial['trial_id']] = {'case_id': trial['case_id'], 'disposition': 'passed'}
        if weights:
            record['pack']['domains'][0]['weight'] = .2
            record['pack']['workload'] = {'owner_reference': 'confirmed-task-mix',
                                        'basis': 'Representative frequency of this exact difficulty/context mix',
                                        'unassessed_weight': .8}
        return record

    def test_sparse_extra_high_and_missing_weights_remain_unknown(self):
        record = self.report_fixture(8)
        result = runs.report(self.state, record)
        self.assertIsNone(result['workload_coverage'])
        extra = next(b for b in result['scope_results'] if b['complexity'] == 'extra_complex')
        self.assertEqual(extra['recommendation'], 'not_established')
        self.assertEqual(extra['counts']['passed'], 1)
        self.assertEqual(result['native_comparison']['status'], 'not_collected')
        self.assertIn('not enforced', result['native_comparison']['native_limits'])

    def test_weights_keep_unfinished_in_denominator_and_show_assumptions(self):
        result = runs.report(self.state, self.report_fixture(2, weights=True))
        self.assertAlmostEqual(result['workload_coverage']['share'], .05)
        self.assertEqual(result['workload_coverage']['denominator'], 'recurring_task_count')
        self.assertEqual(result['unassessed_workload_share'], .8)
        self.assertEqual(result['counts']['planned'], 8)
        self.assertEqual(result['counts']['not_run'], 6)
        simple = next(b for b in result['scope_results'] if b['complexity'] == 'simple')
        self.assertEqual(simple['recommendation'], 'suitable_within_tested_scope')

    def test_project_approval_preserves_legacy_and_rejects_untested_scope(self):
        self.qualified_source()
        from local_model_delegation.projects import resolve_project_identity
        record = self.report_fixture(2)
        atomic_json(self.state / 'assessments' / record['assessment_id'] / 'assessment.json', record)
        source = onboarding._profile(self.state, 'fictional')
        original = copy.deepcopy(source['scope'])
        scope = [{'capability': 'code_change', 'language': 'python', 'complexity': 'simple',
                  'context_bucket': 'small', 'max_input_bytes': 100}]
        # Exact effective settings remain an explicit approval dimension.
        onboarding.approve_scope(self.state, 'fictional', 'owner-project', scope,
                                 project_root=self.project, assessment_id=record['assessment_id'], max_output_tokens=2048)
        current = onboarding._profile(self.state, 'fictional')
        self.assertEqual(current['scope'][:-1], original)
        self.assertEqual(current['scope'][-1]['project'], resolve_project_identity(self.project))
        self.assertEqual(current['scope'][-1]['assessment_id'], record['assessment_id'])
        scope[0]['complexity'] = 'extra_complex'
        with self.assertRaisesRegex(ValueError, 'project_scope_not_established'):
            onboarding.approve_scope(self.state, 'fictional', 'owner-project', scope,
                                     project_root=self.project, assessment_id=record['assessment_id'])

    def test_comparison_context_uses_campaign_project_not_private_stage(self):
        from local_model_delegation import measurements as metrics
        from local_model_delegation.contracts import digest, canonical
        prepared, store, job = self.generated()
        record = onboarding._assessment(self.state, prepared['assessment_id'])
        metrics.initialize_measurements(self.state)
        registered = metrics.register_project(self.state, self.project, 'Fictional project')
        case = record['pack']['domains'][0]['assignments'][0]
        brief = job['brief']
        context = {'project_id': registered['project_id'], 'origin': 'synthetic_assessment',
                   'scope': {'capability': brief['capability'],
                             **{k: brief['task_requirements'][k] for k in ('language', 'complexity', 'context_bucket')},
                             'input_bytes': len(canonical({'contract': brief['behavior_contract'], 'files': brief['files'],
                                                          'editable_paths': brief['editable_paths']}).encode()),
                             'file_count': len(brief['files'])},
                   'environment_digest': None, 'environment_manifest': None, 'native_binding': None,
                   'source_revision': None, 'case_id': case['id'], 'case_hash': digest(case)}
        metrics.begin_measurement(self.state, job['job_id'], context, job['job_id'])
        with metrics.connection(self.state) as db:
            observed = metrics.job_observation(db, job['job_id'])
        self.assertEqual(observed['binding']['runtime_digest'], digest(record['binding']['runtime']))
        self.assertIsNotNone(observed['binding']['helper_digest'])
        context['case_hash'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'comparison_case_mismatch'):
            metrics.begin_measurement(self.state, 'wrong', context, job['job_id'])

    def qualified_source(self, ceiling=2048):
        source = onboarding._profile(self.state, 'fictional')
        source['capabilities'].append('python_code_change')
        source['request_settings']['max_output_tokens'] = ceiling
        binding = onboarding._binding(source)
        source['approval'].update(model_identity=binding['runtime'], artifact_digest=binding['artifact']['digest'],
                                  capabilities=source['capabilities'], request_settings=copy.deepcopy(source['request_settings']))
        atomic_json(self.state / 'profiles/fictional.json', source)

    def test_project_grant_cannot_resurrect_stale_legacy_permission(self):
        self.qualified_source()
        (self.artifact / 'weights.bin').write_bytes(b'replacement fictional artifact')
        record = self.report_fixture(2)
        atomic_json(self.state / 'assessments' / record['assessment_id'] / 'assessment.json', record)
        before = (self.state / 'profiles/fictional.json').read_bytes()
        scope = [{'capability': 'code_change', 'language': 'python', 'complexity': 'simple',
                  'context_bucket': 'small', 'max_input_bytes': 100}]
        with self.assertRaisesRegex(ValueError, 'retained_approval_stale'):
            onboarding.approve_scope(self.state, 'fictional', 'owner-simple-project-only', scope,
                                     project_root=self.project, assessment_id=record['assessment_id'])
        self.assertEqual(before, (self.state / 'profiles/fictional.json').read_bytes())

    def test_project_grant_cannot_expand_retained_global_generation_ceiling(self):
        self.qualified_source(1024)
        record = self.report_fixture(2)
        atomic_json(self.state / 'assessments' / record['assessment_id'] / 'assessment.json', record)
        before = (self.state / 'profiles/fictional.json').read_bytes()
        scope = [{'capability': 'code_change', 'language': 'python', 'complexity': 'simple',
                  'context_bucket': 'small', 'max_input_bytes': 100}]
        with self.assertRaisesRegex(ValueError, 'retained_settings_change_requires_approval'):
            onboarding.approve_scope(self.state, 'fictional', 'owner-simple-project-only', scope,
                project_root=self.project, assessment_id=record['assessment_id'], max_output_tokens=2048)
        self.assertEqual(before, (self.state / 'profiles/fictional.json').read_bytes())
