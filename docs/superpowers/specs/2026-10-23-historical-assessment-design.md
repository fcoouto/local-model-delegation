# Project-specific local model assessment

Date: 2026-10-23. Status: independently reviewed design, awaiting owner approval.

## Purpose

Answer three practical questions for a selected project:

1. Which usual tasks can this local model handle, and at what difficulty and context size?
2. What portion of the project's usual workload might those tasks represent?
3. How much slower or faster is the local workflow, and how much native effort does it actually avoid?

A model need not handle everything to be useful. Evidence of a useful subset is a successful assessment outcome. Speed does not determine capability: a slow correct result passes, and time-limited unfinished work remains inconclusive.

The owner replaced the generic specialty benchmark with project-specific qualification. Every assignment must originate in actual project work or be generated directly from that project's concrete code, requirements and maintenance patterns. A synthetic assignment means a constructed scenario grounded in the selected project, never an unrelated generic exercise. Results apply to the tested project and conditions, not to all projects or the model in general.

This is a design, not authorization to execute a campaign. Existing approvals, routing, saved results and native settings remain intact. No product code or local model assessment generation is part of this document change.

## Approach and user experience

The selected approach replaces both historical-only coverage and fixed synthetic/historical quotas with a project-derived task portfolio. Reuse the current assessment and verification machinery. Do not add an unrestricted repository agent or a second scheduler.

Setup and Assess My Model use the same project-selection and assessment flow:

1. **Select the project and model.** Require an explicit project folder or an already selected project that the owner has authorized for this assessment. Ask only for missing scope or permission; reuse clear authorization. A folder without Git history remains eligible. Assess My Model requires the model to be loaded; Setup retains its existing prerequisite stages.
2. **Inspect with permission.** Read the selected project's instructions, code, tests, documentation and available local history. Connected PRs can supplement that evidence when access is authorized. Do not scan sibling projects or private unrelated directories. Keep source and task artifacts private under current native provider/authentication settings.
3. **Describe the usual work.** Propose a short project-specific list of recurring task families, including difficulty and context demands. Distinguish observed history from inferred needs. Let the owner correct the workload description before treating it as representative.
4. **Prepare a concrete portfolio.** Use historical replay where suitable; otherwise construct scenarios from the project's actual patterns. Explain what each assignment represents and what remains untested. Preview the exact task count, references, checks, model settings, cycle limits and resource bounds before inference consent.
5. **Run and verify.** Work only in isolated disposable snapshots, using the existing queue and independent native verification. Do not apply assessment proposals to the live project.
6. **Report project fit.** Show suitable task families, demonstrated levels, failures, unknowns, provisional workload coverage, timing and measured native effort. Setup can then obtain explicit project-bound approval; Assess My Model stops after the report unless the owner requests onboarding.

Installation and connection checks need not wait for project selection. Assessment and evidence-backed project qualification do. Setup may reuse matching project assessment evidence without repeating generations. Declining assessment does not create a qualification claim or silently enable routing. Existing explicitly approved provisional use retains its current meaning.

Coordinator proposal: remove fixed per-specialty counts and the 4+4 split. Select the smallest portfolio that represents the owner's important recurring task families and includes distinct examples at the claimed difficulty boundaries. Freeze the count and coverage in the preview. When evidence is too sparse, narrow the conclusion rather than manufacture a percentage. The exact initial count is a preparation decision, visible to the owner before execution.

## Turning project work into assignments

Each assignment needs a traceable reason to exist: source paths and hashes, relevant requirements, a historical change, or a recurring pattern supported by project evidence. The manifest records whether it is historical replay or a constructed project scenario. “This language appears in the repository” alone is insufficient evidence that a task is usual work.

For historical cases, freeze the pre-change base and the reviewed solution. Split bundled releases into coherent tasks. Record review provenance only when known. Withhold patches, later commits, Git metadata and solution-revealing discussions from contestants. Independently validate the reference: the targeted behavior must fail on the original and pass on the solution. Merged code is a reference, not an infallible oracle.

For constructed cases, use the project's actual interfaces, conventions, dependencies and constraints. A native author prepares a standalone requirement, isolated starting snapshot, reference solution and public checks. An independent reviewer validates the reference and hidden checks. The assessed model must not author its own evaluation. Preserve realistic cross-file requirements, compatibility obligations and edge cases; do not add irrelevant complexity or context padding. Missing history permits this approach without requiring another project.

Test-writing assignments must execute the genuine framework, discover the expected tests, pass correct behavior and reject realistic defects through assertions. Missing imports, syntax errors, skipped tests and fake framework APIs do not count as defect detection. Summaries must support their claims with source citations. Accept alternative correct implementations without comparing patch similarity.

Freeze task requirements, references, hidden checks, environments and comparison selection before candidate execution. Reject ambiguous or unverifiable cases. Known reference defects invalidate that case and require a new pack version; never alter the scoring rules after seeing a model's answer. Keep original evidence readable.

The portfolio is reusable across models for this project, enabling direct comparison. Reusing it on another project does not establish that project's suitability. Record exposure to published solutions and previous runs as a limitation; do not claim tasks are unseen without evidence.

## Capability levels and workload coverage

Report concrete project task families, such as regression tests for this project's API, compatibility fixes in its adapters, or documentation grounded in its modules. For each family show tested difficulty, context range, distinct assignments, first-cycle success, success after allowed cycles, completed failures and unfinished/unsupported cases. Levels must describe demonstrated constraints, not an invented global intelligence score.

Use three principal conclusions per family: **suitable within the tested scope, mixed results requiring narrower scope, or not established**. Completed failed work remains explicit. Untested harder tasks are unknown, not incapable. A native rewrite is assisted delivery and never an unassisted local success. A family needs multiple distinct successful examples and no unresolved failures inside the proposed scope before recommending that scope; smaller samples remain case-level evidence. This is provisional qualification, not statistical reliability certification.

To estimate a portion of usual work, define the denominator first. Default to **share of recurring task count**, not lines changed, commits, developer hours or token savings. Build a mutually exclusive task-family inventory, including untested and unsupported work. Historical PRs may inform it, but commit counts are not task frequencies. Record the observation period, grouping rules and missing work such as planning, reviews or operations. Have the owner confirm or supply the approximate workload mix. Unknown frequencies mean no numerical project-coverage claim.

For the assessed family i, let w_i be its confirmed fraction of usual task count. Let p_i be the observed fraction of all its frozen representative assignments that completed successfully within the declared scope and assistance rules. A transparent provisional coverage estimate is sum(w_i * p_i). Include unfinished and unresolved assignments in the displayed planned denominator; giving them no demonstrated contribution is not a capability-failure verdict. Untested families contribute no demonstrated coverage and retain their own unknown share. Do not extrapolate success at one difficulty to the whole family; split or restrict weights to the tested difficulty/context band.

Example, illustrative only: if adapter test-writing represents 20% of usual task count and all representative tested cases succeed, the provisional suitable share is about 20%. That is not evidence that the model is 100% reliable, can handle 20% of development hours, or saves 20% of native usage. Show case counts and workload assumptions beside the estimate. If workloads are only bounded estimates, report a transparent scenario range under those bounds rather than a fabricated statistical confidence interval. Do not infer sampling probabilities from a hand-curated portfolio.

The initial report should say “potentially suitable for approximately X% of recurring tasks, subject to native verification.” Reserve stronger reliability claims for accumulated representative outcomes from ordinary approved project work, with failures and assistance recorded. No automatic promotion follows. If representativeness is doubtful, provide the task-family map without a percentage. Project usefulness may still be evident.

## Work cycles, budgets and independent verification

Retain the proposed maximum of three proposal cycles per assignment, including the initial attempt. Record cycle lineage and distinguish first-cycle from final success. The coordinator supplies current allowed files and deterministic public-check feedback, never suggested fixes or hidden-test results. Invalid output consumes a cycle and leaves the previous valid snapshot intact. Hidden checks and semantic review occur only on final submission or after the final permitted cycle; do not coach a subsequent repair with them.

For the first version, preserve current limits: eight supplied/working files in total per assignment, 100,000 UTF-8 bytes per file, allowed replacement paths, strict JSON, source hashes and qualified isolation. Do not trim essential context to make a task fit. Unsupported tasks remain visible in the workload denominator. Larger-file or repository-navigation support requires an explicit later extension.

Use a separate unapproved assessment profile and generous finite generation allowances supported by the exact runtime and loaded context. Do not silently raise production approval ceilings. Reserve the largest permitted cycle input and feedback plus template headroom. Retain conservative UTF-8-byte input screening unless qualified tokenization exists. A large context window alone does not prove a supported output maximum.

Derive generous model-specific deadlines from comparable prefill latency, decode throughput, generation allowances and public-check timeouts. Proposed initial margin: twice the measured upper prefill time plus decode allowance divided by conservative throughput plus check timeout totals, with the factor applied to the whole sum. Record the exact formula and values in the preview. Missing calibration requires a separately authorized bounded qualification, excluded from scored tasks. Do not promise duration from unmatched telemetry.

Persist active elapsed accounting across restarts. Separate queue time, owner pauses, suspension and final independent verification from generation/public-check execution time, and report total elapsed separately. Stop admitting further cycles at the deadline. Request cancellation only through a qualified operation; a socket close or observer exit does not prove generation stopped. Retain uncertain slots and block conflicting work until terminal evidence is reconciled. No automatic unload/reset is authorized.

Timeouts, exhausted allowances and incomplete outputs are unfinished/inconclusive, not proof of inability. Verify any candidate demonstrably completed before the deadline even if verification occurs later. A completed final answer violating requirements fails. More time or cycles requires a separately authorized follow-up linked to the original record; never silently rerun completed or ambiguous generations.

## Native comparisons, speed and practical benefit

Retain fresh native comparisons on a small subset selected before results. Coordinator proposal: two representative assignments when at least two exist, spanning important task families or difficulty levels. Use identical briefs, permitted files, public feedback, cycle opportunities and hidden final criteria. Fresh contestants must not inherit reference/author/reviewer context. Preserve native model, reasoning, provider and authentication.

Use model-specific measured time allowances so slower local hardware does not lose reasoning opportunity. Record generation allowances and tokenizer/accounting differences. If native token enforcement or usage is unavailable, disclose the mismatch and do not call the comparison token-matched. Broader native tool access is a separate workflow comparison, not controlled evidence.

For paired completed tasks, report actual local and native seconds and the per-task ratio local/native. Show median paired ratios with sample count, and separate generation, checks, waiting and verification. An unsuccessful fast attempt is not an efficiency win. Missing measurements remain unknown. Timing never changes the capability verdict.

Task coverage and native-effort savings are different. Estimate native effort avoided only from comparable measured baselines, including local coordination, native verification, corrections and fallback overhead. Preserve negative results. Unknown telemetry means savings unknown; task coverage must not be relabeled as time, money, token or subscription savings. Report useful scope even when no savings estimate is available.

## Project binding, compatibility and implementation scope

Bind evidence to existing project identity, snapshot/task hashes, model artifact and runtime, effective settings, toolchains, assignment version, allowed assistance and verification version. Reuse `projects.py::resolve_project_identity` and existing private measurement records where suitable; do not create a parallel project registry. Sibling projects do not share approval through similar names, languages or a shared model.

New recommendations and resulting approvals must carry the selected project and tested scope through eligibility checks. Ordinary routing must verify those bindings plus existing approval, capacity and native verification requirements. Do not silently convert existing model-global approvals into project qualification, revoke them, or expand them. Preserve their legacy provenance explicitly. Historical reports and replayed responses remain immutable and readable; they do not acquire project evidence retroactively.

A project revision change alone need not invalidate all evidence. Reuse requires matching relevant task contracts, dependencies, checker environment and context assumptions. A changed artifact/runtime or material project assumptions requires review before evidence can justify new scope. If current compatibility cannot be established, mark the recommendation stale; do not silently reuse it. Exact invalidation checks belong in the implementation plan.

Source facts inspected on 2026-10-23 at `f065e8c771732e7ca83b4b069398854298acfeea`: current onboarding uses packaged cases repeated twice; briefs have no model tools; deadlines and multi-cycle campaigns are absent; project identity and comparison recording exist separately; the scheduler's benefit policy is model-global. Reinspect these facts when their source changes.

Extend both skill entry points and their operations, current assessment preparation/selection/reporting, project-bound approval and eligibility, versioned manifests/receipts and worker lifecycle. Reuse queue ownership, native verification and comparison helpers. Keep production delivery measurements separate from replay or constructed scenarios. No second runner service, unrestricted shell, new provider or automatic cross-project routing is part of this design.

Required implementation proof covers permission/project selection in both entry points; source-grounded task provenance; reference and real-framework validation; representative weights and honest coverage denominators; cross-project eligibility rejection for new scoped approvals with unchanged legacy state; frozen consent; cycle lineage; hidden-check isolation; timeout and ambiguous cancellation recovery; capability independent of speed; comparison asymmetry; and unchanged historical reports. Run focused tests, the repository's offline suite and `git diff --check`. Offline tests do not establish real runtime termination, large-output support or model reliability.

## Delivery and remaining decisions

This document supersedes fixed specialty quotas and generic synthetic assignment generation. It retains native verification, bounded multi-cycle execution, fair selected comparisons and separate speed reporting. Campaign preparation must identify the actual project, confirm usual work and its frequency basis, validate tasks and present exact resource bounds. No such campaign is started by approving this design.

After independent design review and owner approval, write the implementation plan. No product implementation, installation, changed approvals or local assessment execution has occurred in this design phase.

Independent builder review on 2026-10-23 found no consequential planning gaps. It checked project identity, existing approval/scheduler contracts, source-grounded task selection, coverage denominators, sparse-evidence limits and capability/speed separation. This was a design review, not runtime qualification.
