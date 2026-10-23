import copy
import subprocess
from pathlib import Path

from tests.support import Fixture
from local_model_delegation.profiles import scope_matches, read_profile_by_id, authorize_job
from local_model_delegation.onboarding import approve_scope
from local_model_delegation.projects import resolve_project_identity


class ProjectApprovals(Fixture):
    def test_project_scope_rejects_other_projects_and_role_labels(self):
        profile = self.profile()
        profile['scope'][0]['project'] = resolve_project_identity(self.project)
        brief = self.brief()
        self.assertTrue(scope_matches(profile, brief))
        other = self.root / 'other' / self.project.name
        other.mkdir(parents=True)
        brief['source_root'] = str(other)
        brief['role'] = 'Builder'
        self.assertFalse(scope_matches(profile, brief))
        profile['scope'][0]['project'] = {'kind': 'git'}
        self.assertFalse(scope_matches(profile, brief))

    def test_git_worktrees_share_project_scope(self):
        subprocess.run(['git', 'init', '-q', str(self.project)], check=True)
        subprocess.run(['git', '-C', str(self.project), '-c', 'user.name=Fixture', '-c',
                        'user.email=fixture@example.invalid', 'commit', '--allow-empty', '-qm', 'fixture'], check=True)
        checkout = self.root / 'linked'
        subprocess.run(['git', '-C', str(self.project), 'worktree', 'add', '-q', '--detach', str(checkout)], check=True)
        profile = self.profile()
        profile['scope'][0]['project'] = resolve_project_identity(self.project)
        brief = self.brief()
        brief['source_root'] = str(checkout)
        self.assertTrue(scope_matches(profile, brief))

    def test_legacy_scope_remains_unchanged_and_is_explicitly_labelled(self):
        profile = self.profile()
        self.write_config(profile)
        result = approve_scope(self.state, 'fictional', 'owner', profile['scope'])
        self.assertEqual(result, {'status': 'approval_recorded', 'routing_enabled': True})
        current = read_profile_by_id(self.state, 'fictional', 'python_code_change')
        self.assertEqual(current['scope'], profile['scope'])
        self.assertTrue(scope_matches(current, self.brief()))

    def test_project_permission_requires_matching_evidence(self):
        profile = self.profile()
        self.write_config(profile)
        before = (self.state / 'profiles/fictional.json').read_bytes()
        with self.assertRaisesRegex(ValueError, 'project_assessment_required'):
            approve_scope(self.state, 'fictional', 'owner', profile['scope'], project_root=self.project)
        self.assertEqual(before, (self.state / 'profiles/fictional.json').read_bytes())

    def test_revoked_project_approval_invalidates_queued_snapshot(self):
        from local_model_delegation.store import Store, atomic_json
        profile = self.profile()
        profile['scope'][0]['project'] = resolve_project_identity(self.project)
        profile['approval']['scope'] = copy.deepcopy(profile['scope'])
        self.write_config(profile)
        store = Store(self.state)
        job = {'brief': self.brief(), 'profile': copy.deepcopy(profile), 'native_task_id': None, 'route_data': {}}
        profile['scope'] = []
        profile['approval']['scope'] = []
        atomic_json(self.state / 'profiles/fictional.json', profile)
        with self.assertRaisesRegex(ValueError, 'approval_changed'):
            authorize_job(store, job)
