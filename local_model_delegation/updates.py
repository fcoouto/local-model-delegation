"""Numbered package identities and update evidence; native hosts install packages."""
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid
from .contracts import canonical, digest, load_json, safe_path
from .profiles import read_config, _quiescent
from .store import Store, atomic_json, private_dir

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_DIRECTORIES = ('local_model_delegation', 'skills', 'docs', 'scripts', 'tests', '.agents', '.github')
PACKAGE_FILES = ('plugin.json', 'delegate.py', 'README.md', 'LICENSE', 'CHANGELOG.md')


def _hash_file(path):
    if path.is_symlink() or not path.is_file(): raise ValueError('unsafe_update_file')
    before = path.stat()
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): h.update(block)
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise ValueError('update_file_changed')
    return h.hexdigest()


def package_identity(root=PACKAGE_ROOT):
    root = Path(root)
    if root.is_symlink() or not root.is_dir() or root != root.resolve(): raise ValueError('unsafe_package_root')
    manifest = load_json(safe_path(root, 'plugin.json').read_text())
    if manifest.get('name') != 'local-model-delegation': raise ValueError('wrong_plugin')
    version = manifest.get('version')
    if not isinstance(version, str) or not re.fullmatch(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)', version):
        raise ValueError('invalid_release_version')
    paths = [safe_path(root, name) for name in PACKAGE_FILES if (root / name).exists()]
    for name in PACKAGE_DIRECTORIES:
        directory = safe_path(root, name)
        if directory.exists():
            for path in directory.rglob('*'):
                if path.is_symlink(): raise ValueError('unsafe_update_file')
                if path.is_file() and '__pycache__' not in path.parts and path.name != '.DS_Store': paths.append(path)
    if not (root / 'delegate.py').is_file(): raise ValueError('incomplete_package')
    files = {str(p.relative_to(root)): _hash_file(p) for p in sorted(paths)}
    return {'name': manifest['name'], 'version': version, 'package_digest': digest(files)}


def check_release(root, tag):
    identity = package_identity(root)
    if tag != 'v' + identity['version']: raise ValueError('release_tag_mismatch')
    return identity


def _files(root):
    result = {}
    for path in root.rglob('*'):
        relative = path.relative_to(root)
        if relative.parts[0] in ('updates', 'locks', 'state.sqlite3', 'state.sqlite3-wal', 'state.sqlite3-shm'): continue
        if '__pycache__' in relative.parts: continue
        if path.is_symlink(): raise ValueError('unsafe_update_file')
        if path.is_file(): result[str(relative)] = _hash_file(path)
    return result


def _database(db):
    tables = {}
    for name, sql in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        quoted = '"' + name.replace('"', '""') + '"'
        rows = [[{'blob': v.hex()} if isinstance(v, bytes) else v for v in row] for row in db.execute('SELECT * FROM ' + quoted)]
        tables[name] = {'schema': sql, 'rows': len(rows), 'digest': digest(sorted(rows, key=canonical))}
    objects = {name: {'type':kind,'table':table,'sql':sql} for kind,name,table,sql in db.execute(
        "SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('index','trigger','view') AND name NOT LIKE 'sqlite_%'")}
    return {'version': db.execute('PRAGMA user_version').fetchone()[0], 'tables': tables, 'objects': objects}


def _settled_assessments(store, db):
    settled = []
    for row in db.execute("SELECT * FROM jobs WHERE status='fallback_required' AND native_task_id IS NULL"):
        job = store._job(row)
        if db.execute('SELECT 1 FROM fallback_dispatches WHERE job_id=?', (job['job_id'],)).fetchone(): continue
        try:
            permit = job['route_data']['assessment']
            identifier = permit['assessment_id']
            if not re.fullmatch('[a-f0-9]{32}', identifier): continue
            path = safe_path(store.root, 'assessments/' + identifier + '/assessment.json')
            assessment = load_json(path.read_text())
            if permit != {'assessment_id': identifier, 'permit_token': assessment['permit_token']}: continue
            matches = [t for t in assessment['trials'] if t['brief_hash'] == digest(job['brief'])]
            if len(matches) != 1: continue
            trial_id = matches[0]['trial_id']; receipt = assessment['receipts'][trial_id]
            if (receipt['job_id'] == job['job_id'] and receipt['trial_id'] == trial_id
                    and receipt['passed'] is False and receipt['status'] == job['status']): settled.append(job['job_id'])
        except (KeyError, TypeError, ValueError, OSError): continue
    return settled


def _disabled(root):
    from .onboarding import require_assessments_paused
    require_assessments_paused(root)
    config = read_config(root)
    if config.get('routing_enabled') is not False or config.get('assessment_policy', {}).get('enabled', False) is not False:
        raise ValueError('admission_must_be_disabled')


def prepare_update(state_dir, target_root=PACKAGE_ROOT, installed_root=PACKAGE_ROOT):
    from .package import pin_runtime_bundle
    from .worker import ownership
    root = Path(state_dir)
    if not (root / 'config.json').is_file() or not (root / 'state.sqlite3').is_file(): raise ValueError('update_state_missing')
    installed, target = package_identity(installed_root), package_identity(target_root)
    numbers = lambda value: tuple(map(int, value['version'].split('.')))
    if numbers(target) < numbers(installed): raise ValueError('release_downgrade')
    if target['version'] == installed['version'] and target != installed: raise ValueError('release_version_reused')
    store = Store(root)
    with ownership(store, 'plugin-update') as owned:
        if not owned: raise ValueError('update_busy')
        _disabled(store.root)
        with store.db() as db:
            settled = _settled_assessments(store, db)
            _quiescent(db, settled, allow_pending_admission=True)
        from .habblaud import quiesce
        quiesce(store.root)
        bundle = pin_runtime_bundle(store.root, Path(installed_root))
        directory = private_dir(store.root / 'updates' / uuid.uuid4().hex)
        backup = private_dir(directory / 'backup')
        files = _files(store.root)
        for name, expected in files.items():
            source = safe_path(store.root, name); destination = backup / name
            private_dir(destination.parent)
            with destination.open('xb') as stream: stream.write(source.read_bytes())
            destination.chmod(0o600)
            if _hash_file(destination) != expected: raise ValueError('state_changed')
        database = backup / 'state.sqlite3'
        fd = os.open(database, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(fd)
        with store.db() as db, sqlite3.connect(database) as destination:
            _quiescent(db, _settled_assessments(store, db), allow_pending_admission=True)
            db.backup(destination)
            snapshot = _database(destination)
        receipt = {'schema_version': 1, 'state_root': str(store.root), 'installed': installed, 'target': target,
                   'prepared_at': time.time(), 'verified_at': None, 'files': files, 'database': snapshot,
                   'settled_assessment_jobs': len(settled), 'runtime_bundle': str(bundle)}
        path = directory / 'receipt.json'; atomic_json(path, receipt)
        _preserved(store, receipt)
    return {'status': 'ready', 'receipt': str(path), 'installed': installed, 'target': target,
            'settled_assessment_jobs': len(settled), 'state_preserved': True, 'routing_enabled': False}


def _preserved(store, receipt):
    for name, expected in receipt['files'].items():
        path = safe_path(store.root, name)
        if not path.is_file() or _hash_file(path) != expected: raise ValueError('state_changed')
    with store.db() as db: current = _database(db)
    before = receipt['database']
    if current['version'] != before['version'] or any(current['tables'].get(k) != v for k, v in before['tables'].items()):
        raise ValueError('state_changed')
    if any(not name.startswith('measurement_') for name in current['tables'].keys() - before['tables'].keys()):
        raise ValueError('state_changed')
    if any(current['objects'].get(k) != v for k,v in before['objects'].items()): raise ValueError('state_changed')
    if any(not current['objects'][name]['table'].startswith('measurement_')
           for name in current['objects'].keys() - before['objects'].keys()): raise ValueError('state_changed')
    _disabled(store.root)


def verify_update(state_dir, receipt_path, installed_root=PACKAGE_ROOT):
    from .worker import ownership
    root = Path(state_dir)
    if not (root / 'config.json').is_file() or not (root / 'state.sqlite3').is_file(): raise ValueError('update_state_missing')
    store = Store(state_dir)
    path = Path(receipt_path)
    if (path.name != 'receipt.json' or path.parent.parent != store.root / 'updates'
            or not re.fullmatch('[a-f0-9]{32}', path.parent.name)):
        raise ValueError('invalid_update_receipt')
    path = safe_path(store.root, str(path.relative_to(store.root)))
    receipt = load_json(path.read_text())
    required = {'schema_version','state_root','installed','target','prepared_at','verified_at','files','database','settled_assessment_jobs','runtime_bundle'}
    if set(receipt) != required or receipt['schema_version'] != 1 or receipt['state_root'] != str(store.root):
        raise ValueError('invalid_update_receipt')
    installed = package_identity(installed_root)
    if installed != receipt['target']: raise ValueError('installed_package_mismatch')
    with ownership(store, 'plugin-update') as owned:
        if not owned: raise ValueError('update_busy')
        _preserved(store, receipt)
        with store.db() as db: _quiescent(db, _settled_assessments(store, db), allow_pending_admission=True)
        if receipt['verified_at'] is None:
            receipt['verified_at'] = time.time(); atomic_json(path, receipt)
    return {'status': 'verified', 'installed': installed, 'state_preserved': True, 'routing_enabled': False,
            'history_counts': {k:v['rows'] for k,v in receipt['database']['tables'].items()},
            'host_reload': 'verify_in_new_chat'}


def build_release(root, tag, output):
    import subprocess
    import tempfile
    import zipfile
    root, output = Path(root), Path(output)
    identity = check_release(root, tag)
    if not output.is_absolute() or output != output.resolve() or output.is_relative_to(root):
        raise ValueError('unsafe_release_output')
    environment = {k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
    def git(*args):
        return subprocess.run(['git','-C',str(root),*args],check=True,capture_output=True,text=True,
                              timeout=30,env=environment).stdout.strip()
    if git('status','--porcelain','--untracked-files=all'): raise ValueError('release_checkout_dirty')
    revision = git('rev-parse','HEAD')
    if git('rev-parse',tag+'^{commit}') != revision: raise ValueError('release_tag_mismatch')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    archive = output / ('local-model-delegation-'+identity['version']+'.zip')
    entries = [name for name in (*PACKAGE_FILES,*PACKAGE_DIRECTORIES) if (root/name).exists()]
    git('archive','--format=zip','--prefix=local-model-delegation/','--output='+str(archive),revision,'--',*entries)
    with tempfile.TemporaryDirectory() as extracted, zipfile.ZipFile(archive) as package:
        package.extractall(extracted)
        if package_identity(Path(extracted).resolve()/'local-model-delegation') != identity:
            raise ValueError('release_archive_mismatch')
    manifest = {**identity,'tag':tag,'source_revision':revision,'archive_file':archive.name,'archive_sha256':_hash_file(archive)}
    (output/'release.json').write_text(canonical(manifest)+'\n')
    return {**manifest,'archive':str(archive)}
