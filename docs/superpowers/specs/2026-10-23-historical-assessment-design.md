# Historical project assessments

Date: 2026-10-23. Status: independently reviewed design, awaiting owner approval.

## Intent and agreed decisions

Assess whether a local model can complete useful moderate and complex work, and separately measure how much slower or faster it is than a native model. Passing the existing small synthetic cases does not establish this broader scope.

The owner selected 6–10 distinct real assignments per specialty, sourced from merged PRs and commits. Reviewed historical solutions provide references; fresh native attempts cover a subset. Use generous runtime-supported generation allowances, measured execution deadlines and multiple work cycles where needed. Speed never determines capability. A slow correct solution passes. An unfinished time-limited attempt is inconclusive, not evidence of inability.

This document designs the assessment upgrade only. It does not authorize inference, installation, loading, production approval, routing changes, publication of private project material or integration of candidate changes. Existing Qwen approvals remain intact. Campaign consent follows a concrete frozen preview.

## Approaches and scope

The discussion considered expanding tiny synthetic tests, replaying curated historical work, and using an unrestricted repository agent. The owner chose historical work with reviewed references and selected fresh comparisons. More tiny cases would repeat the current evidence limit. An unrestricted agent would require a much larger tool and permission surface.

The proposed implementation is a coordinator-mediated historical runner. It reuses current proposal validation, queue ownership, isolated checks and native receipts. Multiple cycles add observed feedback and new candidate revisions; the model never gains an unrestricted shell. Existing synthetic assessments remain available with their original meaning.

Coordinator proposals, open to correction during design approval:

- Default to eight assignments per specialty: four moderate and four complex. Permit six to ten when source quality warrants it. Do not fill gaps with disguised synthetic cases.
- Freeze two fresh native comparisons per specialty before observing candidate results: one moderate and one complex, chosen for representative constraints.
- Permit at most three proposal cycles per assignment, including the first. Report first-cycle and final results separately. Do not count cycles as additional assignments.
- Start curation with this plugin repository. Add another owner-selected repository only when the selected specialty lacks sufficient suitable history.

A specialty is a concrete capability and language/domain, with separate difficulty and context measurements. Protected and generic Python verification of the same case are not independent specialties or assignments. A custom specialty label never creates an approval.

## Current implementation and required changes

Inspected at `f065e8c771732e7ca83b4b069398854298acfeea` on 2026-10-23:

- `local_model_delegation/onboarding.py` creates three packaged cases repeated twice per group. Selection supports all groups or one exact group. There is no historical assignment manifest or multi-cycle runner.
- `contracts.py` bounds supplied text to eight files and 100,000 UTF-8 bytes per file. Candidate code contains complete replacements of allowed files. General candidates have no tools. Existing path, hash, JSON and output-size validation must remain.
- `worker.py::context_fits` conservatively reserves prompt UTF-8 bytes plus 2,048 tokens of template headroom and the selected generation allowance. This is not qualified tokenization.
- Profile approval bounds production generation settings. Current request monitoring detects silence, a defined repetition pattern and token exhaustion, but imposes no total inference deadline.
- Native verification binds source, candidate, attempt and checks. Uncertain requests retain ownership. Assessment jobs cannot dispatch a solving native fallback.
- Project measurement comparison helpers record evidence; they do not execute comparisons. Private framework replay tools are not packaged framework support.

These facts expire when the referenced contracts change. Reinspect before implementation. Extend the existing assessment entry point and versioned contracts rather than introducing another scheduler, approval system or inference client.

## Assignment curation and reusable packs

Search merged history, not the presence of a backlog. Treat one coherent behavioral change as a candidate. A release merge can contain several unrelated changes and is not itself an assignment. Commits must be reachable from the selected merged revision. Retain merge/commit identity and review evidence separately; an unknown reviewer or model stays unknown.

For each candidate:

1. Freeze the exact pre-change base and reviewed solution revisions. For merges, record the intended parent explicitly. Include necessary pre-existing dependencies; exclude tasks that require unreconstructable services, secrets or nondeterministic external state.
2. Reconstruct a standalone behavioral requirement without describing the solution. Resolve ambiguity before the pack is frozen. Record constraints, editable paths, relevant context, public checks and private acceptance criteria.
3. Build separate contestant and evaluator artifacts. Contestants receive only the base snapshot and task brief. Withhold the patch, later commits, Git metadata, PR discussions and solution-revealing comments or artifacts. Check package contents for leakage.
4. Verify the reference independently. For changes, the base must fail the targeted behavioral check and the reference must pass; unrelated pre-existing failures must be documented and isolated. A broken reference excludes the case until repaired and revalidated.
5. Classify difficulty from interacting constraints, dependencies, ambiguity and relevant context. Line count and required output length do not establish difficulty. Record why the case belongs in its category.
6. Freeze the assignment, environment, tests, review rubric and baseline subset before candidate execution. Never strengthen or relax checks because a particular model passed or failed.

For test-writing assignments, ask for tests against the appropriate production snapshot without supplying the historical tests. Require tests to pass correct behavior and fail specified historical defects or independently constructed defect variants through real assertions. Require expected discovery counts, no skips, and genuine framework execution. Syntax errors, missing dependencies and imports are not defect detection.

For summary/documentation specialties, use historical documentation work only where the base sources support a substantive reconstruction. Verify citations and required claims independently. Do not invent six cases merely to fill that specialty.

This repository offers candidate sources such as Bionic identity resolution (`3068c97`), strict Markdown JSON handling (`d5a34ed`) and update-preference preservation. These are not yet selected or certified moderate/complex. Curation may find fewer than six eligible cases for a specialty; report that shortage and request another repository rather than claiming complete coverage.

Reusable packs are immutable and versioned, with explicit source/licensing provenance. Private pack content and results stay in private state. Publishing a public pack is a separate action. Reuse the same pack across models; tag potential training exposure and repeated assessment exposure as unknown or known. Reviewed historical code is a reference, not proof of unseen performance or a requirement to reproduce the same patch.

## Data and evidence

A versioned pack manifest binds assignment IDs, specialty, difficulty, source revisions, reviewer evidence, disclosure status, initial files, allowed working files, acceptance rubric, public feedback commands, private checks and pinned environment fingerprints. Record repository-relative paths and hashes without embedding credentials or machine-private source paths in distributable material.

The campaign preview binds pack digest, model artifact/runtime/settings, selected assignments, comparison IDs, cycle ceiling, per-cycle token allowances, deadline derivation, verifier identities, context limits and maximum possible submissions. With eight assignments and three cycles, local submissions are at most 24; two native comparisons add at most six proposal cycles. Native internal inference calls may exceed proposal cycles and must not be misreported as six calls.

Each cycle records its parent candidate, input/context digest, working-tree digest, feedback digest, generation identity, effective allowance, terminal evidence, timestamps, usage availability and bound verification receipt. Preserve original output privately under current evidence rules; do not begin storing full private reasoning. Record settings and usage separately for local and native participants.

Old synthetic reports, profiles and saved responses remain immutable. New report schemas must distinguish historical work from synthetic trials and real production delivery. Offline reverification creates a new verifier-version result linked to the original response; it never regenerates or silently replaces a historical verdict.

## Work cycles and context

Each assignment starts in a disposable copy of the frozen base. The initial packet contains the relevant files and public requirements. For the first version, the total supplied/working-file union remains at most eight files, each within existing size bounds; the frozen manifest identifies that union. Dependencies and read-only test fixtures can exist in the evaluator environment without becoming model-visible files. No deletions, renames, binary edits or arbitrary new paths are introduced.

If a task cannot be represented honestly within those limits, classify it unsupported rather than trim essential context or lower its difficulty. Larger repository navigation is a later, explicit contract extension. Relevant long files and cross-file constraints can still exercise longer context within these limits. Record actual context supplied at each cycle, not a guessed token count.

A cycle submits a structured proposal, validates it, stages permitted replacements and runs the predeclared public checks. The next cycle receives the current allowed source files, original brief and standardized public feedback. Native coordination may supply mechanical check output and fixed format-error descriptions, but no suggested fix, reference-derived hint or rewritten code.

Only structurally valid proposals update the disposable working snapshot. Invalid output consumes that cycle; the next packet retains the previous valid snapshot. Public check failures may be revised within the cycle limit. Hidden checks and semantic reference review happen only after the contestant declares completion or the last allowed cycle ends; their findings are never fed back for repair in that attempt. An early completion declaration finalizes the candidate.

Intermediate snapshots are not accepted project changes. A final candidate requires all independent verification. Preserve source/hash and protected-test boundaries at every step. A native reviewer who knows the reference cannot also coach the contestant. Record any accidental assistance as a contaminated comparison, excluded from unassisted results.

## Token ceilings and measured deadlines

There is no fixed 32K policy for historical assessments and no symbolic unlimited number. Each campaign uses a separate unapproved assessment profile/permit; it never raises the approved production profile ceiling.

Before consent, establish loaded context, supported generation parameters and accounting, template reserve, input bound for all planned feedback cycles, and known runtime/model output maximum. Use a qualified tokenizer if available; otherwise retain the current conservative UTF-8-byte bound. Reserve enough input space for the largest permitted cycle packet, including feedback. Bound and truncate public logs deterministically before hashing them.

Choose the largest usable generation allowance within the verified runtime output maximum and the remaining context reservation. When an explicit maximum is unavailable, require documented adapter behavior plus separately authorized bounded qualification to establish an accepted finite ceiling; never infer support from a large context window alone. Label unverified accounting/support as unavailable and block that configuration. Do not silently reduce a frozen allowance after a run begins.

Measure prefill/startup latency and decode throughput from compatible saved telemetry: same artifact, backend, machine, settings and relevant context range. Sparse or unmatched telemetry is insufficient for a precise deadline. A missing calibration requires a separately previewed bounded calibration run, excluded from the 6–10 scored assignments; design approval is not calibration consent.

Proposed conservative initial deadline formula per model and cycle: twice the sum of observed upper prefill/startup time, allowance divided by a conservative observed decode rate, and the declared public-check timeouts. Store the measurements, sample count, context range, formula and resulting seconds. The factor of two is a coordinator proposal, not a measured safety guarantee. Freeze exact values only in the run preview; do not promise elapsed duration during design.

The assignment allowance is the sum of its permitted cycle allowances; its execution deadline is the sum of the measured cycle deadlines. Count generation, active public checks and automatic packet preparation. Exclude queue delay, machine suspension, owner pauses and final independent review from that execution budget, while reporting them separately in end-to-end elapsed time. Persist elapsed accounting across restarts; never reset a clock by reopening a run. Host interruptions make timing noncomparable unless the excluded duration is known.

At a deadline, stop admission of further cycles and request cancellation only through a qualified adapter operation. A closed connection, local timer or killed observer does not prove that inference stopped. Without verified terminal/cancellation evidence, retain the slot, mark the attempt unresolved and block conflicting work. The deadline bounds permitted workflow progress; it cannot promise a hard compute stop on an unqualified backend. No automatic unload/reset is authorized.

Budget exhaustion, deadline expiry or incomplete output produces an unfinished/inconclusive assignment. Preserve any valid partial work for inspection, not a pass. Completed candidates can still be verified after the deadline using their recorded completion time. More time or additional cycles require a separately authorized follow-up linked to the original; do not overwrite or silently replay the original result.

## Fair native comparisons

Freeze a difficulty-stratified subset before local results. Run fresh native contestants without inherited task history containing solutions. Preserve the owner's native model, provider, authentication and reasoning settings. Never switch profiles or billing paths merely to create a baseline.

Both contestants receive identical initial task packets, permitted file scope, public checks, feedback rules, proposal-cycle count and hidden final criteria. Native contestants use the same coordinator-mediated proposal protocol for controlled comparisons. They do not browse the full repository or obtain private check feedback. Wider native tool access is a separately labeled workflow comparison, not the controlled score.

Allow model-specific measured execution deadlines so slower hardware does not receive less opportunity to reason and revise. A common wall-clock cutoff would confound capability with throughput. Token counts are tokenizer-dependent; record each model's effective allowance and actual usage, not a claim of equal compute. If the native interface cannot enforce or expose an equivalent generation limit, label that asymmetry and report an opportunity-matched comparison rather than a token-matched one. Do not fabricate native usage or enforcement evidence.

Use the same pinned checks and semantic rubric for both; conceal contestant identity from final review where practical. Grade alternative valid solutions on behavior, scope compliance, regressions and maintainability. Do not use patch similarity or reviewer-model prestige as the oracle. Record who reviewed the historical solution only when supported by evidence.

## Capability and speed reporting

Capability is based on completed, independently verified work. Neither latency nor local/native time ratio changes a correctness verdict. Report first-cycle passes and final passes alongside planned assignments, completed failures, unfinished/inconclusive attempts, invalid cases and unresolved runtime attempts. A valid final submission that violates requirements fails; an unfinished attempt does not establish inability. Protocol failures and their observed effects remain visible rather than being hidden in a single proficiency percentage.

Display coverage explicitly: for example, “5 passed, 1 completed failure, 2 unfinished; 8 planned.” Do not present five passes among five evaluated tasks as complete specialty proficiency. A reference/environment failure invalidates the case and remains in the audit trail; replacement changes the pack version and campaign preview.

For paired completed tasks, report local and native execution seconds and `local_seconds / native_seconds`, described as “local took N times as long.” Keep generation time, public-check time, queue delay, final native verification and total elapsed time separate. Report median paired ratios with sample count and range; never divide unrelated suite medians. Missing timing remains unknown. Two paired tasks are descriptive evidence, not a general speed benchmark.

Report correctness and timing when only one contestant succeeds, but do not label an unsuccessful quick attempt an efficiency win. For unfinished timed runs, show observed duration and that completion time is unknown. Verification and coordination costs count in end-to-end workflow measurements even though they do not grade capability. Historical references have no fresh baseline timing unless recorded comparably.

No 6–10-case score certifies universal reliability. Report demonstrated specialty, difficulty, context, assistance level, settings and limits. The report can support a proposed production scope, but approval and routing remain separate explicit actions. Speed can inform an owner's later routing preference; it never silently downgrades demonstrated ability.

## Implementation boundaries and validation

Extend `assess-my-model` operations, assessment preparation/selection/reporting in `onboarding.py`, versioned manifest/receipt validation, and current queue/worker lifecycle as necessary. Reuse `lmstudio.py` for qualified runtime accounting and termination behavior, `validation.py` for candidate checks, and existing comparison-record helpers where their schema fits. Do not record replay work as shipped project delivery. Keep data formats and code placement open to the builder within these boundaries.

Required offline proof before any real campaign:

- Historical base/reference discrimination; test-writing defect discrimination; genuine framework discovery; deterministic environment and leakage inspection.
- Pack tamper detection, exact preview consent, private/public artifact separation, unsupported-file rejection and no widening of live approval.
- Candidate lineage across cycles, unchanged protected files, strict JSON validation, public-only feedback and no hidden-check coaching.
- Exhaustion/deadline/late terminal/cancellation ambiguity, restart accounting, pause/stop, duplicate submission and retained uncertain slots.
- Capability verdict independent of latency; explicit incomplete coverage; correct paired ratios; missing native telemetry and asymmetric budgets labeled.
- Legacy synthetic runs and offline response replays preserve their original interpretation and settings.

Run relevant focused tests and the repository's offline suite plus `git diff --check` during implementation. Offline tests do not prove runtime cancellation, large-token support or live native fairness; these require separately authorized qualification with exact runtime evidence.

The design is complete when review finds no consequential planning gaps and the owner approves it. The next phase is an implementation plan, not model execution. Campaign preparation later selects actual tasks, validates references, derives numerical budgets and presents the exact consent preview.

## Design review

An independent native builder check on 2026-10-23 found no consequential planning questions. It checked the current contracts, capability/speed separation, cycle lineage, hidden-check isolation, deadline recovery and comparison asymmetries. This review did not execute models or qualify runtime behavior. No production code has changed.
