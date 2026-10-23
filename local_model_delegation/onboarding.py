"""Owner-permitted synthetic assessments. Evidence never constitutes project-use approval."""
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
import uuid
from .contracts import PYTHON_CHANGE_CAPABILITIES, canonical, digest, load_json, text_hash, validate_brief
from .profiles import fingerprint_artifact, model_identity, read_config, read_profiles
from .store import Store, atomic_json, private_dir


def fixtures_path():
    bundled=Path(__file__).resolve().parents[1]/'assessment-cases.json'
    return bundled if bundled.exists() else Path(__file__).resolve().parents[1] / 'skills/setup/fixtures/assessment-cases.json'


def discover_models(runtime):
    snapshot = runtime.list_models()
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get('models'), list): raise ValueError('unsupported_discovery')
    result = []
    for model in snapshot['models']:
        if not isinstance(model, dict): raise ValueError('unsupported_discovery')
        if model.get('type') != 'llm': continue
        if not isinstance(model.get('key'), str) or not model['key']: raise ValueError('unsupported_discovery')
        result.append({'model_id': model['key'], 'status': 'needs_assessment' if model.get('format') in ('gguf', 'mlx', 'splash') else 'unsupported',
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
    record = load_json((Path(state_dir) / 'assessments' / identifier / 'assessment.json').read_text())
    if not isinstance(record, dict): raise ValueError('invalid_assessment_record')
    new_fields = {'authorization', 'preview', 'preview_digest', 'profile_snapshot', 'source_profile'}
    if 'schema_version' not in record:
        if new_fields & record.keys(): raise ValueError('invalid_assessment_record')
        return record
    try:
        preview, auth = record['preview'], record['authorization']
        trials = record['trials']
        if (type(record['schema_version']) is not int or record['schema_version'] != 1
                or record['assessment_id'] != identifier or auth['mode'] != 'run'
                or auth['state'] not in ('draft', 'authorized', 'paused', 'stopped', 'invalidated', 'complete')
                or set(auth) != {'mode', 'state', 'owner_reference', 'timestamp', 'preview_digest'}
                or digest(preview) != record['preview_digest'] or auth['preview_digest'] != record['preview_digest']
                or preview['profile_digest'] != digest(record['profile_snapshot'])
                or preview['profile_id'] != record['profile_id'] or record['profile_snapshot']['profile_id'] != record['profile_id']
                or preview['binding'] != record['binding'] or preview['source_profile'] != record['source_profile']
                or preview['fixture_digest'] != record['fixture_digest'] or record['capacity_target'] != 1
                or preview['max_submissions'] != len(trials) or not trials
                or len({t['trial_id'] for t in trials}) != len(trials)
                or not isinstance(record['receipts'], dict)
                or not set(record['receipts']) <= {t['trial_id'] for t in trials}):
            raise ValueError('invalid_assessment_record')
        from .profiles import generation_settings
        frozen = []
        for trial in trials:
            brief = trial['brief']
            validate_brief(brief)
            if (digest(brief) != trial['brief_hash'] or brief['task_key'] != trial['trial_id']
                    or brief['origin_chat_id'] != 'assessment-' + identifier): raise ValueError('invalid_assessment_record')
            frozen.append({'trial_id': trial['trial_id'], 'brief_hash': trial['brief_hash'],
                           'settings': generation_settings(brief, record['profile_snapshot'])})
        if frozen != preview['trials']: raise ValueError('invalid_assessment_record')
        if auth['state'] == 'draft':
            if auth['owner_reference'] is not None or auth['timestamp'] is not None: raise ValueError('invalid_assessment_record')
        elif auth['state'] in ('authorized', 'paused', 'complete'):
            if not all(isinstance(auth[k], str) and auth[k].strip() for k in ('owner_reference', 'timestamp')):
                raise ValueError('invalid_assessment_record')
    except (KeyError, TypeError, AttributeError, ValueError):
        raise ValueError('invalid_assessment_record') from None
    return record


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
    trials = _build_trials(state_dir, identifier, profile, manifest)
    assessment = {'assessment_id': identifier, 'permit_token': uuid.uuid4().hex + uuid.uuid4().hex,
                  'profile_id': profile_id, 'owner_reference': owner_reference, 'binding': binding,
                  'fixture_digest': digest(manifest), 'capacity_target':1, 'trials': trials, 'receipts': {}}
    atomic_json(Path(state_dir) / 'assessments' / identifier / 'assessment.json', assessment)
    return assessment


def _build_trials(state_dir, assessment_id, profile, manifest, *, groups=None):
    identifier = assessment_id
    root = private_dir(Path(state_dir) / 'assessments' / identifier)
    target=1
    trials = []
    for case in manifest['cases']:
        if groups is not None and _case_group(case) not in groups: continue
        if groups is None and case['capability'] in PYTHON_CHANGE_CAPABILITIES and case['capability'] not in profile['capabilities']:
            compatible = next((c for c in profile['capabilities'] if c in PYTHON_CHANGE_CAPABILITIES), None)
            if compatible: case = {**case, 'capability':compatible}
        if case['capability'] not in profile['capabilities']: continue
        source = private_dir(root / case['id'])
        for name, text in case['files'].items():
            path = source / name; path.write_text(text); path.chmod(0o600)
        for repeat in range(1,max(2,target)+1):
            trial_id = case['id'] + '-' + str(repeat)
            brief = {'schema_version': 2, 'origin_chat_id': 'assessment-' + identifier, 'task_key': trial_id,
                     'capability': case['capability'], 'source_root': str(source),
                     'files': {n: {'content': t, 'sha256': text_hash(t)} for n, t in case['files'].items()},
                     'editable_paths': case['editable_paths'], 'behavior_contract': case['contract'],
                     'task_requirements': {**{k: case[k] for k in ('language','complexity','context_bucket')}, 'urgency':'normal','wait_budget_seconds':120},
                     'fallback': profile['fallback'],
                     'acceptance': {'method': 'python_isolated' if case['capability'] in PYTHON_CHANGE_CAPABILITIES else 'native_verified',
                                    'criteria': ['Meets the stated contract; tests must distinguish the specified behaviors.'], 'protected_paths': [], 'checks': []}}
            if case['capability'] in PYTHON_CHANGE_CAPABILITIES:
                brief.update({k: case[k] for k in ('supplied_tests','independent_tests','checks')})
                brief['acceptance']['checks'] = [{'id':'python','argv':[str(Path(sys.executable).resolve()),'-m','unittest'],'cwd':'.','timeout_seconds':30}]
            elif case['capability'] != 'file_summary':
                # Native coordinator must also verify semantics; syntax alone never qualifies a trial.
                import shutil
                executable = str(Path(sys.executable).resolve()) if case['language']=='python' else shutil.which('node')
                if not executable:
                    if groups is not None: raise ValueError('assessment_checker_unavailable')
                    continue
                argv = [executable, '-m', 'compileall', '-q', '.'] if case['language']=='python' else [str(Path(executable).resolve()), '--check', 'helper.js']
                brief['acceptance']['checks'] = [{'id':'syntax','argv':argv,'cwd':'.','timeout_seconds':30}]
            validate_brief(brief)
            trials.append({'trial_id': trial_id, 'case_id': case['id'], 'brief': brief, 'brief_hash': digest(brief)})
    if not trials: raise ValueError('assessment_scope_unsupported')
    return trials


def _case_group(case):
    return {k: case[k] for k in ('capability', 'language', 'complexity', 'context_bucket')}


def assessment_choices():
    groups = []
    for case in load_json(fixtures_path().read_text())['cases']:
        group = _case_group(case)
        match = next((g for g in groups if _case_group(g) == group), None)
        if match is None:
            match = {**group, 'distinct_cases': 0, 'trials': 0}
            groups.append(match)
        match['distinct_cases'] += 1
        match['trials'] += 2
    return {'groups': groups, 'total_trials': sum(g['trials'] for g in groups)}


def _verification_snapshot(trials):
    executables = {str(Path(sys.executable).resolve())}
    executables.update(check['argv'][0] for t in trials for check in t['brief']['acceptance']['checks'])
    return {name: fingerprint_artifact(Path(name).parent, [Path(name).name]) for name in sorted(executables)}


def prepare_assessment(state_dir, profile_id, selection, *, source_profile_id=None):
    from .lmstudio import Runtime, select_loaded
    from .profiles import validate_profile_fields, generation_settings
    from .validation import _qualified_isolation
    from .worker import context_fits
    from .package import pin_runtime_bundle
    choices = assessment_choices()['groups']
    all_groups = [_case_group(g) for g in choices]
    if isinstance(selection, dict) and set(selection) == {'all'} and selection['all'] is True:
        groups = all_groups
    elif (isinstance(selection, dict) and set(selection) == {'groups'}
          and isinstance(selection['groups'], list) and len(selection['groups']) == 1
          and selection['groups'][0] in all_groups):
        groups = selection['groups']
    else: raise ValueError('invalid_assessment_selection')
    profile = _profile(state_dir, profile_id)
    if profile.get('approval') is not None or profile.get('scope') or profile.get('qualification_status') != 'needs_assessment':
        raise ValueError('assessment_requires_unapproved_profile')
    for group in groups:
        validate_profile_fields(profile, group['capability'])
        if group['capability'] not in profile['capabilities']: raise ValueError('assessment_scope_unsupported')
    binding = _binding(profile)
    if binding['runtime']['metadata']['format'] not in ('gguf', 'mlx', 'splash'):
        raise ValueError('assessment_model_unsupported')
    source_profile = None
    if source_profile_id is not None:
        source = _profile(state_dir, source_profile_id)
        source_binding = _binding(source)
        if source_profile_id == profile_id or any(source_binding[k] != binding[k] for k in ('artifact', 'runtime')):
            raise ValueError('assessment_source_mismatch')
        source_profile = {'profile_id': source_profile_id, 'binding': source_binding,
                          'approval_at_preparation': source.get('approval')}
    runtime = Runtime(profile['endpoint'], token_env=profile.get('token_env'))
    loaded = select_loaded(runtime.list_models(), profile, binding['runtime'])
    if loaded is None: raise ValueError('assessment_model_unavailable')
    if any(g['capability'] != 'file_summary' for g in groups) and not _qualified_isolation():
        raise ValueError('isolation_unsupported')
    identifier = uuid.uuid4().hex
    manifest = load_json(fixtures_path().read_text())
    trials = _build_trials(state_dir, identifier, profile, manifest, groups=groups)
    if any(not context_fits(t['brief'], profile, loaded) for t in trials):
        raise ValueError('assessment_context_unfit')
    bundle = pin_runtime_bundle(state_dir)
    preview = {'profile_id': profile_id, 'binding': binding, 'source_profile': source_profile,
               'profile_digest': digest(profile),
               'groups': groups, 'distinct_cases': len({t['case_id'] for t in trials}),
               'max_submissions': len(trials), 'concurrency': 1, 'loaded_config': loaded['config'],
               'fixture_digest': digest(manifest), 'runtime_bundle': bundle.name,
               'verification': _verification_snapshot(trials),
               'trials': [{'trial_id': t['trial_id'], 'brief_hash': t['brief_hash'],
                           'settings': generation_settings(t['brief'], profile)} for t in trials]}
    preview_digest = digest(preview)
    record = {'schema_version': 1, 'assessment_id': identifier,
              'permit_token': uuid.uuid4().hex + uuid.uuid4().hex, 'profile_id': profile_id,
              'binding': binding, 'fixture_digest': digest(manifest), 'capacity_target': 1,
              'trials': trials, 'receipts': {}, 'preview': preview, 'preview_digest': preview_digest,
              'profile_snapshot': profile, 'source_profile': source_profile,
              'authorization': {'mode': 'run', 'state': 'draft', 'owner_reference': None,
                                'timestamp': None, 'preview_digest': preview_digest}}
    atomic_json(Path(state_dir) / 'assessments' / identifier / 'assessment.json', record)
    return {'assessment_id': identifier, 'state': 'draft', 'preview': preview, 'preview_digest': preview_digest}


def _check_run_bindings(state_dir, assessment, *, check_runtime=False):
    from .package import runtime_contents, validate_bundle
    preview = assessment['preview']
    profile = _profile(state_dir, assessment['profile_id'])
    if digest(profile) != preview['profile_digest'] or _binding(profile) != assessment['binding']:
        raise ValueError('assessment_identity_changed')
    if digest(load_json(fixtures_path().read_text())) != assessment['fixture_digest']:
        raise ValueError('assessment_scope_mismatch')
    bundle = Path(state_dir).resolve() / 'runtimes' / preview['runtime_bundle']
    validate_bundle(bundle, preview['runtime_bundle'])
    source = Path(__file__).resolve().parents[1]
    running_digest = source.name if source == bundle else digest(runtime_contents(source)[1])
    if running_digest != preview['runtime_bundle']: raise ValueError('assessment_helper_changed')
    if _verification_snapshot(assessment['trials']) != preview['verification']:
        raise ValueError('assessment_checker_changed')
    if check_runtime:
        from .lmstudio import Runtime, select_loaded
        from .worker import context_fits
        from .validation import _qualified_isolation
        loaded = select_loaded(Runtime(profile['endpoint'], token_env=profile.get('token_env')).list_models(),
                               profile, assessment['binding']['runtime'])
        if loaded is None: raise ValueError('assessment_model_unavailable')
        if loaded['config'] != preview['loaded_config']: raise ValueError('assessment_runtime_changed')
        if any(not context_fits(t['brief'], profile, loaded) for t in assessment['trials']):
            raise ValueError('assessment_context_unfit')
        if any(t['brief']['capability'] != 'file_summary' for t in assessment['trials']) and not _qualified_isolation():
            raise ValueError('isolation_unsupported')
    return profile


def consent_assessment(state_dir, assessment_id, preview_digest, owner_reference):
    from .worker import ownership
    if not isinstance(owner_reference, str) or not owner_reference.strip(): raise ValueError('owner_confirmation_required')
    store = Store(state_dir)
    with ownership(store, 'plugin-update') as maintenance:
        if not maintenance: raise ValueError('assessment_busy')
        with ownership(store, 'assessment-' + assessment_id) as owned:
            if not owned: raise ValueError('assessment_busy')
            record = _assessment(state_dir, assessment_id)
            if record.get('schema_version') != 1: raise ValueError('assessment_run_required')
            auth = record['authorization']
            if preview_digest != record['preview_digest']: raise ValueError('assessment_preview_mismatch')
            if auth['state'] not in ('draft', 'authorized'): raise ValueError('assessment_' + auth['state'])
            if auth['state'] == 'authorized' and auth['owner_reference'] != owner_reference:
                raise ValueError('assessment_consent_conflict')
            _check_run_bindings(state_dir, record, check_runtime=True)
            if auth['state'] == 'draft':
                auth.update(state='authorized', owner_reference=owner_reference, timestamp=datetime.now(timezone.utc).isoformat())
                atomic_json(store.root / 'assessments' / assessment_id / 'assessment.json', record)
            return {'assessment_id': assessment_id, 'state': auth['state']}


def authorize_assessment(state_dir, brief, permit, *, purpose='submit', job=None):
    if purpose not in ('submit', 'verify'): raise ValueError('invalid_authorization_purpose')
    if not isinstance(permit, dict) or set(permit) != {'assessment_id', 'permit_token'}: raise ValueError('assessment_scope_mismatch')
    assessment = _assessment(state_dir, permit['assessment_id'])
    if permit.get('permit_token') != assessment['permit_token']: raise ValueError('assessment_scope_mismatch')
    if assessment.get('schema_version') == 1:
        if not any(digest(brief) == trial['brief_hash'] for trial in assessment['trials']):
            raise ValueError('assessment_scope_mismatch')
        if purpose == 'submit':
            state = assessment['authorization']['state']
            if state != 'authorized': raise ValueError('assessment_consent_required' if state == 'draft' else 'assessment_' + state)
            profile = _check_run_bindings(state_dir, assessment)
        else:
            profile = assessment['profile_snapshot']
            if (not job or not job.get('attempt_id') or job.get('native_task_id')
                    or job.get('route_data', {}).get('assessment') != permit
                    or job.get('profile') != profile or job.get('brief') != brief):
                raise ValueError('assessment_scope_mismatch')
            store = Store(state_dir)
            persisted = store.job(job['job_id'])
            attempt = store.attempt(job['attempt_id'])
            from .profiles import generation_settings
            if (any(persisted[k] != job[k] for k in ('job_id', 'brief', 'profile', 'attempt_id', 'native_task_id'))
                    or persisted.get('route_data', {}).get('assessment') != permit or attempt['job_id'] != job['job_id']
                    or not attempt['data'].get('submitted_at')
                    or attempt['data'].get('request_settings') != generation_settings(brief, profile)):
                raise ValueError('assessment_scope_mismatch')
            if _verification_snapshot(assessment['trials']) != assessment['preview']['verification']:
                raise ValueError('assessment_checker_changed')
        from .validation import source_matches
        if not source_matches(brief): raise ValueError('assessment_scope_mismatch')
        return profile
    _policy(state_dir, assessment['owner_reference'])
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
        if not isinstance(receipt, dict) or set(receipt) not in ({'trial_id','job_id'},{'trial_id','job_id','memory_samples'}): raise ValueError('invalid_trial_receipt')
        trial = next((t for t in assessment['trials'] if t['trial_id']==receipt['trial_id']), None)
        job = store.job(receipt['job_id'])
        permit = {'assessment_id': assessment_id, 'permit_token': assessment['permit_token']}
        authorize_assessment(state_dir, job['brief'], permit, purpose='verify', job=job)
        if not trial or digest(job['brief']) != trial['brief_hash'] or job.get('route_data', {}).get('assessment') != permit:
            raise ValueError('assessment_scope_mismatch')
        if job['status'] not in ('accepted','failed','fallback_required'): raise ValueError('trial_not_complete')
        value = {k:receipt[k] for k in ('trial_id','job_id')}
        value.update(passed=job['status']=='accepted' and not job['native_task_id'],status=job['status'])
        if 'memory_samples' in receipt:
            from .capacity import measure_request_memory
            if not job['attempt_id'] or store.attempt(job['attempt_id'])['state']!='complete' or job['native_task_id']:
                raise ValueError('memory_trial_not_complete')
            value['memory']=measure_request_memory(receipt['memory_samples'])
            timing=store.attempt(job['attempt_id'])['data']
            if (receipt['memory_samples'][0]['observed_at']>timing.get('submitted_at',0)
                    or receipt['memory_samples'][-1]['observed_at']<timing.get('finished_at',float('inf'))):
                raise ValueError('memory_samples_incomplete')
        previous = assessment['receipts'].get(receipt['trial_id'])
        if previous and previous != value: raise ValueError('trial_conflict')
        if 'memory_samples' in receipt:
            atomic_json(store.root/'assessments'/assessment_id/(receipt['trial_id']+'-memory.json'),receipt['memory_samples'])
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
        scope.update(capability=brief['capability'], max_input_bytes=len(canonical({'contract': brief['behavior_contract'], 'files': brief['files'], 'editable_paths': brief['editable_paths']}).encode()))
        key = digest({k:v for k,v in scope.items() if k!='max_input_bytes'})
        bucket = buckets.setdefault(key, {'scope': scope, 'trials': 0, 'passed': 0, 'cases': set()})
        bucket['scope']['max_input_bytes'] = max(bucket['scope']['max_input_bytes'], scope['max_input_bytes'])
        bucket['trials'] += 1
        bucket['cases'].add(trial['case_id'])
        bucket['passed'] += assessment['receipts'].get(trial['trial_id'], {}).get('passed') is True
    qualified = [b['scope'] for b in buckets.values() if current and b['trials'] >= 6 and b['passed']==b['trials'] and len(b['cases'])>=3]
    capacity = profile.get('capacity_evidence', {})
    benefit = profile.get('benefit_evidence') or {}
    ready = bool(qualified)
    return {'assessment_id':assessment_id, 'profile_id':profile['profile_id'], 'completed_trials':len(assessment['receipts']),
            'total_trials':len(assessment['trials']), 'tested_scope':qualified, 'capacity_status':'qualified' if capacity.get('qualified') is True else 'single_slot_default',
            'expected_savings':'usage_proxy' if benefit.get('credible') is True else 'unknown',
            'recommendation':'approve_provisional_scope' if ready else 'do_not_approve_yet',
            'limitations':['Tested byte sizes describe observations, not model limits or required operating budgets.',
                           'Six passing trials are provisional evidence, not a statistical reliability guarantee.',
                           'Unknown savings do not block approval; normal authorized work supplies measurement evidence.',
                           'Runtime binding trusts the local index and discovery metadata; it does not attest weights in memory.',
                           'Actual account savings and live host continuity remain unqualified.']}


def approve_assessment(state_dir, assessment_id, owner_reference, scope):
    if _assessment(state_dir, assessment_id).get('schema_version') == 1: raise ValueError('explicit_setup_onboarding_required')
    if not isinstance(owner_reference, str) or not owner_reference.strip(): raise ValueError('owner_confirmation_required')
    report = assessment_report(state_dir, assessment_id)
    if report['recommendation'] != 'approve_provisional_scope' or scope != report['tested_scope']: raise ValueError('assessment_incomplete')
    return approve_scope(state_dir, report['profile_id'], owner_reference, scope)


def approve_scope(state_dir, profile_id, owner_reference, scope, *, max_output_tokens=None):
    """Record explicit provisional operating permission, never fabricated assessment evidence."""
    if not isinstance(owner_reference, str) or not owner_reference.strip(): raise ValueError('owner_confirmation_required')
    profile = _profile(state_dir, profile_id)
    if max_output_tokens is not None:
        if type(max_output_tokens) is not int or max_output_tokens <= 0: raise ValueError('invalid_generation_ceiling')
        profile['request_settings'] = {**profile['request_settings'], 'max_output_tokens':max_output_tokens}
    if not isinstance(scope, list) or not scope: raise ValueError('invalid_scope')
    for item in scope:
        if (not isinstance(item, dict)
                or set(item) != {'capability','language','complexity','context_bucket','max_input_bytes'}
                or item['capability'] not in profile['capabilities']
                or item['complexity'] not in ('simple','moderate','complex')
                or any(not isinstance(item[k], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', item[k]) for k in ('language','context_bucket'))
                or type(item['max_input_bytes']) is not int or not 0 < item['max_input_bytes'] <= 800000):
            raise ValueError('invalid_scope')
    binding = _binding(profile)
    profile['artifact'].update(binding['artifact'])
    profile.update(scope=scope, qualification_status='qualified')
    profile['approval'] = {'owner_reference':owner_reference, 'timestamp':datetime.now(timezone.utc).isoformat(),
                           'artifact_digest':binding['artifact']['digest'], 'model_identity':binding['runtime'],
                           'capabilities':profile['capabilities'], 'request_settings':profile['request_settings'], 'scope':scope}
    atomic_json(Path(state_dir) / 'profiles' / (profile['profile_id']+'.json'), profile)
    return {'status':'approval_recorded','routing_enabled':read_config(state_dir).get('routing_enabled') is True}


def submit_trial(state_dir, assessment_id, trial_id):
    from .worker import ownership, launch
    from .contracts import envelope
    store = Store(state_dir)
    with ownership(store, 'assessment-' + assessment_id) as owned:
        if not owned: raise ValueError('assessment_busy')
        assessment = _assessment(state_dir, assessment_id)
        trial = next((t for t in assessment['trials'] if t['trial_id'] == trial_id), None)
        if trial is None: raise ValueError('unknown_trial')
        if assessment.get('schema_version') == 1:
            existing = store.lookup(trial['brief']['origin_chat_id'], trial_id)
            if existing:
                job = store.job(existing['job_id'])
                if digest(job['brief']) != trial['brief_hash'] or job['route_data'].get('assessment') != {
                        'assessment_id': assessment_id, 'permit_token': assessment['permit_token']}:
                    raise ValueError('assessment_scope_mismatch')
                return envelope(job)
            progress = _run_progress(store, assessment)
            if progress['pending_jobs'] or progress['blockers']: raise ValueError('assessment_trial_pending')
        permit = {'assessment_id': assessment_id, 'permit_token': assessment['permit_token']}
        try: authorize_assessment(state_dir, trial['brief'], permit)
        except (ValueError, OSError):
            if assessment.get('schema_version') == 1 and assessment['authorization']['state'] == 'authorized':
                assessment['authorization']['state'] = 'invalidated'
                atomic_json(store.root / 'assessments' / assessment_id / 'assessment.json', assessment)
            raise
        result = store.enqueue(trial['brief'], trial['brief']['fallback'], assessment=permit)
    launch(state_dir, 'scheduler', 'queue')
    return result


def _run_jobs(store, assessment):
    jobs = []
    for trial in assessment['trials']:
        found = store.lookup(trial['brief']['origin_chat_id'], trial['trial_id'])
        if found: jobs.append((trial, store.job(found['job_id'])))
    return jobs


def _trial_blocker(store, job):
    if job['attempt_id']:
        attempt = store.attempt(job['attempt_id'])
        if attempt['state'] == 'uncertain': return 'request_uncertain'
    if job['status'] == 'needs_reassessment': return job['reason'] or 'needs_reassessment'
    if job['status'] in ('fallback_required', 'failed'):
        if not job['attempt_id'] or not store.attempt(job['attempt_id'])['data'].get('submitted_at'):
            return job['reason'] or 'not_submitted'
        if store.attempt(job['attempt_id'])['state'] != 'complete': return job['reason'] or 'request_unresolved'
        if job['reason'] == 'verification_unsupported': return 'verification_unsupported'
        failure = store.root / 'jobs' / job['job_id'] / 'check-failure.json'
        if failure.exists():
            reason = load_json(failure.read_text()).get('reason', '')
            if reason.startswith(('assessment_', 'isolation_', 'source_', 'attempt_')):
                return reason
    return None


def _run_progress(store, assessment):
    pending, blockers, seen = [], [], set()
    for trial, job in _run_jobs(store, assessment):
        seen.add(trial['trial_id'])
        blocker = _trial_blocker(store, job)
        if blocker: blockers.append({'job_id': job['job_id'], 'reason': blocker})
        if trial['trial_id'] not in assessment['receipts']: pending.append(job['job_id'])
    next_trial = next((t['trial_id'] for t in assessment['trials'] if t['trial_id'] not in seen), None)
    return {'assessment_id': assessment['assessment_id'], 'state': assessment['authorization']['state'],
            'pending_jobs': pending, 'blockers': blockers,
            'next_trial_id': next_trial if not pending and not blockers and assessment['authorization']['state'] == 'authorized' else None}


def _defer_run_job(store, job, state):
    """Called under the run lock; only definitely unsubmitted reservations may be freed."""
    if job['attempt_id']:
        attempt = store.attempt(job['attempt_id'])
        if attempt['state'] != 'reserved' or attempt['data'].get('submitted_at'): return
        if not store.transition(attempt['attempt_id'], attempt['generation'], 'reserved', 'released', {}): return
    elif job['status'] != 'waiting': return
    with store.db(write=True) as db:
        db.execute("UPDATE jobs SET status=?,reason=?,attempt_id=NULL WHERE job_id=? AND status IN ('waiting','reserved')",
                   ('waiting' if state == 'paused' else 'failed', 'assessment_' + state, job['job_id']))


def control_assessment(state_dir, assessment_id, action):
    from .worker import ownership, reconcile_attempts, launch
    if action not in ('pause', 'stop', 'resume'): raise ValueError('invalid_assessment_control')
    store = Store(state_dir)
    if action == 'resume': reconcile_attempts(state_dir, assessment_id=assessment_id)
    with ownership(store, 'plugin-update') as maintenance:
        if not maintenance: raise ValueError('assessment_busy')
        with ownership(store, 'assessment-' + assessment_id) as owned:
            if not owned: raise ValueError('assessment_busy')
            assessment = _assessment(state_dir, assessment_id)
            if assessment.get('schema_version') != 1: raise ValueError('assessment_run_required')
            auth = assessment['authorization']
            if action == 'resume':
                if auth['state'] in ('stopped', 'invalidated', 'draft'): raise ValueError('assessment_' + auth['state'])
                if auth['state'] != 'complete':
                    try: _check_run_bindings(state_dir, assessment, check_runtime=True)
                    except (ValueError, OSError):
                        auth['state'] = 'invalidated'
                        atomic_json(store.root / 'assessments' / assessment_id / 'assessment.json', assessment)
                        raise
                    auth['state'] = 'paused' if _run_progress(store, assessment)['blockers'] else 'authorized'
            elif auth['state'] not in ('stopped', 'invalidated', 'complete'):
                if action == 'pause' and auth['state'] == 'draft': raise ValueError('assessment_consent_required')
                auth['state'] = 'paused' if action == 'pause' else 'stopped'
            if auth['state'] in ('paused', 'stopped', 'invalidated'):
                for _, job in _run_jobs(store, assessment): _defer_run_job(store, job, auth['state'])
            elif auth['state'] == 'authorized':
                with store.db(write=True) as db:
                    db.execute("UPDATE jobs SET reason='waiting_for_slot' WHERE chat=? AND status='waiting' AND reason='assessment_paused'",
                               ('assessment-' + assessment_id,))
            atomic_json(store.root / 'assessments' / assessment_id / 'assessment.json', assessment)
    reconcile_attempts(state_dir, assessment_id=assessment_id)
    for trial, job in _run_jobs(store, assessment):
        if (trial['trial_id'] not in assessment['receipts'] and job['status'] in ('accepted', 'failed', 'fallback_required')
                and job['attempt_id'] and store.attempt(job['attempt_id'])['state'] == 'complete'
                and not _trial_blocker(store, job)):
            record_trial(state_dir, assessment_id, {'trial_id': trial['trial_id'], 'job_id': job['job_id']})
    assessment = _assessment(state_dir, assessment_id)
    progress = _run_progress(store, assessment)
    if action == 'resume' and progress['state'] == 'authorized': launch(state_dir, 'scheduler', 'queue')
    return progress


def require_assessments_paused(state_dir):
    for path in (Path(state_dir) / 'assessments').glob('*/assessment.json'):
        assessment = _assessment(state_dir, path.parent.name)
        if assessment.get('schema_version') == 1 and assessment['authorization']['state'] == 'authorized':
            raise ValueError('assessments_must_be_paused')


def record_outcome(state_dir, job_id, receipt):
    from .contracts import positive
    from .profiles import scope_matches
    from .worker import ownership
    required={'native_usage','coordination_tokens','checking_tokens','fallback_tokens','native_baseline_tokens','onboarding_tokens','latency_seconds','provenance'}
    if not isinstance(receipt,dict) or set(receipt)!=required:raise ValueError('invalid_outcome')
    for key in ('coordination_tokens','checking_tokens','fallback_tokens','native_baseline_tokens','onboarding_tokens'):
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
            permit = route.get('assessment')
            if permit and _assessment(state_dir, permit['assessment_id']).get('schema_version') == 1:
                raise ValueError('assessment_has_no_global_outcome')
            previous=route.get('outcome')
            if previous and previous!=receipt:raise ValueError('outcome_conflict')
            route['outcome']=receipt
            db.execute('UPDATE jobs SET route_data=? WHERE job_id=?',(canonical(route),job_id))
            records=[store._job(r) for r in db.execute('SELECT * FROM jobs')]
        profile=job['profile'];identifier=profile.get('profile_id')
        related=[j for j in records if j['profile'].get('profile_id')==identifier and j['profile'].get('artifact',{}).get('digest')==profile.get('artifact',{}).get('digest') and j.get('route_data',{}).get('outcome')]
        accepted=sum(j['status']=='accepted' for j in related)
        counts=[receipt[k] for k in ('coordination_tokens','checking_tokens','fallback_tokens')]
        saved=receipt['native_baseline_tokens']-sum(counts)-receipt['onboarding_tokens']/max(1,accepted) if all(v is not None for v in [receipt['native_baseline_tokens'],receipt['onboarding_tokens'],*counts]) else None
        if not identifier:
            return {'job_id':job_id,'status':job['status'],'accepted_tasks':accepted,'usage_proxy_saved_tokens':saved,'subscription_savings':'unknown'}
        current=_profile(state_dir,identifier)
        if current.get('approval')==profile.get('approval'):
            suspended=current.get('suspended_scope',[])
            for record in related:
                if (record['status']=='failed' or record.get('route_data',{}).get('local_failure')) and record['brief'].get('schema_version')==2:
                    for scope in current.get('scope',[]):
                        if scope_matches({'scope':[scope]},record['brief']) and scope not in suspended:suspended.append(scope)
            current['suspended_scope']=suspended
            current['outcomes']={'accepted_tasks':accepted,'completed_tasks':len(related)}
            if saved is not None and saved>0 and job['status']=='accepted' and not job['native_task_id'] and not route.get('local_failure'):
                scopes=[s for s in current.get('scope',[]) if job['brief'].get('schema_version')==2 and scope_matches({'scope':[s]},job['brief'])]
                if not scopes and route.get('assessment'):
                    brief=job['brief']
                    scopes=[{'capability':brief['capability'],**{k:brief['task_requirements'][k] for k in ('language','complexity','context_bucket')},
                             'max_input_bytes':len(canonical({'contract':brief['behavior_contract'],'files':brief['files'],'editable_paths':brief['editable_paths']}).encode())}]
                current['benefit_evidence']={'credible':True,'kind':'usage_proxy','native_overhead':sum(counts),
                                            'job_id':job_id,'subscription_savings':'unknown',
                                            'scope':scopes}
            elif saved is not None and saved<=0:
                current['benefit_evidence']={'credible':False,'kind':'usage_proxy','job_id':job_id,'subscription_savings':'unknown'}
            atomic_json(store.root/'profiles'/(identifier+'.json'),current)
        return {'job_id':job_id,'status':job['status'],'accepted_tasks':accepted,
                'usage_proxy_saved_tokens':saved,'subscription_savings':'unknown'}


def record_capacity(state_dir, assessment_id, receipt):
    if _assessment(state_dir, assessment_id).get('schema_version') == 1: raise ValueError('assessment_single_slot_only')
    from .capacity import qualify_measurements, available_budget, machine_snapshot
    if (not isinstance(receipt,dict) or set(receipt)!={'context_length','resources','batches'}
            or not isinstance(receipt['batches'],list) or not isinstance(receipt['resources'],dict)):
        raise ValueError('invalid_capacity_receipt')
    initial_budget=available_budget(receipt['resources'],loaded=True)
    assessment=_assessment(state_dir,assessment_id)
    profile=_profile(state_dir,assessment['profile_id'])
    _policy(state_dir,assessment['owner_reference'])
    if _binding(profile)!=assessment['binding']:raise ValueError('assessment_identity_changed')
    store=Store(state_dir);batches=[];seen=set()
    for batch in receipt['batches']:
        if not isinstance(batch,dict) or set(batch)!={'job_ids','request_bytes','pressure','swapout_delta_bytes'} or not isinstance(batch['job_ids'],list) or not batch['job_ids']:raise ValueError('invalid_capacity_receipt')
        timings=[]
        for identifier in batch['job_ids']:
            job=store.job(identifier)
            if job['status']!='accepted' or job['native_task_id'] or not job['attempt_id']:raise ValueError('capacity_trial_not_accepted')
            permit=job.get('route_data',{}).get('assessment')
            if not permit or authorize_assessment(state_dir,job['brief'],permit)['profile_id']!=profile['profile_id']:raise ValueError('assessment_scope_mismatch')
            if identifier in seen:raise ValueError('capacity_trial_reused')
            seen.add(identifier)
            attempt=store.attempt(job['attempt_id']);instance=store.instance(attempt['instance_key'])
            if instance['data']['config'].get('context_length')!=receipt['context_length']:raise ValueError('capacity_context_mismatch')
            data=attempt['data']
            if not data.get('submitted_at') or not data.get('finished_at') or data['finished_at']<=data['submitted_at']:raise ValueError('capacity_timing_unavailable')
            timings.append((data['submitted_at'],data['finished_at']))
        if min(end for start,end in timings)<=max(start for start,end in timings):raise ValueError('capacity_overlap_unproven')
        batches.append({k:v for k,v in batch.items() if k!='job_ids'}|{'concurrency':len(timings),'task_seconds':[end-start for start,end in timings],'all_correct':True})
    if not initial_budget: raise ValueError('resources_unqualified')
    # Artifact authorization may outlast the observation window for every trial.
    resources=machine_snapshot()
    if (resources.get('machine_fingerprint')!=receipt['resources'].get('machine_fingerprint')
            or resources.get('physical_bytes')!=receipt['resources'].get('physical_bytes')):
        raise ValueError('capacity_machine_changed')
    evidence=qualify_measurements(profile,batches,resources,receipt['context_length'])
    evidence['assessment_id']=assessment_id
    profile['capacity_evidence']=evidence
    atomic_json(Path(state_dir)/'profiles'/(profile['profile_id']+'.json'),profile)
    atomic_json(Path(state_dir)/'assessments'/assessment_id/'capacity.json',receipt)
    atomic_json(Path(state_dir)/'assessments'/assessment_id/'capacity-resources.json',resources)
    return evidence
