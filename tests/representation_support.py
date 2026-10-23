"""Fictional loopback hook receiver; never reads native accounts or transcripts."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PARENT = '0199b0c0-0000-7000-8000-000000000001'
OTHER_PARENT = '0199b0c0-0000-7000-8000-000000000004'
CONTEXT = {'coordinator_chat_id': PARENT, 'role': 'Reviewer', 'specialty': 'Security'}


class Receiver:
    def __init__(self):
        self.events, self.agents = [], {}
        self.accounts = [{'id': '.codex', 'provider': 'codex'}]
        self.reject = self.drop_ack = self.drip_headers = False
        self.get_status, self.raw, self.delay = 200, None, 0
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass

            def send(self, status, value):
                data = json.dumps(value).encode() if owner.raw is None else owner.raw
                if owner.drip_headers:
                    try:
                        self.wfile.write(b'HTTP/1.0 200 OK\r\nX-Drip: ')
                        for _ in range(7):
                            self.wfile.write(b'x'); self.wfile.flush(); time.sleep(.5)
                        self.wfile.write(b'\r\n')
                    except (BrokenPipeError, ConnectionResetError): return
                else: self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Location', '/redirected')
                self.end_headers()
                if owner.delay: time.sleep(owner.delay)
                try: self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError): pass

            def do_GET(self):
                self.send(owner.get_status, {'accounts': owner.accounts, 'agents': list(owner.agents.values()),
                                             'meta': {'version': '1.0.3', 'startedAt': 1}})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.events.append(body)
                e = body['event']; key = body['account'] + ':' + e['agent_id']
                if not owner.reject:
                    if e['hook_event_name'] == 'SubagentStart':
                        owner.agents[key] = {'id': key, 'sessionId': e['agent_id'], 'status': 'working',
                                             'role': e.get('agent_type', 'Subagente'), 'parentId': body['account'] + ':' + e['session_id']}
                    elif e['hook_event_name'] == 'SubagentStop' and key in owner.agents:
                        owner.agents[key]['status'] = 'done'
                if owner.drop_ack:
                    owner.drop_ack = False
                    self.connection.close()
                    return
                self.send(200, {'ok': not owner.reject})

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.endpoint = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(3)
