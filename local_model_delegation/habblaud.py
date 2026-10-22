"""Optional presentation through unchanged Habblaud hooks; never execution authority."""
import http.client
import re
import socket
import threading
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from .contracts import canonical, load_json
from .profiles import read_config
from .store import Store, atomic_json, private_dir

ROLES = {'Coordinator', 'Scout', 'Builder', 'Tester', 'Reviewer', 'Scribe', 'Investigator'}
LIMITATIONS = ['inherited_codex_provider', 'completion_is_not_verification',
               'labels_may_be_clipped', 'model_stats_unavailable', 'unmeasured_tokens', 'native_statistics_and_world']


def thread_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', value):
        raise ValueError('invalid_coordinator_chat_id')
    return str(uuid.UUID(value))


def validate_context(value):
    if (not isinstance(value, dict) or 'coordinator_chat_id' not in value
            or set(value) - {'coordinator_chat_id', 'role', 'specialty'}):
        raise ValueError('invalid_visibility_context')
    result = {**value, 'coordinator_chat_id': thread_id(value['coordinator_chat_id'])}
    if 'role' in value and (not isinstance(value['role'], str) or value['role'] not in ROLES):
        raise ValueError('invalid_assignment_role')
    if 'specialty' in value and (not isinstance(value['specialty'], str)
            or not value['specialty'].strip() or len(value['specialty']) > 4096):
        raise ValueError('invalid_assignment_specialty')
    return result


def bind_context(db, job_id, context, rebind=False):
    if context is None: return
    context = validate_context(context)
    row = db.execute('SELECT route_data FROM jobs WHERE job_id=?', (job_id,)).fetchone()
    if row is None: raise ValueError('unknown_job')
    route = load_json(row['route_data']); saved = route.get('habblaud', {})
    previous = saved.get('context')
    if previous == context: return
    if previous and (not rebind or (saved.get('labels_locked') and any(
            previous.get(k) != context.get(k) for k in ('role', 'specialty')))):
        raise ValueError('visibility_context_conflict')
    route['habblaud'] = {**saved, 'context': context}
    db.execute('UPDATE jobs SET route_data=? WHERE job_id=?', (canonical(route), job_id))


def bind(state_dir, job_id, context):
    store = Store(state_dir)
    with store.db(write=True) as db: bind_context(db, job_id, context, rebind=True)
    result = status(state_dir, job_id)
    result['observer'] = ensure_observer(state_dir, job_id)
    return result


class Client:
    def __init__(self, endpoint):
        try:
            parsed = urlsplit(endpoint)
            if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', '::1')
                    or parsed.username is not None or parsed.password is not None
                    or parsed.path not in ('', '/') or parsed.query or parsed.fragment
                    or not 1 <= (parsed.port or 80) <= 65535):
                raise ValueError('unsupported_habblaud_endpoint')
        except (TypeError, AttributeError, ValueError):
            raise ValueError('unsupported_habblaud_endpoint') from None
        self.endpoint = endpoint.rstrip('/')
        self.host, self.port = parsed.hostname, parsed.port or 80

    def request(self, path, value=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=2)
        limit = 2 * 1024 * 1024 if value is None else 65536
        body = None if value is None else canonical(value).encode()
        if body is not None and len(body) > 65536: raise ValueError('habblaud_event_too_large')
        deadline = time.monotonic() + 2
        expired = threading.Event(); timer = response = None
        try:
            connection.connect()
            wire = connection.sock
            def expire():
                expired.set()
                try: wire.shutdown(socket.SHUT_RDWR)
                except OSError: pass
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise ValueError('habblaud_timeout')
            # Capture the socket: HTTP/1.0 responses detach it from the connection.
            timer = threading.Timer(remaining, expire); timer.daemon = True; timer.start()
            connection.request('GET' if body is None else 'POST', path, body=body,
                               headers={'Content-Type': 'application/json'})
            response = connection.getresponse()
            if response.status != 200: raise ValueError('habblaud_http_error')
            if response.length is not None and response.length > limit: raise ValueError('habblaud_response_too_large')
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise ValueError('habblaud_timeout')
                if connection.sock: connection.sock.settimeout(remaining)
                chunk = response.read1(min(65536, limit + 1 - size))
                if not chunk: break
                chunks.append(chunk); size += len(chunk)
                if size > limit: raise ValueError('habblaud_response_too_large')
            if expired.is_set() or time.monotonic() >= deadline: raise ValueError('habblaud_timeout')
            return load_json(b''.join(chunks).decode('utf-8'))
        except (OSError, http.client.HTTPException, UnicodeError):
            raise ValueError('habblaud_timeout' if expired.is_set() else 'habblaud_unavailable') from None
        finally:
            if timer: timer.cancel()
            if response: response.close()
            connection.close()

    def snapshot(self, account):
        value = self.request('/api/snapshot')
        if (not isinstance(value, dict) or not isinstance(value.get('accounts'), list)
                or not isinstance(value.get('agents'), list) or not isinstance(value.get('meta'), dict)
                or not all(isinstance(a, dict) for a in value['agents'])):
            raise ValueError('incompatible_habblaud_snapshot')
        matches = [a for a in value['accounts'] if isinstance(a, dict)
                   and a.get('id') == account and a.get('provider') == 'codex']
        if len(matches) != 1: raise ValueError('habblaud_account_unavailable')
        return value

    def event(self, account, event):
        result = self.request('/api/codex/events', {'account': account, 'event': event})
        if not isinstance(result, dict) or set(result) != {'ok'} or result['ok'] is not True:
            raise ValueError('habblaud_event_rejected')


def configure(state_dir, endpoint, account):
    if not isinstance(account, str) or not account.strip() or len(account) > 200 or account != account.strip():
        raise ValueError('invalid_habblaud_account')
    client = Client(endpoint); client.snapshot(account)
    root = private_dir(Path(state_dir))
    from .visibility import _lock
    with _lock(root):
        config = read_config(root)
        config['habblaud'] = {'enabled': True, 'endpoint': client.endpoint, 'account': account}
        atomic_json(root/'config.json', config)
    return status(root)


def _receipt_path(root, job_id):
    if not isinstance(job_id, str) or not re.fullmatch('[a-f0-9]{32}', job_id): raise ValueError('invalid_job_id')
    return Path(root)/'habblaud'/f'{job_id}.json'


def _read_receipt(root, job_id):
    path = _receipt_path(root, job_id)
    if path.is_symlink() or path.parent.is_symlink(): raise ValueError('unsafe_visibility')
    try:
        if path.stat().st_size > 65536: raise ValueError('oversized_visibility_receipt')
        return load_json(path.read_text())
    except FileNotFoundError: return {}


def status(state_dir, job_id=None):
    config = read_config(state_dir); target = config.get('habblaud', {})
    result = {'enabled': target.get('enabled') is True and config.get('visibility_enabled', True) is True,
              'configured': bool(target.get('endpoint')), 'limitations': LIMITATIONS,
              **{k: target[k] for k in ('endpoint', 'account') if k in target}}
    if job_id is not None:
        receipt = _read_receipt(state_dir, job_id)
        result['job_id'] = job_id
        result['observation'] = {k: receipt[k] for k in ('state', 'phase', 'error', 'agent_id', 'last_sent_at') if k in receipt}
        if receipt.get('binding', {}).get('model'):
            result['observation']['model'] = receipt['binding']['model']
    return result


def _phase(job, attempt, now):
    if not attempt or attempt['state'] == 'reserved': return None, False
    state = attempt['state']
    if state == 'uncertain': return 'Execution status unknown', False
    if state in ('submitting', 'streaming'):
        observed = attempt['data'].get('last_event_at', attempt['data'].get('submitted_at', attempt['data'].get('created')))
        import math
        if (type(observed) not in (int, float) or not math.isfinite(observed)
                or now - observed > job['profile'].get('stale_tolerance_seconds', 120)):
            return 'Execution status unknown', False
    if job.get('native_task_id') or job['status'] in (
            'fallback_required', 'fallback_dispatching', 'dispatch_uncertain', 'fallback_running'):
        return 'Native fallback', False
    if job['status'] == 'accepted': return 'Verified', False
    if job['status'] in ('failed', 'needs_reassessment'): return 'Failed or scope changed', False
    if state in ('submitting', 'streaming'):
        return ('Starting' if state == 'submitting' else 'Generating'), True
    if state == 'complete' and job['status'] in ('candidate_ready', 'checking'):
        return 'Awaiting verification', True
    return 'Execution status unknown', False


def _binding(store, job_id, target):
    # Freeze only presentation metadata. No execution clocks or brief fields change.
    locked = store.job(job_id)['route_data'].get('habblaud', {}).get('labels_locked') is True
    with store.db(write=not locked) as db:
        job = store._job(db.execute('SELECT * FROM jobs WHERE job_id=?', (job_id,)).fetchone())
        route = job['route_data']; saved = route.get('habblaud', {})
        context = validate_context(saved.get('context', {'coordinator_chat_id': job['brief']['origin_chat_id']}))
        model = job['profile'].get('model_id')
        if not isinstance(model, str) or not model.strip() or len(model) > 4096:
            raise ValueError('unsupported_habblaud_label')
        clean = lambda text: ' '.join(''.join(c if c.isprintable() else ' ' for c in text).split())
        display = job['profile'].get('display_name')
        if not display:
            parts = re.split(r'[-_\s]+', model.strip())
            display = ' '.join(re.sub(r'(\d)b$', r'\1B', part[:1].upper()+part[1:]) for part in parts)
        if not isinstance(display, str) or not display.strip() or len(display) > 4096:
            raise ValueError('unsupported_habblaud_label')
        label = context.get('role', 'Unspecified role')+' · '+clean(display)
        if 'guardian' in label.lower(): raise ValueError('unsupported_habblaud_label')
        if not saved.get('labels_locked'):
            route['habblaud'] = {'context': context, 'labels_locked': True}
            db.execute('UPDATE jobs SET route_data=? WHERE job_id=?', (canonical(route), job_id))
    identity = [str(store.root), job_id, job['attempt_id'], target['endpoint'], target['account'], context['coordinator_chat_id']]
    return {'endpoint': target['endpoint'], 'account': target['account'], 'parent': context['coordinator_chat_id'],
            'agent_id': str(uuid.uuid5(uuid.NAMESPACE_URL, canonical(identity))), 'label': label,
            'cwd': job['brief']['source_root'], 'model': model}


def _event(binding, name, phase=None):
    value = {'hook_event_name': name, 'session_id': binding['parent'], 'agent_id': binding['agent_id'],
             'agent_type': binding['label'], 'cwd': binding['cwd']}
    if phase is not None:
        value.update(tool_name=phase, tool_use_id=binding['agent_id']+':'+phase, tool_input={})
    return value


class Observer:
    def __init__(self, state_dir, job_id):
        self.store = Store(state_dir)
        self.path = _receipt_path(self.store.root, job_id)
        self.job_id = job_id
        self.receipt = _read_receipt(self.store.root, job_id)

    def save(self):
        atomic_json(self.path, self.receipt)

    def stop(self, phase, now):
        binding = self.receipt.get('binding')
        if binding and self.receipt.get('may_exist') and self.receipt.get('state') != 'stopped':
            try:
                client = Client(binding['endpoint']); snapshot = client.snapshot(binding['account'])
                if any(a.get('id') == binding['account']+':'+binding['agent_id']
                       and a.get('status') not in ('done', 'offline') for a in snapshot['agents']):
                    if phase: client.event(binding['account'], _event(binding, 'PreToolUse', phase))
                    client.event(binding['account'], _event(binding, 'SubagentStop'))
                self.receipt.pop('error', None)
                self.receipt['last_sent_at'] = now
            except (ValueError, OSError):
                # shortcut: an unavailable receiver expires the entry; hooks offer no neutral removal.
                self.receipt['error'] = 'habblaud_stop_unconfirmed'
        if self.receipt:
            self.receipt.update(state='stopped', phase=phase)
            self.save()
        return False

    def step(self, now=None):
        now = time.time() if now is None else now
        config = read_config(self.store.root); target = config.get('habblaud', {})
        if config.get('visibility_enabled', True) is not True or target.get('enabled') is not True:
            return self.stop('Visibility disabled', now)
        job = self.store.job(self.job_id)
        attempt = self.store.attempt(job['attempt_id']) if job.get('attempt_id') else None
        phase, active = _phase(job, attempt, now)
        if not active: return self.stop(phase, now)
        if now < self.receipt.get('next_retry_at', 0): return True
        try:
            binding = _binding(self.store, self.job_id, target)
            previous = self.receipt.get('binding')
            if previous and previous != binding:
                self.stop('Coordinator binding changed', now)
                self.receipt = {}
            if (self.receipt.get('state') == 'active' and self.receipt.get('phase') == phase
                    and now - self.receipt.get('last_sent_at', 0) < 20): return True
            if not self.receipt.get('binding'):
                self.receipt = {'binding': binding, 'agent_id': binding['agent_id'], 'state': 'pending'}
                self.save()
            client = Client(binding['endpoint']); snapshot = client.snapshot(binding['account'])
            existing = next((a for a in snapshot['agents'] if a.get('id') == binding['account']+':'+binding['agent_id']), None)
            created = not existing or existing.get('status') in ('done', 'offline')
            if created:
                self.receipt['may_exist'] = True; self.save()
                client.event(binding['account'], _event(binding, 'SubagentStart'))
            else:
                if existing.get('parentId') != binding['account']+':'+binding['parent'] or existing.get('role') != binding['label']:
                    raise ValueError('habblaud_binding_mismatch')
                self.receipt['may_exist'] = True
            if created or self.receipt.get('phase') != phase:
                client.event(binding['account'], _event(binding, 'PreToolUse', phase))
            else: client.event(binding['account'], _event(binding, 'SessionStart'))
            self.receipt.update(state='active', phase=phase, last_sent_at=now, next_retry_at=0, failures=0)
            self.receipt.pop('error', None); self.save()
            return True
        except (ValueError, OSError, KeyError, TypeError) as error:
            code = str(error)
            allowed = {'unsupported_habblaud_label', 'invalid_coordinator_chat_id', 'habblaud_account_unavailable',
                       'habblaud_event_rejected', 'habblaud_binding_mismatch', 'unsupported_habblaud_endpoint'}
            code = code if code in allowed else 'habblaud_unavailable'
            failures = min(self.receipt.get('failures', 0) + 1, 5)
            self.receipt.update(state='error', error=code, failures=failures, next_retry_at=now+min(20, 2**failures))
            self.save()
            return code not in ('unsupported_habblaud_label', 'invalid_coordinator_chat_id', 'unsupported_habblaud_endpoint')


def run_observer(state_dir, job_id):
    from .worker import ownership
    store = Store(state_dir); _receipt_path(store.root, job_id)
    with ownership(store, 'habblaud-'+job_id) as owned:
        if not owned: return 0
        from .visibility import _lock
        with _lock(store.root):
            if not status(state_dir)['enabled']: return 0
            observer = Observer(state_dir, job_id)
            observer.save()
        try:
            while observer.step(): time.sleep(1)
        except (OSError, ValueError, KeyError, TypeError):
            observer.stop('Observation unavailable', time.time())
    return 0


def ensure_observer(state_dir, job_id):
    # This is called from execution paths: all observability failures are nonfatal.
    try:
        if not status(state_dir)['enabled']: return {'state': 'disabled'}
        from .worker import ownership, launch
        store = Store(state_dir); job = store.job(job_id)
        attempt = store.attempt(job['attempt_id']) if job.get('attempt_id') else None
        if not _phase(job, attempt, time.time())[1]: return {'state': 'inactive'}
        from .visibility import _lock
        with _lock(store.root):
            if not status(state_dir)['enabled']: return {'state': 'disabled'}
            with ownership(store, 'habblaud-'+job_id) as owned:
                if not owned: return {'state': 'observing'}
            pid = launch(state_dir, 'habblaud-observer', job_id)
        return {'state': 'starting', 'pid': pid}
    except Exception:
        return {'state': 'unavailable', 'error': 'habblaud_observer_unavailable'}


def disable(state_dir):
    root = private_dir(Path(state_dir))
    from .visibility import _lock
    with _lock(root):
        config = read_config(root)
        config['habblaud'] = {**config.get('habblaud', {}), 'enabled': False}
        atomic_json(root/'config.json', config)
    return status(root)


def quiesce(state_dir):
    """Stop only owned display observers before a package-state snapshot."""
    root = Path(state_dir)
    if 'habblaud' not in read_config(root): return
    disable(root)
    from .worker import ownership
    store = Store(root); deadline = time.monotonic()+8
    while True:
        busy = False
        for path in (root/'habblaud').glob('*.json'):
            _receipt_path(root, path.stem)
            with ownership(store, 'habblaud-'+path.stem) as owned:
                if not owned: busy = True
        if not busy: return
        if time.monotonic() >= deadline: raise ValueError('habblaud_observer_busy')
        time.sleep(.1)
