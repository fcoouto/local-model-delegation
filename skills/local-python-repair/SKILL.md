---
name: local-python-repair
description: Use when an understood, nonurgent pure-Python helper defect has a small file allowlist and independent regression checks, and an owner-approved local-model route is configured.
---

# Local Python Repair

Codex owns scope, checks and integration. The local model proposes files only. Follow explicit user restrictions first.

Invoke `python3.11 <this-skill>/scripts/repair.py --state-dir <private-state> <command>`; use `--help` for arguments. Read [the brief contract](references/contracts.md) when preparing a repair.

1. Establish `origin_chat_id` and a stable `task_key` for this repair. Prepare source hashes, editable paths, supplied tests and independent checks before generation. Never delegate trading/risk, authorization, migrations, services, broad investigation or unrestricted tools through this capability.
2. `submit --brief <private-brief.json>`. `not_eligible` means continue the ordinary OpenAI workflow. Do not enable routing, install anything, approve a model or invent owner confirmation. Capability testing is optional and cannot activate a profile.
3. For `reserved`/`running`, keep this task active with `wait --job <id> --seconds 5`. Compaction does not stop the detached monitor. Resume with `lookup --chat <origin> --task-key <key>`, then recover the same job. Never create a replacement key because context was compacted. Observer heartbeats do not reset model silence.
4. For `candidate_ready`, run `check --job <id>`. Only `accepted` is independently checked. Recheck original source hashes immediately before applying the candidate with normal Codex editing tools; run the owning repository's checks/review. The helper never edits project source.
5. For `fallback_required`, run `fallback claim --job <id>`. The claim provides exact OpenAI model/effort, dispatch token and stable task name. Inspect native agents for that name. If `may_dispatch` is true and no matching task exists, invoke native `collaboration.spawn_agent` with that `task_name`, `fork_turns: "none"`, and the claim's explicit `model`/`reasoning_effort`. Supply behavior, allowed source/tests, output-file location and checks; forbid recursive local delegation. Keep independent oracle source private. Preserve native account/provider/permissions. No cloud API or proxy substitute.
6. Immediately save the returned canonical task identifier with `fallback attach --job <id> --dispatch-token <token> --native-task-id <canonical-name>`. On resume, reconcile an existing matching native task. Use `fallback reconcile --job <id> --listing <private-json-list>` with actual native `task_name` entries. If dispatch is ambiguous or the exact model is unavailable, report that limitation; do not spawn again, change models or fabricate completion. Native dispatch may wait for compaction to finish.
7. Wait for the native task using native tools, save its exact candidate JSON, and run `fallback result --job <id> --native-task-id <canonical-name> --candidate <file>`, then `check`. Repeated calls recover the existing task/result. A failed fallback check is `failed`, never another fallback.

`needs_reassessment` requires rebuilding scope/checks for changed source before a new user task is attempted. `dispatch_uncertain` retains the original intent. Instance recovery is automatic, protects healthy peers and does not mean an uncertain slot is free. Local silence has a per-model stale tolerance; active inference has no total deadline. Model approval/version changes remain owner decisions.
