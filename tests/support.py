"""Disposable fictional profiles and source; no real model approvals."""
import copy
import hashlib
import json
import tempfile
import unittest
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
