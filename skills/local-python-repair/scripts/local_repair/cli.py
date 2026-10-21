"""Explicit local operations; native OpenAI dispatch remains with Codex."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from .contracts import CAPABILITY, MAX_ANSWER_BYTES, canonical, digest, envelope, load_json, validate_brief
from .lmstudio import Runtime, select_loaded
from .profiles import fingerprint_artifact, read_profile
from .store import Store, atomic_json
from .worker import run_attempt, start_worker, wait_job

DEFAULT_STATE = Path.home() / ".local/state/codex-local-repairs"


def reconcile_native(store, job_id, native_tasks):
    claim = store.claim_fallback(job_id)
    matches = [task["task_name"] for task in native_tasks if isinstance(task, dict)
               and isinstance(task.get("task_name"), str) and task["task_name"].rsplit("/", 1)[-1] == claim["task_name"]]
    if len(set(matches)) == 1:
        store.attach_fallback(job_id, claim["dispatch_token"], matches[0])
    else:
        store.mark_dispatch_uncertain(job_id, claim["dispatch_token"])
    return envelope(store.job(job_id))


def read_input(path):
    path = Path(path)
    if path.is_symlink() or path.stat().st_size > MAX_ANSWER_BYTES: raise ValueError("unsafe_input")
    return load_json(path.read_text())


def submit(state_dir, path):
    brief = read_input(path)
    # Disabled/missing configuration causes no database, process or HTTP side effects.
    profile = read_profile(state_dir / "profiles.json", brief.get("capability", CAPABILITY))
    validate_brief(brief)
    from .validation import isolation_supported
    if not isolation_supported(brief): raise ValueError("isolation_unsupported")
    store = Store(state_dir)
    existing = store.lookup(brief["origin_chat_id"], brief["task_key"])
    if existing:
        if digest(store.job(existing["job_id"])["brief"]) != digest(brief): raise ValueError("job_conflict")
        return existing
    try: loaded = select_loaded(Runtime(profile["endpoint"]).list_models(), profile)
    except (OSError, ValueError): loaded = None
    result = store.reserve(brief, profile, loaded)
    if result["status"] == "reserved":
        start_worker(state_dir, result["attempt_id"])
    elif result["reason"] == "instance_closed" and loaded:
        from .recovery import request_recovery
        key = digest([loaded["endpoint"], loaded["model_id"], loaded["instance_id"]])
        request_recovery(state_dir, key)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="HTTP-only bounded repairs; routing disabled unless separately configured and approved.")
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("worker", "recover"):
        p = commands.add_parser(name)
        p.add_argument("identifier")
    p = commands.add_parser("submit")
    p.add_argument("--brief", type=Path, required=True)
    p = commands.add_parser("lookup")
    p.add_argument("--chat", required=True)
    p.add_argument("--task-key", required=True)
    for name in ("status", "check", "wait"):
        p = commands.add_parser(name)
        p.add_argument("--job", required=True)
        if name == "wait": p.add_argument("--seconds", type=float, default=5)
    p = commands.add_parser("fallback")
    p.add_argument("action", choices=["claim", "attach", "uncertain", "result", "reconcile"])
    p.add_argument("--job", required=True)
    p.add_argument("--dispatch-token")
    p.add_argument("--native-task-id")
    p.add_argument("--candidate", type=Path)
    p.add_argument("--listing", type=Path)
    p = commands.add_parser("profile")
    p.add_argument("action", choices=["inspect", "record-approval"])
    p.add_argument("--file", type=Path, required=True)
    p.add_argument("--owner-reference")
    args = parser.parse_args(argv)
    try:
        if args.command == "worker": return run_attempt(args.state_dir, args.identifier)
        if args.command == "recover":
            from .recovery import recover_instance
            return recover_instance(args.state_dir, args.identifier)
        if args.command == "submit": result = submit(args.state_dir, args.brief)
        elif args.command == "profile":
            profile = read_input(args.file)
            identity = fingerprint_artifact(Path(profile["artifact"]["root"]), profile["artifact"]["files"])
            result = {"schema_version": 1, "profile_id": profile["profile_id"], "identity": identity, "routing_enabled": False}
            if args.action == "record-approval":
                if not args.owner_reference: raise ValueError("owner_confirmation_required")
                profile["artifact"].update(identity)
                profile["approval"] = {"owner_reference": args.owner_reference, "timestamp": datetime.now(timezone.utc).isoformat(),
                                       "artifact_digest": identity["digest"], "capabilities": profile["capabilities"],
                                       "request_settings": profile["request_settings"]}
                atomic_json(args.file, profile)
                result["status"] = "approval_recorded"
        else:
            if not (args.state_dir / "state.sqlite3").exists(): raise ValueError("no_saved_jobs")
            store = Store(args.state_dir)
            if args.command == "lookup":
                result = store.lookup(args.chat, args.task_key)
                if result is None: raise ValueError("unknown_job")
            elif args.command in ("status", "wait"):
                result = wait_job(args.state_dir, args.job, args.seconds if args.command == "wait" else 0)
            elif args.command == "check":
                from .validation import check_candidate
                result = check_candidate(args.state_dir, args.job)
            elif args.command == "fallback":
                if args.action == "claim": result = store.claim_fallback(args.job)
                elif args.action == "attach":
                    if not store.attach_fallback(args.job, args.dispatch_token, args.native_task_id): raise ValueError("dispatch_mismatch")
                    result = envelope(store.job(args.job))
                elif args.action == "uncertain":
                    store.mark_dispatch_uncertain(args.job, args.dispatch_token)
                    result = envelope(store.job(args.job))
                elif args.action == "reconcile":
                    result = reconcile_native(store, args.job, read_input(args.listing))
                else:
                    result = store.record_fallback_candidate(args.job, args.native_task_id, args.candidate)
        print(canonical(result))
        return 0
    except (ValueError, OSError, KeyError, TypeError, sqlite3.Error) as error:
        reason = str(error) if isinstance(error, ValueError) and re.fullmatch(r"[a-z_]+", str(error)) else "operation_failed"
        print(canonical(envelope({"status": "not_eligible", "reason": reason})))
        return 2
