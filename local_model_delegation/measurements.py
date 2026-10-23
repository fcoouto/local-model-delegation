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
    committed = False
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
        if write:
            db.commit(); committed = True
    except BaseException:
        if write: db.rollback()
        raise
    finally:
        db.close()
    if committed:
        try:
            from .visibility import publish_measurements
            publish_measurements(state_dir)
        except (OSError,ValueError,sqlite3.Error):
            pass  # A read-only export cannot undo a committed measurement.


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
               (comparison_id TEXT PRIMARY KEY, manifest TEXT NOT NULL, consent_reference TEXT NOT NULL UNIQUE, revocation TEXT)''',
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


def _begin(db, task_id, context, job_id=None, *, assessment_project=None):
    require(identifier(task_id), 'invalid_measurement_task')
    validate_context(context)
    project = db.execute('SELECT * FROM measurement_projects WHERE project_id=?', (context['project_id'],)).fetchone()
    require(project is not None, 'unknown_project')
    if job_id:
        from .projects import resolve_project_identity
        job = db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()
        require(job is not None,'unknown_job')
        brief = load_json(job['brief'])
        require((assessment_project or resolve_project_identity(Path(brief['source_root'])))['identity'] == project['identity'], 'measurement_project_mismatch')
        require(brief.get('schema_version') == 2, 'invalid_brief')
        scope = {'capability':brief['capability'], **{k:brief['task_requirements'][k] for k in ('language','complexity','context_bucket')},
                 'input_bytes':len(canonical({'contract':brief['behavior_contract'],'files':brief['files'],'editable_paths':brief['editable_paths']}).encode()),
                 'file_count':len(brief['files'])}
        require(context['scope'] == scope, 'measurement_scope_mismatch')
        route = load_json(dict(job).get('route_data') or '{}')
        require(not route.get('assessment') or context['origin'] == 'synthetic_assessment','measurement_origin_mismatch')
    previous = db.execute('SELECT * FROM measurement_tasks WHERE task_id=? OR job_id=?', (task_id, job_id)).fetchone()
    if previous:
        require(previous['task_id'] == task_id and previous['job_id'] == job_id and previous['context'] == canonical(context), 'measurement_conflict')
    else:
        if job_id: require(db.execute('SELECT 1 FROM jobs WHERE job_id=?', (job_id,)).fetchone(), 'unknown_job')
        db.execute('INSERT INTO measurement_tasks VALUES (?,?,?,?)', (task_id, job_id, context['project_id'], canonical(context)))
    return {'task_id': task_id, 'project_id': context['project_id'], 'job_id': job_id}


def begin_measurement(state_dir: Path, task_id: str, context: dict, job_id=None) -> dict:
    project = None
    if job_id:
        from .store import Store
        job = Store(state_dir, read_only=True).job(job_id)
        permit = job.get('route_data', {}).get('assessment')
        if permit:
            from .onboarding import _assessment
            record = _assessment(state_dir, permit['assessment_id'])
            if record.get('schema_version') == 2:
                require(permit['permit_token'] == record['permit_token'], 'assessment_scope_mismatch')
                trial = next((t for t in record['trials'] if t['brief_hash'] == digest(job['brief'])), None)
                require(trial is not None, 'assessment_scope_mismatch')
                from .project_runs import _task
                _, task = _task(record, trial['case_id'])
                require(context.get('case_id') == task['id'] and context.get('case_hash') == digest(task),
                        'comparison_case_mismatch')
                project = record['preview']['project']
    with connection(state_dir, write=True) as db:
        return _begin(db, task_id, context, job_id, assessment_project=project)


def _validate_payload(kind, payload):
    if kind == 'usage':
        validate_usage(payload)
    elif kind == 'comparison_run':
        require(isinstance(payload,dict) and sha(payload.get('comparison_id')))
    elif kind == 'local_verdict':
        fields(payload, {'attempt_id','candidate_hash','checks_hash','accepted','category'})
        require(identifier(payload['attempt_id']) and sha(payload['candidate_hash']) and sha(payload['checks_hash']))
        require(type(payload['accepted']) is bool and payload['category'] in ('accepted','semantic','format','framework','source_changed','verification'))
    elif kind == 'job_observation':
        fields(payload, {'status','reason','binding','attempts','native_task_id','fallback','queued_at','request_bytes','resource_sample'})
        require(isinstance(payload['attempts'],list) and isinstance(payload['binding'],dict))
    elif kind == 'delivery':
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


def _append(db, task_id, receipt, *, internal=False):
    fields(receipt, {'schema_version','producer','source_key','kind','observed_at','payload'}, {'supersedes'})
    require(type(receipt['schema_version']) is int and receipt['schema_version'] == 1)
    require(identifier(receipt['producer']) and identifier(receipt['source_key']) and number(receipt['observed_at']))
    require(len(canonical(receipt).encode()) <= MAX_ANSWER_BYTES)
    _validate_payload(receipt['kind'], receipt['payload'])
    require(internal or receipt['kind'] not in ('local_verdict','job_observation','comparison_run'), 'helper_observation_required')
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
    if receipt['kind'] == 'delivery' and not supersedes:
        require(not db.execute("SELECT 1 FROM measurement_events WHERE task_id=? AND kind='delivery'",(task_id,)).fetchone(), 'delivery_already_recorded')
    if receipt['kind'] == 'delivery':
        outcome=receipt['payload']['outcome']
        if outcome == 'unchanged_local':
            require(task['job_id'] is not None,'delivery_not_verified')
            job=db.execute('SELECT status,native_task_id FROM jobs WHERE job_id=?',(task['job_id'],)).fetchone()
            verdicts=[load_json(r['receipt'])['payload'] for r in db.execute("SELECT receipt FROM measurement_events WHERE task_id=? AND kind='local_verdict' ORDER BY rowid",(task_id,))]
            require(job['status']=='accepted' and job['native_task_id'] is None and verdicts and verdicts[-1]['accepted'],'delivery_not_verified')
        if outcome == 'native_only': require(task['job_id'] is None,'fallback_is_not_baseline')
    if receipt['kind'] == 'incident':
        require(db.execute("SELECT 1 FROM measurement_events WHERE event_id=? AND task_id=? AND kind='delivery'",
                           (receipt['payload']['delivery_event'],task_id)).fetchone(), 'invalid_incident')
    if receipt['kind'] == 'usage':
        payload = receipt['payload']
        require(load_json(task['context'])['native_binding'] == payload['native_binding'], 'usage_binding_mismatch')
        if supersedes:
            previous_payload=load_json(prior['receipt'])['payload']
            require(all(previous_payload[k]==payload[k] for k in ('source_run_id','span_id','native_binding')), 'usage_span_conflict')
            require(prior['producer']==receipt['producer'],'usage_span_conflict')
        for row in db.execute("SELECT event_id,task_id,receipt FROM measurement_events e WHERE kind='usage' AND NOT EXISTS (SELECT 1 FROM measurement_events newer WHERE newer.supersedes=e.event_id)"):
            other = load_json(row['receipt'])
            if (other['producer'],other['payload']['source_run_id'],other['payload']['span_id']) == (receipt['producer'],payload['source_run_id'],payload['span_id']):
                require(supersedes == row['event_id'] and row['task_id'] == task_id, 'usage_span_conflict')
        for target in payload['allocations'] or {}:
            require(db.execute('SELECT 1 FROM measurement_tasks WHERE task_id=?',(target,)).fetchone(), 'unknown_allocation_task')
    event_id = uuid.uuid4().hex
    db.execute('INSERT INTO measurement_events VALUES (?,?,?,?,?,?,?,?)',
               (event_id,task_id,receipt['producer'],receipt['source_key'],receipt['kind'],receipt['observed_at'],canonical(receipt),supersedes))
    return {'event_id': event_id}


def append_event(state_dir: Path, task_id: str, receipt: dict) -> dict:
    with connection(state_dir, write=True) as db:
        return _append(db, task_id, receipt)


def validate_usage(payload):
    fields(payload, {'native_binding','source_run_id','span_id','start','end','phase','usage_schema','tokens',
                     'complete','attribution','evidence_hash','group_id','role','expected_spans','overhead_complete','allocations'})
    validate_native(payload['native_binding'])
    require(all(identifier(payload[k]) for k in ('source_run_id','span_id','group_id','usage_schema')))
    require(payload['start'] is None or number(payload['start']))
    require(payload['end'] is None or number(payload['end']))
    require(payload['phase'] in ('whole_task','briefing','coordination','verification','rewriting','integration','fallback','measurement','onboarding','assessment','comparison'))
    require(payload['attribution'] in ('exclusive','shared','unknown') and sha(payload['evidence_hash']))
    require(type(payload['complete']) is bool and type(payload['overhead_complete']) is bool)
    require(payload['role'] in ('total','component') and type(payload['expected_spans']) is int and 1 <= payload['expected_spans'] <= 10000)
    fields(payload['tokens'], {'input','output','cached_input','reasoning_output'})
    require(all(v is None or type(v) is int and v >= 0 for v in payload['tokens'].values()))
    for subset,parent in (('cached_input','input'),('reasoning_output','output')):
        a,b=payload['tokens'][subset],payload['tokens'][parent]
        require(a is None or b is None or a <= b)
    allocations=payload['allocations']
    if allocations is not None:
        require(payload['phase'] in ('onboarding','assessment','comparison') and payload['role']=='total')
        require(isinstance(allocations,dict) and all(identifier(k) and number(v) and v <= 1 for k,v in allocations.items()))
        require(sum(allocations.values()) <= 1)


def record_usage(state_dir: Path, task_id: str, receipt: dict) -> dict:
    require(receipt.get('kind') == 'usage')
    return append_event(state_dir,task_id,receipt)


def read_report(state_dir: Path, *, project_id: str, profile_id=None) -> dict:
    require(identifier(project_id),'invalid_project_id')
    try:
        with connection(state_dir) as db:
            rows = read_measurement_rows(db)
    except ValueError as error:
        if str(error) not in ('measurement_state_missing','measurements_not_initialized'): raise
        return {'schema_version':1,'project_id':project_id,'cohorts':[], 'measurement_status':str(error),
                'control':'read_only_recommendations'}
    return build_report(rows,project_id=project_id,profile_id=profile_id,now=time.time())


def read_measurement_rows(db):
    rows={'projects':[dict(r) for r in db.execute('SELECT project_id,label FROM measurement_projects')],
          'tasks':[], 'events':[], 'pairs':[]}
    for r in db.execute('SELECT * FROM measurement_tasks'):
        task=dict(r);task['context']=load_json(task['context'])
        task['observation']=job_observation(db,task['job_id']) if task['job_id'] else {}
        rows['tasks'].append(task)
    for r in db.execute('SELECT * FROM measurement_events ORDER BY rowid'):
        rows['events'].append({**load_json(r['receipt']),'event_id':r['event_id'],'task_id':r['task_id']})
    from .measurement_comparisons import comparison_status
    rows['comparisons']=[]
    for r in db.execute('SELECT * FROM measurement_comparisons'):
        summary=comparison_status(db,r['comparison_id'])
        rows['comparisons'].append(summary);rows['pairs'].extend(summary['pairs'])
    return rows


def build_report(rows: dict, *, project_id: str, profile_id=None, now: float) -> dict:
    from .measurement_reports import build_report as build
    return build(rows,project_id=project_id,profile_id=profile_id,now=now)


def register_comparison(state_dir, manifest):
    from .measurement_comparisons import register_comparison as register
    return register(state_dir,manifest)


def record_comparison_run(state_dir, comparison_id, receipt):
    from .measurement_comparisons import record_comparison_run as record
    return record(state_dir,comparison_id,receipt)


def revoke_comparison(state_dir, comparison_id, revoked_at, evidence_hash):
    from .measurement_comparisons import revoke_comparison as revoke
    return revoke(state_dir,comparison_id,revoked_at,evidence_hash)


def render_text_report(report):
    if not report['cohorts']:
        return 'No measured tasks. '+report.get('measurement_status','No project evidence recorded.')
    lines=[]
    for cohort in report['cohorts']:
        quality=cohort['quality'];saving=cohort['savings'];scope=cohort['scope']
        lines.append(f"{cohort['model_binding'].get('profile_id','Unassigned')} / {scope['language']} {scope['capability']} / {cohort['origin']}")
        rate=quality['first_candidate']
        lines.append(f"First candidates: {rate['passed']}/{rate['evaluated']} accepted; {cohort['coverage']['missing_verdicts']} missing verdicts")
        lines.append('Delivery: '+', '.join(f'{k}={v}' for k,v in quality['deliveries'].items()))
        value=saving['net_native_token_proxy']
        lines.append('Native token proxy: '+(str(value) if value is not None else 'unknown — '+', '.join(saving['unknown_reasons'])))
        lines.append(f"Overall median: {cohort['latency']['overall']['median']} seconds; samples={cohort['latency']['overall']['samples']}")
        lines.append(f"Evidence: {cohort['coverage']['tasks']} tasks, {cohort['coverage']['distinct_cases']} distinct cases; {cohort['recommendation']}")
    return '\n'.join(lines)+'\nAccount savings remain unknown. Recommendations do not grant approval.'


def bind_enqueued(db, job_id, context):
    if context is None: return
    # Missing optional collection cannot block existing authorization. Reports show the gap.
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='measurement_meta'").fetchone(): return
    require([r[0] for r in db.execute('SELECT version FROM measurement_meta')] == [1], 'unsupported_measurement_version')
    _begin(db, job_id, context, job_id)


def model_binding(profile, *, executed=False, request_settings=None, runtime_identity=None):
    if not profile: return {}
    identity = runtime_identity or (profile.get('approval') or {}).get('model_identity')
    return {'profile_id':profile['profile_id'], 'artifact_digest':profile['artifact']['digest'],
            'runtime_digest':digest(identity) if identity is not None else None,
            'settings_digest':digest(profile['request_settings'] if request_settings is None else request_settings), 'helper_digest':helper_digest() if executed else None}


def helper_digest():
    from .contracts import text_hash
    root = Path(__file__).parent
    return digest({p.name:text_hash(p.read_text()) for p in sorted(root.glob('*.py'))})


def job_observation(db, job_id):
    row = db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone()
    require(row is not None,'unknown_job')
    job = dict(row); profile = load_json(job['profile']); route = load_json(job.get('route_data') or '{}')
    attempts = []
    for a in db.execute('SELECT * FROM attempts WHERE job_id=? ORDER BY rowid',(job_id,)):
        data = load_json(a['data'])
        attempts.append({'attempt_id':a['attempt_id'],'state':a['state'],
                         **{k:data.get(k) for k in ('submitted_at','finished_at','inference_seconds')},
                         **{k:data[k] for k in ('request_settings','terminal') if k in data}})
    return {'status':job['status'],'reason':job['reason'],'binding':route.get('measurement_binding',model_binding(profile)),
            'attempts':attempts,'native_task_id':job['native_task_id'],
            'fallback': bool(route.get('local_failure') or job['native_task_id'] or job['status'].startswith(('fallback','dispatch'))),
            'queued_at':job.get('queued_at'),'request_bytes':route.get('request_bytes'),
            'resource_sample':route.get('measurement_resource_sample')}


def capture_job_observation(state_dir: Path, job_id: str) -> dict:
    with connection(state_dir, write=True) as db:
        task = db.execute('SELECT task_id FROM measurement_tasks WHERE job_id=?',(job_id,)).fetchone()
        if not task: return {'status':'unscoped'}
        payload = job_observation(db,job_id)
        key = job_id+':'+digest(payload)
        previous = db.execute("SELECT event_id FROM measurement_events WHERE producer='helper' AND source_key=?",(key,)).fetchone()
        if previous: return {'event_id':previous['event_id']}
        return _append(db, task['task_id'], {'schema_version':1,'producer':'helper','source_key':key,
                       'kind':'job_observation','observed_at':time.time(),'payload':payload}, internal=True)


def record_local_verdict(state_dir: Path, job_id: str, evidence: dict) -> dict:
    from .store import atomic_json
    from .contracts import text_hash
    with connection(state_dir) as db:
        task = db.execute('SELECT task_id FROM measurement_tasks WHERE job_id=?',(job_id,)).fetchone()
        if not task: return {'status':'unscoped'}
        job = dict(db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone())
        if job['native_task_id'] or not job['attempt_id']: return {'status':'not_local'}
        require(job['status'] in ('checking','candidate_ready'), 'verdict_not_current')
        path = Path(job['result_path'])
        require(not path.is_symlink() and path.resolve().is_relative_to(Path(state_dir).resolve()/'jobs'/job_id), 'unsafe_result')
        candidate = load_json(path.read_text())
        require(text_hash(candidate['text']) == candidate['sha256'], 'candidate_hash_mismatch')
        if evidence['accepted']:
            attempt = db.execute('SELECT state FROM attempts WHERE attempt_id=?',(job['attempt_id'],)).fetchone()
            require(attempt['state'] == 'complete','attempt_not_complete')
    payload = {'attempt_id':job['attempt_id'],'candidate_hash':candidate['sha256'], 'checks_hash':digest(evidence['checks']),
               'accepted':evidence['accepted'],'category':evidence['category']}
    receipt = {'schema_version':1,'producer':'helper','source_key':job_id+':verdict:'+digest(payload),
               'kind':'local_verdict','observed_at':time.time(),'payload':payload}
    archive = Path(state_dir)/'jobs'/job_id/'measurement-checks'/(digest(payload)+'.json')
    if archive.exists():
        saved = load_json(archive.read_text()); require(saved['checks'] == evidence['checks'],'measurement_conflict')
        receipt = saved['receipt']
    else:
        atomic_json(archive, {'receipt':receipt, 'checks':evidence['checks'], 'brief_hash':job['brief_hash']})
    with connection(state_dir,write=True) as db:
        return _append(db,task['task_id'],receipt,internal=True)


def collect_verdict(state_dir, job_id, checks, accepted, category='verification'):
    try:
        record_local_verdict(state_dir,job_id,{'checks':checks,'accepted':accepted,'category':'accepted' if accepted else category})
    except (OSError,ValueError,sqlite3.Error,KeyError,TypeError):
        pass  # Missing bound verdict is reported as a coverage gap, never a success.


def reconcile_measurements(state_dir: Path) -> dict:
    with connection(state_dir) as db:
        tasks = [dict(r) for r in db.execute('SELECT * FROM measurement_tasks WHERE job_id IS NOT NULL')]
    conflicts = []
    for task in tasks:
        try:
            capture_job_observation(state_dir,task['job_id'])
            root = Path(state_dir)/'jobs'/task['job_id']/'measurement-checks'
            require(not root.is_symlink(),'unsafe_measurement_archive')
            for path in sorted(root.glob('*.json')):
                require(not path.is_symlink(),'unsafe_measurement_archive')
                saved = load_json(path.read_text()); receipt = saved['receipt']; payload = receipt['payload']
                require(path.stem == digest(payload) and payload['checks_hash'] == digest(saved['checks']), 'invalid_measurement_archive')
                with connection(state_dir,write=True) as db:
                    job = db.execute('SELECT brief_hash FROM jobs WHERE job_id=?',(task['job_id'],)).fetchone()
                    require(job['brief_hash'] == saved['brief_hash'], 'invalid_measurement_archive')
                    require(db.execute('SELECT 1 FROM attempts WHERE job_id=? AND attempt_id=?',
                                       (task['job_id'],payload['attempt_id'])).fetchone(), 'invalid_measurement_archive')
                    _append(db,task['task_id'],receipt,internal=True)
        except (OSError,ValueError,sqlite3.Error,KeyError,TypeError) as error:
            conflicts.append({'task_id':task['task_id'],'reason':type(error).__name__})
    return {'tasks':len(tasks),'conflicts':conflicts}
