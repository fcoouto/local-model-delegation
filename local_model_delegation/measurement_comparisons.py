"""Consent-bound evidence imports. This module never executes comparisons."""
from collections import Counter, defaultdict
from .contracts import canonical, digest, load_json, MAX_ANSWER_BYTES
from .measurements import connection, fields, require, identifier, sha, number, validate_native, _append, job_observation


def register_comparison(state_dir, manifest):
    fields(manifest, {'project_id','scope','environment_digest','local_binding','native_binding','method','limits',
                      'consent_reference','consent_at','expires_at','cases'})
    require(identifier(manifest['project_id']) and sha(manifest['environment_digest']))
    validate_native(manifest['native_binding'])
    fields(manifest['local_binding'], {'profile_id','artifact_digest','runtime_digest','settings_digest','helper_digest'})
    require(identifier(manifest['local_binding']['profile_id']) and all(sha(v) for k,v in manifest['local_binding'].items() if k!='profile_id'))
    require(manifest['method'] in ('paired','observational'))
    fields(manifest['limits'], {'local','native'})
    require(all(type(v) is int and 0 <= v <= 10000 for v in manifest['limits'].values()))
    require(isinstance(manifest['consent_reference'],str) and 0 < len(manifest['consent_reference']) <= 512)
    require(number(manifest['consent_at']) and number(manifest['expires_at']) and manifest['expires_at']>manifest['consent_at'])
    require(isinstance(manifest['cases'],list) and 1 <= len(manifest['cases']) <= 1000)
    ids=set()
    for case in manifest['cases']:
        fields(case, {'case_id','case_hash','source_hash','checks_hash','contract_hash'})
        require(identifier(case['case_id']) and case['case_id'] not in ids)
        require(all(sha(v) for k,v in case.items() if k!='case_id'));ids.add(case['case_id'])
    require(len(canonical(manifest).encode()) <= MAX_ANSWER_BYTES)
    comparison_id=digest(manifest)
    with connection(state_dir,write=True) as db:
        require(db.execute('SELECT 1 FROM measurement_projects WHERE project_id=?',(manifest['project_id'],)).fetchone(),'unknown_project')
        prior=db.execute('SELECT * FROM measurement_comparisons WHERE consent_reference=?',(manifest['consent_reference'],)).fetchone()
        if prior: require(prior['comparison_id']==comparison_id,'comparison_consent_conflict')
        else: db.execute('INSERT INTO measurement_comparisons VALUES (?,?,?,NULL)',(comparison_id,canonical(manifest),manifest['consent_reference']))
    return {'comparison_id':comparison_id,'execution_authorized':False}


def _comparison(db, comparison_id):
    require(sha(comparison_id),'invalid_comparison_id')
    row=db.execute('SELECT * FROM measurement_comparisons WHERE comparison_id=?',(comparison_id,)).fetchone()
    require(row is not None,'unknown_comparison')
    return load_json(row['manifest']),load_json(row['revocation']) if row['revocation'] else None


def record_comparison_run(state_dir, comparison_id, receipt):
    fields(receipt, {'case_id','route','task_id','attempt_id','state','submitted_at','recorded_at','source_hash',
                     'checks_hash','contract_hash','order','isolated','isolation_hash','evaluator'})
    require(all(identifier(receipt[k]) for k in ('case_id','task_id','attempt_id','evaluator')))
    require(receipt['route'] in ('local','native') and receipt['state'] in ('submitted','uncertain','completed','failed'))
    require(number(receipt['submitted_at']) and number(receipt['recorded_at']) and receipt['recorded_at']>=receipt['submitted_at'])
    require(type(receipt['order']) is int and receipt['order']>=0 and type(receipt['isolated']) is bool)
    require(receipt['isolation_hash'] is None or sha(receipt['isolation_hash']))
    with connection(state_dir,write=True) as db:
        manifest,_=_comparison(db,comparison_id)
        case=next((c for c in manifest['cases'] if c['case_id']==receipt['case_id']),None)
        require(case and all(case[k]==receipt[k] for k in ('source_hash','checks_hash','contract_hash')),'comparison_case_mismatch')
        task=db.execute('SELECT * FROM measurement_tasks WHERE task_id=?',(receipt['task_id'],)).fetchone()
        require(task is not None,'unknown_measurement_task');context=load_json(task['context'])
        require(all(context[k]==manifest[k] for k in ('project_id','scope','environment_digest','native_binding'))
                and context['case_hash']==case['case_hash'],'comparison_context_mismatch')
        if manifest['method']=='paired': require(receipt['isolated'] and sha(receipt['isolation_hash']),'comparison_isolation_missing')
        if receipt['route']=='local':
            require(task['job_id'] is not None,'comparison_local_job_required')
            obs=job_observation(db,task['job_id'])
            require(obs['binding']==manifest['local_binding'],'comparison_binding_mismatch')
            attempt=next((a for a in obs['attempts'] if a['attempt_id']==receipt['attempt_id']),None)
            require(attempt is not None,'comparison_attempt_mismatch')
            if receipt['state']=='completed': require(attempt['state']=='complete','comparison_attempt_not_complete')
            if attempt['submitted_at'] is not None:
                require(receipt['submitted_at']==attempt['submitted_at'],'comparison_submission_mismatch')
        else:
            require(task['job_id'] is None,'fallback_is_not_baseline')
        for row in db.execute("SELECT receipt FROM measurement_events WHERE kind='comparison_run'"):
            prior=load_json(row['receipt'])['payload']
            if prior['route']==receipt['route'] and prior['attempt_id']==receipt['attempt_id']:
                require(prior['comparison_id']==comparison_id and prior['task_id']==receipt['task_id'] and prior['case_id']==receipt['case_id'],
                        'comparison_attempt_reused')
                require(prior['submitted_at']==receipt['submitted_at'] and prior['order']==receipt['order'],'comparison_attempt_conflict')
                require(prior['state'] not in ('completed','failed') or prior['state']==receipt['state'],'comparison_state_conflict')
        payload={'comparison_id':comparison_id,**receipt}
        event={'schema_version':1,'producer':'comparison','source_key':digest(payload), 'kind':'comparison_run',
               'observed_at':receipt['recorded_at'],'payload':payload}
        _append(db,receipt['task_id'],event,internal=True)
        return comparison_status(db,comparison_id)


def revoke_comparison(state_dir, comparison_id, revoked_at, evidence_hash):
    require(number(revoked_at) and sha(evidence_hash))
    value={'revoked_at':revoked_at,'evidence_hash':evidence_hash}
    with connection(state_dir,write=True) as db:
        _,previous=_comparison(db,comparison_id)
        require(previous is None or previous==value,'comparison_revocation_conflict')
        db.execute('UPDATE measurement_comparisons SET revocation=? WHERE comparison_id=?',(canonical(value),comparison_id))
    return {'comparison_id':comparison_id,'revoked':True,'execution_authorized':False}


def comparison_status(db, comparison_id):
    manifest,revocation=_comparison(db,comparison_id)
    attempts={};violations=set();legs=defaultdict(list)
    for row in db.execute("SELECT receipt FROM measurement_events WHERE kind='comparison_run' ORDER BY rowid"):
        payload=load_json(row['receipt'])['payload']
        if payload['comparison_id']==comparison_id: attempts[(payload['route'],payload['attempt_id'])]=payload
    consumed=Counter(p['route'] for p in attempts.values())
    for route in ('local','native'):
        if consumed[route]>manifest['limits'][route]: violations.add(route+'_allowance_exceeded')
    for p in attempts.values():
        legs[p['case_id'],p['route']].append(p)
        if not manifest['consent_at']<=p['submitted_at']<manifest['expires_at'] or revocation and p['submitted_at']>=revocation['revoked_at']:
            violations.add('consent_not_valid_at_submission')
    if any(len(v)>1 for v in legs.values()): violations.add('duplicate_case_leg')
    pairs=[]
    for case in manifest['cases']:
        local,native=legs[case['case_id'],'local'],legs[case['case_id'],'native']
        if len(local)==len(native)==1 and local[0]['state']==native[0]['state']=='completed' and local[0]['order']!=native[0]['order']:
            pairs.append({'local_task':local[0]['task_id'],'native_task':native[0]['task_id'],
                          'method':'paired_usage_proxy' if manifest['method']=='paired' else 'observational_estimate'})
    return {'comparison_id':comparison_id,'project_id':manifest['project_id'],
            'consumed':{k:consumed[k] for k in ('local','native')},
            'remaining':{k:max(0,manifest['limits'][k]-consumed[k]) for k in ('local','native')},
            'violations':sorted(violations),'states':dict(Counter(p['state'] for p in attempts.values())),
            'pairs':pairs if not violations else [],'execution_authorized':False}
