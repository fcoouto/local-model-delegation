# Model measurements per project implementation plan

> **For agentic workers:** Use `superpowers:executing-plans` to implement this plan natively, task by task. Preserve the owner's restriction against another independent reviewer loop. The owner authorized native implementation on 2026-10-22.

**Goal:** Produce private, auditable model/project reports for quality, native usage, time, and resource suitability without changing routing or executing extra work.

**Architecture:** Extend the existing SQLite database with an independently versioned measurement ledger. Bind project context separately from immutable task briefs, collect durable local outcomes and trusted coordinator receipts, and expose read-only aggregates. Comparisons ingest separately authorized evidence; they do not add an execution engine.

**Tech stack:** Python 3.11+, standard library, SQLite, existing macOS Codex plugin and HTTP helper.

**Spec:** [Model measurements per project](../specs/2026-10-22-project-model-measurements-design.md).

**Source baseline:** `63cc02ba6ef9eb7b3dd372fa726a7e479be65b2c`. Recheck the branch, current source, applicable instructions, and connected callers before implementation. Preserve unrelated onboarding and deferred loading work.

## Completion status

All five source implementation tasks are complete. The original task recipes below remain as planning history; actual checks, self-review findings, implementation adjustments, and remaining qualification gates are recorded in [Offline validation](../../project-measurements-validation.md). The completed offline suite passed 219 tests. No installation or live qualification was performed.

## Global constraints

- Native implementation authorized; live qualification remains separately gated.
- Routing remains disabled; model approval remains unchanged. No live inference, lifecycle operations, installs, provider/default changes, or authentication changes during implementation/tests.
- Python 3.11+ and standard library only; no new service, daemon, dashboard, or provider adapter.
- Existing queue schema, briefs, hashes, approvals, slots, and fallback claims remain unchanged.
- `measurement_meta.version = 1`; queue `PRAGMA user_version` remains unchanged.
- Model output cannot supply authoritative quality, usage, consent, or integration receipts.
- Missing quantities are null, not zero. Savings remain token proxies; actual subscription savings remain unknown.
- Metrics never write profile benefit/suspension/approval fields or call `record_outcome`.
- Synthetic, normal-work, paired-comparison, and legacy records remain distinguishable.
- Private cases and owner evidence stay outside this repository. Use fictional fixtures only.

## Review focus

- A crash after acceptance but before measurement must yield a gap or evidence-based reconciliation, never a guessed success. Task 2 covers this.
- Worktrees, symlink aliases, duplicate labels, and changed environments must not mix unrelated evidence. Task 1 covers this.
- A successful native rescue, repeated receipt, or local rewrite must not inflate local delivery. Tasks 2 and 3 cover this.
- Shared coordinator spans, cached/reasoning subsets, and failed work must not disappear or count twice in savings. Task 3 covers this.
- Read-only reports, disabled exports, and comparison imports must never become control input or trigger inference. Tasks 4 and 5 cover this.

## File structure

Create `local_model_delegation/projects.py` (identity), `local_model_delegation/measurements.py` (ledger/contracts/aggregation), `tests/test_projects.py`, and `tests/test_measurements.py`.

Extend `store.py`, `cli.py`, `package.py`, `worker.py`, `validation.py`, and `visibility.py` only at the hooks described below. Extend their existing tests, the two installed-source skill documents, `docs/onboarding.md`, and `README.md`. Add `skills/local-delegation/references/measurements.md` for exact receipt contracts. Do not edit the installed plugin cache.

Do not change `scheduler.rank_profiles` or `onboarding.record_outcome` in this release. Their existing global behavior is documented as a limitation. Project-aware routing is a subsequent feature, not an implicit effect of metrics collection.

## Task 1: Project identity and additive private ledger

**Files:** Create `projects.py`, `measurements.py`, `tests/test_projects.py`, `tests/test_measurements.py`; modify `package.py`, `cli.py`, `tests/test_plugin.py`, `tests/test_cli.py`.

**Interfaces:**

- `projects.resolve_project_identity(root: Path) -> dict`: returns `kind` (`git` or `directory`) and canonical identity path. Use bounded local Git discovery with `git -C`, argument arrays, no network, and no remote inspection. A Git error is an error, not a silent non-Git identity.
- `measurements.initialize_measurements(state_dir: Path) -> dict`: creates the five namespaced tables in the spec in one transaction; preserves existing queue schema and state.
- `measurements.register_project(state_dir: Path, root: Path, label: str) -> dict`: returns stable `project_id`, `kind`, and `label` for the resolved identity.
- `measurements.begin_measurement(state_dir: Path, task_id: str, context: dict, job_id: str | None = None) -> dict`: immutable context; identical retry succeeds, differing context/job binding fails.
- `measurements.append_event(state_dir: Path, task_id: str, receipt: dict) -> dict`: strict version/kind contract and unique producer/source key; no model calls.

Context fields: `project_id`, `origin`, `scope`, `environment_digest`, `environment_manifest`, `native_binding`, `source_revision`, `case_id`, `case_hash`. Scope contains capability/language/complexity/context bucket/input bytes/file count. Local model binding is captured from the durable selected job profile at admission, not an untrusted context field. Unknown optional facts are null.

Every event contains `schema_version: 1`, `producer`, `source_key`, `kind`, `observed_at`, `payload`, and optional `supersedes`. Validate finite nonnegative counts/durations, bounded strings, strict known keys, predecessor ownership, and JSON limits. Define kind-specific fields beside their consumers in Tasks 2–4; never accept an arbitrary payload as authoritative evidence.

- Write failing tests: shared Git common directory resolves one UUID; independent clones/same labels resolve two; non-Git roots remain separate; canonical aliases resolve consistently; unsafe state is rejected.
- Add tests proving initialization preserves config/profile bytes, queue version, all jobs/attempts/fallback claims, and existing pinned bundles. Repeated initialization must be idempotent; future measurement versions must be rejected.
- Add tests for context/event retry versus conflict, foreign-task corrections, non-finite values, and one unique job binding. Failed validation must write nothing.
- Run `python3.11 -B -m unittest tests.test_projects tests.test_measurements tests.test_plugin tests.test_cli -q`; confirm the new assertions fail before implementation.
- Implement the interfaces and `metrics init`, `metrics register --root --label`, `metrics begin --task --context [--job]`, and `metrics record --task --receipt`. Fresh `initialize_state` calls initialization; existing state uses explicit `metrics init`. Readers must not create state.
- Rerun affected tests and commit only this task's changes.

## Task 2: Bind real task outcomes without changing execution

**Files:** Modify `store.py`, `cli.py`, `worker.py`, `validation.py`, `measurements.py`; extend `tests/test_store.py`, `tests/test_worker.py`, `tests/test_delegation.py`, `tests/test_validation.py`, `tests/test_measurements.py`.

**Interfaces:**

- Extend `Store.enqueue(brief, fallback, assessment=None, measurement=None)` and `submit_task(state_dir, path, measurement_path=None)`; expose `submit --measurement-context`. Default callers remain unchanged. Measurement metadata is not part of the model brief.
- `measurements.capture_job_observation(state_dir: Path, job_id: str) -> dict`: records only available durable identity/state/timing; records coverage gaps explicitly.
- `measurements.record_local_verdict(state_dir: Path, job_id: str, evidence: dict) -> dict`: validates attempt/candidate/check binding and preserves the local verdict before fallback replacement.
- `measurements.reconcile_measurements(state_dir: Path) -> dict`: idempotent recovery from existing bound evidence only; no scheduling or inference.

Define typed `local_verdict`, `delivery`, and `incident` payloads. Local verdict contains attempt ID, candidate hash, check-receipt hash, accepted/rejected verdict, and controlled failure category. Delivery contains final artifact hash, destination-check receipt hash, `unchanged_local|native_edited|native_fallback|not_integrated`, and native task ID when applicable. Summary delivery uses a verified answer hash instead of a repository commit. Incident contains affected delivery event, evidence reference/hash, and `confirmed|withdrawn` disposition. All are coordinator/helper-authored, not model-authored.

- Reproduce in fixtures: local failure followed by native success; a second candidate overwriting current verification files; duplicate enqueue with changed context; crash before receipt collection; active/uncertain attempt; accepted-but-not-integrated candidate.
- Assert local verdict survives fallback, native success is not local success, uncertainty remains pending, old unscoped jobs stay unscoped, and replay never adds another attempt or receipt.
- Add timing tests for queue/inference/verification/delivery boundaries, clock reversal, and unknown restart intervals. No fake zero durations.
- Run `python3.11 -B -m unittest tests.test_store tests.test_worker tests.test_delegation tests.test_validation tests.test_measurements tests.test_cli -q`; confirm new tests fail.
- Attach immutable metadata on enqueue, selected binding on admission, and local verdict at the common verifier/fallback seams. Preserve check evidence by candidate hash. Add only missing timestamps/durations; keep stale/admission/recovery behavior unchanged.
- Expose `metrics reconcile`. A missing measurement schema/export failure must leave task execution intact and report degraded coverage; an explicit malformed receipt must fail.
- Rerun affected tests and existing recovery/scheduler tests. Commit the coherent change.

## Task 3: Honest quality, time, usage, and savings aggregates

**Files:** Modify `measurements.py`; extend `tests/test_measurements.py`.

**Interfaces:**

- `measurements.record_usage(state_dir: Path, task_id: str, receipt: dict) -> dict`: validates native binding, producer schema, span ownership, phase, completeness, and optional one-time overhead allocation.
- `measurements.build_report(rows: dict, *, project_id: str, profile_id: str | None, now: float) -> dict`: pure function; returns versioned cohorts, numerators/denominators, coverage, time summaries, comparison method, savings proxy, and explicit unknown reasons.
- `measurements.read_report(state_dir: Path, *, project_id: str, profile_id: str | None = None) -> dict`: opens SQLite read-only and supplies all relevant ledger records; no model discovery or mutation.

Usage payload fields: native binding, `source_run_id`, `span_id`, start/end, `phase`, `usage_schema`, token fields, `complete`, `attribution` (`exclusive|shared|unknown`), and evidence hash/reference. Authoritative totals and decompositions carry a common group ID with explicit `total|component` role. Components cannot be added to their authoritative total. Unknown source schemas and unresolved shared attribution cannot yield savings. One-time spans have allocation fractions per cohort whose sum cannot exceed 1; unallocated remainder stays visible.

- Add table-driven tests for every denominator in the spec; separate first-candidate verdicts, local delivery, admission fallback, native rescue, cancellation, pending, and confirmed/withdrawn incidents.
- Test version/environment/project separation, three repeated cases versus six distinct cases, last-30 versus lifetime, missing timings, and p95 hidden at 19 samples but present at 20.
- Add a fictional arithmetic fixture: baseline 1,000 tokens, complete delegated-route usage 300, allocated overhead 100; expected proxy 600. A failed route with 1,100 usage and 100 overhead produces -200, never zero.
- Test every missing term gives unknown; unique spans count once; totals plus components do not double-count; cached/reasoning subsets are not added twice; mixed producers/models are incomparable; partial coverage is not a whole-cohort claim.
- Test allocating one overhead span across two projects cannot charge more than its original amount. An incomplete allocation leaves all-in savings unknown.
- Run `python3.11 -B -m unittest tests.test_measurements -q`; confirm failures, implement the pure calculations with standard-library functions, then rerun.
- Verify successful local-only selection cannot hide fallback costs or failed native baselines. Commit after the affected tests pass.

## Task 4: Register and compare separately authorized evidence

**Files:** Modify `measurements.py`, `cli.py`; extend `tests/test_measurements.py`, `tests/test_cli.py`.

**Interfaces:**

- `measurements.register_comparison(state_dir: Path, manifest: dict) -> dict`: records frozen manifest/hash and consent provenance; never creates jobs.
- `measurements.record_comparison_run(state_dir: Path, comparison_id: str, receipt: dict) -> dict`: validates linked task/attempt and consent budget; returns consumed/remaining allowance and evidence completeness.
- CLI: `metrics comparison-register --manifest`, `metrics comparison-record --comparison --receipt`.

Manifest fields: project/cohort, case IDs and snapshot/contract/check hashes, exact local/native bindings, local/native maximum calls, consent reference, expiry/revocation evidence, and method (`paired|observational`). Run receipt links case, route, task ID, attempt identity, submitted/uncertain/completed state, source/check hashes, execution-order index, isolation evidence, and evaluator provenance. Registration is bookkeeping, not permission to execute. The external executor must reserve/enforce its own authorized budget before POST; report ingestion cannot retroactively prevent excess calls.

- Write failing tests rejecting changed artifacts/cases/checks/settings, duplicate pair legs, wrong project, native fallback used as baseline, missing isolation, and reused consent for a different manifest.
- Test identical receipt replay consumes no additional allowance; distinct failed and uncertain attempts do. Over-budget evidence is retained as a violation, excluded from qualification, and never triggers retry.
- Test normal-work baselines are labelled observational; a paired label requires matching frozen cases and independent execution. Native baseline failure stays visible and cannot become a comparable saving.
- Patch runtime streaming, native dispatch, and lifecycle functions to raise in command tests; all registration/report operations must still pass with zero calls.
- Implement bounded ledger/import behavior only. Do not extend `begin_assessment`, its bundled fixture consent, or native fallback dispatch to run arbitrary cases.
- Run `python3.11 -B -m unittest tests.test_measurements tests.test_cli tests.test_onboarding -q`; commit once passing.

## Task 5: Reports, optional visibility, coordinator guidance, and release proof

**Files:** Modify `cli.py`, `visibility.py`, `package.py`, `README.md`, `docs/onboarding.md`, `skills/local-delegation/SKILL.md`, `skills/setup/SKILL.md`; add `skills/local-delegation/references/measurements.md`; extend `tests/test_cli.py`, `tests/test_visibility.py`, `tests/test_plugin.py`, `tests/test_measurements.py`.

**Interfaces:**

- CLI: `metrics report --project --model [--format json|text]` (`--model` optional; JSON default).
- `measurements.render_text_report(report: dict) -> str`.
- `visibility.build_measurements_snapshot(report: dict, generated_at: float) -> dict`: sanitized read-only projection, sharing the existing visibility preference.

- Add failing tests for empty/old state without writes, all cohorts visible, exact unknown reasons, correct format, and no usage figure inferred from account limits or text length.
- Test export excludes source/prompts/paths/remotes/secrets; disabled visibility removes both exports and never republishes them. Export failures must not alter accepted work. Reports must work with visibility disabled.
- Document the exact context/event/usage/comparison schemas, first-release limits, and examples using fictional data. Explain optional host receipt capture and unsupported telemetry yielding unknown savings.
- Update coordinator guidance to capture normal-work context and final integration, preserve canonical verification, include its own overhead, and use report recommendations without granting approval. Keep legacy `outcome` behavior explicit and separate; do not double-submit receipts to both APIs as if they were one measurement.
- Implement commands and projection. Keep existing generic task labels. Make private collection independent of the viewer; extend uninstall/export cleanup without deleting measurement history.
- Run `python3.11 -B -m unittest discover -s tests -t . -q` and `git diff --check`. Check Markdown links and package portability. Run the skill validator only if its existing dependencies are available; otherwise record the limitation without installing anything.
- Replay a fictional sequence covering two projects, local acceptance, failed local plus native rescue, missing usage, a comparable pair, an uncertain attempt, and a process restart. Assert zero inference/lifecycle calls and unchanged routing/profile/auth fixtures.
- Perform native self-review against the spec and every connected caller. No new independent reviewer loop. Commit coherent corrections and record exact source revision/check results.

## Stop condition and live qualification handoff

Finish when the offline release proves truthful, private, per-project measurements and read-only reports. Do not activate routing or run a model to complete this implementation plan.

Before a later project pilot: establish a supported native usage source and its attribution semantics; obtain fresh bounded authorization for any extra comparison calls; verify the executor can enforce that manifest; select representative project cases and unchanged acceptance checks. Existing small synthetic trials may remain visible as historical model evidence but cannot populate project delivery metrics.

Remaining gates: real-host collection continuity, realistic project reliability, measured total native overhead/net benefit, arbitrary project comparison execution, and project-aware routing policy. Automatic loading and parallel capacity remain separate deferred qualifications.
