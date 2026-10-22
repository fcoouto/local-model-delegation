"""Optional presentation through unchanged Habblaud hooks; never execution authority."""
import http.client
import re
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit
from .contracts import canonical, load_json
from .profiles import read_config
from .store import Store, atomic_json, private_dir

ROLES = {'Coordinator', 'Scout', 'Builder', 'Tester', 'Reviewer', 'Scribe', 'Investigator'}
LIMITATIONS = ['inherited_codex_provider', 'completion_is_not_verification',
               'labels_may_be_clipped', 'unmeasured_tokens', 'native_statistics_and_world']


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
    return status(state_dir, job_id)


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
        try:
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
            return load_json(b''.join(chunks).decode('utf-8'))
        except (OSError, http.client.HTTPException, UnicodeError):
            raise ValueError('habblaud_unavailable') from None
        finally: connection.close()

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
        if self.request('/api/codex/events', {'account': account, 'event': event}) != {'ok': True}:
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
    return result
