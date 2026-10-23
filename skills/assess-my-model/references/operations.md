# Assessment operations

Use the packaged `delegate.py` and the owner's selected state directory throughout. Paths below are relative to `skills/assess-my-model/SKILL.md`. Keep selection, receipts, profiles and reports in private state, never in the plugin or a project.

## Shared prerequisites and profile

Read Setup's [inspection and state](../../setup/references/operations.md#inspection-and-state), [connection](../../setup/references/operations.md#connection), and [unapproved profile preparation](../../setup/references/operations.md#unapproved-profile-preparation). These are the canonical procedures for both actions. An assessment request permits the minimal private assessment state and unapproved record; it does not authorize installing prerequisites or changing model lifecycle/approvals. If the model is not already loaded, report that blocker and one next step.

For reassessment, preserve the owner's exact selected original profile ID as `--source-profile-id`. Use a separate unapproved candidate. Several profiles can share a model binding; do not guess the source ID. Its saved approval is provenance only and never supplies run permission.

## Choose and preview

`assessment choices` reads only the packaged fixture manifest. The current six groups are file summary/text, code change/Python, protected Python code change/Python, code change/JavaScript, test writing/Python and test writing/JavaScript. All currently cover simple work and small context. The two Python change paths overlap; do not sell them as independent abilities. Each group has three cases repeated twice: six trials; all groups total 36. Use command output as authority if the pack changes.

Focused selection is the default. Translate the owner's ability into one exact returned group. Store either `{"groups":[{"capability":"test_writing","language":"python","complexity":"simple","context_bucket":"small"}]}` or the explicit full selection `{"all":true}` in a private JSON file. Empty, duplicate, unknown and mixed selections are rejected.

Run `assessment prepare --profile-id ID --selection FILE`, adding `--source-profile-id SOURCE` only for explicit reassessment. Preparation performs identity/prerequisite checks and freezes a draft; it does not generate. It fails instead of silently skipping an unavailable checker or group. Preserve the returned run ID and preview digest. The record lives at `STATE/assessments/ID/assessment.json`; no public permit needs to be copied.

Present the preview's exact model/settings, groups, distinct cases, maximum submissions, per-trial output allowances, one-slot limit and required native verification. Describe the synthetic package-only inputs, private evidence, absence of approval/routing changes and unknown elapsed time. If every dimension was already explicitly authorized, reuse that authorization. Otherwise ask for the missing run consent once. Record it with `assessment consent --assessment-id ID --preview-digest HASH --owner-reference REF`, using a real conversation reference rather than an invented approval. Never modify `assessment_policy` to authorize this run. Consent does not authorize another run or expanded scope.

## Submit, verify and record

Read the [existing checking contract](../../local-delegation/references/contracts.md) and [bounded execution procedure](../../local-delegation/SKILL.md) for check command/receipt formats. Keep the current native model, reasoning, provider and authentication. The assessment permit cannot dispatch native fallback or apply changes to the owner's project.

1. Submit the selected run's next trial with `assessment submit --assessment-id ID --trial-id TRIAL`. Repeated submissions return the same job.
2. Observe that job with existing `wait --job JOB --seconds N` (at most 60 seconds). Waiting does not impose a total inference deadline. For `route_decision_required`, obtain the owner's wait decision and use existing `route decide` to extend the same queued job; do not create a replacement trial.
3. For a candidate, use existing protected Python verification or native verification preparation, predeclared isolated checks, semantic/citation review and the bound receipt. Syntax alone never proves correctness. A completed exhausted-output request is a failed trial; unavailable checks or uncertain transport remain blockers, not model-quality failures.
4. Record final verified results with `assessment trial --assessment-id ID --receipt FILE`, where FILE contains `{"trial_id":"TRIAL","job_id":"JOB"}`. Continue only after that disposition. Verification cannot be replaced by model self-assessment or a native solution.

## Pause, stop and restart

Use `assessment pause --assessment-id ID` for an explicit pause and `assessment stop --assessment-id ID` for revocation. Neither claims cancellation of an already committed request. A stopped run cannot resume or receive new consent; a requested retry needs a new preview and consent.

After interruption, read the saved run and `assessment report` first. An unchanged authorized unfinished run may use `assessment resume --assessment-id ID` to reconcile its jobs and return `pending_jobs`, `blockers` and `next_trial_id`. A paused run requires the owner's explicit resume request. Never call resume merely to read a report. Completed or stopped runs retain their status. Reconcile submitted/checking work; do not replay failed, finished or uncertain generations. Changed identity, settings, helper/fixtures or checkers invalidates remaining permission. Explain the mismatch before proposing a new run.

## Read results and explicit handoff

`assessment report --assessment-id ID` is offline and leaves state unchanged. Optional `--check-current` checks current matching read-only; unavailable current evidence remains unverified. Reports retain original model/setting/source-profile snapshots even if profiles or artifacts disappear. Evidence writers refresh private `report.json`; report-only reads do not.

Show selected coverage, passed/evaluated/planned, not-run/pending/unresolved counts, reasons and actual timing/tokens where observed. Keep missing data unknown. Six passing cases provide provisional synthetic evidence only; no specialist certification, project reliability, larger capacity, or subscription savings follow. State current recorded approval and routing separately. Do not record model-global outcomes or project delivery measurements for these trials.

Stop after the report. Only an explicit onboarding request hands the selected run/profile, original source profile if any, settings, tested scope, freshness and limitations to **local-model-delegation:setup**. Read the [Setup skill](../../setup/SKILL.md) before continuing; preserve its one-decision-at-a-time conversation. Setup owns approval and activation; its [approval procedure](../../setup/references/operations.md#approval-and-activation) revalidates current bindings and reuses evidence. Ask for missing operating scope before asking about routing; do not bundle them into the handoff reply. Explanation, export and another-assessment requests do not trigger onboarding.

Legacy unversioned runs remain governed by Setup's [legacy standing-consent procedure](../../setup/references/operations.md#legacy-standing-consent-assessments). Do not relabel or upgrade them into per-run consent. New runs reject legacy `assessment approve` and `assessment capacity` commands.
