"""Project campaigns share the existing queue, model transport and native verifier."""
import copy
from contextlib import contextmanager
from datetime import datetime, timezone
import math
from pathlib import Path
import tempfile
import uuid

from .contracts import canonical, digest, load_json, safe_path, text_hash, validate_brief, positive
from .project_assessment import project_preview, _fields, _text
from .store import Store, atomic_json, private_dir


def _save(state_dir, record):
    atomic_json(Path(state_dir) / 'assessments' / record['assessment_id'] / 'assessment.json', record)


def _write_files(root, files):
    for name, content in files.items():
        target = safe_path(root, name)
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.write_text(content)
        target.chmod(0o600)


def _execution(task):
    execution = task['execution']
    if execution is None:
        raise ValueError('project_execution_required')
    if execution.get('schema_version') == 2:
        from .repository_runs import validate_execution
        return validate_execution(execution)
    _fields(execution, 'files editable_paths criteria public_checks private_files private_checks reference_files review_reference max_cycles budget',
            'invalid_project_execution')
    for name in ('files', 'private_files', 'reference_files'):
        files = execution[name]
        if (not isinstance(files, dict) or len(files) > 8
                or any(not isinstance(v, str) or '\0' in v or len(v.encode()) > 100000 for v in files.values())):
            raise ValueError('invalid_project_execution')
        for path in files:
            safe_path(Path('/'), path)
    if (not execution['files'] or set(execution['files']) & set(execution['private_files'])
            or not isinstance(execution['editable_paths'], list)
            or not set(execution['editable_paths']) <= set(execution['files'])
            or not set(execution['reference_files']) <= set(execution['editable_paths'])
            or type(execution['max_cycles']) is not int or not 1 <= execution['max_cycles'] <= 3):
        raise ValueError('invalid_project_execution')
    _text(execution['review_reference'])
    validate_budget(execution['budget'])
    return execution


def validate_budget(budget):
    _fields(budget, 'context_length output_ceiling prefill_seconds decode_tokens_per_second measurement_reference',
            'invalid_project_budget')
    if (any(type(budget[k]) is not int or budget[k] <= 0 for k in ('context_length', 'output_ceiling'))
            or not positive(budget['decode_tokens_per_second'])
            or type(budget['prefill_seconds']) not in (int, float)
            or not math.isfinite(budget['prefill_seconds']) or budget['prefill_seconds'] < 0):
        raise ValueError('invalid_project_budget')
    _text(budget['measurement_reference'])
    return budget


def _checks(root, checks):
    from .validation import run_isolated
    result = {}
    for check in checks:
        executable = Path(check['argv'][0])
        if not executable.is_file():
            raise ValueError('verification_unsupported')
        cwd = root if check['cwd'] == '.' else safe_path(root, check['cwd'])
        code = 'import os\nos.chdir(' + repr(str(cwd)) + ')\nos.execv(' + repr(str(executable)) + ',' + repr(check['argv']) + ')\n'
        observation = run_isolated(root, code, check['timeout_seconds'], (str(executable.resolve().parent),))
        if observation['reason'] is not None:
            raise ValueError('verification_unsupported')
        result[check['id']] = observation['returncode'] == 0
    return result


def verify_references(state_dir, task):
    """Run frozen base/reference checks; semantic review remains independently native."""
    execution = _execution(task)
    if execution.get('schema_version') == 2:
        from .repository_runs import verify_references as verify_repository
        return verify_repository(state_dir, task)
    from .validation import _qualified_isolation
    if (execution['public_checks'] or execution['private_checks']) and not _qualified_isolation():
        raise ValueError('isolation_unsupported')
    parent = private_dir(Path(state_dir) / 'project-reference-checks')
    observations = {}
    for variant in ('base', 'reference'):
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            root = Path(directory)
            files = {**execution['files'], **execution['private_files']}
            if variant == 'reference':
                files.update(execution['reference_files'])
            _write_files(root, files)
            observations[variant] = _checks(root, execution['public_checks'] + execution['private_checks'])
    if (not all(observations['reference'].values())
            or (execution['private_checks'] and all(observations['base'][c['id']] for c in execution['private_checks']))):
        raise ValueError('project_reference_failed')
    return {'verified': True, 'checks': observations, 'review_reference': execution['review_reference'],
            'execution_digest': digest(execution)}


def _brief(state_dir, identifier, domain, task, profile, cycle, files=None, feedback=''):
    execution = _execution(task)
    if execution.get('schema_version') == 2:
        from .repository_runs import build_trial
        return build_trial(state_dir, identifier, domain, task, profile, cycle)
    trial_id = task['id'] + '-cycle-' + str(cycle)
    root = private_dir(Path(state_dir) / 'assessments' / identifier / trial_id)
    _write_files(root, files)
    brief = {'schema_version': 2, 'origin_chat_id': 'assessment-' + identifier, 'task_key': trial_id,
             'capability': domain['capability'], 'source_root': str(root),
             'files': {n: {'content': t, 'sha256': text_hash(t)} for n, t in files.items()},
             'editable_paths': execution['editable_paths'],
             'behavior_contract': task['contract'] + feedback,
             'task_requirements': {'language': domain['language'], 'complexity': task['difficulty'],
                                   'context_bucket': task['context_bucket'], 'urgency': 'normal', 'wait_budget_seconds': 120},
             'acceptance': {'method': 'native_verified', 'criteria': execution['criteria'], 'protected_paths': [],
                            'checks': execution['public_checks'] + execution['private_checks']},
             'fallback': profile['fallback']}
    if domain['capability'] != 'file_summary' and not execution['private_checks']:
        raise ValueError('project_behavior_checks_required')
    if domain['capability'] == 'python_code_change':
        raise ValueError('project_requires_native_verification')
    validate_brief(brief)
    from .worker import build_model_request
    request = build_model_request(brief, profile, 'preview')
    # Reserve public feedback separately; future source growth is rechecked before each cycle.
    input_bound = len((request['system_prompt'] + request['input']).encode()) + 2048 + 1024
    allowance = min(execution['budget']['output_ceiling'], execution['budget']['context_length'] - input_bound)
    if allowance <= 0:
        raise ValueError('assessment_context_unfit')
    brief['task_requirements']['max_output_tokens'] = allowance
    validate_brief(brief)
    deadline = 2 * (execution['budget']['prefill_seconds']
                    + allowance / execution['budget']['decode_tokens_per_second'])
    return {'trial_id': trial_id, 'case_id': task['id'], 'domain_id': domain['id'], 'cycle': cycle,
            'brief': brief, 'brief_hash': digest(brief), 'deadline_seconds': deadline}


def prepare_project_run(state_dir, profile_id, project_root, pack, owner_reference):
    from .onboarding import _profile, _binding, _verification_snapshot
    from .profiles import validate_profile_fields
    from .lmstudio import Runtime, select_loaded
    from .package import pin_runtime_bundle
    preview = project_preview(project_root, pack, owner_reference)
    source = _profile(state_dir, profile_id)
    source_binding = _binding(source)
    if source_binding['runtime']['metadata']['format'] not in ('gguf', 'mlx', 'splash'):
        raise ValueError('assessment_model_unsupported')
    loaded = select_loaded(Runtime(source['endpoint'], token_env=source.get('token_env')).list_models(), source, source_binding['runtime'])
    if loaded is None:
        raise ValueError('assessment_model_unavailable')
    identifier = uuid.uuid4().hex
    profile = copy.deepcopy(source)
    profile.update(profile_id='assessment-' + identifier, approval=None, scope=[], qualification_status='needs_assessment')
    for key in ('loading_permission', 'suspended_scope', 'benefit_evidence', 'outcomes'):
        profile.pop(key, None)
    ceilings = [_execution(t)['budget']['output_ceiling'] for d in pack['domains'] for t in d['assignments']]
    profile['request_settings']['max_output_tokens'] = max(ceilings)
    trials, references = [], {}
    for domain in pack['domains']:
        validate_profile_fields(profile, domain['capability'])
        if domain['capability'] not in profile['capabilities']:
            raise ValueError('assessment_scope_unsupported')
        for task in domain['assignments']:
            execution = _execution(task)
            if execution['budget']['context_length'] != loaded['config'].get('context_length'):
                raise ValueError('assessment_runtime_changed')
            trials.append(_brief(state_dir, identifier, domain, task, profile, 1, execution.get('files')))
            references[task['id']] = verify_references(state_dir, task)
    binding = _binding(profile)
    from .worker import context_fits
    if any(not context_fits(t['brief'], profile, loaded) for t in trials):
        raise ValueError('assessment_context_unfit')
    verification = _verification_snapshot(trials)
    bundle = pin_runtime_bundle(state_dir)
    preview.update(status='prepared', ready_for_assessment=True, project_root=str(Path(project_root).resolve()),
                   profile_id=profile['profile_id'], source_profile_id=profile_id,
                   binding=binding, profile_digest=digest(profile), loaded_config=loaded['config'],
                   prepared_at=datetime.now(timezone.utc).isoformat(), concurrency=1,
                   max_submissions=sum(t['execution']['max_cycles'] + (12 if t['execution'].get('schema_version') == 2 else 0) for d in pack['domains'] for t in d['assignments']),
                   initial_trials=[{'trial_id': t['trial_id'], 'brief_hash': t['brief_hash'],
                                    'deadline_seconds': t['deadline_seconds']} for t in trials],
                   runtime_bundle=bundle.name, verification=verification, reference_checks=references,
                   comparison_protocol={'feedback': 'public checks only', 'native_limits': 'not enforced by this helper',
                                        'tool_parity': 'supplied files and isolated checks; disclose every asymmetry',
                                        'subset': [next(t['id'] for t in d['assignments'] if t['difficulty'] == level)
                                                   for d in pack['domains'] for level in ('moderate', 'complex')][:2],
                                        'comparison_boundary': 'first_cycle', 'max_cycles': 1},
                   timing_policy='Generation deadlines exclude queue wait; each check has its own frozen timeout. '
                                 'Record complete elapsed work separately; interruption is inconclusive.')
    if any(t['brief']['schema_version'] == 3 for t in trials):
        preview['repository_protocol'] = {'context_turns_per_assignment':12,'proposals_per_assignment':3,
                                          'response_bytes':32768,'retained_views':2,
                                          'approval_supported':False}
        preview['comparison_protocol']['tool_parity'] = 'Same frozen public source, bounded context actions and one proposal; disclose every asymmetry.'
    preview.pop('preview_digest', None)
    preview_digest = digest(preview)
    record = {'schema_version': 2, 'assessment_id': identifier, 'profile_id': profile['profile_id'],
              'permit_token': uuid.uuid4().hex + uuid.uuid4().hex, 'binding': binding,
              'profile_snapshot': profile, 'source_profile': {'profile_id': profile_id, 'binding': source_binding,
                                                            'approval_at_preparation': source.get('approval')},
              'pack': copy.deepcopy(pack), 'preview': preview, 'preview_digest': preview_digest,
              'trials': trials, 'receipts': {}, 'cycle_receipts': {},
              'authorization': {'mode': 'run', 'state': 'draft', 'owner_reference': None,
                                'timestamp': None, 'preview_digest': preview_digest}}
    atomic_json(Path(state_dir) / 'profiles' / (profile['profile_id'] + '.json'), profile)
    _save(state_dir, record)
    return {'assessment_id': identifier, 'state': 'draft', 'preview': preview, 'preview_digest': preview_digest}


def validate_record(record, identifier):
    try:
        preview = record['preview']
        if (record['assessment_id'] != identifier or digest(preview) != record['preview_digest']
                or record['authorization']['preview_digest'] != record['preview_digest']
                or record['authorization']['mode'] != 'run'
                or record['authorization']['state'] not in ('draft', 'authorized', 'paused', 'stopped', 'invalidated', 'complete')
                or digest(record['pack']) != preview['pack_digest']
                or digest(record['profile_snapshot']) != preview['profile_digest']
                or record['profile_snapshot']['profile_id'] != record['profile_id']
                or record['binding'] != preview['binding']):
            raise ValueError('invalid_assessment_record')
        authorization = record['authorization']
        if authorization['state'] in ('authorized', 'paused', 'complete'):
            _text(authorization['owner_reference'])
            datetime.fromisoformat(authorization['timestamp'])
        initial = []
        previous = {}
        seen = set()
        for trial in record['trials']:
            validate_brief(trial['brief'])
            if (digest(trial['brief']) != trial['brief_hash'] or trial['trial_id'] in seen
                    or trial['brief']['task_key'] != trial['trial_id']
                    or trial['brief']['origin_chat_id'] != 'assessment-' + identifier):
                raise ValueError('invalid_assessment_record')
            domain, task = _task(record, trial['case_id'])
            if (trial['domain_id'] != domain['id'] or type(trial['cycle']) is not int
                    or not 1 <= trial['cycle'] <= task['execution']['max_cycles']
                    or trial['trial_id'] != task['id'] + '-cycle-' + str(trial['cycle']) +
                    ('-context-' + str(trial.get('context_turns')) if trial['brief']['schema_version'] == 3 else '')
                    or not positive(trial['deadline_seconds'])):
                raise ValueError('invalid_assessment_record')
            parent = previous.get(task['id'])
            repository = trial['brief']['schema_version'] == 3
            if repository and (trial.get('context_turns') != trial['brief']['repository']['context_turns']):
                raise ValueError('invalid_assessment_record')
            if trial['cycle'] > 1 or (repository and trial['context_turns'] > 0):
                receipt = record['cycle_receipts'][parent['trial_id']]
                context_step = repository and receipt.get('operation') == 'context'
                if (trial['cycle'] != parent['cycle'] + (0 if context_step else 1)
                        or (repository and trial['context_turns'] != parent['context_turns'] + (1 if context_step else 0))
                        or trial['deadline_seconds'] != parent['deadline_seconds']
                        or receipt['next_trial_id'] != trial['trial_id']
                        or receipt['case_id'] != trial['case_id']
                        or receipt['job_id'] != trial['parent_job_id']
                        or receipt['candidate_hash'] != trial['parent_candidate_hash']
                        or digest(receipt['public_checks']) != trial['feedback_digest']):
                    raise ValueError('invalid_assessment_record')
            elif parent is not None:
                raise ValueError('invalid_assessment_record')
            previous[task['id']] = trial
            seen.add(trial['trial_id'])
            if trial['cycle'] == 1 and (not repository or trial['context_turns'] == 0):
                initial.append({k: trial[k] for k in ('trial_id', 'brief_hash', 'deadline_seconds')})
        if (initial != preview['initial_trials'] or len(seen) > preview['max_submissions']
                or set(record['receipts']) & set(record['cycle_receipts'])
                or not set(record['receipts']) | set(record['cycle_receipts']) <= seen):
            raise ValueError('invalid_assessment_record')
    except (KeyError, TypeError, AttributeError, ValueError):
        raise ValueError('invalid_assessment_record') from None
    return record


def check_bindings(state_dir, record, *, check_runtime=False):
    from .onboarding import _profile, _binding, _verification_snapshot
    from .package import runtime_contents, validate_bundle
    profile = _profile(state_dir, record['profile_id'])
    preview = record['preview']
    if digest(profile) != preview['profile_digest'] or _binding(profile) != record['binding']:
        raise ValueError('assessment_identity_changed')
    project_preview(Path(preview['project_root']), record['pack'], preview['owner_reference'])
    bundle = Path(state_dir).resolve() / 'runtimes' / preview['runtime_bundle']
    validate_bundle(bundle, preview['runtime_bundle'])
    source = Path(__file__).resolve().parents[1]
    running_digest = source.name if source == bundle else digest(runtime_contents(source)[1])
    if running_digest != preview['runtime_bundle']:
        raise ValueError('assessment_helper_changed')
    if _verification_snapshot(record['trials']) != preview['verification']:
        raise ValueError('assessment_checker_changed')
    if check_runtime:
        from .lmstudio import Runtime, select_loaded
        from .worker import context_fits
        loaded = select_loaded(Runtime(profile['endpoint'], token_env=profile.get('token_env')).list_models(), profile, record['binding']['runtime'])
        if loaded is None:
            raise ValueError('assessment_model_unavailable')
        if loaded['config'] != preview['loaded_config']:
            raise ValueError('assessment_runtime_changed')
        if any(not context_fits(t['brief'], profile, loaded) for t in record['trials']):
            raise ValueError('assessment_context_unfit')
        from .validation import _qualified_isolation
        if any(t['brief']['schema_version'] == 2 and t['brief']['acceptance']['checks'] for t in record['trials']) and not _qualified_isolation():
            raise ValueError('isolation_unsupported')
    return profile


def authorize(state_dir, record, brief, permit, *, purpose='submit', job=None):
    if not any(t['brief_hash'] == digest(brief) for t in record['trials']):
        raise ValueError('assessment_scope_mismatch')
    if purpose == 'submit':
        state = record['authorization']['state']
        if state != 'authorized':
            raise ValueError('assessment_consent_required' if state == 'draft' else 'assessment_' + state)
        profile = check_bindings(state_dir, record)
    else:
        if brief['task_key'] in record['cycle_receipts']:
            raise ValueError('assessment_cycle_revised')
        from .onboarding import _verification_snapshot
        if _verification_snapshot(record['trials']) != record['preview']['verification']:
            raise ValueError('assessment_checker_changed')
        profile = record['profile_snapshot']
        if (not job or not job.get('attempt_id') or job.get('native_task_id')
                or job.get('profile') != profile or job.get('brief') != brief
                or job.get('route_data', {}).get('assessment') != permit):
            raise ValueError('assessment_scope_mismatch')
        store = Store(state_dir, read_only=True)
        persisted = store.job(job['job_id'])
        attempt = store.attempt(job['attempt_id'])
        from .profiles import generation_settings
        if (persisted != job or attempt['job_id'] != job['job_id'] or not attempt['data'].get('submitted_at')
                or attempt['data'].get('request_settings') != generation_settings(brief, profile)):
            raise ValueError('assessment_scope_mismatch')
    from .validation import source_matches
    if not source_matches(brief):
        raise ValueError('assessment_scope_mismatch')
    return profile


def report(state_dir, record, *, check_current=False):
    from .onboarding import _run_jobs, _trial_observation
    store = Store(state_dir, read_only=True) if (Path(state_dir) / 'state.sqlite3').exists() else None
    jobs = {t['trial_id']: j for t, j in _run_jobs(store, record)} if store else {}
    counts = dict.fromkeys(('planned', 'passed', 'failed', 'unfinished', 'not_run', 'pending'), 0)
    results = []
    for domain in record['pack']['domains']:
        for task in domain['assignments']:
            trials = [t for t in record['trials'] if t['case_id'] == task['id']]
            trial = trials[-1]
            job = jobs.get(trial['trial_id'])
            receipt = next((r for r in record['receipts'].values() if r['case_id'] == task['id']), None)
            disposition = receipt['disposition'] if receipt else 'pending' if job else 'not_run'
            counts['planned'] += 1
            counts[disposition] += 1
            results.append({'case_id': task['id'], 'domain_id': domain['id'], 'difficulty': task['difficulty'],
                            'origin': task['origin'], 'disposition': disposition, 'cycles': trial['cycle'],
                            'context_turns': trial.get('context_turns',0),
                            'observation': _trial_observation(store, job) if job else None})
    freshness = 'unverified'
    if check_current:
        try: check_bindings(state_dir, record, check_runtime=True)
        except (ValueError, OSError): freshness = 'stale_or_unavailable'
        else: freshness = 'current'
    from .project_reports import summarize
    return {'schema_version': 2, **summarize(record, results), 'freshness': freshness, 'assessment_id': record['assessment_id'], 'state': record['authorization']['state'],
            'project': record['preview']['project'], 'counts': counts, 'assignments': results,
            'limitations': ['Project evidence is provisional; approval and routing are separate.',
                                                      'Speed does not determine capability.']}


def progress(store, record):
    from .onboarding import _run_jobs, _trial_blocker
    jobs = _run_jobs(store, record)
    settled = set(record['receipts']) | set(record['cycle_receipts'])
    pending, blockers, seen = [], [], set()
    for trial, job in jobs:
        seen.add(trial['trial_id'])
        if trial['trial_id'] in settled:
            continue
        pending.append(job['job_id'])
        reason = _trial_blocker(store, job)
        if reason:
            blockers.append({'job_id': job['job_id'], 'reason': reason})
    unsubmitted = [t for t in record['trials'] if t['trial_id'] not in seen]
    unsubmitted.sort(key=lambda t: -t['cycle'])
    return {'assessment_id': record['assessment_id'], 'state': record['authorization']['state'],
            'pending_jobs': pending, 'blockers': blockers,
            'next_trial_id': unsubmitted[0]['trial_id'] if unsubmitted and not pending and not blockers
            and record['authorization']['state'] == 'authorized' else None}


def _task(record, case_id):
    for domain in record['pack']['domains']:
        for task in domain['assignments']:
            if task['id'] == case_id:
                return domain, task
    raise ValueError('unknown_trial')


def advance_cycle(state_dir, assessment_id, job_id):
    from .onboarding import _assessment
    from .worker import ownership
    from .validation import prepare_verification, _proposal, InvalidProposal
    store = Store(state_dir)
    with ownership(store, 'assessment-' + assessment_id) as owned:
        if not owned:
            raise ValueError('assessment_busy')
        record = _assessment(state_dir, assessment_id)
        if record.get('schema_version') != 2:
            raise ValueError('project_assessment_required')
        previous = next((t for t in record['trials'] if t.get('parent_job_id') == job_id), None)
        if previous:
            return {'assessment_id': assessment_id, 'trial_id': previous['trial_id']}
        if record['authorization']['state'] != 'authorized':
            raise ValueError('assessment_' + record['authorization']['state'])
        check_bindings(state_dir, record, check_runtime=True)
        job = store.job(job_id)
        trial = next((t for t in record['trials'] if t['brief_hash'] == digest(job['brief'])), None)
        if not trial:
            raise ValueError('assessment_scope_mismatch')
        authorize(state_dir, record, job['brief'], {k: record[k] for k in ('assessment_id', 'permit_token')}, purpose='verify', job=job)
        if (job['status'] not in ('candidate_ready', 'checking')
                or store.attempt(job['attempt_id'])['state'] != 'complete'):
            raise ValueError('candidate_not_ready')
        domain, task = _task(record, trial['case_id'])
        execution = task['execution']
        if trial['brief']['schema_version'] != 3 and trial['cycle'] >= execution['max_cycles']:
            raise ValueError('assessment_cycle_limit')
        job_root = store.root / 'jobs' / job_id
        if any((job_root / name).exists() for name in ('project-finalizing.json', 'native-checks.json')):
            raise ValueError('assessment_already_finalizing')
        if trial['brief']['schema_version'] == 3:
            from .repository_runs import advance
            return advance(state_dir, record, trial, job)
        try:
            proposal, candidate_hash = _proposal(store, job)
        except InvalidProposal:
            candidate_hash = load_json(Path(job['result_path']).read_text())['sha256']
            proposal, outcomes = {}, {'format': 'invalid_proposal'}
        else:
            session = prepare_verification(state_dir, job_id)
            outcomes = _checks(Path(session['stage']), execution['public_checks'])
        feedback = '\nPublic check results (no private checks were run): ' + canonical(outcomes)
        if len(feedback.encode()) > 1024:
            raise ValueError('assessment_feedback_too_large')
        files = {n: item['content'] for n, item in trial['brief']['files'].items()}
        files.update(proposal.get('files', {}))
        child = _brief(state_dir, assessment_id, domain, task, record['profile_snapshot'], trial['cycle'] + 1, files, feedback)
        if child['brief']['task_requirements']['max_output_tokens'] != trial['brief']['task_requirements']['max_output_tokens']:
            raise ValueError('assessment_context_unfit')
        child.update(parent_job_id=job_id, parent_candidate_hash=candidate_hash, feedback_digest=digest(outcomes))
        receipt = {'job_id': job_id, 'case_id': trial['case_id'], 'candidate_hash': candidate_hash,
                   'public_checks': outcomes, 'next_trial_id': child['trial_id']}
        record['cycle_receipts'][trial['trial_id']] = receipt
        record['trials'].append(child)
        # Save lineage before retiring the parent; repeating the operation never creates a second child.
        _save(state_dir, record)
        with store.db(write=True) as db:
            db.execute("UPDATE jobs SET status='failed',reason='assessment_cycle_revised' WHERE job_id=?", (job_id,))
        return {'assessment_id': assessment_id, 'trial_id': child['trial_id']}


def prepare_hidden_checks(state_dir, job, session):
    """Finalization is durable before any held-out fixture reaches the check stage."""
    permit = job.get('route_data', {}).get('assessment')
    if not permit:
        return
    from .onboarding import _assessment
    record = _assessment(state_dir, permit['assessment_id'])
    if record.get('schema_version') != 2:
        return
    trial = next(t for t in record['trials'] if t['brief_hash'] == digest(job['brief']))
    _, task = _task(record, trial['case_id'])
    atomic_json(Path(state_dir) / 'jobs' / job['job_id'] / 'project-finalizing.json',
                {'candidate_hash': session['candidate_hash'], 'trial_id': trial['trial_id']})
    if task['execution'].get('schema_version') != 2:
        _write_files(Path(session['stage']), task['execution']['private_files'])


def record_final(state_dir, record, receipt):
    """Called while the existing assessment lock is held."""
    from .onboarding import _trial_blocker, _trial_observation
    _fields(receipt, 'trial_id job_id', 'invalid_trial_receipt')
    store = Store(state_dir)
    trial = next((t for t in record['trials'] if t['trial_id'] == receipt['trial_id']), None)
    job = store.job(receipt['job_id'])
    if not trial or trial['brief_hash'] != digest(job['brief']) or trial['trial_id'] in record['cycle_receipts']:
        raise ValueError('assessment_scope_mismatch')
    authorize(state_dir, record, job['brief'], {k: record[k] for k in ('assessment_id', 'permit_token')}, purpose='verify', job=job)
    if job['status'] not in ('accepted', 'failed', 'fallback_required'):
        raise ValueError('trial_not_complete')
    reset = verified_termination(store, job)
    if _trial_blocker(store, job) and not reset:
        raise ValueError('trial_unresolved')
    disposition = ('unfinished' if reset else 'passed' if job['status'] == 'accepted' else 'unfinished'
                   if job['reason'] in ('output_budget_exhausted', 'context_budget_exhausted', 'project_verification_incomplete') else 'failed')
    value = {**receipt, 'case_id': trial['case_id'], 'disposition': disposition,
             'passed': disposition == 'passed', **_trial_observation(store, job)}
    existing = record['receipts'].get(trial['trial_id'])
    if existing and existing != value:
        raise ValueError('trial_conflict')
    record['receipts'][trial['trial_id']] = value
    if len(record['receipts']) == record['preview']['assignment_count'] and record['authorization']['state'] in ('authorized', 'paused'):
        record['authorization']['state'] = 'complete'
    _save(state_dir, record)
    return report(state_dir, record)


def execution_deadline(state_dir, job):
    permit = job.get('route_data', {}).get('assessment')
    if not permit:
        return None
    from .onboarding import _assessment
    record = _assessment(state_dir, permit['assessment_id'])
    if record.get('schema_version') != 2:
        return None
    trial = next((t for t in record['trials'] if t['brief_hash'] == digest(job['brief'])), None)
    if not trial:
        raise ValueError('assessment_scope_mismatch')
    return trial['deadline_seconds']


@contextmanager
def verification_lock(state_dir, job_id):
    """Serialize final checks/receipts against public-feedback continuation."""
    from .onboarding import _assessment
    from .worker import ownership
    store = Store(state_dir)
    permit = store.job(job_id).get('route_data', {}).get('assessment')
    if not permit or _assessment(state_dir, permit['assessment_id']).get('schema_version') != 2:
        yield
        return
    with ownership(store, 'assessment-' + permit['assessment_id']) as owned:
        if not owned:
            raise ValueError('assessment_busy')
        yield


def reset_profile(state_dir, instance):
    """Explicit reset permission can retire a paused campaign, never load or approve it."""
    from .onboarding import _assessment, _profile, _binding
    identifier = instance['data']['profile']['profile_id']
    if not identifier.startswith('assessment-'):
        raise ValueError('model_not_approved')
    record = _assessment(state_dir, identifier.removeprefix('assessment-'))
    profile = _profile(state_dir, identifier)
    if (record.get('schema_version') != 2 or record['profile_id'] != identifier
            or record['authorization']['state'] not in ('paused', 'stopped', 'invalidated', 'complete')
            or profile != record['profile_snapshot'] or _binding(profile) != record['binding']):
        raise ValueError('assessment_scope_mismatch')
    return profile


def verified_termination(store, job):
    attempt = store.attempt(job['attempt_id'])
    resolution = attempt['data'].get('reset_resolution') or {}
    if attempt['state'] != 'released' or resolution.get('previous_state') != 'uncertain':
        return False
    with store.db() as db:
        row = db.execute("SELECT data FROM model_operations WHERE operation_id=? AND state='complete'",
                         (resolution.get('operation_id'),)).fetchone()
    if not row:
        return False
    operation = load_json(row['data'])
    return (operation.get('kind') == 'external_reset' and operation.get('absence_verified') is True
            and operation.get('instance_key') == attempt['instance_key']
            and operation.get('generation') == attempt['generation']
            and any(a.get('attempt_id') == job['attempt_id'] for a in operation.get('attempts_before', [])))


def record_check_observation(state_dir, job_id, session, checks, reasons):
    job = Store(state_dir).job(job_id)
    permit = job.get('route_data', {}).get('assessment')
    if not permit:
        return
    from .onboarding import _assessment
    if _assessment(state_dir, permit['assessment_id']).get('schema_version') == 2:
        atomic_json(Path(state_dir) / 'jobs' / job_id / 'project-checks.json',
                    {'session_token': session['session_token'], 'candidate_hash': session['candidate_hash'],
                     'checks': checks, 'reasons': reasons})


def checks_incomplete(state_dir, job, session, checks):
    permit = job.get('route_data', {}).get('assessment')
    if not permit:
        return False
    from .onboarding import _assessment
    if _assessment(state_dir, permit['assessment_id']).get('schema_version') != 2 or not session['acceptance']['checks']:
        return False
    path = Path(state_dir) / 'jobs' / job['job_id'] / 'project-checks.json'
    if not path.is_file():
        raise ValueError('project_checks_required')
    observed = load_json(path.read_text())
    if (observed['session_token'] != session['session_token'] or observed['candidate_hash'] != session['candidate_hash']
            or observed['checks'] != checks):
        raise ValueError('verification_mismatch')
    return any(reason is not None for reason in observed['reasons'].values())
