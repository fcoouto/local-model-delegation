"""Owned, network-disabled container checks; never fall back to host execution."""
import os
from contextlib import contextmanager
import fcntl
from pathlib import Path
import re
import selectors
import subprocess
import time
import uuid

from .contracts import canonical, load_json
from .store import atomic_json, private_dir

LABEL = 'local-model-delegation.operation'
IMAGE = re.compile(r'sha256:[a-f0-9]{64}')
IDENTITY = re.compile(r'[a-f0-9]{32}')
MARKER = 'LMD_TEST_RESULT='


def _fields(value, keys):
    if not isinstance(value, dict) or set(value) != set(keys.split()):
        raise ValueError('invalid_container_contract')


def validate_environment(spec):
    _fields(spec, 'schema_version docker_binary endpoint image postgres_image limits')
    if type(spec['schema_version']) is not int or spec['schema_version'] != 1:
        raise ValueError('invalid_container_environment')
    if (not isinstance(spec['docker_binary'], str) or not Path(spec['docker_binary']).is_absolute()
            or not isinstance(spec['endpoint'], str) or not spec['endpoint'].startswith('unix:///')
            or any(c in spec['endpoint'] + spec['docker_binary'] for c in '\0\n\r')):
        raise ValueError('local_docker_required')
    for image in (spec['image'], spec['postgres_image']):
        if image is not None and (not isinstance(image, str) or not IMAGE.fullmatch(image)):
            raise ValueError('immutable_container_image_required')
    if spec['image'] is None:
        raise ValueError('immutable_container_image_required')
    limits = spec['limits']
    _fields(limits, 'memory_bytes cpus pids storage_bytes output_bytes')
    bounds = {'memory_bytes': (64*1024**2, 16*1024**3), 'cpus': (1, 16), 'pids': (16, 1024),
              'storage_bytes': (16*1024**2, 4*1024**3), 'output_bytes': (1024, 4*1024**2)}
    for key, (low, high) in bounds.items():
        if type(limits[key]) is not int or not low <= limits[key] <= high:
            raise ValueError('invalid_container_limit')
    return spec


def _mount(path, target):
    path = Path(path)
    if (not path.is_absolute() or path != path.resolve() or not path.is_dir()
            or any(c in str(path) for c in ',\0\r\n')):
        raise ValueError('invalid_container_mount')
    return f'type=bind,src={path},dst={target},readonly'


def _base(spec, operation, role, user):
    validate_environment(spec)
    if not isinstance(operation, str) or not IDENTITY.fullmatch(operation) or role not in ('candidate', 'postgres', 'setup'):
        raise ValueError('invalid_container_owner')
    limits = spec['limits']
    return ['create', '--name', 'lmd-' + operation + '-' + role, '--label', LABEL + '=' + operation,
            '--pull=never', '--network=none', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges:true', '--log-driver=none', '--user=' + user,
            '--memory=' + str(limits['memory_bytes']), '--memory-swap=' + str(limits['memory_bytes']),
            '--cpus=' + str(limits['cpus']), '--pids-limit=' + str(limits['pids']),
            '--ulimit', 'nofile=1024:1024', '--ulimit', 'core=0:0']


def container_arguments(spec, operation, role, source, assets, argv, *, socket_volume=None, environment=None):
    if role not in ('candidate', 'setup'):
        raise ValueError('invalid_container_command')
    _command(argv)
    args = _base(spec, operation, role, '65534:999')
    storage = spec['limits']['storage_bytes']
    args += ['--workdir=/work', '--tmpfs', f'/work:rw,nosuid,nodev,size={storage},uid=65534,gid=999,mode=0700',
             '--tmpfs', f'/tmp:rw,nosuid,nodev,noexec,size={storage},uid=65534,gid=999,mode=0700',
             '--mount', _mount(source, '/source'), '--mount', _mount(assets, '/evaluator')]
    if socket_volume is not None:
        if socket_volume != 'lmd-' + operation:
            raise ValueError('invalid_container_volume')
        args += ['--mount', f'type=volume,src={socket_volume},dst=/var/run/postgresql,readonly']
    for key, value in (environment or {}).items():
        if key not in {'PGHOST', 'PGPORT', 'PGDATABASE', 'PGUSER', 'PGPASSWORD'} or not isinstance(value, str) or '\0' in value:
            raise ValueError('invalid_container_environment')
        args += ['--env', key + '=' + value]
    return args + ['--entrypoint', argv[0], spec['image'], *argv[1:]]


def _receipt(output, expected):
    try:
        lines = [line[len(MARKER):] for line in output.splitlines() if line.startswith(MARKER)]
        if len(lines) != 1 or not expected or len(set(expected)) != len(expected):
            return None
        result = load_json(lines[0])
        _fields(result, 'tests')
        if not isinstance(result['tests'], dict) or set(result['tests']) != set(expected):
            return None
        if any(value not in ('passed', 'failed', 'error') for value in result['tests'].values()):
            return None
        return result['tests']
    except (ValueError, TypeError):
        return None


def check_receipt(output, expected):
    receipt = _receipt(output, expected)
    return receipt is not None and all(value == 'passed' for value in receipt.values())


class Docker:
    def __init__(self, spec, directory):
        self.spec = validate_environment(spec)
        self.directory = Path(directory)
        self.home = private_dir(self.directory / 'docker-home')

    def call(self, args, *, timeout=30, stdin=None, check=True, output_limit=None):
        """Bound streaming output as well as wall time; killing CLI never proves container exit."""
        if stdin is not None and (not isinstance(stdin,str) or len(stdin.encode()) > 4096):
            raise ValueError('invalid_container_stdin')
        started = time.monotonic()
        limit = output_limit or self.spec['limits']['output_bytes']
        command = [self.spec['docker_binary'], '--host', self.spec['endpoint'], *args]
        with subprocess.Popen(command, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True,
                              env={'PATH': '/usr/bin:/bin', 'HOME': str(self.home), 'DOCKER_CONFIG': str(self.home)}) as child:
            if stdin is not None:
                child.stdin.write(stdin.encode())
                child.stdin.close()
            output = bytearray()
            reason = None
            deadline = time.monotonic() + timeout
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                while selector.get_map():
                    if time.monotonic() >= deadline:
                        reason = 'check_timeout'
                        break
                    for key, _ in selector.select(min(0.2, max(0, deadline - time.monotonic()))):
                        data = os.read(key.fd, 65536)
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        remaining = max(0, limit - len(output))
                        output.extend(data[:remaining])
                        if len(data) > remaining:
                            reason = 'check_output_limit'
                            break
                    if reason:
                        break
            if reason:
                child.kill()
            try:
                returncode = child.wait(timeout=max(1, deadline-time.monotonic()))
            except subprocess.TimeoutExpired:
                child.kill(); child.wait()
                returncode, reason = child.returncode, 'check_timeout'
        result = {'returncode': returncode, 'reason': reason, 'stdout': output.decode(errors='replace'),
                  'elapsed_seconds': time.monotonic()-started}
        if check and (returncode or reason):
            raise ValueError(reason or 'container_command_failed')
        return result

    def exists(self, kind, name):
        args = ['container', 'ls', '--all', '--format', '{{.Names}}'] if kind == 'container' else ['volume', 'ls', '--format', '{{.Name}}']
        return name in self.call(args)['stdout'].splitlines()

    def owned(self, kind, name, operation):
        if not self.exists(kind, name):
            return False
        template = '{{json .Config.Labels}}' if kind == 'container' else '{{json .Labels}}'
        labels = load_json(self.call([kind, 'inspect', '--format', template, name])['stdout'])
        if not isinstance(labels, dict) or labels.get(LABEL) != operation:
            raise ValueError('container_ownership_mismatch')
        return True


@contextmanager
def _check_lock(parent):
    fd = os.open(parent / '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('container_checker_busy') from None
        yield
    finally:
        os.close(fd)


def reconcile_operation(operation_path):
    path = Path(operation_path)
    with _check_lock(path.parent.parent):
        return _reconcile_operation(path)


def _reconcile_operation(operation_path):
    path = Path(operation_path)
    record = load_json(path.read_text())
    operation = record['operation']
    if not isinstance(operation, str) or not IDENTITY.fullmatch(operation):
        raise ValueError('invalid_container_owner')
    docker = Docker(record['environment'], path.parent)
    expected = ['lmd-' + operation + '-' + role for role in ('candidate', 'setup', 'postgres')]
    if record['containers'] != expected or record['volume'] not in (None, 'lmd-' + operation):
        raise ValueError('invalid_container_owner')
    try:
        for name in expected:
            if docker.owned('container', name, operation):
                docker.call(['container', 'rm', '--force', name])
            if docker.exists('container', name):
                raise ValueError('container_cleanup_incomplete')
        name = record['volume']
        if name:
            if docker.owned('volume', name, operation):
                docker.call(['volume', 'rm', name])
            if docker.exists('volume', name):
                raise ValueError('container_cleanup_incomplete')
        record['cleanup'] = 'verified_absent'
    except (ValueError, OSError):
        record['cleanup'] = 'pending'
        atomic_json(path, record)
        raise
    atomic_json(path, record)
    return {'operation': operation, 'cleanup': record['cleanup']}


def _copy_inputs(source, destination):
    """Only regular files reach a read-only mount; parent private paths are never mounted."""
    from .repository_context import snapshot
    source = Path(source)
    paths = []
    for path in source.rglob('*'):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise ValueError('invalid_container_input')
        if path.is_file():
            paths.append(path.relative_to(source).as_posix())
    snapshot(source, paths, destination)
    destination.chmod(0o755)
    for path in destination.rglob('*'):
        path.chmod(0o755 if path.is_dir() else 0o444)


def _postgres(docker, operation, volume, admin_password):
    spec = docker.spec
    name = 'lmd-' + operation + '-postgres'
    docker.call(['volume', 'create', '--label', LABEL + '=' + operation, volume])
    args = _base(spec, operation, 'postgres', '999:999')
    args += ['--tmpfs', f'/var/lib/postgresql/data:rw,nosuid,nodev,size={spec["limits"]["storage_bytes"]},uid=999,gid=999,mode=0700',
             '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=16777216,uid=999,gid=999,mode=0700',
             '--mount', f'type=volume,src={volume},dst=/var/run/postgresql',
             '--env', 'POSTGRES_PASSWORD=' + admin_password,
             '--env', 'POSTGRES_INITDB_ARGS=--auth-local=scram-sha-256 --auth-host=scram-sha-256',
             '--entrypoint', '/usr/local/bin/docker-entrypoint.sh', spec['postgres_image'],
             'postgres', '-c', 'listen_addresses=', '-c', 'unix_socket_permissions=0770',
             '-c', 'max_connections=32', '-c', 'shared_buffers=32MB']
    docker.call(args)
    docker.call(['start', name])
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        result = docker.call(['exec', '--env', 'PGPASSWORD=' + admin_password, name,
                              'psql', '-h', '/var/run/postgresql', '-U', 'postgres', '-d', 'postgres',
                              '-XAt', '-c', 'SELECT 1'], check=False, timeout=3)
        if result['returncode'] == 0 and result['stdout'].strip() == '1':
            return name
        time.sleep(0.1)
    raise ValueError('postgres_start_timeout')


def _command(argv):
    if (not isinstance(argv, list) or not 1 <= len(argv) <= 64
            or argv[0] != '/usr/local/bin/python'
            or any(not isinstance(arg, str) or not arg or len(arg) > 4096 or '\0' in arg for arg in argv)):
        raise ValueError('invalid_container_command')


def validate_check(check, environment, setup_root):
    validate_environment(environment)
    _fields(check, 'id argv timeout_seconds expected_tests setup_argv')
    if (not isinstance(check['id'], str) or not re.fullmatch('[A-Za-z0-9_-]+', check['id'])
            or type(check['timeout_seconds']) is not int or not 1 <= check['timeout_seconds'] <= 3600
            or not isinstance(check['expected_tests'], list) or not 1 <= len(check['expected_tests']) <= 10000
            or any(not isinstance(name, str) or not name or len(name) > 1024 for name in check['expected_tests'])
            or len(set(check['expected_tests'])) != len(check['expected_tests'])):
        raise ValueError('invalid_container_check')
    database = environment['postgres_image'] is not None
    if database != (setup_root is not None and check['setup_argv'] is not None):
        raise ValueError('trusted_database_setup_required')
    _command(check['argv'])
    if database:
        _command(check['setup_argv'])
    elif check['setup_argv'] is not None or setup_root is not None:
        raise ValueError('trusted_database_setup_required')
    return check


def run_check(state_dir, source_root, assets_root, check, environment, *, setup_root=None):
    parent = private_dir(Path(state_dir) / 'container-checks')
    with _check_lock(parent):
        return _run_check(parent, source_root, assets_root, check, environment, setup_root=setup_root)


def _run_check(parent, source_root, assets_root, check, environment, *, setup_root=None):
    validate_check(check, environment, setup_root)
    database = environment['postgres_image'] is not None
    for previous in parent.glob('*/operation.json'):
        if load_json(previous.read_text()).get('cleanup') != 'verified_absent':
            raise ValueError('container_cleanup_pending')
    operation = uuid.uuid4().hex
    directory = private_dir(parent / operation)
    source, assets = directory / 'source', directory / 'assets'
    _copy_inputs(Path(source_root), source)
    _copy_inputs(Path(assets_root), assets)
    volume = 'lmd-' + operation if database else None
    path = directory / 'operation.json'
    record = {'operation': operation, 'environment': environment,
              'containers': ['lmd-' + operation + '-' + role for role in ('candidate', 'setup', 'postgres')],
              'volume': volume, 'cleanup': 'pending', 'state': 'preparing'}
    atomic_json(path, record)
    docker = Docker(environment, directory)
    observation = {'returncode': None, 'reason': 'verification_unsupported', 'stdout': '', 'tests': None}
    setup_observation = None
    started = time.monotonic()
    try:
        for image in (environment['image'], environment['postgres_image']):
            if image and docker.call(['image', 'inspect', '--format', '{{.Id}}', image])['stdout'].strip() != image:
                raise ValueError('container_image_changed')
        database_env = {}
        if database:
            admin_password, candidate_password = uuid.uuid4().hex + uuid.uuid4().hex, uuid.uuid4().hex
            server = _postgres(docker, operation, volume, admin_password)
            def sql(statement):
                return docker.call(['exec', '-i', '--env', 'PGPASSWORD=' + admin_password, server,
                                    'psql', '-h', '/var/run/postgresql', '-U', 'postgres', '-d', 'postgres',
                                    '-X', '-v', 'ON_ERROR_STOP=1'], stdin=statement)
            sql("CREATE ROLE assessed LOGIN PASSWORD '" + candidate_password + "' NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;\n"
                "REVOKE CONNECT ON DATABASE postgres FROM PUBLIC;\nREVOKE CONNECT ON DATABASE template1 FROM PUBLIC;\n"
                "CREATE DATABASE assessment;\nREVOKE ALL ON DATABASE assessment FROM PUBLIC;\nGRANT CONNECT ON DATABASE assessment TO assessed;\n")
            database_env = {'PGHOST': '/var/run/postgresql', 'PGPORT': '5432', 'PGDATABASE': 'assessment',
                            'PGUSER': 'assessed', 'PGPASSWORD': candidate_password}
            trusted = directory / 'trusted-source'
            _copy_inputs(Path(setup_root), trusted)
            setup_env = {**database_env, 'PGUSER': 'postgres', 'PGPASSWORD': admin_password}
            docker.call(container_arguments(environment, operation, 'setup', trusted, assets, check['setup_argv'],
                                            socket_volume=volume, environment=setup_env))
            setup_observation = docker.call(['start', '--attach', 'lmd-' + operation + '-setup'],
                                            timeout=check['timeout_seconds'],check=False)
            if setup_observation['reason'] is not None:
                raise ValueError(setup_observation['reason'])
            setup_state = load_json(docker.call(['inspect', '--format', '{{json .State}}',
                                               'lmd-' + operation + '-setup'])['stdout'])
            if (setup_state['Running'] or setup_state.get('OOMKilled') or setup_state.get('Error')
                    or setup_state['ExitCode'] != 0):
                raise ValueError('trusted_database_setup_failed')
            sql("\\connect assessment\nREVOKE CREATE ON SCHEMA public FROM PUBLIC;\nGRANT USAGE ON SCHEMA public TO assessed;\n"
                "GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public TO assessed;\n"
                "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO assessed;\n")
        docker.call(container_arguments(environment, operation, 'candidate', source, assets, check['argv'],
                                        socket_volume=volume, environment=database_env))
        record['state'] = 'running'
        atomic_json(path, record)
        observation = docker.call(['start', '--attach', 'lmd-' + operation + '-candidate'],
                                  timeout=check['timeout_seconds'], check=False)
        if observation['reason'] is None:
            state = load_json(docker.call(['inspect', '--format', '{{json .State}}',
                                          'lmd-' + operation + '-candidate'])['stdout'])
            if state['Running'] or state.get('OOMKilled') or state.get('Error'):
                observation['reason'] = 'container_execution_incomplete'
            else:
                observation['returncode'] = state['ExitCode']
        tests = _receipt(observation['stdout'], check['expected_tests'])
        observation['tests'] = tests
        if tests is None and observation['reason'] is None:
            observation['reason'] = 'check_discovery_incomplete'
        if tests is not None and any(value != 'passed' for value in tests.values()) and observation['returncode'] == 0:
            observation['returncode'] = 1
    except (ValueError, OSError) as error:
        observation['reason'] = str(error) if isinstance(error, ValueError) else 'container_io_error'
    finally:
        try:
            cleanup = _reconcile_operation(path)
        except (ValueError, OSError):
            observation['reason'] = 'container_cleanup_pending'
            cleanup = {'cleanup': 'pending'}
        observation['cleanup'] = cleanup['cleanup']
        observation['operation'] = operation
        observation['setup'] = setup_observation
        observation['total_elapsed_seconds'] = time.monotonic()-started
        atomic_json(directory / 'observation.json', observation)
    return observation
