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


class AssessmentProjects(Fixture):
    def discover(self, root=None, selected=None, owner='owner inspection permission'):
        from local_model_delegation import projects
        self.assertTrue(hasattr(projects, 'assessment_projects'), 'assessment project selection is missing')
        return projects.assessment_projects(root or self.project, owner, selected)

    def git(self, *args):
        subprocess.run(['git', *map(str, args)], check=True, capture_output=True)

    def repo(self, name):
        root = self.project / name
        self.git('init', root)
        return root

    def test_umbrella_requires_selection_and_selects_multiple_independent_roots(self):
        first, second = self.repo('backend'), self.repo('frontend')
        found = self.discover()
        self.assertEqual(found['kind'], 'umbrella')
        self.assertTrue(found['selection_required'])
        self.assertEqual(found['selected'], [])
        self.assertEqual([p['root'] for p in found['candidates']], [str(first), str(second)])
        selected = self.discover(selected=['backend', str(second)])
        self.assertFalse(selected['selection_required'])
        self.assertEqual(selected['selected'], selected['candidates'])
        self.assertNotEqual(*[p['project'] for p in selected['selected']])
        self.assertFalse(self.state.exists())

    def test_git_subdirectory_resolves_to_owning_root_without_enrolling_children(self):
        repo = self.repo('backend')
        nested = repo / 'source'; nested.mkdir()
        self.git('init', repo / 'independent')
        result = self.discover(nested)
        self.assertEqual(result['kind'], 'git')
        self.assertEqual([p['root'] for p in result['selected']], [str(repo)])
        self.assertEqual(result['selected'], result['candidates'])

    def test_non_git_directory_is_preserved_and_scan_is_not_recursive(self):
        nested = self.project/'group'/'repo'
        self.git('init', nested)
        result = self.discover()
        self.assertEqual(result['kind'], 'directory')
        self.assertEqual(result['selected'][0]['project']['kind'], 'directory')
        self.assertEqual(self.discover(self.project/'group')['kind'], 'umbrella')

    def test_even_one_child_repository_needs_explicit_selection(self):
        self.repo('backend')
        self.assertTrue(self.discover()['selection_required'])
        self.assertEqual(len(self.discover(selected=['backend'])['selected']), 1)

    def test_rejects_outside_alias_duplicate_and_non_repository_selections(self):
        repo = self.repo('backend')
        outside = self.root/'outside'; self.git('init', outside)
        alias = self.project/'alias'; alias.symlink_to(outside, target_is_directory=True)
        local_alias = self.project/'local-alias'; local_alias.symlink_to(repo, target_is_directory=True)
        ordinary = self.project/'notes'; ordinary.mkdir()
        child = repo/'source'; child.mkdir()
        for selection in ([str(outside)], ['alias'], ['local-alias'], ['notes'], ['backend/source'],
                          ['backend', str(repo)], ['backend/../backend'], [], 'backend'):
            with self.subTest(selection=selection):
                with self.assertRaisesRegex(ValueError, 'invalid_repository_selection'):
                    self.discover(selected=selection)
        self.assertEqual(len(self.discover()['candidates']), 1)
        with self.assertRaisesRegex(ValueError, 'project_permission_required'):
            self.discover(owner=' ')

    def test_worktrees_are_one_project_and_selection_accepts_either_root(self):
        repo = self.repo('backend')
        self.git('-C', repo, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                 'commit', '--allow-empty', '-m', 'fixture')
        tree = self.project/'backend-worktree'
        self.git('-C', repo, 'worktree', 'add', '--detach', tree)
        result = self.discover()
        self.assertEqual(len(result['candidates']), 1)
        selected = self.discover(selected=['backend-worktree'])
        self.assertEqual(selected['selected'][0]['project'], result['candidates'][0]['project'])
        self.assertEqual(selected['selected'][0]['root'], str(tree))
        with self.assertRaisesRegex(ValueError, 'invalid_repository_selection'):
            self.discover(selected=['backend', 'backend-worktree'])

    def test_git_paths_preserve_whitespace_and_exact_root_identity_pairing(self):
        plain = self.repo('plain')
        spaced = self.repo('plain ')
        trailing_newline = self.repo('line\n')
        carriage_return = self.repo('return\r')
        from local_model_delegation.projects import resolve_project_identity
        for repo in (plain, spaced, trailing_newline, carriage_return):
            with self.subTest(repo=repr(str(repo))):
                result = self.discover(repo)
                self.assertEqual(result['selected'], [{'root': str(repo), 'project': resolve_project_identity(repo)}])
                selected = self.discover(selected=[repo.name])
                self.assertEqual(selected['selected'], result['selected'])
        self.assertEqual(len(self.discover()['candidates']), 4)

    def test_selection_rechecks_repository_existence(self):
        repo = self.repo('backend')
        self.discover(selected=['backend'])
        (repo/'.git').rename(repo/'former-git')
        with self.assertRaisesRegex(ValueError, 'invalid_repository_selection'):
            self.discover(selected=['backend'])
