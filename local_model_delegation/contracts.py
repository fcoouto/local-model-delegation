"""Strict boundary contracts shared by the CLI, store and checker."""
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any

PYTHON_CODE_CHANGE = "python_code_change"
PYTHON_CHANGE_CAPABILITIES = {PYTHON_CODE_CHANGE}
CAPABILITIES = PYTHON_CHANGE_CAPABILITIES | {"test_writing", "code_change", "file_summary"}
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
    if isinstance(data, dict) and type(data.get("schema_version")) is int and data["schema_version"] == 2:
        return validate_v2(data)
    raise ValueError("invalid_brief")


def validate_python_checks(data):
    if data["capability"] not in PYTHON_CHANGE_CAPABILITIES:
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


def validate_fallback(value):
    if (not isinstance(value, dict) or set(value) != {"model", "reasoning_effort"}
            or not all(isinstance(v, str) and v.strip() and len(v) <= 128 for v in value.values())):
        raise ValueError("explicit_fallback_required")
    return value


def validate_v2(data):
    common = {"schema_version", "origin_chat_id", "task_key", "capability", "source_root", "files",
              "editable_paths", "behavior_contract", "task_requirements", "acceptance", "fallback"}
    python_fields = {"supplied_tests", "checks", "independent_tests"} if data.get("capability") in PYTHON_CHANGE_CAPABILITIES else set()
    if set(data) != common | python_fields or data["capability"] not in CAPABILITIES: raise ValueError("invalid_brief")
    validate_fallback(data["fallback"])
    for key in ("origin_chat_id", "task_key", "behavior_contract"):
        if not isinstance(data[key], str) or not data[key] or len(data[key]) > 20000: raise ValueError("invalid_brief")
    requirements = data["task_requirements"]
    if (not isinstance(requirements, dict) or set(requirements) - {'max_output_tokens'} != {"language", "complexity", "context_bucket", "urgency", "wait_budget_seconds"}
            or ('max_output_tokens' in requirements and (type(requirements['max_output_tokens']) is not int or requirements['max_output_tokens'] <= 0))
            or requirements["complexity"] not in ("simple", "moderate", "complex")
            or requirements["urgency"] not in ("normal", "urgent") or not positive(requirements["wait_budget_seconds"])
            or any(not isinstance(requirements[k], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", requirements[k]) for k in ("language", "context_bucket"))):
        raise ValueError("invalid_requirements")
    root = Path(data["source_root"])
    if not root.is_absolute() or not root.is_dir() or root != root.resolve(): raise ValueError("invalid_source_root")
    if not isinstance(data["files"], dict) or not 1 <= len(data["files"]) <= 8: raise ValueError("invalid_files")
    for name, item in data["files"].items():
        path = safe_path(root, name)
        if not path.is_file() or not isinstance(item, dict) or set(item) != {"content", "sha256"}: raise ValueError("invalid_source_file")
        if (not isinstance(item["content"], str) or len(item["content"].encode()) > 100000 or "\0" in item["content"]
                or text_hash(item["content"]) != item["sha256"]): raise ValueError("source_hash_mismatch")
    if sum(len(i["content"].encode()) for i in data["files"].values()) > MAX_ANSWER_BYTES: raise ValueError("oversized_context")
    acceptance = data["acceptance"]
    if (not isinstance(acceptance, dict) or set(acceptance) != {"method", "criteria", "protected_paths", "checks"}
            or acceptance["method"] != ("python_isolated" if python_fields else "native_verified")
            or not isinstance(acceptance["criteria"], list) or not acceptance["criteria"]
            or not all(isinstance(c, str) and c.strip() for c in acceptance["criteria"])):
        raise ValueError("invalid_acceptance")
    for names in (data["editable_paths"], acceptance["protected_paths"]):
        if not isinstance(names, list) or any(not isinstance(n, str) for n in names) or len(set(names)) != len(names):
            raise ValueError("invalid_path_list")
        for name in names:
            path = safe_path(root, name)
            if path.exists() and name not in data["files"]: raise ValueError("missing_source_snapshot")
    if set(data["editable_paths"]) & set(acceptance["protected_paths"]): raise ValueError("protected_path_editable")
    checks = acceptance["checks"]
    if not isinstance(checks, list): raise ValueError("invalid_checks")
    ids = set()
    for check in checks:
        if (not isinstance(check, dict) or set(check) != {"id", "argv", "cwd", "timeout_seconds"}
                or not isinstance(check["id"], str) or not re.fullmatch(r"[A-Za-z0-9_-]+", check["id"]) or check["id"] in ids
                or not isinstance(check["argv"], list) or not check["argv"]
                or not all(isinstance(s, str) and s and "\0" not in s for s in check["argv"])
                or not Path(check["argv"][0]).is_absolute() or not positive(check["timeout_seconds"])):
            raise ValueError("invalid_check")
        if check["cwd"] != ".": safe_path(root, check["cwd"])
        ids.add(check["id"])
    if data["capability"] == "file_summary":
        if data["editable_paths"] or checks: raise ValueError("summary_is_read_only")
    elif not data["editable_paths"] or not checks: raise ValueError("missing_checks")
    if python_fields:
        validate_python_checks(data)
    return data


def envelope(job: dict[str, Any]) -> dict[str, Any]:
    return {"schema_version": 1, **{key: job.get(key) for key in (
        "job_id", "attempt_id", "status", "reason", "fallback", "result_path", "native_task_id")}}
