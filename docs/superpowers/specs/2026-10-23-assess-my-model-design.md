# Assess my Model

Date: 2026-10-23. Status: approved by the owner on 2026-10-23; not implemented.

## Purpose and agreed decisions

Add a third plugin action, **Assess my Model**, for evaluating a local model without onboarding it for project delegation. The action saves an unapproved profile and private assessment evidence, then stops after explaining the results. Onboarding starts only when the owner explicitly requests it.

The owner selected:

- A dedicated assessment flow using consent for each run, rather than standing assessment permission.
- Permission to save an unapproved model profile and assessment report.
- A focused ability selection by default, with an explicit **All supported abilities** option.
- The user-facing action name **Assess my Model**.
- An explicit handoff to Setup for onboarding; a passing assessment never triggers that handoff automatically.

The remaining details below are proposed design defaults, not authorization to run assessments, approve models, install software, change settings, or implement this design. Approval of the design is separate from any future model-use consent.

## Approaches considered

| Approach | Tradeoff | Decision |
| --- | --- | --- |
| Expose the existing assessment commands through a thin skill | Smallest change, but retains standing consent and setup-oriented reporting | Not selected |
| Add a dedicated flow with run-specific consent, focused selection, and a standalone report | Reuses the existing execution and verification machinery while making the authorization boundary explicit | Selected by the owner |
| Build a separate benchmark service or assessment engine | Duplicates identity, queue, verification, and recovery responsibilities | Outside scope |

The implementation should extend the existing Python core. It needs no new service, dependency, provider, dashboard, or model runner.

## Current behavior and reuse

Inspected on 2026-10-23 at source revision `520ee1b243ff6f79ba4afaafe80b88d26912dc4f`:

- [Setup](../../../skills/setup/SKILL.md) currently includes assessment in its trigger and workflow. [Local Delegation](../../../skills/local-delegation/SKILL.md) handles ordinary authorized work. The [manifest](../../../plugin.json) identifies Setup as the onboarding skill.
- [Assessment operations](../../../local_model_delegation/onboarding.py) already create private synthetic trials bound to exact artifacts, runtime identity, request settings, fixture content, and brief hashes. They currently require a matching enabled standing assessment policy.
- [The queue](../../../local_model_delegation/store.py) and [scheduler](../../../local_model_delegation/scheduler.py) permit assessment jobs while ordinary routing is disabled. Assessment jobs use the shared queue and reject native fallback claims. Assessment scheduling does not automatically load an unapproved model.
- [The fixture pack](../../../skills/setup/fixtures/assessment-cases.json) contains 18 cases in six groups. Each group has three distinct cases, repeated twice, giving six trials per group and 36 trials for the full current pack.
- [Practical qualification](../../qualification.md) uses real project work under provisional model approval. It remains a different workflow; this action must not silently use real project tasks to avoid the synthetic-assessment consent boundary.
- The existing report exposes completed counts and provisionally tested scopes, but does not provide the complete per-trial failure, incomplete-work, and freshness breakdown required here.

These observations are invalidated by changes to the referenced entry points, consent enforcement, fixture generation, scheduler, or verification contracts. Reinspect them before implementation and before claiming compatibility with a different package version.

## User experience

### Entry points

Use a new skill directory, proposed as `skills/assess-my-model/`, with **Assess my Model** as its title and intended displayed action name. Use the client's supported skill metadata for the exact display label and verify discovery separately from package validation.

Its trigger should cover requests to assess, evaluate, or reassess a local model, and to inspect or resume a saved assessment. An ordinary delegation request does not trigger assessment. Selecting the action opens the assessment conversation; it does not grant permission for an unspecified suite of inference calls.

Setup retains installation, connection setup, approval, activation, updates, and removal. During an owner-requested onboarding conversation, Setup may hand the assessment stage to this flow. Assessment requests themselves must not launch the full Setup workflow. Local Delegation remains an ordinary-work entry point and does not launch assessments to qualify an otherwise ineligible task.

### 1. Select and inspect a candidate

Reuse the selected private state directory and configured loopback connection. Run the existing read-only inspection procedures. If several models are available, ask which one to assess; do not infer competence from its name or size.

The first version targets downloaded text models already loaded in the supported LM Studio runtime. Missing runtime, identity, model loading, toolchains, or isolation produces a specific prerequisite message and a pending assessment. It does not install, download, load, unload, reset, or change settings automatically. Read-only inspection of a supplied endpoint is permitted; port scanning is not.

Create or reuse an unapproved assessment profile for the exact candidate binding. Reuse the canonical private state and shared queue, including any explicitly selected custom location. If private state is absent, assessment-authorized minimal initialization may create it with ordinary routing disabled. This preparation is not project-use onboarding.

When reassessing an approved model, preserve its approved profile, approval, scope, benefit evidence, suspension state, loading permissions, and routing preference. Use a distinct unapproved assessment profile, reusing an existing matching assessment profile when safe. Record provenance to the existing profile without granting authority through that link. Changing assessment settings must not rewrite an approved profile or an active run's binding.

### 2. Choose an ability

Start by asking which ability the owner wants to assess. Offer three understandable categories: **Summarizing files**, **Making code changes**, and **Writing tests**, plus **All supported abilities**. For a focused category, resolve the language and applicable verification path before previewing the run. Reuse choices already explicit in the request.

Current coverage maps as follows:

| Choice | Language and verification path | Trials |
| --- | --- | --- |
| Summarizing files | Text, native semantic and citation verification | 6 |
| Making code changes | Python, native semantic review and declared isolated checks | 6 |
| Making code changes | Python, restrictive protected Python verification | 6 |
| Making code changes | JavaScript, native semantic review and declared isolated checks | 6 |
| Writing tests | Python, native semantic review and declared isolated checks | 6 |
| Writing tests | JavaScript, native semantic review and declared isolated checks | 6 |
| All supported abilities | All six groups above | 36 |

All current cases are simple and use small contexts. The two Python code-change groups exercise different verification paths; do not present them as two independent areas of general competence. Recommend the existing protected path for a focused Python change assessment when its restrictions fit the intended work; explain the scope rather than exposing a capability identifier as an ability name.

Derive the offered groups and counts from the installed fixture manifest. Do not hard-code these counts into consent logic. Show missing prerequisites before consent. If any selected group cannot run, name it and let the owner resolve the prerequisite or explicitly select a smaller scope; never label a reduced run as the full pack.

### 3. Preview and authorize one run

Before inference, show a compact preview with:

- The exact model, artifact identity, runtime, and relevant request settings, including thinking and loaded context.
- Selected abilities, languages, verification paths, distinct case count, repetitions, and maximum number of generation submissions.
- Input/context bounds and per-trial output allowances, preserving explicit settings and the existing context-fit checks.
- One-slot execution, native verification, and the private evidence that will be saved.
- The fact that approval and routing preferences will remain unchanged.

Ask for consent only when it is missing. An explicit request that already specifies the complete bounded run can supply consent; do not ask for the same authorization twice. A generic “assess this model” request does not authorize an undisclosed all-abilities run.

Example after scope selection:

> Assess this model's Python test writing using three synthetic cases, each run twice: six local generations, one at a time, with native verification. Save the results without approving the model or changing delegation. Run this assessment?

Include the actual model and generation budgets in the accompanying preview. This example is conversation copy, not a substitute for the stored authorization binding.

### 4. Execute and verify

Submit only the frozen selected trials, sequentially, through the existing queue. Use native verification and the existing isolation, pressure, context, progress, and recovery rules. Other clients' healthy jobs remain untouched; one assessment slot does not create a second queue or imply endpoint exclusivity.

Every local answer is a candidate until verification completes. Native review can judge and explain a candidate but cannot repair it into a passing assessment result. Native fallback cannot solve a failed trial. Preserve the existing backend rejection of assessment fallback claims.

Do not apply candidate files to the user's project. All executable examples stay in the assessment's private synthetic workspace, with protected checks and receipts outside candidate control. Keep credentials and unnecessary project context out of model inputs.

### 5. Report and stop

Save a private machine-readable report and provide a concise human summary. The action finishes after reporting; it may state that onboarding is available on explicit request, but must not start an approval or activation questionnaire automatically.

An example conclusion is: “Python test writing: six of six planned trials passed across three small synthetic cases. Larger contexts and project reliability remain untested. This assessment profile is unapproved; delegation settings are unchanged.” Use actual results and actual existing routing state.

## Run authorization and lifecycle

Introduce an explicitly versioned run-specific authorization record. Reuse existing assessment IDs, permits, brief hashes, receipts, and job identity rather than building a second job registry. The record binds:

- The run ID, candidate profile, exact artifact/runtime/settings identity, and loaded-context/verification conditions relevant to the run.
- The package/fixture version or digest, selected trial IDs, frozen briefs, acceptance checks, and their hashes.
- The per-trial generation allowances, maximum submissions, one-slot limit, owner authorization reference, and authorization timestamp.
- Durable run status and each trial's submission identity, so resuming never creates duplicate generations.

Never toggle `assessment_policy.enabled` temporarily to implement per-run consent. The new action always uses its run record, even when standing permission exists elsewhere. Existing legacy runs retain their original standing-policy checks and historical meaning; missing or unknown authorization versions must never fall back to a broader permission path.

Separate authorization for **new generation submissions** from authority to **reconcile and verify already-submitted work**. Revoking consent stops new submissions, but must not make existing requests untrackable or discard their eventual receipts.

| Situation | Required behavior |
| --- | --- |
| Preview only or consent declined | No inference; retain a draft only if useful for the requested continuation |
| Authorized run | Execute only its frozen trials, at most one generation submission per trial |
| Conversation interruption or application restart | Reconcile saved jobs first; continue only the same authorized unfinished run under unchanged bindings |
| Explicit owner pause | Admit no new trials; require an explicit resume request before continuing remaining authorized trials |
| Explicit owner stop/revocation | Permanently prevent new submissions for that run; preserve submitted work and evidence |
| Generation already in progress at pause/stop | Report its state; stopping orchestration or closing a socket does not prove model cancellation |
| Completed or failed trial | Never rerun it automatically; a retry needs a new bounded run and consent |
| Ambiguous submission or runtime response | Keep uncertainty and occupied-slot protections; reconcile rather than resubmit |
| Changed model, settings, suite, briefs, or verification conditions | Block new submissions; preserve old evidence and create a new authorized run if requested |
| Report-only request | Read saved evidence without inference or consent renewal |

An authorized unsubmitted trial can wait for safe capacity without consuming an attempt. The durable boundary between “not submitted” and “possibly submitted” must follow existing attempt/POST bookkeeping. A crash cannot reset the submission budget.

Bounds are call count, supplied context, output allowance, and existing progress checks. Do not introduce a total inference deadline or claim a reliable elapsed-time estimate. A model/content failure is recorded and the run may continue to its remaining authorized trials; an identity, authorization, safety, or uncertain-runtime blocker pauses further submissions.

A run can have all generations finished while verification is pending. Mark it complete only when every planned trial has a final disposition. A stopped or invalidated run retains a partial report and never becomes “passed” by excluding unfinished trials.

## Report contract and evidence limits

Report from durable attempt records and native verification receipts, never model self-evaluation. Include:

| Field | Meaning |
| --- | --- |
| Identity and provenance | Run/profile IDs, exact model binding, suite/package/checker identity, timestamps, and evidence paths |
| Coverage | Selected abilities, languages, verification paths, complexity, context sizes, distinct cases, and repetitions |
| Outcomes | Planned, submitted, passed, failed, awaiting verification, unresolved, and not-run counts, with reasons |
| Failure detail | Separate semantic failure, invalid output, budget exhaustion, missing prerequisite, admission deferral, transport uncertainty, and owner stop |
| Timing and usage | Observed queue, inference, and verification timing when available; runtime-reported token counts only; missing values remain unknown |
| Freshness | Evidence bound to its original model/settings/suite; show current, stale, or unverified matching status separately from historical results |
| Interpretation | A narrow description of what was demonstrated, what needs attention, and what remains untested |
| Operating state | Assessment profile approval, any separately linked approved profile, and actual routing status, each stated independently |

Show `passed / evaluated` alongside the planned denominator and unfinished counts. Separate failed model outputs from checks that could not run. A complete six-of-six group provides provisional synthetic evidence, not general reliability. Do not invent a weighted score, maximum model capability, specialist role certification, project acceptance rate, or subscription saving.

Viewing old evidence must still work if the runtime is offline, model files are unavailable, or the original profile has changed or disappeared. Retain enough immutable run metadata to render the historical report; current identity verification is an optional read-only check. An unavailable current check means “current match unverified,” not a rewritten historical failure.

Keep run-specific interpretation distinct from legacy `assessment_report` approval recommendations. Preserve old report fields and approval semantics where callers rely on them; the new human-facing flow does not translate “passed” into “approved.” Assessment completion must not call legacy `record_outcome`, create real-project delivery measurements, set model-global benefit evidence, qualify higher concurrency, or clear suspensions. Evidence stays private and separate from normal project measurements.

## Explicit onboarding handoff

“Onboard this model” or an equivalent direct request starts Setup using the selected candidate and assessment ID. A request for further explanation, report export, or another assessment does not.

The handoff carries the candidate identity, assessment reference, tested scope, generation settings, freshness information, and known limitations. Setup reads current state, revalidates the binding, and reuses valid evidence. It does not repeat completed trials merely because the entry point changed.

The handoff authorizes the requested onboarding process; it does not itself grant a particular project-use scope or routing activation unless the owner has also explicitly authorized those decisions. Setup obtains only missing decisions, keeps approval and activation distinct, and preserves existing preferences. Missing or stale evidence is explained before proposing any additional assessment.

## Implementation boundaries

The following are affected surfaces, not an implementation task list:

- **Skill and documentation:** add `skills/assess-my-model/SKILL.md` and its focused operation reference; narrow Setup's direct assessment behavior into a handoff; update README and relevant operation/qualification pointers. Keep Setup as the manifest's onboarding skill. Verify the exact displayed name using supported metadata.
- **Assessment core and CLI:** add preview/frozen selection, run-specific authorization, pause/stop/resume semantics, and standalone reporting. Keep the existing `assessment` command family; choose exact subcommand names during implementation planning.
- **Execution integration:** audit every assessment authorization caller, including queue admission and pre-POST checks, and split new-submission checks from historical receipt verification. Preserve shared slots, durable identity, existing fallback rejection, and unrelated task behavior.
- **Evidence and compatibility:** version the new authorization/report records. Preserve old assessments without converting their permission or widening approval. Do not mutate existing model profiles during a read-only report.
- **Packaging and tests:** include the third skill in package/relocation checks. Reuse the existing fixture pack and pinned runtime bundle; moving fixtures is unnecessary for this change. Update caller and documentation tests only where contracts change.

Storage details, helper extraction, exact CLI spelling, and the minimal display metadata are left to the builder. Behavioral boundaries, identity checks, consent limits, and evidence separation are requirements. The builder must not silently weaken a requirement to avoid touching an existing caller.

## Acceptance and validation

Use disposable state, fictional identities/consent, fake loopback runtimes, and bound native verification fixtures to prove:

1. The package exposes three skills and keeps Setup as onboarding. The assessment description and exact intended display label are covered by structural checks; actual desktop discovery remains a separate qualification.
2. Focused selection produces only the selected group. All supported abilities produces the current full pack, with accurate counts and explicit unavailable groups. Empty or unknown selection is rejected.
3. Preview, selection, and reporting make no generation POST. No run starts without its explicit authorization, even if a standing policy exists.
4. Consent is restricted to the exact run, identity, settings, fixture/brief/check hashes, and budgets. Forged permits, scope substitution, unknown versions, and changed bindings are rejected.
5. Restart and repeated resume cannot duplicate submitted, completed, failed, or uncertain trials. Concurrent submission/revocation is serialized at the dispatch boundary; a committed submission remains tracked, and revocation prevents later ones.
6. Pause/stop blocks new submissions without releasing uncertain slots or preventing reconciliation and verification of work already submitted. Terminal stop cannot be resumed as fresh permission.
7. Native verification remains required, generated code remains isolated, and assessment jobs cannot claim native fallback or apply files to the project.
8. New and reassessed profiles remain unapproved. Existing approval, routing, standing policy, loading permission, benefit, capacity, and suspension records remain unchanged.
9. Partial, failed, stale, offline, and orphaned-profile reports preserve historical evidence and show missing information explicitly. Synthetic outcomes do not enter real-project delivery or savings calculations.
10. Only an explicit onboarding request transfers control to Setup. Successful results, report viewing, and action selection cannot approve a model or enable routing. Test this conversation boundary with bounded workflow scenarios as well as backend invariants.
11. Existing legacy standing-consent assessment behavior remains intact; new run consent cannot authorize legacy jobs or arbitrary project briefs.

For implementation, run the existing offline suite, `python3.11 -B -m unittest discover -s tests -t . -q`, and `git diff --check`, plus relevant skill validation. Read platform requirements before isolation canaries. Independently review consent enforcement, resume/revocation races, compatibility, and profile side effects. Unit tests do not prove actual model quality or fresh desktop skill discovery.

This design-writing task performs no model inference, installation, approval, activation, or live desktop qualification. Implementation and any later live assessment require their applicable authorization.
