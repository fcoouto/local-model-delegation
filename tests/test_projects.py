import importlib.util
import subprocess
from unittest.mock import patch
from tests.support import Fixture


class Projects(Fixture):
    def api(self):
        self.assertIsNotNone(importlib.util.find_spec('local_model_delegation.projects'), 'project identity is missing')
        from local_model_delegation.projects import resolve_project_identity
        return resolve_project_identity

    def test_worktrees_share_identity_but_clones_and_labels_do_not(self):
        resolve = self.api()
        def git(*args):
            subprocess.run(['git', *map(str, args)], check=True, capture_output=True)
        git('init', self.project)
        git('-C', self.project, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
            'commit', '--allow-empty', '-m', 'fixture')
        tree, clone = self.root/'worktree', self.root/'clone'
        git('-C', self.project, 'worktree', 'add', '--detach', tree)
        git('clone', '--local', self.project, clone)
        self.assertEqual(resolve(self.project), resolve(tree))
        self.assertNotEqual(resolve(self.project), resolve(clone))
        alias = self.root/'alias'; alias.symlink_to(tree)
        self.assertEqual(resolve(alias), resolve(tree))

    def test_non_git_roots_and_git_failure(self):
        resolve = self.api()
        self.assertEqual(resolve(self.project), {'kind':'directory', 'identity':str(self.project)})
        self.assertNotEqual(resolve(self.project), resolve(self.artifact))
        with patch('subprocess.run', side_effect=OSError('unavailable')):
            with self.assertRaisesRegex(ValueError, 'project_discovery_failed'): resolve(self.project)
