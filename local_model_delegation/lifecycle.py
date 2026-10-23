"""Consent-bound HTTP loading and verified retirement of external runtimes."""
from contextlib import ExitStack
import time
import uuid
from .contracts import canonical, digest, load_json
from .lmstudio import Runtime, select_loaded
from .profiles import read_config, read_profiles, validate_profile
from .store import Store, atomic_json
from .worker import ownership


def _owner(reference):
    if not isinstance(reference, str) or not reference.strip() or len(reference) > 4096:
        raise ValueError('owner_reference_required')


def _profile(root, identifier):
    profile = next((p for p in read_profiles(root) if p['profile_id'] == identifier), None)
    if not profile or not profile.get('capabilities'): raise ValueError('model_not_approved')
    return validate_profile(profile, profile['capabilities'][0])


def _snapshot(runtime):
    value = runtime.list_models()
    if not isinstance(value, dict) or not isinstance(value.get('models'), list):
        raise ValueError('invalid_model_list')
    keys, instances = set(), set()
    for model in value['models']:
        if (not isinstance(model, dict) or not isinstance(model.get('key'), str)
                or model['key'] in keys or not isinstance(model.get('loaded_instances'), list)):
            raise ValueError('invalid_model_list')
        keys.add(model['key'])
        for instance in model['loaded_instances']:
            if (not isinstance(instance, dict) or not isinstance(instance.get('id'), str)
                    or not instance['id'] or instance['id'] in instances
                    or not isinstance(instance.get('config'), dict)):
                raise ValueError('invalid_model_list')
            instances.add(instance['id'])
    return value


def _loaded(snapshot, exclude=None):
    return {i['id']: {'model': m['key'], 'config': i['config']}
            for m in snapshot['models'] for i in m['loaded_instances'] if i['id'] != exclude}


def endpoint_operation(db, endpoint, exclude=None):
    for row in db.execute("SELECT * FROM model_operations WHERE state NOT IN ('complete','failed')"):
        data = load_json(row['data'])
        if row['operation_id'] != exclude and data.get('endpoint', data.get('profile', {}).get('endpoint', endpoint)) == endpoint:
            return dict(row)
    return None


def _idle(db, endpoint, uncertain_key=None, operation=None):
    for row in db.execute("SELECT a.*,j.profile FROM attempts a JOIN jobs j USING(job_id) WHERE a.state IN ('reserved','submitting','streaming','uncertain')"):
        if load_json(row['profile']).get('endpoint') == endpoint:
            if row['state'] != 'uncertain' or row['instance_key'] != uncertain_key:
                raise ValueError('endpoint_busy')
    if endpoint_operation(db, endpoint, operation): raise ValueError('lifecycle_busy')


def _locks(stack, store, endpoint, model_id):
    for name in ('lifecycle-' + digest(endpoint), 'recovery-' + digest([endpoint, model_id])):
        if not stack.enter_context(ownership(store, name)): raise ValueError('lifecycle_busy')


def _operation(store, identifier):
    with store.db() as db:
        row = db.execute('SELECT * FROM model_operations WHERE operation_id=?', (identifier,)).fetchone()
    return {**dict(row), 'data': load_json(row['data'])} if row else None


def _save(store, identifier, state, data):
    with store.db(write=True) as db:
        db.execute('UPDATE model_operations SET state=?,data=? WHERE operation_id=?',
                   (state, canonical(data), identifier))


def reset_verified(db, instance):
    """An administrative flag alone cannot make an uncertain generation settled."""
    data = load_json(instance['data']) if isinstance(instance['data'], str) else instance['data']
    identifier = data.get('verified_reset')
    row = db.execute("SELECT data FROM model_operations WHERE operation_id=? AND state='complete'", (identifier,)).fetchone()
    if not row: return False
    receipt = load_json(row['data'])
    return (receipt.get('kind') == 'external_reset' and receipt.get('absence_verified') is True
            and receipt.get('instance_key') == instance['instance_key']
            and receipt.get('generation') == instance['generation'] - 1)


def reset_external(state_dir, instance_key, owner_reference):
    """Unload at most once; reconcile only observed absence, never inferred completion."""
    from .updates import _disabled
    _owner(owner_reference)
    store = Store(state_dir)
    identifier = 'external-reset-' + digest([instance_key, owner_reference])
    with ExitStack() as stack:
        _disabled(store.root)
        instance = store.instance(instance_key)
        assessment_identity = None
        try:
            profile = _profile(store.root, instance['data']['profile']['profile_id'])
        except ValueError:
            from .project_runs import reset_profile
            profile = reset_profile(store.root, instance)
            from .profiles import model_identity
            assessment_identity = model_identity(profile)
        previous = instance['data']['profile']
        # Owner-authorized retirement survives scope changes, never runtime identity changes.
        if assessment_identity is None and isinstance(previous.get('approval'), dict):
            previous = {**previous, 'scope': profile['scope'], 'approval': {
                **previous['approval'], **{k: profile['approval'][k]
                                          for k in ('owner_reference', 'timestamp', 'scope')}}}
        if profile != previous: raise ValueError('approval_changed')
        _locks(stack, store, profile['endpoint'], profile['model_id'])
        operation = _operation(store, identifier)
        if operation and operation['state'] == 'complete': return operation['data']['result']
        with store.db() as db:
            _idle(db, profile['endpoint'], instance_key, identifier)
            attempts = [dict(r) for r in db.execute('SELECT * FROM attempts WHERE instance_key=? AND generation=?',
                                                   (instance_key, instance['generation']))]
        for attempt in attempts:
            for name in ('attempt-' + attempt['attempt_id'], 'check-' + attempt['job_id']):
                if not stack.enter_context(ownership(store, name)): raise ValueError('observer_active')
        runtime = Runtime(profile['endpoint'], token_env=profile.get('token_env'))
        before = _snapshot(runtime)
        loaded = select_loaded(before, profile, assessment_identity)
        old_id = instance['data']['instance_id']
        if old_id in _loaded(before) and (not loaded or loaded['instance_id'] != old_id):
            raise ValueError('runtime_binding_mismatch')
        if operation:
            data = operation['data']
            if data['generation'] != instance['generation']: raise ValueError('generation_changed')
        else:
            data = {'kind': 'external_reset', 'endpoint': profile['endpoint'], 'model_id': profile['model_id'],
                    'owner_reference': owner_reference, 'instance_key': instance_key, 'instance_id': old_id,
                    'generation': instance['generation'], 'before': before, 'attempts_before': attempts,
                    'instance_before': instance, 'created_at': time.time(), 'absence_verified': False}
            with store.db(write=True) as db:
                _idle(db, profile['endpoint'], instance_key, identifier)
                db.execute("INSERT INTO model_operations VALUES (?,?,'submitting',?)",
                           (identifier, digest([profile['endpoint'], profile['model_id']]), canonical(data)))
            if old_id in _loaded(before):
                try:
                    data['unload_response'] = runtime.unload(old_id)
                except (OSError, ValueError) as error:
                    data['unload_error'] = type(error).__name__
                _save(store, identifier, 'uncertain', data)
        # Fresh absence is also decisive after an interrupted/lost unload acknowledgement.
        try:
            after = _snapshot(runtime)
        except (OSError, ValueError) as error:
            data['discovery_error'] = type(error).__name__
            _save(store, identifier, 'uncertain', data)
            return {'status': 'uncertain', 'operation_id': identifier}
        if old_id in _loaded(after) or _loaded(data['before'], old_id) != _loaded(after, old_id):
            _save(store, identifier, 'uncertain', data)
            return {'status': 'uncertain', 'operation_id': identifier}
        _disabled(store.root)
        result = {'status': 'retired', 'operation_id': identifier, 'instance_key': instance_key}
        data.update(after=after, absence_verified=True, verified_at=time.time(), result=result)
        with store.db(write=True) as db:
            _idle(db, profile['endpoint'], instance_key, identifier)
            current = db.execute('SELECT * FROM instances WHERE instance_key=?', (instance_key,)).fetchone()
            if current['generation'] != data['generation']: raise ValueError('generation_changed')
            for attempt in db.execute("SELECT * FROM attempts WHERE instance_key=? AND generation=? AND state='uncertain'",
                                      (instance_key, data['generation'])).fetchall():
                evidence = {**load_json(attempt['data']), 'reset_resolution': {
                    'operation_id': identifier, 'previous_state': 'uncertain', 'verified_at': data['verified_at']}}
                db.execute("UPDATE attempts SET state='released',data=? WHERE attempt_id=?", (canonical(evidence), attempt['attempt_id']))
            updated = {**load_json(current['data']), 'recovery_phase': 'retired', 'verified_reset': identifier}
            db.execute("UPDATE instances SET generation=generation+1,state='closed',data=? WHERE instance_key=?", (canonical(updated), instance_key))
            db.execute("UPDATE model_operations SET state='complete',data=? WHERE operation_id=?", (canonical(data), identifier))
        return result


def configure_loading(state_dir, profile_id, owner_reference, context_length):
    _owner(owner_reference)
    if type(context_length) is not int or context_length <= 0: raise ValueError('invalid_context_length')
    store = Store(state_dir)
    with ownership(store, 'loading-policy') as owned:
        if not owned: raise ValueError('lifecycle_busy')
        profile = _profile(store.root, profile_id)
        config = read_config(store.root)
        policy = dict(config.get('loading_policy', {}))
        policy[profile_id] = {'owner_reference': owner_reference, 'approval_digest': digest(profile['approval']),
                              'context_length': context_length, 'parallel': 1}
        config['loading_policy'] = policy
        atomic_json(store.root / 'config.json', config)
    return {'status': 'loading_permitted', 'profile_id': profile_id}


def _consent(store, profile):
    policy = read_config(store.root).get('loading_policy', {}).get(profile['profile_id'])
    if (not isinstance(policy, dict) or set(policy) != {'owner_reference','approval_digest','context_length','parallel'}
            or policy.get('approval_digest') != digest(profile['approval'])
            or type(policy.get('context_length')) is not int or policy['context_length'] <= 0
            or type(policy.get('parallel')) is not int or policy['parallel'] != 1):
        raise ValueError('loading_consent_required')
    _owner(policy['owner_reference'])
    return policy


def _register_loaded(store, profile, loaded, operation=None):
    key = digest([profile['endpoint'], profile['model_id'], loaded['instance_id']])
    with store.db(write=True) as db:
        row = db.execute('SELECT * FROM instances WHERE instance_key=?', (key,)).fetchone()
        if row and row['state'] != 'ready' and not reset_verified(db, row):
            raise ValueError('instance_closed')
        data = {**loaded, 'profile': profile, 'artifact_digest': profile['artifact']['digest']}
        if row:
            old = load_json(row['data'])
            if row['state'] == 'ready' and old['profile'] != profile: raise ValueError('approval_changed')
            if 'verified_reset' in old: data['verified_reset'] = old['verified_reset']
            if row['state'] == 'ready' and old.get('config') == loaded['config'] and old.get('owned_operation_id'):
                data['owned_operation_id'] = old['owned_operation_id']
        if operation: data['owned_operation_id'] = operation
        if row:
            db.execute("UPDATE instances SET state='ready',data=? WHERE instance_key=?", (canonical(data), key))
        else:
            db.execute("INSERT INTO instances VALUES (?,0,'ready',?)", (key, canonical(data)))


def ensure_loaded(state_dir, profile_id):
    from .capacity import inference_available, pressure_snapshot
    store = Store(state_dir)
    profile = _profile(store.root, profile_id)
    policy = _consent(store, profile)
    with ExitStack() as stack:
        _locks(stack, store, profile['endpoint'], profile['model_id'])
        with store.db() as db:
            pending = endpoint_operation(db, profile['endpoint'])
            if pending: return {'status': 'uncertain', 'operation_id': pending['operation_id']}
            _idle(db, profile['endpoint'])
        runtime = Runtime(profile['endpoint'], token_env=profile.get('token_env'))
        before = _snapshot(runtime)
        loaded = select_loaded(before, profile)
        if loaded:
            if loaded['config'].get('context_length') != policy['context_length'] or loaded['capacity'] != 1:
                raise ValueError('loaded_configuration_mismatch')
            _register_loaded(store, profile, loaded)
            return {'status': 'loaded', 'loaded': loaded}
        if _loaded(before): raise ValueError('runtime_not_empty')
        # Validate the unloaded entry too; discovery must match the approved local index.
        from .profiles import verify_runtime_binding
        models = [m for m in before['models'] if m['key'] == profile['model_id']]
        if len(models) != 1: raise ValueError('model_unavailable')
        verify_runtime_binding(profile, models[0])
        if not inference_available(pressure_snapshot()): raise ValueError('resources_unavailable')
        if _consent(store, profile) != policy: raise ValueError('loading_consent_required')
        identifier = 'load-' + uuid.uuid4().hex
        data = {'kind': 'load', 'endpoint': profile['endpoint'], 'model_id': profile['model_id'],
                'profile': profile, 'policy': policy, 'before': before, 'created_at': time.time(),
                'ownership_verified': False}
        with store.db(write=True) as db:
            _idle(db, profile['endpoint'])
            db.execute("INSERT INTO model_operations VALUES (?,?,'submitting',?)",
                       (identifier, digest([profile['endpoint'], profile['model_id']]), canonical(data)))
        try:
            response = runtime.load({'model': profile['model_id'], 'context_length': policy['context_length'], 'echo_load_config': True})
            data['response'] = response
            _save(store, identifier, 'uncertain', data)
            after = _snapshot(runtime)
            loaded = select_loaded(after, profile)
            if (not loaded or not isinstance(response, dict) or response.get('status') != 'loaded' or response.get('type') != 'llm'
                    or response.get('instance_id') != loaded['instance_id']
                    or loaded['config'].get('context_length') != policy['context_length']
                    or loaded['capacity'] != 1 or len(_loaded(after)) != 1):
                raise ValueError('loaded_configuration_mismatch')
            if _consent(store, profile) != policy: raise ValueError('loading_consent_required')
            data.update(after=after, instance_id=loaded['instance_id'], ownership_verified=True, verified_at=time.time())
            _register_loaded(store, profile, loaded, identifier)
            _save(store, identifier, 'complete', data)
            return {'status': 'loaded', 'loaded': loaded, 'operation_id': identifier}
        except (OSError, ValueError) as error:
            data['error'] = str(error) if isinstance(error, ValueError) else type(error).__name__
            _save(store, identifier, 'uncertain', data)
            return {'status': 'uncertain', 'operation_id': identifier, 'reason': data['error']}


def reconcile_load(state_dir, operation_id):
    """Read-only discovery can settle a load; a lost response cannot establish ownership."""
    store = Store(state_dir)
    operation = _operation(store, operation_id)
    if not operation or operation['data'].get('kind') != 'load' or 'policy' not in operation['data']:
        raise ValueError('unsupported_load_operation')
    if operation['state'] == 'complete': return {'status': 'complete', 'operation_id': operation_id}
    data = operation['data']
    profile = _profile(store.root, data['profile']['profile_id'])
    if profile != data['profile'] or _consent(store, profile) != data['policy']:
        raise ValueError('loading_consent_required')
    with ExitStack() as stack:
        _locks(stack, store, profile['endpoint'], profile['model_id'])
        with store.db() as db: _idle(db, profile['endpoint'], operation=operation_id)
        snapshot = _snapshot(Runtime(profile['endpoint'], token_env=profile.get('token_env')))
        loaded = select_loaded(snapshot, profile)
        if (not loaded or len(_loaded(snapshot)) != 1 or loaded['capacity'] != 1
                or loaded['config'].get('context_length') != data['policy']['context_length']):
            return {'status': 'uncertain', 'operation_id': operation_id}
        # On reconciliation we observe presence, not who loaded this possibly reused identifier.
        data.update(after=snapshot, instance_id=loaded['instance_id'], ownership_verified=False,
                    reconciled_at=time.time(), resolution='observed_loaded_without_ownership')
        _register_loaded(store, profile, loaded)
        _save(store, operation_id, 'complete', data)
        return {'status': 'loaded', 'loaded': loaded, 'operation_id': operation_id, 'ownership_verified': False}
