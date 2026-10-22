"""Local delegation commands; native fallback dispatch remains with the host agent."""
import argparse
from pathlib import Path
import re
import sqlite3
from .contracts import MAX_ANSWER_BYTES, canonical, digest, envelope, load_json, validate_brief
from .lmstudio import Runtime
from .profiles import fingerprint_artifact, model_identity, read_config
from .store import Store, atomic_json
from .worker import run_local_attempt, start_worker, wait_job

DEFAULT_STATE = Path.home() / ".local/state/local-model-delegation"


def resolve_state_directory(explicit):
    if explicit is not None: return explicit
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


def submit_task(state_dir, path, measurement_path=None, visibility_path=None):
    brief = read_input(path)
    # Disabled/missing configuration causes no database, process or HTTP side effects.
    config = read_config(state_dir)
    if config.get("routing_enabled") is not True: raise ValueError("routing_disabled")
    validate_brief(brief)
    store = Store(state_dir)
    result = store.enqueue(brief, brief["fallback"], measurement=read_input(measurement_path) if measurement_path else None,
                           visibility=read_input(visibility_path) if visibility_path else None)
    from .scheduler import schedule_once
    schedule_once(state_dir)
    result = {**result, **envelope(store.job(result["job_id"]))}
    if result["status"] == "waiting" and result["reason"] != "route_decision_required":
        from .worker import launch
        launch(state_dir, "scheduler", "queue")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="Delegate tasks to assessed local models with native verification and fallback. Routing is disabled by default.")
    parser.add_argument("--state-dir", type=Path, help="Shared private state directory (default: ~/.local/state/local-model-delegation).")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("resources")
    for name in ("setup", "prepare-uninstall"):
        commands.add_parser(name)
    p = commands.add_parser('version')
    p.add_argument('--root', type=Path)
    p = commands.add_parser('prepare-update')
    p.add_argument('--target', type=Path, required=True)
    p.add_argument('--installed', type=Path)
    p = commands.add_parser('verify-update')
    p.add_argument('--receipt', type=Path, required=True)
    p.add_argument('--installed', type=Path)
    p = commands.add_parser("doctor")
    p.add_argument("--inspect-runtime", action="store_true")
    for name in ("worker", "recover", "scheduler", "habblaud-observer"):
        p = commands.add_parser(name)
        p.add_argument("identifier")
    p = commands.add_parser("submit")
    p.add_argument("--brief", type=Path, required=True)
    p.add_argument('--measurement-context', type=Path)
    p.add_argument('--visibility-context', type=Path)
    h = commands.add_parser('habblaud').add_subparsers(dest='action', required=True)
    p = h.add_parser('enable'); p.add_argument('--endpoint', required=True); p.add_argument('--account', required=True)
    p = h.add_parser('status'); p.add_argument('--job')
    h.add_parser('disable')
    p = h.add_parser('resume'); p.add_argument('--job', required=True)
    p = h.add_parser('bind'); p.add_argument('--job', required=True); p.add_argument('--context', type=Path, required=True)
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
    p.add_argument("--task-name")
    p = commands.add_parser("profile")
    p.add_argument("action", choices=["inspect", "approve"])
    p.add_argument("--file", type=Path)
    p.add_argument("--profile-id")
    p.add_argument("--owner-reference")
    p.add_argument("--scope", type=Path)
    p.add_argument("--max-output-tokens", type=int)
    p = commands.add_parser("verify")
    p.add_argument("action", choices=["prepare", "checks", "record"])
    p.add_argument("--job", required=True)
    p.add_argument("--receipt", type=Path)
    p = commands.add_parser("discover")
    p.add_argument("--endpoint", required=True)
    p = commands.add_parser('models')
    p.add_argument('action', choices=['permit-load','load','reconcile-load','reset'])
    p.add_argument('--profile-id')
    p.add_argument('--owner-reference')
    p.add_argument('--context-length', type=int)
    p.add_argument('--instance-key')
    p.add_argument('--operation-id')
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
    p = commands.add_parser('metrics')
    metrics = p.add_subparsers(dest='action', required=True)
    metrics.add_parser('init')
    metrics.add_parser('reconcile')
    p = metrics.add_parser('report')
    p.add_argument('--project', required=True)
    p.add_argument('--model')
    p.add_argument('--format', choices=['json','text'], default='json')
    p = metrics.add_parser('register')
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--label', required=True)
    p = metrics.add_parser('begin')
    p.add_argument('--task', required=True)
    p.add_argument('--context', type=Path, required=True)
    p.add_argument('--job')
    p = metrics.add_parser('record')
    p.add_argument('--task', required=True)
    p.add_argument('--receipt', type=Path, required=True)
    p = metrics.add_parser('comparison-register')
    p.add_argument('--manifest', type=Path, required=True)
    p = metrics.add_parser('comparison-record')
    p.add_argument('--comparison', required=True)
    p.add_argument('--receipt', type=Path, required=True)
    p = metrics.add_parser('comparison-revoke')
    p.add_argument('--comparison', required=True)
    p.add_argument('--at', type=float, required=True)
    p.add_argument('--evidence-hash', required=True)
    args = parser.parse_args(argv)
    try:
        args.state_dir = resolve_state_directory(args.state_dir)
        if args.command == 'habblaud-observer':
            from .habblaud import run_observer
            return run_observer(args.state_dir, args.identifier)
        if args.command == "worker": return run_local_attempt(args.state_dir, args.identifier)
        if args.command == "scheduler":
            from .scheduler import run_scheduler
            return run_scheduler(args.state_dir)
        if args.command == "recover":
            from .recovery import recover_instance
            return recover_instance(args.state_dir, args.identifier)
        if args.command == 'models':
            from . import lifecycle
            if args.action == 'permit-load':
                result = lifecycle.configure_loading(args.state_dir,args.profile_id,args.owner_reference,args.context_length)
            elif args.action == 'load': result = lifecycle.ensure_loaded(args.state_dir,args.profile_id)
            elif args.action == 'reconcile-load': result = lifecycle.reconcile_load(args.state_dir,args.operation_id)
            else: result = lifecycle.reset_external(args.state_dir,args.instance_key,args.owner_reference)
            print(canonical(result))
            return 0
        if args.command == 'metrics':
            from . import measurements
            if args.action == 'init': result = measurements.initialize_measurements(args.state_dir)
            elif args.action == 'reconcile': result = measurements.reconcile_measurements(args.state_dir)
            elif args.action == 'report':
                result = measurements.read_report(args.state_dir,project_id=args.project,profile_id=args.model)
                if args.format == 'text':
                    print(measurements.render_text_report(result)); return 0
            elif args.action == 'register': result = measurements.register_project(args.state_dir, args.root, args.label)
            elif args.action == 'begin': result = measurements.begin_measurement(args.state_dir, args.task, read_input(args.context), args.job)
            elif args.action == 'comparison-register': result = measurements.register_comparison(args.state_dir, read_input(args.manifest))
            elif args.action == 'comparison-record': result = measurements.record_comparison_run(args.state_dir, args.comparison, read_input(args.receipt))
            elif args.action == 'comparison-revoke': result = measurements.revoke_comparison(args.state_dir, args.comparison, args.at, args.evidence_hash)
            else: result = measurements.append_event(args.state_dir, args.task, read_input(args.receipt))
        elif args.command in ('version', 'prepare-update', 'verify-update'):
            from .updates import package_identity, prepare_update, verify_update, PACKAGE_ROOT
            if args.command == 'version': result = package_identity(args.root or PACKAGE_ROOT)
            elif args.command == 'prepare-update': result = prepare_update(args.state_dir, args.target, args.installed or PACKAGE_ROOT)
            else: result = verify_update(args.state_dir, args.receipt, args.installed or PACKAGE_ROOT)
        elif args.command == "resources":
            from .capacity import machine_snapshot
            result = machine_snapshot()
        elif args.command in ("setup", "doctor", "prepare-uninstall"):
            from .package import initialize_state, doctor, prepare_uninstall
            if args.command == "doctor": result = doctor(args.state_dir, args.inspect_runtime)
            else: result = {"setup": initialize_state, "prepare-uninstall": prepare_uninstall}[args.command](args.state_dir)
        elif args.command == 'habblaud':
            from . import habblaud
            if args.action == 'enable': result = habblaud.configure(args.state_dir, args.endpoint, args.account)
            elif args.action == 'bind': result = habblaud.bind(args.state_dir, args.job, read_input(args.context))
            elif args.action == 'disable': result = habblaud.disable(args.state_dir)
            elif args.action == 'resume': result = {**habblaud.status(args.state_dir, args.job), 'observer': habblaud.ensure_observer(args.state_dir, args.job)}
            else: result = habblaud.status(args.state_dir, args.job)
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
        elif args.command == "submit": result = submit_task(args.state_dir, args.brief, args.measurement_context, args.visibility_context)
        elif args.command == "profile" and args.action == 'approve':
            from .onboarding import approve_scope
            result = approve_scope(args.state_dir, args.profile_id, args.owner_reference, read_input(args.scope), max_output_tokens=args.max_output_tokens)
        elif args.command == "profile":
            profile = read_input(args.file)
            if profile.get("schema_version") != 2: raise ValueError("invalid_profile")
            identity = fingerprint_artifact(Path(profile["artifact"]["root"]), profile["artifact"]["files"])
            result = {"schema_version": 1, "profile_id": profile["profile_id"], "identity": identity, "model_identity": model_identity(profile), "routing_enabled": False}
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
                if args.action == "claim": result = store.claim_fallback(args.job, args.task_name)
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
