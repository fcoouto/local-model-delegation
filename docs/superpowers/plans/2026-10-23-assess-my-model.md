# Assess my Model Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Preserve the owner's chosen execution method and current model, reasoning, provider, authentication, and permissions.

**Goal:** Add **Assess my Model**, with focused ability selection, optional full coverage, consent per run, private evidence, and onboarding only on explicit request.

**Architecture:** Extend the assessment implementation already used by Setup in `local_model_delegation/onboarding.py`. Both skills share its fixture builder, authorization, submission, verification, and report paths. Keep the current queue, runtime adapter, state directory, fixtures, and approval commands; add only the missing run-specific behavior.

**Tech Stack:** Python 3.11+, standard library, existing SQLite/JSON private state, macOS isolation, LM Studio loopback HTTP, Markdown skills, and `unittest` fake runtimes.

**Spec:** [Approved design](../specs/2026-10-23-assess-my-model-design.md). The owner explicitly requires reuse of Setup functionality, without duplicate implementations.

## Global Constraints

- User-facing action name: **Assess my Model**. Default: focused ability. Explicit alternative: **All supported abilities**.
- Three distinct synthetic cases repeated twice: six trials per current group; six current groups and 36 trials for all. Derive counts from the installed manifest.
- One slot; no total inference deadline; no automatic retries of submitted, failed, completed, or uncertain trials.
- Already-downloaded, loaded text models through the supported LM Studio connection. No implicit install, download, load, reset, model approval, or routing change.
- Save unapproved profiles and reports privately. Preserve existing approvals, operating scope, benefit/capacity/suspension evidence, settings, and selected state directory.
- Consent belongs to one frozen run. Never temporarily enable `assessment_policy` to authorize it. Preserve legacy standing-consent behavior without converting its history.
- Native verification remains required; native fallback cannot solve an assessment. Never apply synthetic candidates to the user's project.
- Separate new inference permission from verification/reconciliation of submitted work. Pause/stop must not make existing requests untrackable.
- Synthetic results cannot establish project reliability, specialist competence, higher concurrency, or subscription savings.
- No new dependency, service, fixture pack, profile registry, queue, runtime adapter, verification engine, or duplicated Setup procedure.
- Before implementation, reverify the task worktree with the installed Vibe helper. Use at most four publication checkpoints, only under applicable publication authority. Do not alter unrelated harness files to execute this plan.

## Review Focus

1. Consent revoked between admission and POST: no later submission commitment, no replay, and no false claim of cancellation. Task 3 tests this race.
2. Interrupted execution after submission intent but before acknowledgement: preserve uncertainty and the original slot. Task 3 tests process loss and repeated resume.
3. Approved model reassessed through an unapproved profile: preserve original permissions and avoid leaking assessment outcomes into routing. Tasks 1, 4, and 5 test this boundary.
4. Old evidence read after profile/artifact/runtime removal: retain historical results without inference, initialization, or false current qualification. Task 4 tests this case.
5. Existing standing-consent runs and update preparation encounter new run records: reject unknown formats and active run permission without relabelling history. Tasks 2 and 3 test compatibility.

---

## Reuse map and file responsibilities

Source inspected on 2026-10-23 at `375cb0ce7fdc46d17be5b68fa2e2c067322f2d34`. Recheck symbols and callers if the implementation base changes. Setup is a Markdown workflow; its reusable executable behavior lives in the Python core.

| Existing owner | Reuse or narrow extension |
| --- | --- |
| `skills/setup/references/operations.md` | Keep canonical state selection, connection/authentication, profile preparation, approval, update, and removal procedures here. Link to them from the new skill; do not copy them. |
| `package.initialize_state`, `package.doctor` | Reuse authorized minimal state initialization and read-only prerequisite inspection. No second bootstrap. |
| `onboarding.discover_models`, `profiles.fingerprint_artifact`, `profiles.model_identity`, `lmstudio.select_loaded` | Reuse discovery and exact identity checks. |
| `profiles.validate_profile` | Extract its structural/request-setting validation into a shared helper; ordinary eligibility remains in `validate_profile`. Never fake approval to validate an assessment profile. |
| `onboarding.begin_assessment`, `fixtures_path`, `_profile`, `_binding`, `_assessment` | Extract the existing trial-construction block once, then call it from both legacy begin and new run preparation. Keep fixtures under Setup. |
| `onboarding.authorize_assessment`, `profiles.authorize_job` | Add explicit submit/verify purposes with versioned run handling; retain the legacy branch. |
| `onboarding.submit_trial`, `record_trial` | Extend these existing functions for idempotent run submission and historical receipts. No parallel submit/record API. |
| `Store.lookup`, `enqueue`, `admit`, `transition`, `claim_fallback` | Keep job identity and attempts authoritative. Add only the gates and read-only constructor path needed below; no second job registry or schema migration. |
| `worker.ownership`, `run_local_attempt`, `reconcile_attempts`, `wait_job`; `scheduler.schedule_once` | Reuse locking, durable POST intent, execution, reconciliation, and waiting. Keep streaming and recovery behavior. |
| `validation.verify_candidate`, `prepare_verification`, `run_native_checks`, `record_verification` | Preserve the checkers and receipt bindings. Change only which authorization purpose they request. |
| `onboarding.assessment_report`, `approve_scope`, `approve_assessment` | Share bucket aggregation and extend the existing report by record version. Approval stays an explicit Setup operation. |
| `updates._disabled`, `_settled_assessments`, `package.prepare_uninstall` | Recognize active per-run permission and preserve bound settled-receipt behavior. |
| `tests.support.Fixture`, `FakeRuntime` | Extend disposable fixtures where needed. Do not build another fake HTTP runtime. |

**New files:** `tests/test_assessment_runs.py`, `skills/assess-my-model/SKILL.md`, `skills/assess-my-model/agents/openai.yaml`, `skills/assess-my-model/references/operations.md`, and `tests/fixtures/assessment-scenarios.json`.

**Modified files:** the core files in the table where explicitly named by a task; `local_model_delegation/cli.py`; existing onboarding, worker, scheduler, update, store, plugin, CLI, and validation tests where the changed contract is owned; `skills/setup/SKILL.md`, its operations reference, `README.md`, `docs/onboarding.md`, `docs/qualification.md`, and `docs/updating.md` for entry-point and compatibility pointers. Keep `plugin.json`'s onboarding skill unchanged. No manifest version bump or release/install work is included.

In task file lists, unqualified Python source filenames refer to `local_model_delegation/`; test filenames refer to `tests/`.

## Concrete record and command decisions

Keep `assessments/<assessment_id>/assessment.json` and the existing two-field job permit `{assessment_id, permit_token}`. Add `schema_version: 1` only to new run records; existing unversioned records remain legacy. Reject any unknown version, malformed versioned record, or unversioned record containing new-format fields instead of treating it as legacy.

New records retain existing trial/receipt fields and add an immutable `preview`, its `preview_digest`, `profile_snapshot`, verification/runtime snapshots, and `authorization`. The authorization has `mode: "run"`, state `draft|authorized|paused|stopped|invalidated|complete`, nullable owner reference/timestamp before consent, and the fixed preview digest. Mutable status and receipts are excluded from the preview hash. Freeze the selected group tuples, exact trial briefs/checks, model/settings identity, loaded configuration, helper/fixture identity, verification executable identities, per-trial output allowances, and maximum submissions. Keep instance/generation fencing in existing attempts; a new instance does not erase an uncertain older attempt.

Also freeze `source_profile` as null for a new candidate or `{profile_id, binding, approval_at_preparation}` for an explicitly selected existing profile. This provenance is informational and never supplies assessment or delegation permission. Preserve the exact selected source ID even when several approved profiles share the model binding. Compare source/candidate artifact and runtime identity when preparing the link; their separately recorded request settings may differ for an explicitly requested assessment. Later source changes or deletion cannot erase that snapshot or transfer authority.

Jobs and attempts remain the submission ledger. Do not maintain a second mutable counter that can disagree with `Store.lookup` or `reserved -> submitting`. One trial can cross that durable submission boundary only once. A definitely unsubmitted reservation may be deferred/re-admitted; a possible submission may not.

Selection JSON is exactly either `{"all": true}` or `{"groups": [{"capability": "test_writing", "language": "python", "complexity": "simple", "context_bucket": "small"}]}`. A focused request selects one exact group; the full option selects every manifest group. Reject empty, duplicate, unknown, mixed, or malformed selections. The conversation translates readable abilities to these existing capability identifiers.

Extend the existing `assessment` command family:

| Command | Arguments and behavior |
| --- | --- |
| `choices` | List manifest groups and counts; no private-state initialization or HTTP. |
| `prepare` | `--profile-id ID --selection FILE`, optionally `--source-profile-id ID` for reassessment; freeze a draft after read-only prerequisite/identity checks; no generation. |
| `consent` | `--assessment-id ID --preview-digest HASH --owner-reference REF`; authorize that draft only. |
| `pause`, `stop`, `resume` | `--assessment-id ID`; control that run. Resume returns pending work/next trial, and never resubmits a completed attempt. |
| `submit`, `trial` | Keep existing arguments; extend the existing functions for new records. |
| `report` | Keep `--assessment-id ID`; optional `--check-current` performs read-only current matching for new runs. Default new-run report is offline. |
| `begin`, `capacity`, `approve` | Preserve legacy behavior. New runs cannot use legacy capacity/approval entry points; explicit onboarding uses Setup's existing `profile approve`. |

No new automatic campaign worker. The skill coordinates one trial through existing submit/wait/check/record operations, then continues to the next authorized trial. A restarted conversation uses the same run ID.

### Task 1: Share preparation and add frozen focused previews

**Files:** modify `onboarding.py` (`begin_assessment` construction block), `profiles.py` (`validate_profile`), `tests/support.py` only if needed; create `tests/test_assessment_runs.py`; extend `tests/test_onboarding.py` and `tests/test_profiles.py` for compatibility.

**Interfaces:**

- Add `profiles.validate_profile_fields(p: dict, capability: str) -> dict`, extracted from the existing validator. `validate_profile(p, capability)` still calls it, fingerprints the artifact, and enforces eligibility.
- Add `onboarding._build_trials(state_dir: Path, assessment_id: str, profile: dict, manifest: dict, *, groups: list[dict] | None = None) -> list[dict]`. `groups=None` preserves legacy filtering, fallback capability handling, and missing-toolchain behavior. Explicit groups require exact coverage and never silently skip/remap a group.
- Add `onboarding.assessment_choices() -> dict` returning `groups` with `distinct_cases`/`trials` and `total_trials`.
- Add `onboarding.prepare_assessment(state_dir: Path, profile_id: str, selection: dict, *, source_profile_id: str | None = None) -> dict` returning `{assessment_id, state, preview, preview_digest}`. It writes a draft only; the permit remains private. The optional source ID captures the informational provenance defined above without modifying either profile.

- [ ] **Step 1: Add failing focused-selection tests.** Use `AssessmentRuns(Fixture)` in the new test file. Its setup creates a `FakeRuntime`, points a fictional unapproved profile at it, and saves it through `write_config(..., enabled=False)` without standing consent. Use all four current candidate capabilities for the full-pack test. If supported discovery metadata is needed, add an optional `model_format` argument to `FakeRuntime` with its old default unchanged and match the fictional catalog; do not duplicate the server. Core assertions:

```python
def test_focused_preview_has_six_trials_without_inference(self):
    run = prepare_assessment(self.state, 'fictional', {
        'groups': [{'capability': 'test_writing', 'language': 'python',
                    'complexity': 'simple', 'context_bucket': 'small'}]})
    self.assertEqual(run['state'], 'draft')
    self.assertEqual(run['preview']['distinct_cases'], 3)
    self.assertEqual(run['preview']['max_submissions'], 6)
    self.assertFalse(any(method == 'POST' for method, _ in self.server.calls))

def test_all_preview_preserves_six_distinct_groups(self):
    run = prepare_assessment(self.state, 'fictional', {'all': True})
    self.assertEqual(len(run['preview']['groups']), 6)
    self.assertEqual(run['preview']['max_submissions'], 36)
```

Also test invalid selections, absent selected capability, missing Node/isolation, unavailable or ambiguous loaded identity, context that cannot fit, changed settings/toolchain between preparation and use, and an approved input profile. Assert rejection before generation, no silent reduced pack, and byte-for-byte preservation of the original approved profile and configuration. Test explicit provenance selection among two approved profiles sharing a binding and rejection of an unrelated source identity. Missing prerequisites return a precise error and no runnable draft.

- [ ] **Step 2: Run `python3.11 -B -m unittest tests.test_assessment_runs -q`.** Expect failure because the new functions do not exist; inspect the actual failure.
- [ ] **Step 3: Extract and implement the interfaces above.** Use `validate_brief`, `private_dir`, `atomic_json`, `_binding`, `select_loaded`, `generation_settings`, `context_fits`, and existing isolation checks. Reuse `pin_runtime_bundle` for helper identity and its immutable files; freeze declared checker executable identities without writing a new package hasher. Store source package/version provenance where available; pinned worker bundles do not contain `plugin.json`, so do not call `updates.package_identity` indiscriminately from a worker. Do not add a profile factory: canonical Setup operations still prepare the private profile, with `approval=null`, empty scope, and `qualification_status=needs_assessment`. Preparation rejects an approved profile rather than modifying it.
- [ ] **Step 4: Run `python3.11 -B -m unittest tests.test_assessment_runs tests.test_onboarding tests.test_profiles tests.test_plugin -q`.** Expect all tests passing, including unchanged legacy fixture behavior and pinned-runtime relocation.
- [ ] **Step 5: Commit only this task's files** with `refactor: share assessment preparation and add focused previews`.

### Task 2: Add run consent without weakening historical verification

**Files:** modify `onboarding.py` (`_assessment`, `authorize_assessment`, `record_trial`, `record_capacity`, `record_outcome`), `profiles.py` (`authorize_job`), `validation.py` (all authorization call sites); extend `tests/test_assessment_runs.py`, `tests/test_onboarding.py`, `tests/test_validation.py`, and `tests/test_delegation.py` as appropriate.

**Interfaces:**

- Add `onboarding.consent_assessment(state_dir: Path, assessment_id: str, preview_digest: str, owner_reference: str) -> dict` returning `{assessment_id, state}`. A matching replay is idempotent; stopped/invalidated/complete runs cannot obtain fresh permission through this function.
- Extend `onboarding.authorize_assessment(state_dir, brief, permit, *, purpose: str = "submit", job: dict | None = None) -> dict`.
- Extend `profiles.authorize_job(store, job, *, purpose: str = "submit") -> dict`. Only the assessment branch gains new semantics; normal task approval remains unchanged.
- Keep `record_trial(state_dir, assessment_id, receipt)`, its required `{trial_id,job_id}` fields, and the existing permit shape.

- [ ] **Step 1: Add failing consent and verification tests.** Assert that `submit` rejects a draft with `assessment_consent_required`, including when global standing permission is true. A wrong digest/reference, changed identity/settings/fixtures/checker, malformed version, or substituted brief must fail. Matching repeated consent must not create another run or change config. Add `test_revoked_run_can_verify_only_its_submitted_candidate`: after a durable local submission and bound candidate receipt, mark the run stopped; normal protected/native checkers may verify it, while a different job or an unsubmitted brief is rejected. Preserve all existing legacy policy/revocation assertions.

```python
with self.assertRaisesRegex(ValueError, 'assessment_consent_required'):
    authorize_assessment(self.state, trial['brief'], permit)
consent_assessment(self.state, run_id, preview_digest, 'fixture-run-consent')
self.assertEqual(authorize_assessment(self.state, trial['brief'], permit)['profile_id'],
                 'fictional')
self.assertEqual((self.state / 'config.json').read_bytes(), original_config)
```

Use the prepared record to obtain `run_id`, `trial`, `permit`, and `preview_digest`; `original_config` is captured before consent. No fabricated accepted receipt is sufficient for the historical-verification test: exercise the existing candidate/check binding.

- [ ] **Step 2: Run `python3.11 -B -m unittest tests.test_assessment_runs tests.test_onboarding -q`.** Expect the new consent/purpose tests to fail before implementation.
- [ ] **Step 3: Implement versioned authorization inside the existing functions.** Legacy records continue through `_policy` and their existing current-binding checks. New submit authorization requires active run consent and the frozen preview binding. New verify authorization requires a matching persisted job, permit, frozen brief/profile/settings, and evidence of its original committed attempt; it uses the saved snapshot, not renewed permission or current model availability. Retain source/candidate hashes, checker identity, receipt tokens, and instance/generation fencing. Update every `validation.authorize_job` call to request `purpose="verify"`; make `record_trial` use the same path for historical receipt recording. Submission, scheduler, admission, and worker calls keep submit semantics. Reject new-format runs in legacy capacity/global-outcome mutators so they cannot update model-global evidence.
- [ ] **Step 4: Run `python3.11 -B -m unittest tests.test_assessment_runs tests.test_onboarding tests.test_validation tests.test_delegation tests.test_profiles -q`.** Expect all passing. Search every `authorize_assessment`/`authorize_job` caller and verify its purpose; ordinary task checks must still enforce current approval.
- [ ] **Step 5: Commit** with `feat: bind assessment consent to individual runs`.

### Task 3: Fence dispatch, pause/stop/resume, and maintenance

**Files:** modify `onboarding.py` (`submit_trial`, new controls), `worker.py` (`run_local_attempt`, `reconcile_attempts`), `scheduler.py` (`schedule_once`, scheduler exit behavior), `store.py` (`admit` only where needed), `updates.py` (`_disabled`, `_settled_assessments` if necessary), and `package.py` (`prepare_uninstall`); extend assessment, worker, scheduler, store, update, and plugin tests.

**Interfaces:**

- Add `onboarding.control_assessment(state_dir: Path, assessment_id: str, action: str) -> dict`, with `action` exactly `pause|stop|resume`, returning `{assessment_id, state, pending_jobs, next_trial_id, blockers}`. `next_trial_id` is null while any earlier submitted trial needs verification/reconciliation or while the run cannot submit.
- Extend `worker.reconcile_attempts(state_dir, *, assessment_id: str | None = None)` with an optional filter. Omission preserves current behavior; a run-specific resume reconciles only its jobs/checkers and their affected instances.
- Add `onboarding.require_assessments_paused(state_dir: Path) -> None` for maintenance checks. It rejects any new-format run still authorized to submit; unknown/malformed records fail closed.
- Keep `submit_trial`, queue keys, attempt transitions, HTTP streaming, and native fallback rejection as the execution interfaces.

- [ ] **Step 1: Add failing concurrency/lifecycle tests.** Use event/barrier synchronization and the existing fake server, not timing guesses. Required assertions: two submissions of one trial yield one job and one POST; second trial is not submitted before the first reaches a final verified disposition; stop before the dispatch commitment yields zero POSTs; stop after commitment retains the original attempt; a killed worker after commitment never gets a second POST; pause followed by explicit resume can run a never-submitted trial; stop is terminal; missing/changed identity invalidates new work; a successful or failed completed trial never repeats. Validate the original `assessment_has_no_native_fallback` error.

```python
self.assertEqual(first['job_id'], repeated['job_id'])
self.assertEqual(self.server.calls.count(('POST', '/api/v1/chat')), 1)
self.assertEqual(store.attempt(attempt_id)['state'], 'uncertain')
with self.assertRaisesRegex(ValueError, 'assessment_stopped'):
    control_assessment(self.state, run_id, 'resume')
```

These assertions belong respectively to idempotency, lost-observer, and terminal-stop tests, each using its own disposable fixture. Add maintenance tests: active authorized run with no queued jobs blocks update/uninstall preparation; paused settled run remains preserved; ambiguous attempts still block; failed bound receipts retain `_settled_assessments` compatibility.

- [ ] **Step 2: Run `python3.11 -B -m unittest tests.test_assessment_runs tests.test_worker tests.test_scheduler tests.test_updates tests.test_plugin -q`.** Expect the new lifecycle/race tests to fail.
- [ ] **Step 3: Implement controls and the narrow dispatch fence.** Reuse `ownership(store, 'assessment-' + id)` for consent/control/submission and the worker's final authorization plus `reserved -> submitting` transition. This transition is the submission commitment: after it, stop cannot promise cancellation, even if the network call has not returned. Release the run lock before streaming. Never hold a run lock while waiting for model output. Keep run-lock-before-SQLite ordering; authorization reads inside `Store.admit` must not acquire the run lock while its database write transaction is held. Lock contention returns a retryable busy result, not fallback or permission.

`submit_trial` first reconciles the frozen trial's existing queue identity; repeated calls return the existing job without launching another worker. Permit at most one unfinished trial per run. A paused definitely-unsubmitted reservation may be safely released/deferred under existing fencing; a committed or uncertain attempt is never released because of run status. Keep paused waiting jobs pending, ensure the scheduler does not spin on them, and relaunch scheduling only on authorized resume. Reuse `Store.decide_wait` for existing wait-budget decisions; the coordinator must explicitly extend a capacity wait without creating another trial or claiming a model failure. Identity/safety/uncertainty blockers pause progress; ordinary verified model failure allows the remaining authorized trials.

Resume reconciles existing attempts, records available final receipts, and returns the next eligible trial. It does not spawn a new campaign or reset a budget. A terminal run returns a report; paused requires explicit resume; stopped/invalidated cannot resume. Include pending-checker recovery in the optional reconciliation filter, preserving instance-wide recovery safeguards.

Add run-permission checks to the existing update/uninstall prerequisites. Reuse the `plugin-update` maintenance lock for consent/resume activation versus update checks, with a consistent outer-maintenance/inner-run/SQLite order where combined. Pending update preparation must not cause implicit run resume; the Setup update procedure pauses these runs before preparing and never restores per-run permission automatically. Preserve current package/state backup and quiescence checks rather than inventing maintenance state or overriding uncertainty.

- [ ] **Step 4: Run the Task 3 tests plus `tests.test_recovery tests.test_generation_budgets tests.test_store`.** Expect all passing, including ordinary task scheduling, loaded-model behavior, exhausted-generation handling, and existing update preservation.
- [ ] **Step 5: Commit** with `feat: make assessment runs resumable and revocable`.

### Task 4: Extend the existing report for offline, private evidence

**Files:** modify `onboarding.py` (`assessment_report`, shared bucket aggregation, `record_trial`), `store.py` (`Store.__init__`, `db`), and tests for assessment runs, onboarding, store, measurements, and updates where relevant.

**Interfaces:**

- Extend `Store(state_dir: Path, *, read_only: bool = False)`. Read-only mode validates existing state and reads a stable snapshot of the database and committed WAL. SQLite opens only a disposable private copy, then reads from memory; it never creates or changes files in saved state, initializes schema, changes its journal mode, or permits `db(write=True)`. Reject a repeatedly changing snapshot instead of dropping WAL commits. Default behavior is unchanged. Independent review established that opening saved state directly with `mode=ro` can create or modify sidecars, so the snapshot replaces that original implementation choice.
- Extract `onboarding._assessment_buckets(assessment: dict) -> list[dict]` from the existing reporter, retaining its grouping/coverage rules.
- Extend `onboarding.assessment_report(state_dir, assessment_id, *, check_current: bool = False) -> dict`. Legacy records retain their original live-binding/approval-report semantics; the flag adds optional current checking only for new runs. New records return the standalone report below from snapshots, receipts, and read-only saved jobs.
- Keep `record_trial` as the evidence writer. Extend its stored receipt with observed disposition/reason/timing when available; preserve the existing `trial_id`, `job_id`, `passed`, and `status` keys consumed by update checks.

- [ ] **Step 1: Add failing report tests.** Cover partial completion, pending verification, owner stop, budget exhaustion, unavailable checks, stale identity, runtime offline, profile/artifact removal, missing historical database, and a report after over 100 unrelated completed jobs. Include `test_reassessment_retains_source_profile_when_changed_or_deleted`: preserve the selected source ID and original snapshot, report its current recorded approval as changed/unavailable, and keep the assessment profile unapproved. Assert no writes, no generation, no new private state, exact historical results, and no cross-run mixing. Test read-only Store with absent/unsafe state and a forbidden write transaction; retain all existing default-Store tests.

```python
report = assessment_report(self.state, run_id)
self.assertEqual(report['counts']['planned'], 6)
self.assertEqual(report['freshness'], 'unverified')
self.assertEqual(report['profile']['approval'], None)
self.assertEqual(self.server.calls, before_calls)
self.assertEqual(config_path.read_bytes(), before_config)
```

The offline test removes the current profile after recording bound historical receipts. Additional assertions must compare passed/failed/not-run totals with those receipts, not only the example fields above. Snapshot existing approved profile and global evidence before the run and require identical bytes afterward.

- [ ] **Step 2: Run `python3.11 -B -m unittest tests.test_assessment_runs tests.test_store tests.test_onboarding -q`.** Expect the new offline/read-only tests to fail.
- [ ] **Step 3: Implement the existing reporter's versioned branch.** Return `schema_version:1`, `assessment_id`, `state`, `profile` snapshot, informational `source_profile`, `groups`, `counts`, `trials`, `freshness`, `limitations`, and separately observed operating state. Show the source profile's current recorded approval separately, or changed/unavailable status; a saved approval is not a newly verified binding. Default reporting may read that private profile file but cannot contact the runtime or fingerprint unavailable model files. Define `planned`, `submitted`, `passed`, `failed`, `awaiting_verification`, `unresolved`, and `not_run`; also expose evaluated count so passed/evaluated never hides the planned denominator. Distinguish model failure from infrastructure/checks unavailable. Use actual attempt observations for timing/tokens or null, never estimated usage. Preserve the original snapshot and add `current|stale|unverified` freshness without rewriting its verdict.

Reuse `_assessment_buckets` for both reporters. Query only this run's exact trial keys through read-only Store; do not use visibility's truncated recent-job list, and do not require initialized measurement tables. When a database is missing, retained final receipts still render and missing job details stay unknown. Default reporting makes no runtime call and does not write `report.json`; evidence-writing/control operations refresh that derived private report using `atomic_json`. No model-global `record_outcome`, capacity update, normal-project delivery, or savings calculation is added. A valid full group can be described as provisional synthetic evidence; it is never a new approval recommendation.

`record_trial` marks an authorized or paused run complete only when every planned trial has a final disposition. It never overwrites stopped/invalidated status. Repeated receipt recording must be idempotent, including after stop or completion. `submitted` counts trials with durable submission intent; outcome categories retain not-run and infrastructure/verification gaps rather than treating them as model failures. Derived reports may refresh; original bindings and final receipts remain immutable.

- [ ] **Step 4: Run `python3.11 -B -m unittest tests.test_assessment_runs tests.test_onboarding tests.test_store tests.test_measurements tests.test_updates -q`.** Expect all passing, including legacy `assessment approve` behavior for legacy records. New-format records are directed to explicit Setup/profile approval instead of that legacy command.
- [ ] **Step 5: Commit** with `feat: report standalone assessment evidence`.

### Task 5: Wire the action and shared procedures; validate end to end

**Files:** modify `cli.py`, `tests/test_cli.py`, `tests/test_plugin.py`, Setup skill/reference and the documentation listed above; create the new skill, metadata/reference, and `tests/fixtures/assessment-scenarios.json`. Extend the assessment tests for complete fake-runtime flows.

**Interfaces:** CLI table above maps directly to Task 1–4 functions. `prepare` reads selection through existing `cli.read_input`. No new wrapper CLI or duplicated core code. New metadata contains `interface.display_name: "Assess my Model"` and a short description such as `Assess local abilities with consent for each run`.

- [ ] **Step 1: Add failing CLI/package tests.** Assert `choices` is side-effect free; `prepare` cannot POST; consent requires both digest and owner reference; invalid combinations reject before mutation; repeated submit/resume reuses IDs; `report` is offline by default. Verify three skill paths, exact metadata/title, valid relative links, unchanged `onboardingSkill`, and pinned bundle execution of the new functions with the original Setup fixture path. Do not treat a text-match test as proof of conversational authorization behavior.
- [ ] **Step 2: Run `python3.11 -B -m unittest tests.test_cli tests.test_plugin tests.test_assessment_runs -q`.** Expect the new command and third-skill checks to fail.
- [ ] **Step 3: Extend the current CLI and write the thin skill.** The new skill reads its assessment reference for selection/consent/control/reporting, and links to named sections of Setup operations for shared inspection, state initialization, endpoint authentication, and profile preparation. Extract those headings in place if needed; do not duplicate their content into the new reference. For reassessment, the shared profile-preparation procedure constructs a separate unapproved record using only the existing connection, artifact, runtime, request-setting, candidate-capability, fallback, and stale-tolerance fields. It drops authority/evidence fields, preserves the original file, validates with the shared validator/`profile inspect`, and reuses an already matching unapproved profile when safe. Pass the owner's explicitly selected original profile as `--source-profile-id`; never infer it from a shared model name or copy its approval into the candidate. Link both skills to that one procedure.

Setup's assessment stage invokes this run-specific workflow; existing legacy commands remain documented for compatibility without being the new action's default. Keep approval/activation instructions exclusively in Setup. The new skill stops after a report, and passes only the selected run/profile references and evidence limits when the owner explicitly asks to onboard. Local Delegation must never auto-trigger it. Missing prerequisites yield one next step without running Setup implicitly. Keep exact native settings in supplied verification/fallback metadata; no substitute native model is introduced.

- [ ] **Step 4: Add and exercise bounded conversation fixtures.** Include focused/default selection, explicit all-selection, a missing group prerequisite, standing consent without run consent, consent already complete in the owner's request, declined consent, pause/restart/stop, successful report without onboarding, explanation-only follow-up, explicit onboarding, and reassessment of an approved model. Reuse the native scenario-evaluation method in `docs/onboarding-validation.md`: supplied fictional observations, no tools/inference/settings changes, same inherited native settings, one fresh read-only evaluator. Record responses and scoring privately. Any invented consent, automatic onboarding, duplicated completed trial, or modified original approval fails the scenario. Structural tests alone cannot pass this gate.
- [ ] **Step 5: Run integrated fake-runtime flows.** Exercise prepare/consent/submit/wait/existing native verification/record/report for one focused group; cover all-group selection with deterministic responses; then test restart/revocation and report-only behavior. Keep runtime quality claims synthetic. Run the full offline suite: `python3.11 -B -m unittest discover -s tests -t . -q`, then `git diff --check`. Run the installed skill validator for all three skills and check local links/metadata. Read platform requirements before isolation canaries. Expect all checks passing; record exact results, not invented new test counts.
- [ ] **Step 6: Independently review the final diff.** Require explicit review of consent enforcement at every submission/verification caller, dispatch/revocation locking, legacy behavior, update handling, read-only reporting, profile preservation, and absence of duplicated Setup logic. Resolve findings and rerun only affected checks plus the final required gate after code changes.
- [ ] **Step 7: Commit** with `feat: expose Assess my Model as a dedicated action`. Record source validation separately from installation and actual desktop discovery. Do not publish, install, approve a model, or run live inference merely to close this task.

## Checkpoints, self-review, and stop condition

The dependencies are sequential: Task 1 preparation, Task 2 authorization, Task 3 execution controls, Task 4 reporting, Task 5 integration. If publication is authorized, use at most four checkpoints: preparation/authorization together, execution controls, reporting, and final integration. Local task commits are finer-grained than publication checkpoints. Preserve the task worktree and private evidence outside tracked product files.

Plan self-review coverage: design entry/selection/preparation maps to Tasks 1 and 5; consent and identity to Task 2; lifecycle/race/maintenance to Task 3; reports/evidence limits to Task 4; explicit onboarding and package discovery to Task 5. All five Review Focus items have named tests. Existing Setup functions remain the owners; only one fixture builder, one job store, one submission path, and the existing verification engines remain.

Stop implementation when the source action, run-specific backend contracts, compatibility tests, scenario evaluation, and independent review pass. Report any desktop-discovery qualification as pending unless separately authorized and observed. Full source completion does not claim installation, model reliability, approval, activation, or savings.

The owner approved this implementation plan and inline execution with an independent final review on 2026-10-23. Implementation progress and exact checks are recorded in the task's private execution ledger. Publication, installation, model approval and live inference remain outside this task.
