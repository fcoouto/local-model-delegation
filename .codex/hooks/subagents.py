#!/usr/bin/env python3
"""Bounded structure guard for native Codex subagents; Python 3.11+, stdlib only."""
import json
import os
from pathlib import Path
import re
import stat
import sys

MAX_INPUT = 128 * 1024
PROJECT = Path(__file__).resolve().parents[2]
SPAWN = re.compile(r"^(spawn_agent|Agent|collaboration[.]?spawn_agent|multi_agent_v[12]spawn_agent)$")
BRIEF_FIELDS = {"objective", "context", "instructions", "allowed_files",
                "mutable_resources", "dependencies", "acceptance", "checks",
                "read_only", "budget"}
ROLES = {"Coordinator", "Scout", "Builder", "Tester", "Reviewer", "Scribe", "Investigator"}
REPORT_FIELDS = {"status", "summary", "changed_files", "checks", "risks",
                 "blockers", "next_action"}
ERROR = (
    "Subagent dispatch denied: missing/invalid task_name (unsupported format) or declaration. "
    "Prepare .codex-delegations/<task_name>.json; see .codex/delegation-brief.md."
)
PROCEDURE = (
    "Before work, require one exact coordinator-supplied declaration pointer in the native task "
    "message: project-root-relative .codex-delegations/<task_name>.json, with task_name matching "
    "[a-z0-9_]{1,64}. Read that record; compare objective, ownership, dependencies and checks "
    "with the assigned scope. Missing, ambiguous, unsafe, unreadable or inconsistent pointer/record "
    "means blocked without task work. If trusted host metadata exposes your own native task name, "
    "compare it with the record: for canonical /root/reader use final component reader; block a "
    "mismatch. If host identity is unavailable, do not fabricate identity from prompt text: "
    "continue authorized declared scope and report native identity binding unverified in risks. "
    "A coordinator-supplied pointer is a task instruction, not identity attestation. The coordinator "
    "checks the actual native spawn task_name, declaration, observed read and resulting diff. "
    "The hook cannot establish child identity or message binding. "
    "Follow that declaration and repository instructions. Confirm dependencies and "
    "owned writable files/resources before editing; read_only means no writes. Preserve "
    "other work, native permissions, model, effort, provider and authentication. "
    "Stop at the brief's time/attempt budget; report blockers instead of retrying indefinitely. "
    "Run the stated checks; never invent results. End with one JSON report fence tagged "
    "delegation-report or json: "
    "status (done|blocked|needs_context), summary (nonempty string), changed_files (string array), "
    "checks (nonempty string array: command, result, evidence; explicitly record unrun checks), "
    "risks and blockers (string arrays), next_action (nonempty string). Empty arrays mean none. "
    "This hook checks structure only; the coordinator reviews diffs, evidence and semantic accuracy."
)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def reject_constant(_value):
    raise ValueError("non-JSON number")


def load_json(raw):
    return json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)


def fenced_object(message, tags):
    if not isinstance(message, str):
        raise ValueError("message must be text")
    found, current, lines = [], None, []
    for line in message.splitlines():
        if current is None:
            match = re.fullmatch(r" {0,3}(`{3,}|~{3,})(.*)", line)
            if match:
                current = (match[1][0], len(match[1]), any(line == f"```{tag}" for tag in tags))
                lines = []
        else:
            marker, length, active = current
            if re.fullmatch(r" {0,3}" + re.escape(marker) + "{" + str(length) + r",}[ \t]*", line):
                if active:
                    if line != "```":
                        raise ValueError("contract closing fence must be exact")
                    found.append(load_json("\n".join(lines)))
                current = None
            elif active:
                lines.append(line)
    if current is not None or len(found) != 1 or not isinstance(found[0], dict):
        raise ValueError("one standalone JSON fence required")
    return found[0]


def text(value):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 4096


def strings(value, nonempty=False):
    return (isinstance(value, list) and len(value) <= 64
            and (not nonempty or bool(value)) and all(text(item) for item in value))


def valid_brief(brief):
    if not isinstance(brief, dict) or set(brief) - {"role", "specialty"} != BRIEF_FIELDS:
        return False
    if "role" in brief and (not isinstance(brief["role"], str) or brief["role"] not in ROLES):
        return False
    if "specialty" in brief and not text(brief["specialty"]):
        return False
    if not all(text(brief[key]) for key in ("objective", "context", "instructions")):
        return False
    if not all(strings(brief[key]) for key in ("allowed_files", "mutable_resources", "dependencies")):
        return False
    if not all(strings(brief[key], nonempty=True) for key in ("acceptance", "checks")):
        return False
    if type(brief["read_only"]) is not bool:
        return False
    has_writes = bool(brief["allowed_files"] or brief["mutable_resources"])
    if brief["read_only"] == has_writes:
        return False
    budget = brief["budget"]
    return (isinstance(budget, dict) and set(budget) == {"minutes", "attempts"}
            and type(budget["minutes"]) is int and 1 <= budget["minutes"] <= 120
            and type(budget["attempts"]) is int and 1 <= budget["attempts"] <= 5)


def read_brief(task_name, project=PROJECT):
    if (os.name != "posix" or os.open not in os.supports_dir_fd
            or any(not hasattr(os, flag) for flag in ("O_DIRECTORY", "O_NOFOLLOW", "O_NONBLOCK"))):
        raise ValueError("safe declaration open requires POSIX")
    if not isinstance(task_name, str) or not re.fullmatch(r"[a-z0-9_]{1,64}", task_name):
        raise ValueError("unsupported task name")
    # Directory-relative opens prevent traversal; nonblocking open avoids FIFO hangs.
    directory = os.open(project / ".codex-delegations", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = os.open(task_name + ".json", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory)
    finally:
        os.close(directory)
    with os.fdopen(descriptor, "rb") as record:
        if not stat.S_ISREG(os.fstat(record.fileno()).st_mode):
            raise ValueError("declaration must be a regular file")
        raw = record.read(MAX_INPUT + 1)
    if len(raw) > MAX_INPUT:
        raise ValueError("declaration too large")
    return load_json(raw)


def valid_report(report):
    return (set(report) == REPORT_FIELDS
            and report["status"] in ("done", "blocked", "needs_context")
            and all(text(report[key]) for key in ("summary", "next_action"))
            and all(strings(report[key]) for key in ("changed_files", "risks", "blockers"))
            and strings(report["checks"], nonempty=True))


def denied():
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                   "permissionDecision": "deny",
                                   "permissionDecisionReason": ERROR}}


def dispatch(data, configured):
    if not isinstance(data, dict) or not isinstance(data.get("hook_event_name"), str):
        raise ValueError("invalid event")
    if data["hook_event_name"] != configured:
        return {}
    if configured == "PreToolUse":
        name = data.get("tool_name")
        if not isinstance(name, str):
            return denied()
        if not SPAWN.fullmatch(name):
            return {}
        args = data.get("tool_input")
        if not isinstance(args, dict):
            return denied()
        brief = read_brief(args.get("task_name"))
        return {} if valid_brief(brief) else denied()
    if configured == "SubagentStart":
        return {"hookSpecificOutput": {"hookEventName": "SubagentStart",
                                       "additionalContext": PROCEDURE}}
    if configured == "SubagentStop":
        # Unknown retry state cannot safely request another continuation.
        if data.get("stop_hook_active") is not False:
            return {}
        try:
            if valid_report(fenced_object(data.get("last_assistant_message"), ("delegation-report", "json"))):
                return {}
        except (ValueError, TypeError, RecursionError):
            pass
        return {"decision": "block", "reason":
                "Supply one complete JSON report fence tagged delegation-report or json, including blocked or "
                "needs_context status if appropriate. " + PROCEDURE}
    return {}


def main():
    configured = sys.argv[1] if len(sys.argv) == 2 else ""
    output = {}
    if configured in ("PreToolUse", "SubagentStart", "SubagentStop"):
        try:
            raw = sys.stdin.buffer.read(MAX_INPUT + 1)
            if len(raw) > MAX_INPUT:
                raise ValueError("input too large")
            output = dispatch(load_json(raw), configured)
        except (ValueError, TypeError, RecursionError, OSError, NotImplementedError):
            if configured == "PreToolUse":
                output = denied()
    print(json.dumps(output))


if __name__ == "__main__":
    main()
