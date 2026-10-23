"""Project preparation is offline and uses only fictional project evidence."""
import io
import json
from contextlib import redirect_stdout
from unittest.mock import patch

from .support import Fixture, sha
from local_model_delegation.projects import resolve_project_identity
from local_model_delegation import project_assessment as project


class ProjectPreparation(Fixture):
    def pack(self):
        tasks = []
        for index, level in enumerate(['simple'] * 2 + ['moderate'] * 3 + ['complex'] * 2 + ['extra_complex']):
            tasks.append({
                'id': 'case-' + str(index), 'title': 'Project scenario ' + str(index),
                'origin': 'constructed', 'difficulty': level,
                'difficulty_reason': 'Interacting requirements: ' + str(index),
                'context_bucket': 'small', 'contract': 'Handle project behavior ' + str(index),
                'source_evidence': [{'path': 'helper.py', 'sha256': sha((self.project / 'helper.py').read_text()), 'revision': None}],
                'verification_plan': 'Run independently reviewed behavioral tests.',
                'execution': None})
        return {'schema_version': 1, 'project': resolve_project_identity(self.project),
                'domains': [{'id': 'python-fixes', 'specialty': 'Project fixes', 'role': 'Builder',
                             'capability': 'code_change', 'language': 'python', 'weight': None,
                             'assignments': tasks}],
                'workload': {'owner_reference': None, 'basis': None, 'unassessed_weight': None}}

    def test_exact_difficulty_mixes(self):
        for count, expected in {6: [1, 2, 2, 1], 7: [2, 2, 2, 1], 8: [2, 3, 2, 1],
                                9: [2, 3, 3, 1], 10: [2, 4, 3, 1]}.items():
            self.assertEqual(list(project.difficulty_distribution(count).values()), expected)
        for bad in (True, 5, 11, 8.0, '8'):
            with self.assertRaisesRegex(ValueError, 'invalid_assignment_count'):
                project.difficulty_distribution(bad)

    def test_preview_is_offline_and_never_runnable_without_execution(self):
        with patch('local_model_delegation.lmstudio.Runtime', side_effect=AssertionError('no runtime')):
            result = project.project_preview(self.project, self.pack(), 'owner-project-permission')
        self.assertEqual(result['assignment_count'], 8)
        self.assertEqual(result['project'], resolve_project_identity(self.project))
        self.assertEqual(result['status'], 'draft')
        self.assertFalse(result['ready_for_assessment'])
        self.assertIsNone(result['workload_coverage'])
        self.assertEqual(result['domains'][0]['difficulty_counts']['extra_complex'], 1)
        self.assertFalse(self.state.exists())

    def test_project_and_permission_are_required(self):
        for permission in ('', None):
            with self.assertRaisesRegex(ValueError, 'project_permission_required'):
                project.project_preview(self.project, self.pack(), permission)
        pack = self.pack()
        pack['project']['identity'] = str(self.root)
        with self.assertRaisesRegex(ValueError, 'project_identity_mismatch'):
            project.project_preview(self.project, pack, 'owner')

    def test_changed_or_unsafe_source_is_rejected(self):
        for name in ('../weights.bin', '/tmp/file', '.git/config'):
            pack = self.pack()
            pack['domains'][0]['assignments'][0]['source_evidence'][0]['path'] = name
            with self.subTest(name=name), self.assertRaises(ValueError):
                project.project_preview(self.project, pack, 'owner')
        pack = self.pack()
        (self.project / 'helper.py').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'project_source_changed'):
            project.project_preview(self.project, pack, 'owner')

    def test_duplicate_ids_and_renamed_scenarios_rejected(self):
        for field in ('id', 'contract'):
            pack = self.pack()
            cases = pack['domains'][0]['assignments']
            cases[1][field] = cases[0][field]
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, 'duplicate_project_assignment'):
                project.project_preview(self.project, pack, 'owner')

    def test_extra_high_must_not_collapse_into_high(self):
        pack = self.pack()
        pack['domains'][0]['assignments'][-1]['difficulty'] = 'complex'
        with self.assertRaisesRegex(ValueError, 'project_difficulty_distribution'):
            project.project_preview(self.project, pack, 'owner')

    def test_extra_high_brief_and_approval_preserve_distinct_scope(self):
        from local_model_delegation.contracts import validate_brief
        from local_model_delegation.onboarding import approve_scope
        from local_model_delegation.profiles import scope_matches
        brief = self.brief()
        brief['task_requirements']['complexity'] = 'extra_complex'
        validate_brief(brief)
        profile = self.profile()
        profile['scope'][0]['complexity'] = 'extra_complex'
        self.write_config(profile)
        approve_scope(self.state, profile['profile_id'], 'owner', profile['scope'])
        self.assertTrue(scope_matches(profile, brief))
        brief['task_requirements']['complexity'] = 'complex'
        self.assertFalse(scope_matches(profile, brief))

    def test_weight_claim_needs_confirmed_complete_denominator(self):
        pack = self.pack()
        pack['domains'][0]['weight'] = .2
        with self.assertRaisesRegex(ValueError, 'invalid_project_workload'):
            project.project_preview(self.project, pack, 'owner')
        pack['workload'] = {'owner_reference': 'owner-mix', 'basis': 'Usual recurring task count',
                            'unassessed_weight': .8}
        result = project.project_preview(self.project, pack, 'owner')
        self.assertEqual(result['unassessed_workload_share'], .8)
        self.assertIsNone(result['workload_coverage'])
        pack['workload']['unassessed_weight'] = .5
        with self.assertRaisesRegex(ValueError, 'invalid_project_workload'):
            project.project_preview(self.project, pack, 'owner')

    def test_unknown_fields_and_nonfinite_values_rejected(self):
        for mutate in (lambda p: p.update(ignored=True),
                       lambda p: p['domains'][0].update(weight=float('nan')),
                       lambda p: p['domains'][0].update(role='ArbitraryRole')):
            pack = self.pack()
            mutate(pack)
            with self.assertRaises(ValueError):
                project.project_preview(self.project, pack, 'owner')

    def test_cli_project_preview_without_state(self):
        from local_model_delegation.cli import main
        path = self.root / 'pack.json'
        path.write_text(json.dumps(self.pack()))
        out = io.StringIO()
        with redirect_stdout(out):
            result = main(['--state-dir', str(self.state), 'assessment', 'project-preview',
                           '--project', str(self.project), '--selection', str(path), '--owner-reference', 'owner'])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(out.getvalue())['assignment_count'], 8)
        self.assertFalse(self.state.exists())
