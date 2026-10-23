"""Disposable fictional profiles and source; no real model approvals."""
import copy
import hashlib
import json
import tempfile
import unittest
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import REPO_ROOT
from pathlib import Path

BUGGY = 'def normalize(value):\n    return value.lstrip()\n'
FIXED = 'def normalize(value):\n    return value.strip()\n'
SUPPLIED = '''import unittest
from helper import normalize

class Supplied(unittest.TestCase):
    def test_leading(self):
        self.assertEqual(normalize(" a"), "a")
'''
ADDED = '''
    def test_trailing(self):
        self.assertEqual(normalize("a "), "a")
'''
ORACLE = '''import unittest
from helper import normalize
class Oracle(unittest.TestCase):
    def test_both(self):
        self.assertEqual(normalize(" a "), "a")
'''


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.state = self.root / "state"
        self.project = self.root / "project"
        self.project.mkdir()
        for name, text in {"helper.py": BUGGY, "test_helper.py": SUPPLIED}.items():
            (self.project / name).write_text(text)
        self.artifact = self.root / "artifact"
        self.artifact.mkdir()
        (self.artifact / "weights.bin").write_bytes(b"fictional weights version one")

    def profile(self):
        from local_model_delegation.profiles import fingerprint_artifact
        identity = fingerprint_artifact(self.artifact, ["weights.bin"])
        settings = {"reasoning": "on", "temperature": 0, "max_output_tokens": 1024}
        catalog = self.root / "runtime-catalog.json"
        catalog.write_text(json.dumps({"models": [{"defaultIdentifier": "fictional-model",
            "indexedModelIdentifier": "test/fictional-model", "autoIdentifiers": [],
            "concreteModelDirAbsolutePath": str(self.artifact),
            "allFiles": [{"absPath": str(self.artifact / "weights.bin")}],
            "format": "fictional", "arch": "fictional", "user": "test", "params": "1B",
            "quant": {"name": "4bit", "bits": 4}}], "conflicts": [], "errors": []}))
        catalog.chmod(0o600)
        profile = {
            "runtime_catalog": str(catalog),
            "schema_version": 2, "profile_id": "fictional", "endpoint": "http://127.0.0.1:1",
            "adapter": "lmstudio_v1", "model_id": "fictional-model",
            "artifact": {"root": str(self.artifact), "files": ["weights.bin"], **identity},
            "capabilities": ["python_code_change"], "request_settings": settings,
            "fallback": {"model": "gpt-6.1-sol", "reasoning_effort": "medium"},
            "stale_tolerance_seconds": 120,
            "approval": {"owner_reference": "fictional-test-owner-not-a-real-approval", "timestamp": "2026-10-21",
                         "artifact_digest": identity["digest"], "capabilities": ["python_code_change"],
                         "request_settings": copy.deepcopy(settings)},
        }
        from local_model_delegation.profiles import model_identity
        profile['qualification_status']='qualified'
        profile['scope']=[{'capability':'python_code_change','language':'python','complexity':'simple','context_bucket':'small','max_input_bytes':100000}]
        profile['approval']['scope']=copy.deepcopy(profile['scope'])
        profile["approval"]["model_identity"] = model_identity(profile)
        return profile

    def brief(self, key="change-one"):
        return {"schema_version": 2, "origin_chat_id": "fixture-chat", "task_key": key,
                "capability": "python_code_change", "source_root": str(self.project),
                "files": {name: {"content": text, "sha256": sha(text)} for name, text in
                          {"helper.py": BUGGY, "test_helper.py": SUPPLIED}.items()},
                "editable_paths": ["helper.py", "test_helper.py"],
                "supplied_tests": ["test_helper.py"], "behavior_contract": "strip both ends",
                "checks": [["unittest", "test_oracle"]],
                "independent_tests": {"test_oracle.py": ORACLE},
                'task_requirements':{'language':'python','complexity':'simple','context_bucket':'small','urgency':'normal','wait_budget_seconds':30},
                'fallback':{'model':'gpt-6.1-sol','reasoning_effort':'medium'},
                'acceptance':{'method':'python_isolated','criteria':['Strip both ends'], 'protected_paths':[],
                              'checks':[{'id':'oracle','argv':['/usr/bin/true'],'cwd':'.','timeout_seconds':5}]}}

    def loaded(self, capacity=1):
        return {"endpoint": "http://127.0.0.1:1", "model_id": "fictional-model", "instance_id": "fixture-instance",
                "capacity": capacity, "config": {"parallel": capacity, "context_length": 8192},
                "binding_verified": True}

    def config(self, profile=None, enabled=True):
        return {"schema_version": 2, "routing_enabled": enabled, "visibility_enabled": True}

    def write_config(self, profile=None, enabled=True):
        from local_model_delegation.store import atomic_json
        from local_model_delegation.profiles import model_identity
        p=profile if profile is not None else self.profile()
        if p.get('approval') is not None and p.get('runtime_catalog'):
            p['approval']['model_identity']=model_identity(p)
        atomic_json(self.state/'config.json',self.config(p,enabled))
        atomic_json(self.state/'profiles'/ (p['profile_id']+'.json'),p)
        return self.state/'config.json'


class FakeRuntime:
    """Actual loopback HTTP, deterministic lifecycle and stream faults."""
    def __init__(self, answer=None, delay=0, incomplete=False, mismatch=False, output_tokens=50, model_format='fictional'):
        self.model_format = model_format
        self.answer = json.dumps({"files": {"helper.py": FIXED, "test_helper.py": SUPPLIED + ADDED}, "summary": "strip both ends"}) if answer is None else answer
        self.output_tokens, self.terminal_result = output_tokens, None
        self.delay, self.incomplete, self.mismatch = delay, incomplete, mismatch
        self.calls, self.requests = [], []
        self.loaded, self.parallel = True, 1
        self.instance_id, self.change_instance_on_load = "fixture-instance", False
        self.load_count = 0
        self.drop_load_ack = self.drop_unload_ack = False
        self.peer_loaded = False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass

            def do_GET(self):
                outer.calls.append(("GET", self.path))
                body = {"models": [{"key": "fictional-model", "type": "llm",
                    "format": outer.model_format, "architecture": "fictional", "publisher": "test", "params_string": "1B",
                    "quantization": {"name": "4bit", "bits_per_weight": 4}, "loaded_instances":
                    ([{"id": outer.instance_id, "config": {"parallel": outer.parallel, "context_length": 8192}}] if outer.loaded else [])}]}
                if outer.peer_loaded:
                    body['models'].append({'key':'peer','type':'llm','loaded_instances':[
                        {'id':'peer-instance','config':{'context_length':8192,'parallel':1}}]})
                encoded = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def do_POST(self):
                outer.calls.append(("POST", self.path))
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                outer.requests.append(body)
                if self.path.endswith("/load") or self.path.endswith("/unload"):
                    loading = self.path.endswith("/load")
                    outer.loaded = loading
                    if loading and outer.change_instance_on_load:
                        outer.load_count += 1
                        outer.instance_id = "fixture-instance-" + str(outer.load_count)
                    if (loading and outer.drop_load_ack) or (not loading and outer.drop_unload_ack):
                        if loading: outer.drop_load_ack = False
                        else: outer.drop_unload_ack = False
                        self.connection.close()
                        return
                    response = {'instance_id':outer.instance_id}
                    if loading:
                        response.update(type='llm', status='loaded', load_config={'context_length':8192})
                    encoded = json.dumps(response).encode()
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                answer = "PROBE_OK" if body.get("input") == "Return exactly PROBE_OK" else outer.answer
                events = [("chat.start", {"model_instance_id": outer.instance_id}),
                          ("reasoning.start", {}), ("reasoning.delta", {"content": "working"})]
                if outer.delay: time.sleep(outer.delay)
                events += [("reasoning.end", {}), ("message.start", {}), ("message.delta", {"content": answer}), ("message.end", {})]
                if not outer.incomplete:
                    result = outer.terminal_result if outer.terminal_result is not None else {"model_instance_id": outer.instance_id, "stats": {"total_output_tokens": outer.output_tokens}, "output": [{"type": "message", "content": answer + ("wrong" if outer.mismatch else "")}]}
                    events.append(("chat.end", {"result": result}))
                try:
                    for event, data in events:
                        self.wfile.write(f"event: {event}\ndata: {json.dumps({'type': event, **data})}\n\n".encode())
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError): pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.endpoint = f"http://127.0.0.1:{self.server.server_port}"
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": .02}, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
