# Habblaud Hooks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Display real local attempts beneath their coordinator in unchanged Habblaud.

**Architecture:** Store optional assignment context in existing job route metadata, outside brief identity. A detached, job-owned observer translates saved observations into bounded loopback HTTP hooks. Existing JSON export, routing, inference and verification remain authoritative and independent.

**Tech Stack:** Python 3.11 standard library, SQLite, existing detached runtime bundles; unittest; disposable Habblaud Docker/npm and Chromium checks.

**Spec:** `docs/superpowers/specs/2026-10-22-habblaud-local-visibility-design.md`

## Global Constraints

- Habblaud source/configuration remains unchanged; use existing `/api/codex/events`.
- Optional, disabled by default; global visibility-off also suppresses hooks.
- Labels: `LOCAL · <Role> · <actual model> · <short specialty>`; preserve model, shorten specialty to 48 printable characters.
- Exact roles: Coordinator, Scout, Builder, Tester, Reviewer, Scribe, Investigator. Specialty: nonblank, at most 4,096 characters. Missing fields remain unspecified.
- No dependencies, remote endpoints, proxies, redirects, credentials, fabricated rollouts or task-control effects.
- Refresh every 20 seconds, observe approximately every second, HTTP timeout two seconds, bounded responses/retries.
- Never infer verification from Habblaud completion; document Codex icons, clipping, expiry/completion and statistics/World limitations.
- Only this repository owns the adapter. Coordinate Vibe metadata documentation with chat `01a16391-ad85-72c0-a50c-ade0215b32df`.

## Review Focus

- Concurrent submit/bind/start must preserve job identity and the first visible assignment label (Task 1/2).
- Timeout or lost POST acknowledgment must not duplicate characters or affect inference (Task 2).
- Native fallback must not replace the local model or convert an uncertain attempt to verified (Task 2).
- Restart, disable, rebind and update must retire only owned display entries/processes (Task 2/3).
- Receiver account mismatch, malformed/oversized responses and endpoint changes must not send events to guessed accounts (Task 1/2).

### Task 1: Optional metadata and configuration

**Files:** create `local_model_delegation/habblaud.py`, `tests/test_habblaud.py`; modify `store.py`, `cli.py`.

**Interfaces:** `validate_context(value) -> dict`; `bind_context(db, job_id, context, rebind=False) -> None`; `configure(state_dir, endpoint, account) -> dict`; `status(state_dir, job_id=None) -> dict`; `bind(state_dir, job_id, context) -> dict`. `Store.enqueue(..., visibility=None)` and `submit_task(..., visibility_path=None)` store context transactionally before scheduling.

- [ ] Write tests rejecting invalid roles/UUIDs/oversized specialty/extra keys and proving optional metadata preserves brief/hash, legacy jobs and duplicate submission identity.
- [ ] Write real loopback receiver tests for exact account verification, disabled defaults, literal-loopback endpoints, redirect rejection and bounded responses.
- [ ] Run `python3.11 -B -m unittest tests.test_habblaud`; expect missing feature failures.
- [ ] Implement context/config/status and CLI `habblaud enable --endpoint --account`, `status [--job]`, `disable`, `bind --job --context`; add `submit --visibility-context`.
- [ ] Run focused tests; expect PASS. Commit metadata/configuration.

### Task 2: Hook observer and execution integration

**Files:** extend `habblaud.py`, `tests/test_habblaud.py`; modify `worker.py`, `cli.py`, `package.py`, `updates.py`.

**Interfaces:** `Client(endpoint).snapshot(account)` validates exact account; `.event(account,event)` validates acknowledgment. `Observer(state_dir, job_id).step(now=None) -> bool` publishes one observation, returning whether to continue. `run_observer`, `ensure_observer`, `disable`, `quiesce` reuse ownership/launcher; private publication receipts live under `habblaud/`.

- [ ] Test real HTTP payloads, initial LOCAL label/model, phase transitions, 20-second heartbeat, stable IDs, receiver restart, lost acknowledgments, failure/backoff and no raw task data.
- [ ] Test no character for queue/reservation/history, unknown/stale priority, local model retention after native fallback, label freeze, rebind, disable and global visibility-off.
- [ ] Run focused tests and observe missing behavior failures.
- [ ] Implement observer; launch after submitting transition and resume on status/bind. Keep network outside DB/inference threads. Use existing runtime package selection; do not forward model credentials to display observers.
- [ ] Add subprocess tests for single ownership, status recovery and runtime bundle operation. Test transport failure leaves real fake-model execution/verification unchanged and cleanup never releases reservations.
- [ ] Quiesce visibility observers before update/uninstall snapshots. Run focused tests and full unittest suite; expect PASS. Commit observer/integration.

### Task 3: Deployment verification and documentation

**Files:** README, plugin skills, design evidence; tests only where integration gaps require them. Private evaluation scripts remain outside Git.

**Interfaces:** use the public adapter operations and real observer from Task 2; coordinate the final context format with Vibe Setup.

- [ ] Run the implemented adapter against isolated Docker and npm instances with fixture state and World off; verify snapshot/Chromium label, linkage, phase, heartbeat, restart/stop, duplicate handling and source fingerprints.
- [ ] Document enable/bind/resume/disable, metadata file format, data exposure, lifecycle limitations and rollback; no live enablement or real inference.
- [ ] Run `python3.11 -B -m unittest discover -s tests` and `git diff --check`; expect PASS.
- [ ] Request one independent whole-branch review; fix important findings with regression tests. Commit the complete implementation and verified documentation.
