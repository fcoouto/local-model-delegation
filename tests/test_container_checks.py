import copy
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch

from local_model_delegation.store import atomic_json
from local_model_delegation.container_checks import reconcile_operation, _check_lock, validate_check

from local_model_delegation.container_checks import validate_environment, container_arguments, check_receipt, Docker


def environment():
    return {'schema_version': 1, 'docker_binary': '/usr/local/bin/docker',
            'endpoint': 'unix:///private/docker.sock', 'image': 'sha256:' + 'a' * 64,
            'postgres_image': 'sha256:' + 'b' * 64,
            'limits': {'memory_bytes': 1024**3, 'cpus': 2, 'pids': 128,
                       'storage_bytes': 512 * 1024**2, 'output_bytes': 1024**2}}


class ContainerBoundaryTests(unittest.TestCase):
    def test_environment_is_closed_and_images_are_immutable(self):
        validate_environment(environment())
        for key, value in [('image', 'python:latest'), ('endpoint', 'tcp://127.0.0.1:2375'),
                           ('docker_binary', 'docker'), ('schema_version', True)]:
            item = environment()
            item[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_environment(item)
        item = environment()
        item['privileged'] = True
        with self.assertRaises(ValueError):
            validate_environment(item)
        for key in item['limits']:
            item = environment()
            item['limits'][key] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_environment(item)

    def test_candidate_arguments_have_no_host_service_or_write_access(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, assets = root/'source', root/'assets'
            source.mkdir(); assets.mkdir()
            args = container_arguments(environment(), 'c' * 32, 'candidate', source, assets,
                                       ['/usr/local/bin/python', '-I', '-B', '/evaluator/run.py'], socket_volume='lmd-'+'c'*32)
        for option in ['--network=none', '--read-only', '--cap-drop=ALL',
                       '--security-opt=no-new-privileges:true', '--pull=never', '--log-driver=none']:
            self.assertIn(option, args)
        self.assertIn('--user=65534:999', args)
        mounts = [args[i+1] for i, value in enumerate(args) if value == '--mount']
        self.assertEqual(len(mounts), 3)
        self.assertTrue(all('readonly' in value for value in mounts))
        self.assertFalse(any('docker.sock' in value for value in mounts))
        self.assertNotIn('--privileged', args)
        self.assertEqual(args[args.index('--entrypoint')+1], '/usr/local/bin/python')
        self.assertEqual(args[-3:], ['-I', '-B', '/evaluator/run.py'])

    def test_receipt_requires_all_discovered_tests_and_no_skips(self):
        valid = 'output\nLMD_TEST_RESULT={"tests":{"a":"passed","b":"passed"}}\n'
        self.assertTrue(check_receipt(valid, ['a','b']))
        for output, expected in [('', ['a']), (valid, ['a']), (valid, []),
                                 (valid.replace('passed','skipped'), ['a','b']),
                                 (valid+valid, ['a','b']),
                                 ('LMD_TEST_RESULT={"tests":{"a":"passed","a":"passed"}}', ['a'])]:
            self.assertFalse(check_receipt(output, expected))

    def test_mount_and_process_inputs_cannot_inject_docker_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for invalid in ['bad,name', 'bad\nname']:
                path = root / invalid
                path.mkdir()
                with self.assertRaises(ValueError):
                    container_arguments(environment(), 'c'*32, 'candidate', path, root,
                                        ['/usr/local/bin/python', '/evaluator/run.py'])
            with self.assertRaises(ValueError):
                container_arguments(environment(), '--privileged', 'candidate', root, root, ['sh'])

    def test_cli_output_and_wait_are_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            cli = root / 'fake-docker'
            cli.write_text('#!' + sys.executable + '\nprint("x" * 100000)\n')
            cli.chmod(0o700)
            spec = environment()
            spec['docker_binary'] = str(cli)
            spec['limits']['output_bytes'] = 1024
            result = Docker(spec, root).call(['unused'], check=False)
            self.assertEqual(result['reason'], 'check_output_limit')
            self.assertEqual(len(result['stdout'].encode()), 1024)
            cli.write_text('#!' + sys.executable + '\nimport time\nprint("x" * 900, flush=True)\ntime.sleep(.05)\nprint("y" * 200, flush=True)\n')
            result = Docker(spec, root).call(['unused'], check=False)
            self.assertEqual(result['reason'], 'check_output_limit')
            cli.write_text('#!' + sys.executable + '\nimport time; time.sleep(10)\n')
            result = Docker(spec, root).call(['unused'], check=False, timeout=0.1)
            self.assertEqual(result['reason'], 'check_timeout')

    def test_check_contract_validates_commands_before_resource_creation(self):
        check = {'id': 'test', 'argv': ['/usr/local/bin/python', '/evaluator/run.py'],
                 'timeout_seconds': 30, 'expected_tests': ['a'], 'setup_argv': None}
        spec = environment(); spec['postgres_image'] = None
        validate_check(check, spec, None)
        for field, value in [('argv', ['sh']), ('expected_tests', []),
                             ('expected_tests', ['a'] * 10001), ('setup_argv', ['sh']),
                             ('timeout_seconds', True)]:
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_check({**check, field: value}, spec, None)

    def test_recovery_never_removes_foreign_resources_or_runs_with_active_owner(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            operation = 'a' * 32
            path = root / operation / 'operation.json'
            path.parent.mkdir(mode=0o700)
            record = {'operation': operation, 'environment': environment(),
                      'containers': ['lmd-' + operation + '-' + role for role in ('candidate','setup','postgres')],
                      'volume': None, 'cleanup': 'pending', 'state': 'running'}
            atomic_json(path, record)
            with _check_lock(root), self.assertRaisesRegex(ValueError, 'container_checker_busy'):
                reconcile_operation(path)
            with patch.object(Docker, 'exists', return_value=True), patch.object(Docker, 'call', return_value={'stdout':'{}'}) as call:
                with self.assertRaisesRegex(ValueError, 'container_ownership_mismatch'):
                    reconcile_operation(path)
                self.assertFalse(any('rm' in args.args[0] for args in call.call_args_list))
            with patch.object(Docker, 'exists', return_value=False):
                self.assertEqual(reconcile_operation(path)['cleanup'], 'verified_absent')
