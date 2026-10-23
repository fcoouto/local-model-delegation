"""Versioned repository fixtures; scheduling and acceptance remain in the existing campaign."""
from pathlib import Path
import tempfile

from .contracts import canonical, digest, safe_path, positive, COMPLEXITIES, validate_fallback
from .repository_context import snapshot, validate_snapshot, context_action, apply_edits, RESPONSE_BYTES
from .container_checks import validate_environment, validate_check
from .store import private_dir

MAX_CONTEXT_TURNS = 12


def _fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError('invalid_repository_contract')


def descriptor(value):
    _fields(value, 'root manifest')
    if not isinstance(value['root'], str):
        raise ValueError('invalid_repository_root')
    validate_snapshot(Path(value['root']), value['manifest'])
    return value


def validate_execution(execution):
    _fields(execution, 'schema_version source public_assets private_assets setup_source environment editable_paths criteria public_checks private_checks reference_edits review_reference max_cycles budget')
    if type(execution['schema_version']) is not int or execution['schema_version'] != 2:
        raise ValueError('invalid_repository_execution')
    for name in ('source', 'public_assets', 'private_assets'):
        descriptor(execution[name])
    if execution['setup_source'] is not None:
        descriptor(execution['setup_source'])
    validate_environment(execution['environment'])
    if (type(execution['max_cycles']) is not int or not 1 <= execution['max_cycles'] <= 3
            or not isinstance(execution['review_reference'], str) or not execution['review_reference'].strip()):
        raise ValueError('invalid_repository_execution')
    from .project_runs import validate_budget
    validate_budget(execution['budget'])
    if any(not isinstance(execution[k],list) for k in ('public_checks','private_checks')):
        raise ValueError('invalid_repository_checks')
    _policy(execution['source'], execution['editable_paths'], execution['criteria'],
            execution['public_checks'] + execution['private_checks'], execution['environment'], execution['setup_source'])
    if not execution['public_checks'] or not execution['private_checks']:
        raise ValueError('project_behavior_checks_required')
    apply_edits(Path(execution['source']['root']), execution['source']['manifest'],
                execution['editable_paths'], execution['reference_edits'])
    return execution


def _policy(source, editable, criteria, checks, environment, setup):
    if (not isinstance(editable, list) or not 1 <= len(editable) <= 64
            or any(not isinstance(p, str) for p in editable) or len(set(editable)) != len(editable)
            or not isinstance(criteria, list) or not 1 <= len(criteria) <= 64
            or any(not isinstance(c, str) or not c.strip() or len(c) > 4096 for c in criteria)
            or not isinstance(checks, list) or not 1 <= len(checks) <= 64):
        raise ValueError('invalid_repository_policy')
    from .repository_context import _names
    _names(Path(source['root']), list(dict.fromkeys([*source['manifest']['files'], *editable])))
    ids = []
    for check in checks:
        validate_check(check, environment, setup)
        ids.append(check['id'])
    if len(set(ids)) != len(ids):
        raise ValueError('invalid_repository_checks')


def validate_brief(brief):
    _fields(brief, 'schema_version origin_chat_id task_key capability source_root files editable_paths behavior_contract task_requirements acceptance fallback repository')
    if (type(brief['schema_version']) is not int or brief['schema_version'] != 3
            or brief['capability'] not in ('code_change', 'test_writing')
            or not isinstance(brief['origin_chat_id'], str) or not brief['origin_chat_id'].startswith('assessment-')):
        raise ValueError('repository_assessment_required')
    for key in ('origin_chat_id', 'task_key', 'behavior_contract'):
        if not isinstance(brief[key], str) or not 1 <= len(brief[key]) <= 20000:
            raise ValueError('invalid_brief')
    validate_fallback(brief['fallback'])
    requirements = brief['task_requirements']
    if (not isinstance(requirements, dict) or set(requirements) - {'max_output_tokens'} !=
            {'language','complexity','context_bucket','urgency','wait_budget_seconds'}):
        raise ValueError('invalid_requirements')
    import re
    if (requirements['complexity'] not in COMPLEXITIES or requirements['urgency'] != 'normal'
            or not positive(requirements['wait_budget_seconds'])
            or any(not isinstance(requirements[k], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', requirements[k])
                   for k in ('language','context_bucket'))
            or ('max_output_tokens' in requirements and (type(requirements['max_output_tokens']) is not int
                                                        or requirements['max_output_tokens'] <= 0))):
        raise ValueError('invalid_requirements')
    repo = brief['repository']
    _fields(repo, 'manifest context context_turns environment public_assets private_assets setup_source public_check_ids')
    source = descriptor({'root':brief['source_root'],'manifest':repo['manifest']})
    if brief['files'] != repo['manifest']['files']:
        raise ValueError('source_hash_mismatch')
    if (type(repo['context_turns']) is not int or not 0 <= repo['context_turns'] <= MAX_CONTEXT_TURNS
            or not isinstance(repo['context'], list) or not 1 <= len(repo['context']) <= 2
            or any(len(canonical(item).encode()) > RESPONSE_BYTES for item in repo['context'])):
        raise ValueError('invalid_repository_context')
    for name in ('public_assets', 'private_assets'):
        descriptor(repo[name])
    if repo['setup_source'] is not None:
        descriptor(repo['setup_source'])
    validate_environment(repo['environment'])
    acceptance = brief['acceptance']
    _fields(acceptance, 'method criteria protected_paths checks')
    if acceptance['method'] != 'native_verified' or acceptance['protected_paths'] != []:
        raise ValueError('invalid_acceptance')
    _policy(source, brief['editable_paths'], acceptance['criteria'], acceptance['checks'],
            repo['environment'], repo['setup_source'])
    ids = repo['public_check_ids']
    if (not isinstance(ids, list) or not ids or any(not isinstance(n, str) for n in ids)
            or len(set(ids)) != len(ids) or not set(ids) < {c['id'] for c in acceptance['checks']}):
        raise ValueError('invalid_repository_checks')
    return brief


def model_input(brief):
    repo = brief['repository']
    return {'contract':brief['behavior_contract'], 'editable_paths':brief['editable_paths'],
            'workspace_digest':repo['manifest']['digest'], 'context':repo['context'],
            'remaining_context_turns':MAX_CONTEXT_TURNS-repo['context_turns'],
            'context_policy':'Only the latest two views are retained. Reread evicted source when needed.'}


PROTOCOL = ('Return one JSON object. Request source with {"action":"list","directory":"","offset":0}, '
            '{"action":"read","path":"file.py","offset":0}, or '
            '{"action":"search","paths":["file.py"],"query":"literal","offset":0}. '
            'Offsets and next cursors are bytes for reads and result indexes for list/search. '
            'Use exact returned continuation cursors. Each response is bounded at 32 KiB. '
            'Alternatively submit {"action":"submit","summary":"...","edits":[{"path":"file.py",'
            '"sha256":"whole-file base hash","changes":[{"old":"unique exact text","new":"replacement"}]}]}. '
            'All changes match the same base file, without overlaps. New allowed files use sha256 null and one empty old string. '
            'No shell, network or tests are available to you. Never claim checks were executed.')


def copy_source(source, destination, replacements=None):
    descriptor(source)
    manifest = snapshot(Path(source['root']), list(source['manifest']['files']), destination)
    for name, text in (replacements or {}).items():
        path = safe_path(destination, name)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.write_text(text); path.chmod(0o600)
    if replacements:
        files = {**manifest['files']}
        from .contracts import text_hash
        for name, text in replacements.items():
            files[name] = {'size':len(text.encode()),'sha256':text_hash(text)}
        manifest = {'schema_version':1,'files':files,'digest':digest(files)}
    validate_snapshot(destination, manifest)
    return {'root':str(destination),'manifest':manifest}


def build_trial(state_dir, identifier, domain, task, profile, cycle, *, source=None, context=None, context_turns=0, feedback=''):
    execution = validate_execution(task['execution'])
    trial_id = task['id'] + '-cycle-' + str(cycle) + '-context-' + str(context_turns)
    parent = private_dir(Path(state_dir)/'assessments'/identifier)
    target = parent/trial_id
    source = source or execution['source']
    if target.exists():
        candidate = {'root':str(target),'manifest':source['manifest']}
        descriptor(candidate)
        source = candidate
    else:
        source = copy_source(source,target)
    if context is None:
        context = [context_action(Path(source['root']),source['manifest'],{'action':'list','directory':'','offset':0})]
    brief = {'schema_version':3,'origin_chat_id':'assessment-'+identifier,'task_key':trial_id,
             'capability':domain['capability'],'source_root':source['root'],'files':source['manifest']['files'],
             'editable_paths':execution['editable_paths'],'behavior_contract':task['contract']+feedback,
             'task_requirements':{'language':domain['language'],'complexity':task['difficulty'],
                                  'context_bucket':task['context_bucket'],'urgency':'normal','wait_budget_seconds':120},
             'acceptance':{'method':'native_verified','criteria':execution['criteria'],'protected_paths':[],
                           'checks':execution['public_checks']+execution['private_checks']},
             'fallback':profile['fallback'],
             'repository':{'manifest':source['manifest'],'context':context[-2:],'context_turns':context_turns,
                           'environment':execution['environment'],'public_assets':execution['public_assets'],
                           'private_assets':execution['private_assets'],'setup_source':execution['setup_source'],
                           'public_check_ids':[c['id'] for c in execution['public_checks']]}}
    # Reserve both maximum views, protocol, edit policy, feedback and template overhead before consent.
    reserve = (2*RESPONSE_BYTES + len((PROTOCOL+task['contract']+canonical(execution['editable_paths'])).encode()) + 8192)
    budget = execution['budget']
    allowance = min(budget['output_ceiling'],budget['context_length']-reserve)
    if allowance <= 0:
        raise ValueError('assessment_context_unfit')
    brief['task_requirements']['max_output_tokens'] = allowance
    validate_brief(brief)
    return {'trial_id':trial_id,'case_id':task['id'],'domain_id':domain['id'],'cycle':cycle,
            'context_turns':context_turns,'brief':brief,'brief_hash':digest(brief),
            'deadline_seconds':2*(budget['prefill_seconds']+allowance/budget['decode_tokens_per_second'])}


def run_checks(state_dir, source_root, execution, checks):
    from .container_checks import run_check
    outcomes, reasons = {}, {}
    public = {c['id'] for c in execution['public_checks']}
    for check in checks:
        assets = execution['public_assets'] if check['id'] in public else execution['private_assets']
        descriptor(assets)
        setup = execution['setup_source']
        if setup is not None:
            descriptor(setup)
        observation = run_check(state_dir,source_root,Path(assets['root']),check,execution['environment'],
                                setup_root=Path(setup['root']) if setup else None)
        outcomes[check['id']] = (observation['returncode'] == 0 and observation['reason'] is None
                                  and observation['cleanup'] == 'verified_absent')
        reasons[check['id']] = observation['reason']
    return outcomes, reasons


def verify_references(state_dir, task):
    execution = validate_execution(task['execution'])
    from .assessment_storage import workspace_root
    parent = private_dir(workspace_root(state_dir)/'reference-checks')
    results = {}
    for variant in ('base','reference'):
        with tempfile.TemporaryDirectory(dir=parent) as directory:
            edits = (apply_edits(Path(execution['source']['root']),execution['source']['manifest'],
                                 execution['editable_paths'],execution['reference_edits']) if variant == 'reference' else {})
            source = copy_source(execution['source'],Path(directory)/'source',edits)
            outcomes, reasons = run_checks(state_dir,Path(source['root']),execution,
                                          execution['public_checks']+execution['private_checks'])
            if any(reasons.values()):
                raise ValueError('verification_unsupported')
            results[variant] = outcomes
    if not all(results['reference'].values()) or all(results['base'][c['id']] for c in execution['private_checks']):
        raise ValueError('project_reference_failed')
    return {'verified':True,'checks':results,'review_reference':execution['review_reference'],
            'execution_digest':digest(execution)}


def verification_identity(brief):
    """Pin checker inputs and the explicit local engine, independently of model context."""
    from .container_checks import Docker
    from .profiles import fingerprint_artifact
    repo = brief['repository']
    spec = validate_environment(repo['environment'])
    for name in ('public_assets','private_assets','setup_source'):
        if repo[name] is not None:
            descriptor(repo[name])
    binary = Path(spec['docker_binary']).resolve()
    identity = {'environment':spec,'docker':fingerprint_artifact(binary.parent,[binary.name]),
                'assets':{name:repo[name] for name in ('public_assets','private_assets','setup_source')}}
    with tempfile.TemporaryDirectory() as directory:
        docker = Docker(spec,Path(directory).resolve())
        for image in (spec['image'],spec['postgres_image']):
            if image and docker.call(['image','inspect','--format','{{.Id}}',image])['stdout'].strip() != image:
                raise ValueError('container_image_changed')
        identity['engine'] = docker.call(['info','--format','{{.ID}} {{.ServerVersion}}'])['stdout'].strip()
    return identity


def execution_from_brief(brief):
    repo = brief['repository']
    return {**{k:repo[k] for k in ('public_assets','private_assets','setup_source','environment')},
            'public_checks':[c for c in brief['acceptance']['checks'] if c['id'] in repo['public_check_ids']]}


def advance(state_dir, record, trial, job):
    """Called under the existing campaign lock after job/attempt/runtime authorization."""
    from .validation import _response, _candidate_json, parse_proposal, prepare_verification
    from .project_runs import _task, _save
    from .store import Store
    store = Store(state_dir)
    domain, task = _task(record,trial['case_id'])
    text, candidate_hash = _response(store,job)
    try:
        value = _candidate_json(text)
    except ValueError:
        value = None
    source = {'root':trial['brief']['source_root'],'manifest':trial['brief']['repository']['manifest']}
    turns, cycle = trial['context_turns'], trial['cycle']
    views = trial['brief']['repository']['context']
    is_context = isinstance(value,dict) and value.get('action') != 'submit'
    feedback = trial['brief']['behavior_contract'][len(task['contract']):]
    if is_context:
        if turns >= MAX_CONTEXT_TURNS:
            store.select_fallback(job['job_id'],'context_budget_exhausted')
            return {'assessment_id':record['assessment_id'],'trial_id':None,'reason':'context_budget_exhausted'}
        turns += 1
        try:
            outcomes = context_action(Path(source['root']),source['manifest'],value)
        except ValueError:
            outcomes = {'error':'invalid_context_action'}
        views = [*views,outcomes][-2:]
    else:
        if cycle >= task['execution']['max_cycles']:
            raise ValueError('assessment_cycle_limit')
        cycle += 1
        try:
            parse_proposal(text,trial['brief'])
        except ValueError:
            outcomes = {'format':'invalid_proposal'}
        else:
            session = prepare_verification(state_dir,job['job_id'])
            source = {'root':session['stage'],'manifest':session['repository_manifest']}
            outcomes, reasons = run_checks(state_dir,Path(source['root']),task['execution'],task['execution']['public_checks'])
            if any(reasons.values()):
                raise ValueError('verification_unsupported')
        feedback = '\nPublic check results (no private checks were run): '+canonical(outcomes)
        if len(feedback.encode()) > 1024:
            raise ValueError('assessment_feedback_too_large')
        # Submitted edits make previous hashes/views stale; restart the public index deterministically.
        views = None
    child = build_trial(state_dir,record['assessment_id'],domain,task,record['profile_snapshot'],cycle,
                        source=source,context=views,context_turns=turns,feedback=feedback)
    child.update(parent_job_id=job['job_id'],parent_candidate_hash=candidate_hash,feedback_digest=digest(outcomes))
    record['cycle_receipts'][trial['trial_id']] = {
        'job_id':job['job_id'],'case_id':trial['case_id'],'candidate_hash':candidate_hash,
        'public_checks':outcomes,'operation':'context' if is_context else 'proposal',
        'next_trial_id':child['trial_id']}
    record['trials'].append(child)
    _save(state_dir,record)
    with store.db(write=True) as db:
        db.execute("UPDATE jobs SET status='failed',reason='assessment_cycle_revised' WHERE job_id=?",(job['job_id'],))
    return {'assessment_id':record['assessment_id'],'trial_id':child['trial_id']}
