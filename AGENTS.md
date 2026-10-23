# Local Model Delegation contributor guide

This repository owns the Codex plugin, local execution adapters, assessment and
verification contracts. Read README.md and the relevant
`skills/local-delegation/references/` contracts before changes. Preserve exact
model approvals, artifact/runtime identity, bounded execution, queue recovery,
private-state separation and native verification. Do not run real inference,
change routing, reinstall the plugin or alter approvals merely to test setup.

Use Python 3.11+ and the existing offline suite:
`python3.11 -B -m unittest discover -s tests -t . -q`, plus `git diff --check`.
Tests use disposable state and fictional approvals; keep live state and credentials
out of fixtures. Read applicable platform requirements before running isolation
canaries. Unit tests do not prove real-model or fresh-desktop behavior.

Preserve user edits and current execution settings. Use the smallest complete
change, run relevant checks and independently review nontrivial changes. Read
actual files and process state when resuming; keep temporary handoffs and private
setup evidence outside tracked product files. Keep durable facts beside their
source, verification date and invalidation condition. Publication, deployment,
plugin installation and model approval need their applicable user authorization.

## Delegation policy

Read the [delegation policy](.codex/delegation-brief.md) before choosing local or
native execution. The main agent is Coordinator; each worker has an explicit role
and separate specialty. Prefer local execution only when enabled routing, existing
approval, matching assessment evidence and safe capacity permit the complete task.
Otherwise retain authorized native execution. Unknown roles are rejected; a custom,
nonempty specialty is allowed but remains **Not assessed** without matching evidence.
Role labels never select a native profile or change model, reasoning, provider,
authentication or permissions. Preserve these settings and all explicit user limits.
The [optional native display adapter](.codex/native-display.md) only fills absent
or null `agent_role`; any supplied value wins. Installing its files does not
activate it. Reuse an already qualified shared integration without adding wrappers;
actual badge delivery needs separate client evidence.

## Vibe task lifecycle

Use the reviewed installed Vibe Setup helper at
`$HOME/.codex/skills/vibe-setup/workflow.py` and its adjacent `task-lifecycle.md`.
Resolve the installed skill's actual path if this location differs; do not copy
its helper into this repository. Normal tasks use the helper directly, without
repeating full onboarding. Read `.codex/vibe-workflow.toml`: lifecycle and cleanup
default ON; preserve independent `enabled=false` and `auto_cleanup=false` choices.

Inspect first. Unless opted out, create or adopt a linked worktree and require
`start` to return `implementation=worktree_verified` before editing. Use its
returned command and worker roots; a failed verification never permits primary
checkout edits. Preview setup with `inspect --task-id`, apply the reviewed plan,
and resume the same operation after interruption. With lifecycle disabled, use
the reviewed component installer and ordinary authorized delivery instead.

Follow the installed lifecycle contract for `sync` and `resume`, under the
repository's publication authority. Stop writers and supply explicit files plus
current checks and independent review. Plan at most four routine checkpoints or one per phase. READY, reopen and blocker
transitions reuse existing milestones without consuming that budget; refreshed
inputs require a fresh READY event and current readiness gates. PRs start draft `[BLOCKED]`; `[READY]` requires current local/remote
checks, review and non-draft status. Withdraw READY before further edits, preserve
human content, reconcile uncertain results and never auto-merge. Publication
failure means “blocked; PR update pending”, with a concrete next action.

Cleanup runs only when reconciliation confirms all associated PRs merged or
records supersession with a verified replacement. Each closure processes all
eligible queued retirement handoffs in the same Git repository. Startup never
runs cleanup; `start` only cancels retirement before a checkout is reused.
Preserve independent `delete_remote_branches=false`, `delete_worktrees=false`,
`auto_cleanup=false` and whole-lifecycle opt-outs. Closed-unmerged PRs retain their
remote branches and worktrees unless explicitly superseded. Keep local branch
refs; preserve active, dirty, shared, foreign or ambiguously owned resources.
Verify ownership, stopped writers, retained heads and remote absence before local
removal when enabled. For managed worktrees, follow the installed native archive
preflight: only verified completed task children with inherited attachments may
be archived; running or uncertain children remain untouched. Use the native owner
and verify filesystem and Git registration absence. Queued archival stays pending.
Inspect `pending_cleanup.tasks` and report each unresolved owner action without
polling. Installation, client discovery and actual execution are separate evidence.

Every task follows the installed Vibe Setup `security-validation.md` at
implementation-complete/READY/production candidate, release/deployment, or an
explicit user/project requirement. Assess impact, check Trail of Bits updates,
review applicable changes and bind required checks and independent review to the
current snapshot. Reuse valid evidence; draft edits and worktree creation do not
independently trigger security reviews. Missing, stale, incomplete or failing
required checks block readiness and release. Use the installed helper's
`check-security` for the exact clean release revision, including lifecycle opt-out.
Preserve existing model approvals, routing, settings and authentication.

For reusable read-only security review, use
[Vibe Prompt 13](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/prompts/13-security-review.md)
against an explicit revision/diff, keeping redacted findings private. Use
[Prompt 14](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/prompts/14-harness-evaluation.md)
for relevant disposable harness cases and
[Prompt 15](https://github.com/soumatheusgomes/vibe-coding-toolkit/blob/790a895304e0c08b70a5b215c9d334f1c86b816c/docs/prompts/15-harness-improvement.md)
for one bounded native comparison after an observed failure. Preserve settings,
checks and original inputs; no official Harness2 CLI or paid benchmark is implied.
Reapply Vibe Setup after material package/client changes and record installation,
discovery and execution separately in private setup evidence.
