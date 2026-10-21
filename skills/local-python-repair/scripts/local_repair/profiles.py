"""Owner-selected profiles and actual local artifact hashes."""
import hashlib
import os
from pathlib import Path
from typing import Any
from .contracts import CAPABILITY, canonical, digest, load_json, positive, safe_path


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
    if profile.get("approval", {}).get("model_identity") != identity:
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
                and approval.get("request_settings") == profile.get("request_settings"))


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
        settings, fallback = p["request_settings"], p["fallback"]
        if (config.get("schema_version") != 1 or p.get("schema_version") != 1 or p["profile_id"] != profile_id
                or p["adapter"] != "lmstudio_v1" or capability != CAPABILITY
                or not positive(p["stale_tolerance_seconds"]) or not isinstance(p["model_id"], str) or not p["model_id"]
                or set(fallback) != {"model", "reasoning_effort"} or not all(isinstance(v, str) and v for v in fallback.values())
                or set(settings) != {"reasoning", "temperature", "max_output_tokens"}
                or settings["reasoning"] not in ("on", "off")
                or type(settings["temperature"]) not in (int, float) or not 0 <= settings["temperature"] <= 2
                or type(settings["max_output_tokens"]) is not int or settings["max_output_tokens"] <= 0
                or (p["model_id"] == "qwen3.8-27b-splash" and settings["reasoning"] != "on")):
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
