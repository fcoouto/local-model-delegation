"""Private observational ledger. Never dispatches work or changes routing policy."""
from contextlib import contextmanager
import math
import os
from pathlib import Path
import re
import sqlite3
import stat
import time
from urllib.parse import quote
import uuid
from .contracts import canonical, digest, load_json, MAX_ANSWER_BYTES


def require(condition, reason='invalid_measurement_receipt'):
    if not condition:
        raise ValueError(reason)


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}', value) is not None


def sha(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def fields(value, names, optional=()):
    require(isinstance(value, dict) and set(names) <= set(value) <= set(names) | set(optional))


@contextmanager
def connection(state_dir, *, write=False, initialize=False):
    root = Path(state_dir).absolute()
    path = root/'state.sqlite3'
    if not path.exists():
        raise ValueError('measurement_state_missing')
    for p in [root, *root.parents, path, Path(str(path)+'-wal'), Path(str(path)+'-shm')]:
        if p.is_symlink():
            raise ValueError('unsafe_measurement_state')
        if p.exists() and (p == root or p.parent == root):
            s = p.stat()
            require(s.st_uid == os.getuid() and not s.st_mode & 0o077, 'unsafe_measurement_state')
            require(stat.S_ISDIR(s.st_mode) if p == root else stat.S_ISREG(s.st_mode), 'unsafe_measurement_state')
    db = sqlite3.connect('file:'+quote(str(path))+'?mode='+('rw' if write else 'ro'), uri=True,
                         timeout=.25, isolation_level=None)
    db.row_factory = sqlite3.Row
    try:
        db.execute('PRAGMA foreign_keys=ON')
        if write: db.execute('BEGIN IMMEDIATE')
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='measurement_meta'").fetchone()
        if exists:
            versions = [r[0] for r in db.execute('SELECT version FROM measurement_meta')]
            require(versions == [1], 'unsupported_measurement_version')
        elif not initialize:
            raise ValueError('measurements_not_initialized')
        yield db
        if write: db.commit()
    except BaseException:
        if write: db.rollback()
        raise
    finally:
        db.close()


def initialize_measurements(state_dir: Path) -> dict:
    with connection(state_dir, write=True, initialize=True) as db:
        statements = [
            'CREATE TABLE IF NOT EXISTS measurement_meta (version INTEGER PRIMARY KEY)',
            'INSERT OR IGNORE INTO measurement_meta VALUES (1)',
            '''CREATE TABLE IF NOT EXISTS measurement_projects
               (project_id TEXT PRIMARY KEY, kind TEXT NOT NULL, identity TEXT NOT NULL UNIQUE, label TEXT NOT NULL)''',
            '''CREATE TABLE IF NOT EXISTS measurement_tasks
               (task_id TEXT PRIMARY KEY, job_id TEXT UNIQUE REFERENCES jobs(job_id),
                project_id TEXT NOT NULL REFERENCES measurement_projects(project_id), context TEXT NOT NULL)''',
            '''CREATE TABLE IF NOT EXISTS measurement_events
               (event_id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES measurement_tasks(task_id),
                producer TEXT NOT NULL, source_key TEXT NOT NULL, kind TEXT NOT NULL, observed_at REAL NOT NULL,
                receipt TEXT NOT NULL, supersedes TEXT UNIQUE REFERENCES measurement_events(event_id),
                UNIQUE(producer,source_key))''',
            '''CREATE TABLE IF NOT EXISTS measurement_comparisons
               (comparison_id TEXT PRIMARY KEY, manifest TEXT NOT NULL, consent_reference TEXT NOT NULL UNIQUE)''',
        ]
        for statement in statements: db.execute(statement)
    return {'measurement_version': 1}


def register_project(state_dir: Path, root: Path, label: str) -> dict:
    from .projects import resolve_project_identity
    require(isinstance(label, str) and 0 < len(label) <= 128 and label.isprintable(), 'invalid_project_label')
    identity = resolve_project_identity(root)
    with connection(state_dir, write=True) as db:
        row = db.execute('SELECT * FROM measurement_projects WHERE identity=?', (identity['identity'],)).fetchone()
        if row is None:
            db.execute('INSERT INTO measurement_projects VALUES (?,?,?,?)',
                       (uuid.uuid4().hex, identity['kind'], identity['identity'], label))
            row = db.execute('SELECT * FROM measurement_projects WHERE identity=?', (identity['identity'],)).fetchone()
    return {k: row[k] for k in ('project_id', 'kind', 'label')}


def validate_context(context):
    try:
        fields(context, {'project_id','origin','scope','environment_digest','environment_manifest',
                         'native_binding','source_revision','case_id','case_hash'})
        require(identifier(context['project_id']) and identifier(context['case_id']) and sha(context['case_hash']))
        require(context['origin'] in ('normal_work','synthetic_assessment','authorized_comparison','legacy_unscoped'))
        scope = context['scope']
        fields(scope, {'capability','language','complexity','context_bucket','input_bytes','file_count'})
        require(all(identifier(scope[k]) for k in ('capability','language','complexity','context_bucket')))
        require(all(type(scope[k]) is int and scope[k] >= 0 for k in ('input_bytes','file_count')))
        require(context['source_revision'] is None or identifier(context['source_revision']))
        environment = context['environment_manifest']
        require((environment is None and context['environment_digest'] is None) or
                (isinstance(environment, dict) and digest(environment) == context['environment_digest']))
        if context['native_binding'] is not None: validate_native(context['native_binding'])
        require(len(canonical(context).encode()) <= MAX_ANSWER_BYTES)
    except (ValueError, TypeError, KeyError) as error:
        raise ValueError('invalid_measurement_context') from error
    return context


def validate_native(binding):
    fields(binding, {'host','provider','model','reasoning','boundary'})
    require(all(identifier(v) for v in binding.values()))


def _begin(db, task_id, context, job_id=None):
    require(identifier(task_id), 'invalid_measurement_task')
    validate_context(context)
    require(db.execute('SELECT 1 FROM measurement_projects WHERE project_id=?', (context['project_id'],)).fetchone(), 'unknown_project')
    previous = db.execute('SELECT * FROM measurement_tasks WHERE task_id=? OR job_id=?', (task_id, job_id)).fetchone()
    if previous:
        require(previous['task_id'] == task_id and previous['job_id'] == job_id and previous['context'] == canonical(context), 'measurement_conflict')
    else:
        if job_id: require(db.execute('SELECT 1 FROM jobs WHERE job_id=?', (job_id,)).fetchone(), 'unknown_job')
        db.execute('INSERT INTO measurement_tasks VALUES (?,?,?,?)', (task_id, job_id, context['project_id'], canonical(context)))
    return {'task_id': task_id, 'project_id': context['project_id'], 'job_id': job_id}


def begin_measurement(state_dir: Path, task_id: str, context: dict, job_id=None) -> dict:
    with connection(state_dir, write=True) as db:
        return _begin(db, task_id, context, job_id)


def _validate_payload(kind, payload):
    if kind == 'delivery':
        fields(payload, {'outcome','artifact_hash','checks_hash','native_task_id','durations'})
        require(payload['outcome'] in ('unchanged_local','native_edited','native_fallback','not_integrated','native_only'))
        require(sha(payload['artifact_hash']) and sha(payload['checks_hash']))
        require(payload['native_task_id'] is None or isinstance(payload['native_task_id'], str) and 0 < len(payload['native_task_id']) <= 160)
        fields(payload['durations'], set(), {'queue','inference','verification','integration','fallback','overall'})
        require(all(v is None or number(v) for v in payload['durations'].values()))
    elif kind == 'incident':
        fields(payload, {'delivery_event','evidence_hash','disposition'})
        require(identifier(payload['delivery_event']) and sha(payload['evidence_hash']))
        require(payload['disposition'] in ('confirmed','withdrawn'))
    else:
        raise ValueError('unsupported_measurement_kind')


def _append(db, task_id, receipt):
    fields(receipt, {'schema_version','producer','source_key','kind','observed_at','payload'}, {'supersedes'})
    require(type(receipt['schema_version']) is int and receipt['schema_version'] == 1)
    require(identifier(receipt['producer']) and identifier(receipt['source_key']) and number(receipt['observed_at']))
    require(len(canonical(receipt).encode()) <= MAX_ANSWER_BYTES)
    _validate_payload(receipt['kind'], receipt['payload'])
    task = db.execute('SELECT * FROM measurement_tasks WHERE task_id=?', (task_id,)).fetchone()
    require(task is not None, 'unknown_measurement_task')
    previous = db.execute('SELECT * FROM measurement_events WHERE producer=? AND source_key=?',
                          (receipt['producer'],receipt['source_key'])).fetchone()
    if previous:
        require(previous['task_id'] == task_id and previous['receipt'] == canonical(receipt), 'measurement_conflict')
        return {'event_id': previous['event_id']}
    supersedes = receipt.get('supersedes')
    if supersedes:
        prior = db.execute('SELECT * FROM measurement_events WHERE event_id=?', (supersedes,)).fetchone()
        require(prior and prior['task_id'] == task_id and prior['kind'] == receipt['kind'], 'invalid_measurement_correction')
        require(not db.execute('SELECT 1 FROM measurement_events WHERE supersedes=?', (supersedes,)).fetchone(), 'measurement_conflict')
    if receipt['kind'] == 'incident':
        require(db.execute("SELECT 1 FROM measurement_events WHERE event_id=? AND task_id=? AND kind='delivery'",
                           (receipt['payload']['delivery_event'],task_id)).fetchone(), 'invalid_incident')
    event_id = uuid.uuid4().hex
    db.execute('INSERT INTO measurement_events VALUES (?,?,?,?,?,?,?,?)',
               (event_id,task_id,receipt['producer'],receipt['source_key'],receipt['kind'],receipt['observed_at'],canonical(receipt),supersedes))
    return {'event_id': event_id}


def append_event(state_dir: Path, task_id: str, receipt: dict) -> dict:
    with connection(state_dir, write=True) as db:
        return _append(db, task_id, receipt)
