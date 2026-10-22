#!/usr/bin/env python3
"""Optional presentation-only wrapper for an existing Habblaud SubagentStart hook."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys

import subagents

UUID = re.compile(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}")
TASK_PATH = re.compile(r"/root(?:/[a-z0-9_]{1,64})+")


def find_metadata(event, home):
    """Read only the real child's bounded first rollout record, never its messages."""
    child = event.get("agent_id")
    parent = event.get("session_id")
    if (not isinstance(child, str) or not UUID.fullmatch(child)
            or not isinstance(parent, str) or not UUID.fullmatch(parent) or child == parent):
        return None
    home = home.resolve(strict=True)
    now = datetime.now(timezone.utc)
    days = {home / "sessions" / (now + timedelta(days=n)).strftime("%Y/%m/%d")
            for n in (-1, 0, 1)}
    transcript = event.get("transcript_path")
    if isinstance(transcript, str):
        directory = Path(transcript).parent
        if directory.is_relative_to(home / "sessions"):
            days.add(directory)
    candidates = []
    for day in days:
        if day.exists() and day.resolve() == day:
            candidates.extend(day.glob(f"rollout-*-{child}.jsonl"))
    if len(candidates) != 1:
        return None
    descriptor = os.open(candidates[0], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            return None
        raw = stream.readline(subagents.MAX_INPUT + 1)
    if len(raw) > subagents.MAX_INPUT:
        return None
    record = subagents.load_json(raw)
    if not isinstance(record, dict) or record.get("type") != "session_meta":
        return None
    meta = record.get("payload")
    if not isinstance(meta, dict) or meta.get("id") != child or meta.get("cwd") != event.get("cwd"):
        return None
    source = meta.get("source", {})
    spawn = source.get("subagent", {}).get("thread_spawn", {}) if isinstance(source, dict) else {}
    if not isinstance(spawn, dict) or spawn.get("parent_thread_id") != parent:
        return None
    return meta, spawn


def display_role(event, role):
    # agent_type is Habblaud's display input here, never a Codex spawn/profile setting.
    if isinstance(role, str) and role.strip():
        return dict(event, agent_role=role, agent_type=role)
    return event


def enrich_event(event, codex_home, harness_root=None):
    """Preserve supplied roles; derive absent/null roles only from a bound declaration."""
    if not isinstance(event, dict) or event.get("hook_event_name") != "SubagentStart":
        return event
    if event.get("agent_role") is not None:
        return display_role(event, event["agent_role"])
    try:
        found = find_metadata(event, codex_home)
        if found is None:
            return event
        meta, spawn = found
        for source in (spawn, meta):
            if source.get("agent_role") is not None:
                return display_role(event, source["agent_role"])
        task_path = spawn.get("agent_path")
        if not isinstance(task_path, str) or not TASK_PATH.fullmatch(task_path):
            return event
        cwd = Path(meta["cwd"]).resolve(strict=True)
        root = harness_root.resolve(strict=True) if harness_root is not None else cwd
        if not cwd.is_relative_to(root):
            return event
        brief = subagents.read_brief(task_path.rsplit("/", 1)[1], root)
        if subagents.valid_brief(brief) and "role" in brief:
            return display_role(event, brief["role"])
    except (OSError, ValueError, TypeError, AttributeError, RecursionError, NotImplementedError):
        pass
    return event


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", type=Path,
                        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")))
    parser.add_argument("--harness-root", type=Path,
                        help="Explicit declaration root; otherwise the native rollout cwd, without ancestor search")
    parser.add_argument("command", nargs=argparse.REMAINDER, help="-- followed by the original hook executable and arguments")
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("the original Habblaud hook command is required after --")
    raw = sys.stdin.buffer.read(subagents.MAX_INPUT + 1)
    if len(raw) <= subagents.MAX_INPUT:
        try:
            event = subagents.load_json(raw)
            enriched = enrich_event(event, args.codex_home, args.harness_root)
            if enriched != event:
                raw = json.dumps(enriched).encode()
        except (ValueError, TypeError, RecursionError):
            pass
        return subprocess.run(command, input=raw).returncode
    # Oversized input bypasses enrichment and streams unchanged to the original hook.
    with subprocess.Popen(command, stdin=subprocess.PIPE) as child:
        try:
            child.stdin.write(raw)
            shutil.copyfileobj(sys.stdin.buffer, child.stdin)
        except BrokenPipeError:
            pass
        finally:
            try:
                child.stdin.close()
            except BrokenPipeError:
                pass
            child.stdin = None
        return child.wait()


if __name__ == "__main__":
    status = main()
    if status < 0:
        signum = -status
        if signum not in (signal.SIGKILL, signal.SIGSTOP):
            signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)
    raise SystemExit(status)
