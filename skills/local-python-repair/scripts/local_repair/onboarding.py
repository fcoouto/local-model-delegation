"""Owner-permitted synthetic assessments. Evidence never constitutes project-use approval."""
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
import uuid
from .contracts import canonical, digest, load_json, text_hash, validate_brief
from .profiles import fingerprint_artifact, model_identity, read_config, read_profiles
from .store import Store, atomic_json, private_dir


def fixtures_path():
    bundled=Path(__file__).resolve().parents[1]/'assessment-cases.json'
    return bundled if bundled.exists() else Path(__file__).resolve().parents[3] / 'setup/fixtures/assessment-cases.json'


def discover_models(runtime):
    snapshot = runtime.list_models()
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('models'), list): raise ValueError('unsupported_discovery')
    result = []
    for model in snapshot['models']:
        if not isinstance(model, dict): raise ValueError('unsupported_discovery')
        if model.get('type') != 'llm': continue
        if not isinstance(model.get('key'), str) or not model['key']: raise ValueError('unsupported_discovery')
        result.append({'model_id': model['key'], 'status': 'needs_assessment' if model.get('format') in ('gguf', 'mlx') else 'unsupported',
                       'format': model.get('format'), 'loaded_instances': model.get('loaded_instances', [])})
    return result


def _profile(state_dir, identifier):
    if not isinstance(identifier, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', identifier): raise ValueError('invalid_profile_id')
    profile = next((p for p in read_profiles(state_dir) if p['profile_id'] == identifier), None)
    if not profile: raise ValueError('unknown_profile')
    return profile


def _binding(profile):
    identity = fingerprint_artifact(Path(profile['artifact']['root']), profile['artifact']['files'])
    return {'artifact': identity, 'runtime': model_identity(profile), 'settings': profile['request_settings']}


def _assessment(state_dir, identifier):
    if not isinstance(identifier, str) or not re.fullmatch('[a-f0-9]{32}', identifier): raise ValueError('invalid_assessment_id')
    return load_json((Path(state_dir) / 'assessments' / identifier / 'assessment.json').read_text())


def _policy(state_dir, owner_reference):
    policy = read_config(state_dir).get('assessment_policy', {})
    if policy.get('enabled') is not True or not owner_reference or policy.get('owner_reference') != owner_reference:
        raise ValueError('assessment_consent_required')
    return policy


def begin_assessment(state_dir, profile_id, owner_reference):
    _policy(state_dir, owner_reference)
    profile = _profile(state_dir, profile_id)
    binding = _binding(profile)
    manifest = load_json(fixtures_path().read_text())
    identifier = uuid.uuid4().hex
    root = private_dir(Path(state_dir) / 'assessments' / identifier)
    trials = []
    for case in manifest['cases']:
        if case['capability'] not in profile['capabilities']: continue
        source = private_dir(root / case['id'])
        for name, text in case['files'].items():
            path = source / name; path.write_text(text); path.chmod(0o600)
        for repeat in (1, 2):
            trial_id = case['id'] + '-' + str(repeat)
            brief = {'schema_version': 2, 'origin_chat_id': 'assessment-' + identifier, 'task_key': trial_id,
                     'capability': case['capability'], 'source_root': str(source),
                     'files': {n: {'content': t, 'sha256': text_hash(t)} for n, t in case['files'].items()},
                     'editable_paths': case['editable_paths'], 'behavior_contract': case['contract'],
                     'task_requirements': {**{k: case[k] for k in ('language','complexity','context_bucket')}, 'urgency':'normal','wait_budget_seconds':120},
                     'fallback': profile['fallback'],
                     'acceptance': {'method': 'python_isolated' if case['capability']=='bounded_python_repair' else 'native_verified',
                                    'criteria': ['Meets the stated contract; tests must distinguish the specified behaviors.'], 'protected_paths': [], 'checks': []}}
            if case['capability'] == 'bounded_python_repair':
                brief.update({k: case[k] for k in ('supplied_tests','independent_tests','checks')})
                brief['acceptance']['checks'] = [{'id':'python','argv':[str(Path(sys.executable).resolve()),'-m','unittest'],'cwd':'.','timeout_seconds':30}]
            elif case['capability'] != 'file_summary':
                # Native coordinator must also verify semantics; syntax alone never qualifies a trial.
                import shutil
                executable = str(Path(sys.executable).resolve()) if case['language']=='python' else shutil.which('node')
                if not executable: continue
                argv = [executable, '-m', 'compileall', '-q', '.'] if case['language']=='python' else [str(Path(executable).resolve()), '--check', 'helper.js']
                brief['acceptance']['checks'] = [{'id':'syntax','argv':argv,'cwd':'.','timeout_seconds':30}]
            validate_brief(brief)
            trials.append({'trial_id': trial_id, 'case_id': case['id'], 'brief': brief, 'brief_hash': digest(brief)})
    if not trials: raise ValueError('assessment_scope_unsupported')
    assessment = {'assessment_id': identifier, 'permit_token': uuid.uuid4().hex + uuid.uuid4().hex,
                  'profile_id': profile_id, 'owner_reference': owner_reference, 'binding': binding,
                  'fixture_digest': digest(manifest), 'trials': trials, 'receipts': {}}
    atomic_json(root / 'assessment.json', assessment)
    return assessment


def authorize_assessment(state_dir, brief, permit):
    assessment = _assessment(state_dir, permit['assessment_id'])
    _policy(state_dir, assessment['owner_reference'])
    if permit.get('permit_token') != assessment['permit_token']: raise ValueError('assessment_scope_mismatch')
    profile = _profile(state_dir, assessment['profile_id'])
    if _binding(profile) != assessment['binding']: raise ValueError('assessment_identity_changed')
    if (digest(load_json(fixtures_path().read_text())) != assessment['fixture_digest']
            or not any(digest(brief) == trial['brief_hash'] for trial in assessment['trials'])):
        raise ValueError('assessment_scope_mismatch')
    from .validation import source_matches
    if not source_matches(brief): raise ValueError('assessment_scope_mismatch')
    return profile


def record_trial(state_dir, assessment_id, receipt):
    from .worker import ownership
    store = Store(state_dir)
    with ownership(store, 'assessment-' + assessment_id) as owned:
        if not owned: raise ValueError('assessment_busy')
        assessment = _assessment(state_dir, assessment_id)
        if not isinstance(receipt, dict) or set(receipt) != {'trial_id','job_id'}: raise ValueError('invalid_trial_receipt')
        trial = next((t for t in assessment['trials'] if t['trial_id']==receipt['trial_id']), None)
        job = store.job(receipt['job_id'])
        permit = {'assessment_id': assessment_id, 'permit_token': assessment['permit_token']}
        authorize_assessment(state_dir, job['brief'], permit)
        if not trial or digest(job['brief']) != trial['brief_hash'] or job.get('route_data', {}).get('assessment') != permit:
            raise ValueError('assessment_scope_mismatch')
        if job['status'] not in ('accepted','failed','fallback_required'): raise ValueError('trial_not_complete')
        value = {**receipt, 'passed': job['status']=='accepted', 'status': job['status']}
        previous = assessment['receipts'].get(receipt['trial_id'])
        if previous and previous != value: raise ValueError('trial_conflict')
        assessment['receipts'][receipt['trial_id']] = value
        atomic_json(store.root / 'assessments' / assessment_id / 'assessment.json', assessment)
    return assessment_report(state_dir, assessment_id)


def assessment_report(state_dir, assessment_id):
    assessment = _assessment(state_dir, assessment_id)
    profile = _profile(state_dir, assessment['profile_id'])
    current = _binding(profile) == assessment['binding']
    buckets = {}
    for trial in assessment['trials']:
        brief = trial['brief']
        scope = {k: brief['task_requirements'][k] for k in ('language','complexity','context_bucket')}
        scope.update(capability=brief['capability'], max_input_bytes=max(4096, len(canonical({'contract': brief['behavior_contract'], 'files': brief['files'], 'editable_paths': brief['editable_paths']}).encode())))
        key = digest({k:v for k,v in scope.items() if k!='max_input_bytes'})
        bucket = buckets.setdefault(key, {'scope': scope, 'trials': 0, 'passed': 0, 'cases': set()})
        bucket['scope']['max_input_bytes'] = max(bucket['scope']['max_input_bytes'], scope['max_input_bytes'])
        bucket['trials'] += 1
        bucket['cases'].add(trial['case_id'])
        bucket['passed'] += assessment['receipts'].get(trial['trial_id'], {}).get('passed') is True
    qualified = [b['scope'] for b in buckets.values() if current and b['trials'] >= 6 and b['passed']==b['trials'] and len(b['cases'])>=3]
    capacity = profile.get('capacity_evidence', {})
    benefit = profile.get('benefit_evidence', {})
    ready = bool(qualified and capacity.get('qualified') is True and benefit.get('credible') is True)
    return {'assessment_id':assessment_id, 'profile_id':profile['profile_id'], 'completed_trials':len(assessment['receipts']),
            'total_trials':len(assessment['trials']), 'tested_scope':qualified, 'capacity_status':'qualified' if capacity.get('qualified') is True else 'unknown',
            'expected_savings':'usage_proxy' if benefit.get('credible') is True else 'unknown',
            'recommendation':'approve_provisional_scope' if ready else 'do_not_approve_yet',
            'limitations':['Six passing trials are provisional evidence, not a statistical reliability guarantee.',
                           'Runtime binding trusts the local index and discovery metadata; it does not attest weights in memory.',
                           'Actual account savings and live host continuity remain unqualified.']}


def approve_assessment(state_dir, assessment_id, owner_reference, scope):
    if not isinstance(owner_reference, str) or not owner_reference.strip(): raise ValueError('owner_confirmation_required')
    report = assessment_report(state_dir, assessment_id)
    if report['recommendation'] != 'approve_provisional_scope' or scope != report['tested_scope']: raise ValueError('assessment_incomplete')
    profile = _profile(state_dir, report['profile_id'])
    binding = _binding(profile)
    profile['artifact'].update(binding['artifact'])
    profile.update(scope=scope, qualification_status='qualified')
    profile['approval'] = {'owner_reference':owner_reference, 'timestamp':datetime.now(timezone.utc).isoformat(),
                           'artifact_digest':binding['artifact']['digest'], 'model_identity':binding['runtime'],
                           'capabilities':profile['capabilities'], 'request_settings':profile['request_settings'], 'scope':scope}
    atomic_json(Path(state_dir) / 'profiles' / (profile['profile_id']+'.json'), profile)
    return {'status':'approval_recorded','routing_enabled':read_config(state_dir).get('routing_enabled') is True}


def submit_trial(state_dir, assessment_id, trial_id):
    assessment=_assessment(state_dir,assessment_id)
    trial=next((t for t in assessment['trials'] if t['trial_id']==trial_id),None)
    if trial is None:raise ValueError('unknown_trial')
    permit={'assessment_id':assessment_id,'permit_token':assessment['permit_token']}
    authorize_assessment(state_dir,trial['brief'],permit)
    store=Store(state_dir)
    result=store.enqueue(trial['brief'],trial['brief']['fallback'],assessment=permit)
    from .worker import launch
    launch(state_dir,'scheduler','queue')
    return result


def record_outcome(state_dir, job_id, receipt):
    from .contracts import positive
    from .profiles import scope_matches
    from .worker import ownership
    required={'native_usage','coordination_tokens','checking_tokens','fallback_tokens','native_baseline_tokens','latency_seconds','provenance'}
    if not isinstance(receipt,dict) or set(receipt)!=required:raise ValueError('invalid_outcome')
    for key in ('coordination_tokens','checking_tokens','fallback_tokens','native_baseline_tokens'):
        if receipt[key] is not None and (type(receipt[key]) is not int or receipt[key]<0):raise ValueError('invalid_outcome')
    usage=receipt['native_usage']
    if (not isinstance(usage,dict) or set(usage)!={'kind','value'} or usage['kind'] not in ('unknown','tokens')
            or usage['kind']=='unknown' and usage['value'] is not None
            or usage['kind']=='tokens' and (type(usage['value']) is not int or usage['value']<0)
            or not positive(receipt['latency_seconds']) or not isinstance(receipt['provenance'],str) or not receipt['provenance'].strip()):
        raise ValueError('invalid_outcome')
    store=Store(state_dir)
    with ownership(store,'outcomes') as owned:
        if not owned:raise ValueError('outcome_busy')
        with store.db(write=True) as db:
            job=store._job(db.execute('SELECT * FROM jobs WHERE job_id=?',(job_id,)).fetchone())
            if job['status'] not in ('accepted','failed'):raise ValueError('outcome_not_final')
            route=job.get('route_data',{})
            previous=route.get('outcome')
            if previous and previous!=receipt:raise ValueError('outcome_conflict')
            route['outcome']=receipt
            db.execute('UPDATE jobs SET route_data=? WHERE job_id=?',(canonical(route),job_id))
            records=[store._job(r) for r in db.execute('SELECT * FROM jobs')]
        profile=job['profile'];identifier=profile.get('profile_id')
        related=[j for j in records if j['profile'].get('profile_id')==identifier and j.get('route_data',{}).get('outcome')]
        accepted=sum(j['status']=='accepted' for j in related)
        counts=[receipt[k] for k in ('coordination_tokens','checking_tokens','fallback_tokens')]
        saved=receipt['native_baseline_tokens']-sum(counts) if all(v is not None for v in [receipt['native_baseline_tokens'],*counts]) else None
        if not identifier:
            return {'job_id':job_id,'status':job['status'],'accepted_tasks':accepted,'usage_proxy_saved_tokens':saved,'subscription_savings':'unknown'}
        current=_profile(state_dir,identifier)
        if current.get('approval')==profile.get('approval'):
            suspended=current.get('suspended_scope',[])
            for record in related:
                if record['status']=='failed' and record['brief'].get('schema_version')==2:
                    for scope in current.get('scope',[]):
                        if scope_matches({'scope':[scope]},record['brief']) and scope not in suspended:suspended.append(scope)
            current['suspended_scope']=suspended
            current['outcomes']={'accepted_tasks':accepted,'completed_tasks':len(related)}
            if saved is not None and saved>0 and job['status']=='accepted':
                current['benefit_evidence']={'credible':True,'kind':'usage_proxy','native_overhead':sum(counts),
                                            'job_id':job_id,'subscription_savings':'unknown'}
            atomic_json(store.root/'profiles'/(identifier+'.json'),current)
        return {'job_id':job_id,'status':job['status'],'accepted_tasks':accepted,
                'usage_proxy_saved_tokens':saved,'subscription_savings':'unknown'}
