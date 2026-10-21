"""Owner-selected profiles and actual local artifact hashes."""
import hashlib
import os
import re
import sqlite3
import uuid
from pathlib import Path
from typing import Any
from .contracts import CAPABILITY, canonical, digest, load_json, positive, safe_path
from .store import Store, atomic_json, private_dir


def fingerprint_artifact(root: Path, files: list[str]) -> dict[str, Any]:
    root = Path(root)
    if not root.is_absolute() or root.is_symlink() or root != root.resolve() or not root.is_dir() or not files or len(set(files)) != len(files):
        raise ValueError("invalid_artifact")
    entries = {}
    for name in sorted(files):
        path = safe_path(root, name)
        before = path.stat()
        if not path.is_file():
            raise ValueError("invalid_artifact_file")
        h = hashlib.sha256()
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                h.update(chunk)
        after = path.stat()
        stamp = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if stamp(before) != stamp(after):
            raise ValueError("artifact_changed_during_hash")
        entries[name] = {"sha256": h.hexdigest(), "size": after.st_size}
    for name in files:
        if Path(name).name == "manifest.json":
            manifest = load_json((root / name).read_text())
            for item in manifest.get("artifacts", []):
                entry = entries.get(item["path"])
                if entry is None or entry["sha256"] != item["sha256"] or entry["size"] != item["size"]:
                    raise ValueError("artifact_manifest_mismatch")
    return {"digest": digest(entries), "entries": entries}


def model_identity(profile):
    """Bind a runtime key to its owner-trusted local LM Studio index and exact files."""
    try:
        path = Path(profile["runtime_catalog"])
        if not path.is_absolute() or path != path.resolve() or not path.is_file():
            raise ValueError("runtime_binding_unavailable")
        stamp = path.stat()
        if stamp.st_uid != os.getuid() or stamp.st_mode & 0o022:
            raise ValueError("runtime_binding_unavailable")
        catalog = load_json(path.read_text())
        if catalog.get("conflicts") or catalog.get("errors"):
            raise ValueError("runtime_binding_unavailable")
        matches = [entry for entry in catalog["models"] if profile["model_id"] in
                   [entry.get("defaultIdentifier"), entry.get("indexedModelIdentifier"),
                    entry.get("originalIndexedModelIdentifier"), *entry.get("autoIdentifiers", [])]]
        if len(matches) != 1: raise ValueError("runtime_binding_unavailable")
        entry = matches[0]
        root = Path(profile["artifact"]["root"])
        expected = sorted(str(safe_path(root, name)) for name in profile["artifact"]["files"])
        files = sorted(item["absPath"] for item in entry["allFiles"])
        if entry["concreteModelDirAbsolutePath"] != str(root) or files != expected:
            raise ValueError("runtime_binding_mismatch")
        metadata = {"format": entry["format"], "architecture": entry["arch"], "publisher": entry["user"],
                    "params_string": entry["params"],
                    "quantization": {"name": entry["quant"]["name"], "bits_per_weight": entry["quant"]["bits"]}}
        return {"endpoint": profile["endpoint"], "adapter": profile["adapter"], "model_id": profile["model_id"],
                "runtime_catalog": str(path), "indexed_identifier": entry["indexedModelIdentifier"],
                "artifact_root": str(root), "files": files, "metadata": metadata}
    except (OSError, KeyError, TypeError, AttributeError):
        raise ValueError("runtime_binding_unavailable") from None


def verify_runtime_binding(profile, model):
    identity = model_identity(profile)
    if (profile.get("approval") or {}).get("model_identity") != identity:
        raise ValueError("model_not_approved")
    if (model.get("key") != profile["model_id"] or model.get("type") != "llm"
            or any(model.get(key) != value for key, value in identity["metadata"].items())):
        raise ValueError("runtime_binding_mismatch")


def eligible(profile: dict[str, Any], identity: dict[str, Any], capability: str) -> bool:
    approval = profile.get("approval")
    try:
        binding = model_identity(profile)
    except ValueError:
        return False
    return bool(isinstance(approval, dict) and approval.get("owner_reference") and approval.get("timestamp")
                and approval.get("model_identity") == binding
                and approval.get("artifact_digest") == identity.get("digest") == profile["artifact"].get("digest")
                and profile["artifact"].get("entries") == identity.get("entries")
                and capability in profile.get("capabilities", []) and capability in approval.get("capabilities", [])
                and approval.get("request_settings") == profile.get("request_settings")
                and (profile.get("schema_version") != 2 or approval.get("scope") == profile.get("scope")))


def read_profile(path: Path, capability: str) -> dict[str, Any]:
    path = Path(path)
    if path.is_symlink():
        raise ValueError("unsafe_configuration")
    try:
        config = load_json(path.read_text())
    except FileNotFoundError:
        raise ValueError("routing_disabled") from None
    if not isinstance(config, dict) or config.get("routing_enabled") is not True:
        raise ValueError("routing_disabled")
    try:
        profile_id = config["preferred_by_capability"][capability]
        p = config["profiles"][profile_id]
        if config.get("schema_version") != 1 or p.get("schema_version") != 1 or p["profile_id"] != profile_id:
            raise ValueError("invalid_profile")
        return validate_profile(p, capability)
    except (KeyError, TypeError, OSError):
        raise ValueError("invalid_profile") from None


def validate_profile(p, capability):
    try:
        settings, fallback = p["request_settings"], p["fallback"]
        if (p.get("schema_version") not in (1, 2) or not re.fullmatch(r"[A-Za-z0-9_-]+", p["profile_id"])
                or p["adapter"] != "lmstudio_v1" or capability not in (CAPABILITY, "test_writing", "code_change", "file_summary")
                or not positive(p["stale_tolerance_seconds"]) or not isinstance(p["model_id"], str) or not p["model_id"]
                or set(fallback) != {"model", "reasoning_effort"} or not all(isinstance(v, str) and v for v in fallback.values())
                or set(settings) not in ({"reasoning", "temperature", "max_output_tokens"}, {"temperature", "max_output_tokens"})
                or (p["schema_version"] == 1 and "reasoning" not in settings)
                or ("reasoning" in settings and settings["reasoning"] not in ("on", "off"))
                or type(settings["temperature"]) not in (int, float) or not 0 <= settings["temperature"] <= 2
                or type(settings["max_output_tokens"]) is not int or settings["max_output_tokens"] <= 0
                or (p["model_id"] == "qwen3.8-27b-splash" and settings.get("reasoning") != "on")):
            raise ValueError("invalid_profile")
        from .contracts import positive as finite_positive
        if settings["temperature"] != 0 and not finite_positive(settings["temperature"]):
            raise ValueError("invalid_profile")
        from urllib.parse import urlsplit
        endpoint = urlsplit(p["endpoint"])
        if endpoint.scheme != "http" or endpoint.hostname not in ("127.0.0.1", "::1") or endpoint.username or endpoint.password or endpoint.path not in ("", "/") or endpoint.query or endpoint.fragment:
            raise ValueError("unsupported_endpoint")
        identity = fingerprint_artifact(Path(p["artifact"]["root"]), p["artifact"]["files"])
        if not eligible(p, identity, capability):
            raise ValueError("model_not_approved")
    except (KeyError, TypeError, OSError):
        raise ValueError("invalid_profile") from None
    return p


def read_config(state_dir):
    root = Path(state_dir)
    path = root / "config.json"
    if not path.exists(): path = root / "profiles.json"
    if path.is_symlink(): raise ValueError("unsafe_configuration")
    try: config = load_json(path.read_text())
    except FileNotFoundError: return {"schema_version": 2, "routing_enabled": False, "visibility_enabled": True}
    if not isinstance(config, dict) or type(config.get("schema_version")) is not int or config["schema_version"] not in (1, 2):
        raise ValueError("unsupported_configuration")
    pending = root / "migration.json"
    if pending.exists() and load_json(pending.read_text()).get("state") != "complete":
        config["routing_enabled"] = False
    return config


def read_profiles(state_dir):
    root = Path(state_dir)
    config = read_config(root)
    if config["schema_version"] == 1: return list(config.get("profiles", {}).values())
    directory = root / "profiles"
    if directory.is_symlink(): raise ValueError("unsafe_configuration")
    result = []
    for path in sorted(directory.glob("*.json")):
        if path.is_symlink() or not re.fullmatch(r"[A-Za-z0-9_-]+", path.stem): raise ValueError("invalid_profile_id")
        value = load_json(path.read_text())
        if not isinstance(value, dict) or value.get("profile_id") != path.stem or value.get("schema_version") != 2:
            raise ValueError("invalid_profile")
        result.append(value)
    return result


def read_profile_by_id(state_dir, profile_id, capability):
    if not isinstance(profile_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", profile_id):
        raise ValueError("invalid_profile_id")
    config = read_config(state_dir)
    if config.get("routing_enabled") is not True: raise ValueError("routing_disabled")
    if config["schema_version"] == 1:
        # Existing jobs retain their selected profile even if the preference changes.
        try: profile = config["profiles"][profile_id]
        except KeyError: raise ValueError("model_not_approved") from None
    else:
        profile = next((p for p in read_profiles(state_dir) if p["profile_id"] == profile_id), None)
        if profile is None: raise ValueError("model_not_approved")
        if profile.get("qualification_status") != "qualified": raise ValueError("needs_assessment")
    return validate_profile(profile, capability)


def authorize_job(store, job):
    if job.get("native_task_id") and not job["profile"]:
        from .contracts import validate_fallback
        validate_fallback(job["fallback"])
        return {}
    if job.get("route_data", {}).get("assessment"):
        from .onboarding import authorize_assessment
        current = authorize_assessment(store.root, job["brief"], job["route_data"]["assessment"])
        if current["profile_id"] != job["profile"]["profile_id"]: raise ValueError("assessment_scope_mismatch")
        return current
    profile = job["profile"]
    current = read_profile_by_id(store.root, profile["profile_id"], job["brief"]["capability"])
    if current["approval"] != profile["approval"]: raise ValueError("approval_changed")
    if job["brief"].get("schema_version") == 2 and not scope_matches(current, job["brief"]):
        raise ValueError("outside_approved_scope")
    return current


def scope_matches(profile, brief):
    from .contracts import canonical
    requirements = brief["task_requirements"]
    size = len(canonical({"contract": brief["behavior_contract"], "files": brief["files"], "editable_paths": brief["editable_paths"]}).encode())
    return any(isinstance(scope, dict) and scope.get("capability") == brief["capability"]
               and all(scope.get(k) == requirements[k] for k in ("language", "complexity", "context_bucket"))
               and type(scope.get("max_input_bytes")) is int and size <= scope["max_input_bytes"]
               for scope in profile.get("scope", []))


def _quiescent(db):
    if (db.execute("SELECT 1 FROM jobs WHERE status NOT IN ('accepted','failed','needs_reassessment') LIMIT 1").fetchone()
            or db.execute("SELECT 1 FROM attempts WHERE state IN ('reserved','submitting','streaming','uncertain') LIMIT 1").fetchone()
            or db.execute("SELECT 1 FROM fallback_dispatches WHERE state NOT IN ('complete','failed') LIMIT 1").fetchone()
            or db.execute("SELECT 1 FROM instances WHERE state != 'ready' LIMIT 1").fetchone()):
        raise ValueError("unresolved_work")
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='model_operations'").fetchone():
        if db.execute("SELECT 1 FROM model_operations WHERE state NOT IN ('complete','failed') LIMIT 1").fetchone():
            raise ValueError("unresolved_work")


def migrate_state(state_dir):
    """Explicit, resumable migration; the old entry point stays disabled throughout."""
    from .worker import ownership
    store = Store(state_dir)
    with ownership(store, "migration") as owned:
        if not owned: raise ValueError("migration_busy")
        journal_path = store.root / "migration.json"
        journal = load_json(journal_path.read_text()) if journal_path.exists() else None
        if journal and journal["state"] == "complete": return journal
        with store.db() as db: _quiescent(db)
        legacy = store.root / "profiles.json"
        if not journal:
            raw = legacy.read_bytes()
            original = load_json(raw.decode())
            if original.get("schema_version") != 1: raise ValueError("unsupported_configuration")
            backup = private_dir(store.root / "backups" / uuid.uuid4().hex)
            fd = os.open(backup / "profiles.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw); stream.flush(); os.fsync(stream.fileno())
            fd = os.open(backup / "state.sqlite3", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            os.close(fd)
            with store.db() as db, sqlite3.connect(backup / "state.sqlite3") as destination: db.backup(destination)
            journal = {"state": "pending", "backup_dir": str(backup)}
            atomic_json(journal_path, journal)
        backup = Path(journal["backup_dir"])
        raw = (backup / "profiles.json").read_bytes()
        original = load_json(raw.decode())
        tombstone = {"schema_version": 1, "routing_enabled": False, "preferred_by_capability": {}, "profiles": {}}
        atomic_json(legacy, tombstone)
        try:
            with store.db(write=True) as db:
                _quiescent(db)
                for identifier, profile in original["profiles"].items():
                    if not re.fullmatch(r"[A-Za-z0-9_-]+", identifier) or profile.get("profile_id") != identifier:
                        raise ValueError("invalid_profile_id")
                    atomic_json(store.root / "profiles" / (identifier + ".json"),
                                {**profile, "schema_version": 2, "qualification_status": "needs_assessment", "scope": []})
                store.upgrade_schema(db)
                atomic_json(store.root / "config.json", {"schema_version": 2, "routing_enabled": False, "visibility_enabled": original.get("visibility_enabled", True)})
        except ValueError as error:
            if str(error) == "unresolved_work" and load_json(legacy.read_text()) == tombstone:
                # Only restore our own tombstone; never overwrite another writer's change.
                temp = legacy.with_name("restore-" + uuid.uuid4().hex)
                fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as stream:
                    stream.write(raw); stream.flush(); os.fsync(stream.fileno())
                os.replace(temp, legacy)
                journal_path.unlink()
            raise
        journal["state"] = "complete"
        atomic_json(journal_path, journal)
        return journal
