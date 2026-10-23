from pathlib import Path
from unittest.mock import patch

from tests.support import Fixture


class AssessmentStorage(Fixture):
    def test_storage_inspection_is_external_stable_and_read_only(self):
        from local_model_delegation.assessment_storage import storage_info, workspace_root
        expected = self.state.with_name('state-assessment-workspaces')
        with patch.dict('os.environ', {'HOME': str(self.state)}):
            self.assertEqual(workspace_root(self.state), expected)
            info = storage_info(self.state)
        self.assertEqual(info['runtimes'], str(expected/'runtimes'))
        self.assertFalse(expected.exists())
        self.assertFalse(self.state.exists())
        self.assertNotEqual(workspace_root(self.root/'other-state'), expected)

    def test_alias_or_overlapping_state_is_rejected_without_writes(self):
        from local_model_delegation.assessment_storage import workspace_root
        link = self.root/'alias'; link.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError): workspace_root(link/'state')
        workspace = self.state.with_name('state-assessment-workspaces')
        workspace.symlink_to(self.project, target_is_directory=True)
        with self.assertRaises(ValueError): workspace_root(self.state)
        workspace.unlink(); workspace.mkdir(mode=0o700)
        for marker in ('config.json', 'state.sqlite3'):
            (workspace/marker).write_text('other state')
            with self.assertRaises(ValueError): workspace_root(self.state)
            (workspace/marker).unlink()
        workspace.chmod(0o755)
        with self.assertRaises(ValueError): workspace_root(self.state)

    def test_private_storage_checks_fail_before_any_sources_are_written(self):
        from local_model_delegation.assessment_storage import workspace_root
        from local_model_delegation.store import private_dir
        root = workspace_root(self.state)
        directory = private_dir(root/'reference-checks')
        self.assertEqual(root.stat().st_mode & 0o777, 0o700)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        directory.rmdir(); directory.symlink_to(self.project, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'unsafe_state'): private_dir(directory)

    def test_reference_checks_create_only_external_temporary_sources(self):
        from local_model_delegation.project_runs import verify_references
        from local_model_delegation.assessment_storage import workspace_root
        execution = {'files': {'helper.py':'base'}, 'private_files': {},
                     'reference_files': {'helper.py':'reference'}, 'public_checks': [],
                     'private_checks': [], 'review_reference':'fictional-review'}
        observed = []
        def checks(root, commands):
            observed.append(root)
            self.assertTrue(root.is_relative_to(workspace_root(self.state)))
            self.assertFalse(root.is_relative_to(self.state))
            return {}
        with patch('local_model_delegation.project_runs._execution', return_value=execution), \
                patch('local_model_delegation.project_runs._checks', side_effect=checks):
            self.assertTrue(verify_references(self.state, {})['verified'])
        self.assertEqual(len(observed), 2)
        self.assertTrue(all(not root.exists() for root in observed))
        self.assertFalse(self.state.exists())
