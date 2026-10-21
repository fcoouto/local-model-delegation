"""An optional local read-only projection. Nothing in the export is control input."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import sqlite3
import time
from urllib.parse import quote
from .contracts import digest,load_json
from .profiles import read_config
from .store import atomic_json,private_dir

TERMINAL={'accepted','failed','needs_reassessment'}
LABELS={'waiting':'Waiting for a local slot','reserved':'Starting','candidate_ready':'Awaiting verification','checking':'Awaiting verification',
        'fallback_required':'Native fallback needed','fallback_dispatching':'Native dispatch pending','dispatch_uncertain':'Native dispatch unconfirmed',
        'fallback_running':'Native execution','accepted':'Verified','failed':'Failed','needs_reassessment':'Scope changed'}
REASONS={'model_busy','model_unavailable','capacity_unqualified','no_qualified_model','route_decision_required','source_changed','routing_disabled',
         'suspected_loop','stale','output_budget_exhausted','native_dispatch_uncertain','native_verification_failed','instance_not_owned','lifecycle_unqualified'}


def read_rows(path):
    path=Path(path)
    if path.is_symlink():raise ValueError('unsafe_visibility')
    with sqlite3.connect('file:'+quote(str(path))+'?mode=ro',uri=True) as db:
        db.row_factory=sqlite3.Row
        rows=db.execute('SELECT j.*, a.data AS observation FROM jobs j LEFT JOIN attempts a ON j.attempt_id=a.attempt_id ORDER BY j.rowid DESC').fetchall()
    result=[];completed=0
    for row in rows:
        value=dict(row)
        if value['status'] in TERMINAL:
            completed+=1
            if completed>100:continue
        for field in ('brief','profile','route_data','observation'):
            value[field]=load_json(value.get(field) or '{}')
        result.append(value)
    return result


def clean(text):
    return ''.join(c for c in str(text) if c.isprintable())[:128]


def build_visibility_snapshot(rows,generated_at):
    jobs=[]
    for row in rows:
        profile,brief=row['profile'],row['brief'];state=row['status'];route=row.get('route_data',{})
        observation=row.get('observation',{})
        observed=observation.get('last_event_at') if state=='running' else route.get('observed_at',observation.get('created',row.get('queued_at')))
        native=row.get('native_task_id')
        kind='native' if native else ('local_model' if row.get('attempt_id') else 'unassigned')
        model=clean(profile.get('display_name') or profile.get('model_id') or '')
        if native:
            fallback=row.get('fallback')
            if isinstance(fallback,str):fallback=load_json(fallback)
            model=clean((fallback or profile.get('fallback') or {}).get('model',''))
        value={'job_id':row['job_id'],'origin_chat_id':brief['origin_chat_id'],'project_id':digest(brief['source_root']),
               'capability':brief['capability'],'model_name':model,'execution_kind':kind,'state':state,
               'label':model if state=='running' else LABELS.get(state,'Unknown'),
               'reason_code':row.get('reason') if row.get('reason') in REASONS else None,
               'observed_at':observed,'stale_after_seconds':profile.get('stale_tolerance_seconds',120) if state=='running' else 120}
        if row.get('attempt_id'):value['attempt_id']=row['attempt_id']
        if native:value['fallback_native_task_id']=native
        jobs.append(value)
    return {'schema_version':1,'generated_at':generated_at,'jobs':jobs}


@contextmanager
def _lock(root):
    directory=private_dir(root/'locks')
    fd=os.open(directory/'visibility',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX)
        yield
    finally:os.close(fd)


def _path(root):
    path=root/'visibility/status.json'
    if root.is_symlink() or path.parent.is_symlink() or path.is_symlink():raise ValueError('unsafe_visibility')
    return path


def visibility_status(state_dir):
    root=Path(state_dir);enabled=read_config(root).get('visibility_enabled',True) is True
    try:
        path=_path(root)
        if not path.exists():return {'enabled':enabled,'export_state':'absent'}
        value=load_json(path.read_text())
        if value.get('schema_version')!=1 or not isinstance(value.get('jobs'),list):raise ValueError('invalid_visibility')
        stale=any(j.get('state') not in TERMINAL and (j.get('observed_at') is None or time.time()-j['observed_at']>j['stale_after_seconds']) for j in value['jobs'])
        return {'enabled':enabled,'export_state':'stale' if stale else 'ready'}
    except (ValueError,OSError,KeyError,TypeError):return {'enabled':enabled,'export_state':'error','reason_code':'visibility_unavailable'}


def publish_visibility(state_dir):
    root=Path(state_dir)
    if not root.exists() or not (root/'state.sqlite3').exists():return visibility_status(root)
    try:
        with _lock(root):
            config=read_config(root)
            if config.get('visibility_enabled',True) is not True:return {'enabled':False,'export_state':'absent'}
            path=_path(root)
            atomic_json(path,build_visibility_snapshot(read_rows(root/'state.sqlite3'),time.time()))
        return visibility_status(root)
    except (ValueError,OSError,sqlite3.Error,KeyError,TypeError):
        return {'enabled':read_config(root).get('visibility_enabled',True) is True,'export_state':'error','reason_code':'visibility_unavailable'}


def set_visibility(state_dir,enabled):
    if type(enabled) is not bool:raise ValueError('invalid_visibility_preference')
    root=private_dir(Path(state_dir))
    with _lock(root):
        config=read_config(root);config['visibility_enabled']=enabled
        path=root/('config.json' if config['schema_version']==2 else 'profiles.json')
        atomic_json(path,config)
        if not enabled:
            try:_path(root).unlink(missing_ok=True)
            except (OSError,ValueError):return {'enabled':False,'export_state':'error','reason_code':'visibility_unavailable'}
    return publish_visibility(root) if enabled else visibility_status(root)
