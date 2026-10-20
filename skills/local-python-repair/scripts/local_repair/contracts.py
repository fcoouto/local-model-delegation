"""Strict boundary contracts shared by the CLI, store and checker."""
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

CAPABILITY = "bounded_python_repair"
MAX_ANSWER_BYTES = 2 * 1024 * 1024


def load_json(text: str) -> Any:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate_json_key")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("invalid_number")))


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def positive(value: Any) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def safe_path(root: Path, name: str) -> Path:
    if (not isinstance(name, str) or not name or "\\" in name or "\x00" in name
            or any(ord(c) < 32 for c in name) or Path(name).is_absolute()
            or any(p in ("", ".", "..") for p in name.split("/"))):
        raise ValueError("unsafe_path")
    result = root
    for part in name.split("/"):
        result = result / part
        if result.is_symlink():
            raise ValueError("symlink_path")
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError("path_escape")
    return result


def validate_brief(data: dict[str, Any]) -> dict[str, Any]:
    required = {"schema_version", "origin_chat_id", "task_key", "capability", "source_root", "files",
                "editable_paths", "supplied_tests", "behavior_contract", "checks", "independent_tests"}
    if not isinstance(data, dict) or set(data) != required or type(data["schema_version"]) is not int or data["schema_version"] != 1:
        raise ValueError("invalid_brief")
    if data["capability"] != CAPABILITY:
        raise ValueError("unsupported_capability")
    for key in ("origin_chat_id", "task_key", "behavior_contract"):
        if not isinstance(data[key], str) or not data[key] or len(data[key]) > 20000:
            raise ValueError("invalid_brief")
    root = Path(data["source_root"])
    if not root.is_absolute() or not root.is_dir() or root.is_symlink() or root != root.resolve():
        raise ValueError("invalid_source_root")
    if not isinstance(data["files"], dict) or not 1 <= len(data["files"]) <= 8:
        raise ValueError("invalid_files")
    for name, item in data["files"].items():
        path = safe_path(root, name)
        if not name.endswith(".py") or not path.is_file() or not isinstance(item, dict) or set(item) != {"content", "sha256"}:
            raise ValueError("invalid_source_file")
        if not isinstance(item["content"], str) or len(item["content"].encode()) > 100000 or text_hash(item["content"]) != item["sha256"]:
            raise ValueError("source_hash_mismatch")
    for key in ("editable_paths", "supplied_tests"):
        names = data[key]
        if not isinstance(names, list) or not names or any(not isinstance(n, str) for n in names) or len(set(names)) != len(names):
            raise ValueError("invalid_path_list")
        for name in names:
            safe_path(root, name)
            if not name.endswith(".py"):
                raise ValueError("invalid_python_path")
    if not set(data["supplied_tests"]) <= data["files"].keys() or not set(data["editable_paths"]) & data["files"].keys():
        raise ValueError("invalid_test_contract")
    oracles = data["independent_tests"]
    if not isinstance(oracles, dict) or not oracles or len(oracles) > 8:
        raise ValueError("missing_independent_checks")
    for name, text in oracles.items():
        safe_path(root, name)
        if (not name.endswith(".py") or name in data["files"] or name in data["editable_paths"]
                or not isinstance(text, str) or len(text.encode()) > 100000):
            raise ValueError("invalid_independent_checks")
    if not isinstance(data["checks"], list) or not data["checks"]:
        raise ValueError("missing_checks")
    for argv in data["checks"]:
        if (not isinstance(argv, list) or len(argv) != 2 or argv[0] != "unittest"
                or not isinstance(argv[1], str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.]*", argv[1])
                or argv[1].split(".")[0] + ".py" not in oracles):
            raise ValueError("unsupported_check_command")
    return data


def envelope(job: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, **{key: job.get(key) for key in (
        "job_id", "attempt_id", "status", "reason", "fallback", "result_path", "native_task_id")}}
