"""Local delegation commands; native fallback dispatch remains with the host agent."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import re
import sqlite3
from .contracts import PYTHON_CODE_CHANGE, MAX_ANSWER_BYTES, canonical, digest, envelope, load_json, validate_brief
from .lmstudio import Runtime, select_loaded
from .profiles import fingerprint_artifact, model_identity, read_legacy_profile, read_config
from .store import Store, atomic_json
from .worker import run_local_attempt, start_worker, wait_job

DEFAULT_STATE = Path.home() / ".local/state/local-model-delegation"
LEGACY_STATE = Path.home() / ".local/state/codex-local-repairs"


def resolve_state_directory(explicit):
    if explicit is not None: return explicit
    if LEGACY_STATE.exists() or LEGACY_STATE.is_symlink():
        raise ValueError("explicit_state_directory_required")
    return DEFAULT_STATE


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


def submit_task(state_dir, path):
    brief = read_input(path)
    # Disabled/missing configuration causes no database, process or HTTP side effects.
    config = read_config(state_dir)
    if config.get("routing_enabled") is not True: raise ValueError("routing_disabled")
    if config["schema_version"] == 2:
        validate_brief(brief)
        store = Store(state_dir)
        result = store.enqueue(brief, brief["fallback"])
        from .scheduler import schedule_once
        schedule_once(state_dir)
        result = envelope(store.job(result["job_id"]))
        if result["status"] == "waiting" and result["reason"] != "route_decision_required":
            from .worker import launch
            launch(state_dir, "scheduler", "queue")
        return result
    profile = read_legacy_profile(state_dir / "profiles.json", brief.get("capability", PYTHON_CODE_CHANGE))
    validate_brief(brief)
    from .validation import python_isolation_supported
    if not python_isolation_supported(brief): raise ValueError("isolation_unsupported")
    store = Store(state_dir)
    existing = store.lookup(brief["origin_chat_id"], brief["task_key"])
    if existing:
        if digest(store.job(existing["job_id"])["brief"]) != digest(brief): raise ValueError("job_conflict")
        return existing
    try: loaded = select_loaded(Runtime(profile["endpoint"], token_env=profile.get("token_env")).list_models(), profile)
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
    parser = argparse.ArgumentParser(description="Delegate tasks to assessed local models with native verification and fallback. Routing is disabled by default.")
    parser.add_argument("--state-dir", type=Path, help="Shared private state directory; required when legacy state exists.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("migrate")
    commands.add_parser("resources")
    for name in ("setup", "prepare-update", "prepare-uninstall"):
        commands.add_parser(name)
    p = commands.add_parser("doctor")
    p.add_argument("--inspect-runtime", action="store_true")
    for name in ("worker", "recover", "scheduler"):
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
    p = commands.add_parser("verify")
    p.add_argument("action", choices=["prepare", "checks", "record"])
    p.add_argument("--job", required=True)
    p.add_argument("--receipt", type=Path)
    p = commands.add_parser("discover")
    p.add_argument("--endpoint", required=True)
    p = commands.add_parser("assessment")
    p.add_argument("action", choices=["begin", "report", "trial", "submit", "capacity", "approve"])
    p.add_argument("--profile-id")
    p.add_argument("--assessment-id")
    p.add_argument("--owner-reference")
    p.add_argument("--receipt", type=Path)
    p.add_argument("--scope", type=Path)
    p.add_argument("--trial-id")
    p = commands.add_parser("route")
    p.add_argument("action", choices=["decide"])
    p.add_argument("--job", required=True)
    p.add_argument("--decision", type=Path, required=True)
    p = commands.add_parser("outcome")
    p.add_argument("action", choices=["record"])
    p.add_argument("--job", required=True)
    p.add_argument("--receipt", type=Path, required=True)
    p = commands.add_parser("visibility")
    p.add_argument("action", choices=["enable", "disable", "status"])
    args = parser.parse_args(argv)
    try:
        args.state_dir = resolve_state_directory(args.state_dir)
        if args.command == "worker": return run_local_attempt(args.state_dir, args.identifier)
        if args.command == "scheduler":
            from .scheduler import run_scheduler
            return run_scheduler(args.state_dir)
        if args.command == "recover":
            from .recovery import recover_instance
            return recover_instance(args.state_dir, args.identifier)
        if args.command == "resources":
            from .capacity import machine_snapshot
            result = machine_snapshot()
        elif args.command in ("setup", "doctor", "prepare-update", "prepare-uninstall"):
            from .package import initialize_state, doctor, prepare_update, prepare_uninstall
            if args.command == "doctor": result = doctor(args.state_dir, args.inspect_runtime)
            else: result = {"setup": initialize_state, "prepare-update": prepare_update, "prepare-uninstall": prepare_uninstall}[args.command](args.state_dir)
        elif args.command == "visibility":
            from .visibility import set_visibility, visibility_status
            result = visibility_status(args.state_dir) if args.action == "status" else set_visibility(args.state_dir, args.action == "enable")
        elif args.command == "discover":
            from .onboarding import discover_models
            result = discover_models(Runtime(args.endpoint))
        elif args.command == "assessment":
            from .onboarding import begin_assessment, assessment_report, record_trial, approve_assessment, submit_trial, record_capacity
            if args.action == "begin": result = begin_assessment(args.state_dir, args.profile_id, args.owner_reference)
            elif args.action == "report": result = assessment_report(args.state_dir, args.assessment_id)
            elif args.action == "capacity": result = record_capacity(args.state_dir, args.assessment_id, read_input(args.receipt))
            elif args.action == "submit": result = submit_trial(args.state_dir, args.assessment_id, args.trial_id)
            elif args.action == "trial": result = record_trial(args.state_dir, args.assessment_id, read_input(args.receipt))
            else: result = approve_assessment(args.state_dir, args.assessment_id, args.owner_reference, read_input(args.scope))
        elif args.command == "migrate":
            from .profiles import migrate_profile_schema
            result = migrate_profile_schema(args.state_dir)
        elif args.command == "submit": result = submit_task(args.state_dir, args.brief)
        elif args.command == "profile":
            profile = read_input(args.file)
            identity = fingerprint_artifact(Path(profile["artifact"]["root"]), profile["artifact"]["files"])
            result = {"schema_version": 1, "profile_id": profile["profile_id"], "identity": identity, "model_identity": model_identity(profile), "routing_enabled": False}
            if args.action == "record-approval":
                if profile.get("schema_version") == 2: raise ValueError("use_assessment_approval")
                if not args.owner_reference: raise ValueError("owner_confirmation_required")
                profile["artifact"].update(identity)
                profile["approval"] = {"owner_reference": args.owner_reference, "timestamp": datetime.now(timezone.utc).isoformat(),
                                       "artifact_digest": identity["digest"], "model_identity": model_identity(profile), "capabilities": profile["capabilities"],
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
                from .validation import verify_candidate
                result = verify_candidate(args.state_dir, args.job)
            elif args.command == "verify":
                from .validation import prepare_verification, record_verification, run_native_checks
                if args.action == "prepare": result = prepare_verification(args.state_dir, args.job)
                elif args.action == "checks": result = run_native_checks(args.state_dir, args.job)
                else: result = record_verification(args.state_dir, args.job, read_input(args.receipt))
            elif args.command == "outcome":
                from .onboarding import record_outcome
                result = record_outcome(args.state_dir, args.job, read_input(args.receipt))
            elif args.command == "route":
                result = store.decide_wait(args.job, read_input(args.decision))
                if result["status"] == "waiting":
                    from .worker import launch
                    launch(args.state_dir, "scheduler", "queue")
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
