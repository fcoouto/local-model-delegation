"""Disposable fictional profiles and source; no real model approvals."""
import copy
import hashlib
import json
import tempfile
import unittest
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from . import SCRIPTS
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
        from local_repair.profiles import fingerprint_artifact
        identity = fingerprint_artifact(self.artifact, ["weights.bin"])
        settings = {"reasoning": "on", "temperature": 0, "max_output_tokens": 8192}
        return {
            "schema_version": 1, "profile_id": "fictional", "endpoint": "http://127.0.0.1:1",
            "adapter": "lmstudio_v1", "model_id": "fictional-model",
            "artifact": {"root": str(self.artifact), "files": ["weights.bin"], **identity},
            "capabilities": ["bounded_python_repair"], "request_settings": settings,
            "fallback": {"model": "gpt-6.1-sol", "reasoning_effort": "medium"},
            "stale_tolerance_seconds": 120,
            "approval": {"owner_reference": "fictional-test-owner-not-a-real-approval", "timestamp": "2026-10-21",
                         "artifact_digest": identity["digest"], "capabilities": ["bounded_python_repair"],
                         "request_settings": copy.deepcopy(settings)},
        }

    def brief(self, key="repair-one"):
        return {"schema_version": 1, "origin_chat_id": "fixture-chat", "task_key": key,
                "capability": "bounded_python_repair", "source_root": str(self.project),
                "files": {name: {"content": text, "sha256": sha(text)} for name, text in
                          {"helper.py": BUGGY, "test_helper.py": SUPPLIED}.items()},
                "editable_paths": ["helper.py", "test_helper.py"],
                "supplied_tests": ["test_helper.py"], "behavior_contract": "strip both ends",
                "checks": [["unittest", "test_oracle"]],
                "independent_tests": {"test_oracle.py": ORACLE}}

    def loaded(self, capacity=1):
        return {"endpoint": "http://127.0.0.1:1", "model_id": "fictional-model", "instance_id": "fixture-instance",
                "capacity": capacity, "config": {"parallel": capacity, "context_length": 8192},
                "binding_verified": True}

    def config(self, profile=None, enabled=True):
        p = profile or self.profile()
        return {"schema_version": 1, "routing_enabled": enabled,
                "preferred_by_capability": {"bounded_python_repair": p["profile_id"]},
                "profiles": {p["profile_id"]: p}}

    def write_config(self, profile=None, enabled=True):
        self.state.mkdir(mode=0o700, exist_ok=True)
        path = self.state / "profiles.json"
        path.write_text(json.dumps(self.config(profile, enabled)))
        path.chmod(0o600)
        return path


class FakeRuntime:
    """Actual loopback HTTP, deterministic lifecycle and stream faults."""
    def __init__(self, answer=None, delay=0, incomplete=False, mismatch=False):
        self.answer = answer or json.dumps({"files": {"helper.py": FIXED, "test_helper.py": SUPPLIED + ADDED}, "summary": "strip both ends"})
        self.delay, self.incomplete, self.mismatch = delay, incomplete, mismatch
        self.calls, self.requests = [], []
        self.loaded, self.parallel = True, 1
        self.drop_load_ack = self.drop_unload_ack = False
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass

            def do_GET(self):
                outer.calls.append(("GET", self.path))
                body = {"models": [{"key": "fictional-model", "type": "llm", "loaded_instances":
                    ([{"id": "fixture-instance", "config": {"parallel": outer.parallel, "context_length": 8192}}] if outer.loaded else [])}]}
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
                    if (loading and outer.drop_load_ack) or (not loading and outer.drop_unload_ack):
                        if loading: outer.drop_load_ack = False
                        else: outer.drop_unload_ack = False
                        self.connection.close()
                        return
                    encoded = b'{}'
                    self.send_response(200)
                    self.send_header("Content-Length", "2")
                    self.end_headers()
                    self.wfile.write(encoded)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                answer = "PROBE_OK" if body.get("input") == "Return exactly PROBE_OK" else outer.answer
                events = [("chat.start", {"model_instance_id": "fixture-instance"}),
                          ("reasoning.start", {}), ("reasoning.delta", {"content": "working"})]
                if outer.delay: time.sleep(outer.delay)
                events += [("reasoning.end", {}), ("message.start", {}), ("message.delta", {"content": answer}), ("message.end", {})]
                if not outer.incomplete:
                    events.append(("chat.end", {"result": {"output": [{"type": "message", "content": answer + ("wrong" if outer.mismatch else "")}]}}))
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
