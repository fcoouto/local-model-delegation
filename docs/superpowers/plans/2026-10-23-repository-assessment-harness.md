# Repository assessment harness implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. The owner approved inline implementation and independent final review on 2026-10-23.

**Goal:** Support and prepare all eight selected backend assignments without inference or weaker validation.

**Architecture:** Add versioned repository execution and brief contracts around the existing project campaign and queue. Frozen manifests provide bounded source views and exact edits. A separate Docker verification adapter runs real frameworks and PostgreSQL without candidate network or host access.

**Tech Stack:** Python 3.11 standard library, existing queue/store, Docker CLI, pinned Python and PostgreSQL images.

**Spec:** `docs/superpowers/specs/2026-10-23-repository-assessment-harness-design.md`

## Global Constraints

- No model responses, calibration generation, new approvals or routing changes.
- Existing contracts, saved runs and legacy limits retain their behavior.
- Repository fixtures: 4 MiB per text file, 128 MiB total, 8,192 regular files; no symlinks, traversal, case collisions or secret paths.
- Context responses: at most 32 KiB serialized, UTF-8 aligned exact continuation. Twelve context turns and three proposals maximum per assignment.
- Exact unique edits with base hashes; no fuzzy matching. Hidden inputs never reach public feedback.
- Containers: pinned image IDs, no pulls during checks, network none, non-root, read-only root, capabilities dropped, no-new-privileges, no Docker socket or host repository mounts.
- PostgreSQL: private Unix socket, fresh database, restricted candidate role, separate administrator identity, real competing connections.
- Preserve selected repository identity and all eight task contracts. Slow correct work passes; interrupted work is inconclusive.
- Private project source, fixtures and evidence never enter the plugin repository.

## Review Focus

1. Snapshot changes after admission, including path aliases and Unicode/case collisions, must invalidate use.
2. A huge single line or JSON escaping must not bypass response bounds or make bytes unreachable.
3. Retries, uncertain requests and interleaved context/proposal turns must not replay work or reset allowances.
4. Candidate SQL/process tricks must not expose administrative credentials, host files or unrelated services.
5. A check timeout, zero discovered tests, skipped concurrency test or cleanup failure must never become a pass.

### Task 1: Frozen source, bounded views and exact edits

**Files:** Create `local_model_delegation/repository_context.py`, `tests/test_repository_context.py`; extend contracts/worker/parser only during Task 3 integration.

**Interfaces:** `snapshot(root, paths, destination, *, revision=None) -> manifest`; `validate_snapshot(root, manifest) -> None`; `context_action(root, manifest, action) -> dict`; `apply_edits(root, manifest, editable_paths, proposal) -> dict[str,str]`. Manifest records schema, files (size/hash) and digest; paths use existing safe-path validation.

- [x] Write failing tests for whole large files, immutable manifests, hostile paths/types/collisions, bounded listing/search/UTF-8 reads, exact stale/ambiguous/overlapping edits and allowed creation.
- [x] Run `python3.11 -B -m unittest tests.test_repository_context -q`; observe failure before implementation.
- [x] Implement deterministic, bounded helpers using the standard library and existing hash/path helpers.
- [x] Run the same tests to green; retain evidence in the plan workspace.
- [x] Record the completed boundary and explicit files for the implementation checkpoint.

### Task 2: Docker and PostgreSQL verification boundary

**Files:** Create `local_model_delegation/container_checks.py`, `tests/test_container_checks.py`; private qualification assets outside source.

**Interfaces:** `validate_environment(spec) -> dict`; `run_check(state_dir, source_root, assets_root, check, environment) -> observation`; `reconcile_operation(operation_path) -> dict`. Observations include exit code, infrastructure reason, bounded output, test discovery receipt and owned-resource cleanup evidence.

- [x] Write failing tests for strict environment/check input, immutable image binding, exact Docker arguments, forbidden mounts/network/privileges, process limits, durable ownership, timeout and uncertain cleanup.
- [x] Run `python3.11 -B -m unittest tests.test_container_checks -q`; observe failure.
- [x] Implement a single adapter, no fallback to unrestricted host execution. PostgreSQL setup runs separately from candidate checks with distinct credentials and only an owned socket shared.
- [x] Run unit tests and real disposable isolation canaries, including denied host/network/database privilege access and separate-connection uniqueness/locking.
- [x] Record exact image digests and measured environment evidence privately; do not claim offline mocks establish isolation.

### Task 3: Existing campaign/queue integration

**Files:** Modify `contracts.py`, `worker.py`, `validation.py`, `project_runs.py`, `project_reports.py`, `onboarding.py` and connected callers identified by searches; create focused repository campaign tests; update relevant skill operations and README.

**Interfaces:** Repository execution schema version 2 in newly prepared project campaigns; brief schema version 3 for repository actions. Existing campaign schema 2 remains the container for both execution versions. No existing saved record is upgraded. New brief stores a frozen public snapshot identity and bounded context separately from candidate source; the worker never sends hidden environment/check assets.

- [x] Add failing tests covering preparation, no inference, action/proposal protocol, source mutation, consent invalidation, queue binding, context/proposal lineage, resume/replay and final hidden-check barriers.
- [x] Integrate Task 1/2 helpers through existing preparation, worker, verification and advance operations. Keep model settings, one-slot ownership and native acceptance unchanged.
- [x] Freeze separate context-turn and proposal-cycle counts; record actual operations and bytes without claiming token counts. Reject unsupported legacy/ordinary dispatch of the new mode.
- [x] Run all focused contract/campaign tests, then the full existing offline suite and `git diff --check`.
- [x] Update portable docs with exact command/schema/limits and report semantics, without private project examples.

### Task 4: Complete private portfolio and independent final review

**Files:** Private assessment directory and user-facing outputs; generic fixes/tests only in the worktree.

**Interfaces:** Eight original assignment IDs and difficulty distribution remain unchanged. Prepared pack binds each fixture, real environment, public/hidden checks, verified base/reference and independent semantic review. Runtime budgets must be observed, not fabricated.

- [x] Materialize all eight pinned historical/constructed source fixtures. Preserve complete modules and actual routing/model/transaction paths.
- [x] Qualify dependency images and isolated settings. Run each reference and deliberately failing base, with required PostgreSQL concurrency and nonzero expected test discovery.
- [x] Inspect saved exact-runtime measurements without generation. Freeze supported measured budgets if available; otherwise record the precise remaining calibration prerequisite without inventing values or generating responses.
- [x] Obtain one independent final code/security review and independent per-case reference semantic review in the same bounded review package. Resolve critical/important findings with regression tests.
- [x] Complete required lifecycle/security evidence and publish the reviewed follow-up PR. No merge, release or install without the applicable authorization.
- [x] Save the full Qwen preparation report and frozen run preview if all gates pass. No consent or submission command is run.

## Checkpoints and completion

Use at most four phases: source, isolation, integration, preparation. Preserve the private ledger and current test evidence on interruption. Completion means all eight preparations are verified and reviewed; a missing runtime measurement remains an explicit blocker even when software work is complete.

## Preparation result

All eight private fixtures have passing reference checks and meaningful failing-base
checks against frozen source and real migration-backed PostgreSQL. Exact-input
receipts and independent semantic review remain private. Sixteen isolation controls
passed. The combined harness and published assessment-storage integration pass
463 offline tests; the reviewed storage patch keeps disposable reference checks
outside durable plugin state.

The owner-facing preparation report records the remaining gate: saved responses
contain no usable exact-runtime throughput or supported-output-ceiling evidence.
Token/time budgets remain unset, so no runnable campaign, consent or submission was
created. No model responses were generated. Runtime calibration requires separate
authorization; approval and routing remain unchanged.
