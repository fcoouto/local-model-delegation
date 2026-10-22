# Model measurements per project

Date: 2026-10-22. Status: source implementation completed on 2026-10-22; see [Offline validation](../../project-measurements-validation.md). Installation and live qualification remain separate.

## Purpose and decisions

Measure whether a particular model helps with a particular kind of work in a particular project. Quality comes first; the objective is lower total native coordination usage without weaker verification. Longer local execution can be acceptable.

The owner selected **measurements from normal work, plus separately authorized comparisons when needed**. Reuse the existing Python helper, SQLite state, durable jobs, verification contracts, and optional visibility extension. Keep the shared core host-neutral; implement and qualify Codex integration first. No new service, dashboard, model runner, dependency, or provider integration is needed for this release.

The remaining choices below are proposed implementation defaults, not owner-approved operating limits. This design does not approve a model, authorize inference, enable routing, or resolve deferred loading work.

## Approaches

1. **Selected: normal work plus bounded comparisons.** Collect cheap evidence from work already authorized. Register comparison evidence when normal work cannot provide a useful native baseline. Extra execution requires its own bounded authorization.
2. **Normal work only.** Cheapest collection, but savings often remain unknown because tasks differ. This remains a supported operating practice within the selected approach.
3. **Continuously execute both routes.** Rejected: duplicates native work, consumes the usage being saved, and creates additional execution and privacy risks.

The first release records and compares evidence. It does not introduce automatic experiment dispatch or a new adaptive routing policy. Reports inform the coordinator; they cannot grant approval, expand scope, or override current routing gates. A later routing change must replace the existing global benefit gate with project-bound evidence before claiming project-aware automatic selection.

## Current implementation and reuse

Reviewed against source revision `63cc02ba6ef9eb7b3dd372fa726a7e479be65b2c`:

- `onboarding.record_outcome` accepts token counts or nulls, accounts for several overhead categories, and labels subscription savings unknown. It stores one receipt in job route data and updates model-global benefit and suspension fields.
- `scheduler.rank_profiles` consumes those global profile fields. It has no project identity or project evidence requirement.
- `Store` already preserves task identity, attempts, queue times, uncertain slots, and native fallback claims in SQLite. `accepted` means candidate verification, not necessarily integration into the target project.
- `validation` binds check receipts to the candidate and source. Native fallback can subsequently replace the current candidate, so historical local verdicts must be captured before replacement.
- `visibility` is an optional read-only projection. Its recent-job limit is unsuitable as the source for aggregate measurements.

New measurement commands must not call the legacy `record_outcome` mutator. Preserve that command for compatibility and label its records `legacy_unscoped`; do not silently import them as project evidence. Document that legacy benefit calculations do not satisfy this design's savings contract.

## Evidence identity

A scorecard is **project + model binding + task scope + verification environment**. It is not one universal model score.

| Dimension | Contract |
| --- | --- |
| Project | Random local UUID bound to a canonical repository identity. Worktrees sharing a Git common directory share the project. Independent repositories and separate clones remain separate. Non-Git workspaces use their canonical root. Never derive identity from a repository name or remote URL. |
| Project relocation | Do not silently merge a new root with old history. Explicit rebinding is deferred; report a new project until supported. |
| Model binding | Profile ID, artifact digest, runtime identity digest, request settings digest, helper/checker version. Display name alone never joins evidence. |
| Scope | Capability, language, declared complexity, context bucket, actual input byte count, and file count. Preserve exact source/task hashes per observation. |
| Environment | Digest of coordinator-selected applicable instructions, toolchain/framework versions, lockfiles, and verification configuration. Preserve the selected file list privately. Missing fingerprints remain unknown. |
| Native comparison | Host, provider, native model, reasoning setting, usage schema, and measurement boundary must match. No conversion between unrelated providers' token counts. |
| Evidence origin | `normal_work`, `synthetic_assessment`, `authorized_comparison`, or `legacy_unscoped`. Never pool synthetic evidence into project work. |

Normal code revisions are recorded but do not create a new scorecard on every commit. Changes to model settings, relevant instructions, dependencies, or acceptance tooling create a new evidence cohort. Prior cohorts remain inspectable. A workspace containing several repositories gets separate scorecards; a combined display must retain those boundaries.

Capacity remains machine/runtime evidence shared across projects. Project grouping must not multiply available slots or weaken admission checks.

## What to measure

| Measure | Meaning and denominator |
| --- | --- |
| First-candidate acceptance | First local candidates independently accepted / first local candidates with a recorded verdict. Show pending and missing verdict counts beside it. |
| Local delivery rate | Tasks delivered from local output without native rewriting or fallback / closed tasks with a confirmed local submission. A native rescue is not local success. |
| Fallback frequency | Tasks requesting native fallback / all closed delegation decisions. Separate pre-POST availability fallback from post-POST model failure. |
| Delivery quality | Integrated unchanged, integrated with native edits, rejected, or not integrated. Integration requires a coordinator receipt with artifact hashes and destination checks. |
| Later corrections | Confirmed task-linked regressions, reverts, or incorrect summary claims. Append evidence; never erase the original acceptance. No report means “no incident reported,” not “defect-free.” |
| Latency | Queue, inference, verification, integration, fallback, and overall elapsed time where recorded. Overall time ends at delivery, not candidate return. |
| Native overhead | Actual attributable native usage for briefing, coordination, verification, rewriting, integration, and fallback; measurement/reporting overhead is included. |
| Resource suitability | Admission denials, pressure/swap observations, and recorded request-memory envelope. Missing samples are unknown. Host memory delta is not per-model resident memory. |
| Evidence coverage | Distinct tasks/cases, attempts, repeat count, time range, completion count, missing usage/verdicts, and applicable version/cohort. |

Keep content/semantic failure, output-format failure, framework mismatch, source change, admission denial, transport uncertainty, and owner cancellation distinct. A failure category must come from durable state or a bound coordinator receipt. A model cannot grade itself.

Show `passed / evaluated`, pending counts, distinct case count, and the last 30 closed tasks alongside lifetime counts. Repeated trials of the same frozen case are repetitions, not independent task diversity. Display latency median when any valid observations exist; display p95 only with at least 20 observations, using nearest rank. These are descriptive measures, not a reliability guarantee.

Do not add an opaque composite score or a statistically unsupported “95% reliable” badge. Recommendations use visible evidence: `insufficient_evidence`, `promising_scope`, `needs_attention`, or `savings_not_demonstrated`. None means approved. The coordinator explains which measures informed its recommendation; v1 has no automatic promotion threshold.

## Savings contract

Native usage measurements and counterfactual savings are different facts. Even a measured paired baseline yields a token-savings proxy, not proof of account quota or currency savings.

1. Record actual usage with producer/version, native task/run identity, unique span IDs, boundary timestamps, token schema, and completeness. Do not infer tokens from characters, SSE chunks, elapsed time, or remaining account quota.
2. Keep input, cached input, output, and reasoning fields according to the producer's schema. Cached/reasoning fields may be subsets; never add them twice. Missing is null, not zero.
3. A total is either a complete authoritative task total or the sum of unique non-overlapping spans. Phase subtotals explain the total and are not added to it. Shared or unassignable coordinator context makes attribution incomplete.
4. Compare native-only work with the same scope, acceptance criteria, environment, native model/settings, and comparable input size. Historical matches are labelled `observational_estimate`. Frozen, independently executed pairs are labelled `paired_usage_proxy`. Never use a fallback execution, which has already seen local work, as an independent native-only baseline.
5. Include failed local attempts, native fallback, native rewriting, measurement overhead, and non-delivering work. Do not report only successful local tasks as the aggregate benefit.

For a fully measured comparable cohort:

`net_native_token_proxy = sum(native_only_baseline) - sum(all_native_usage_on_delegated_route) - one_time_allocated_overhead`

Store one-time assessment/onboarding/comparison overhead as unique usage spans, with an allocation ledger. Charge each span once across all projects; do not repeatedly subtract the full onboarding cost or silently charge it nowhere. Unallocated overhead makes the all-in result unknown. Show the running difference before and after allocated overhead. Never clamp a negative value to zero.

If any required usage, baseline, or allocation is missing, the whole-cohort all-in saving is **unknown**. A complete subset may have a separate result with its coverage and selection bias stated. Report native baseline failures and incomparable pairs separately rather than dropping them silently.

Actual subscription/quota savings and energy/currency savings stay unknown in v1. No pricing conversion, new billing source, proxy, or authentication change is introduced.

## Collection and persistence

Add `projects.py` for project identity and `measurements.py` for validated receipts, aggregation, and reports. Reuse standard-library SQLite, hashing, and existing private-state permission checks.

Add namespaced tables to the existing SQLite database: `measurement_meta`, `measurement_projects`, `measurement_tasks`, `measurement_events`, and `measurement_comparisons`. Maintain an independent `measurement_meta.version = 1`; do not change queue `PRAGMA user_version`, job briefs, approvals, or existing task hashes. An explicit `metrics init` initializes the additive schema in existing state. Fresh authorized setup initializes it too. Read commands never initialize or migrate state.

- `measurement_projects`: project UUID, canonical identity, display label; unique identity.
- `measurement_tasks`: task ID, optional unique job ID, immutable context JSON/hash. Native-only tasks have a coordinator-provided UUID; starting a measurement never starts inference.
- `measurement_events`: event ID, task ID, producer/source key, kind, observed time, payload/hash. Unique `(producer, source_key)` makes identical retries idempotent; different data under the same key fails. Corrections append an event referencing its predecessor; no destructive overwrite.
- `measurement_comparisons`: manifest ID/hash, owner consent reference, frozen case/binding/check hashes, explicit inference allowance, and linked execution receipts. Registration records evidence; it does not create execution authority in the scheduler.

Context binds at enqueue through an optional separate metadata argument; it never enters the model prompt or changes a saved brief hash. Changed metadata on an idempotent enqueue is a conflict. Existing calls without metadata remain supported and are unscoped, not guessed into a project.

Record local verification outcome with candidate/attempt/check hashes before fallback can replace the candidate. Preserve immutable verification evidence by candidate hash. A crash between authoritative outcome and measurement collection produces a visible gap; reconciliation may fill it only from preserved bound evidence. No reconciliation can generate a new model attempt, free an uncertain slot, or infer a verdict from the terminal status alone.

Use existing monotonic intervals for same-process durations, with epoch timestamps for ordering. Clock reversal, incomplete intervals, or restart boundaries without proof yield unknown durations. New timing observations must not change stale detection, abort, or capacity behavior.

Missing measurement schema or an exporter failure must not corrupt or stop already-authorized work. Report collection health and lost coverage; never manufacture missing successes. Integrity conflicts are reported for operator repair. Invalid explicit receipt commands fail without mutation.

Native telemetry is optional. The coordinator can supply verified receipts from a supported host source. Qualify the source's scope and token semantics before automatic collection; do not scrape authentication files or assume a stable undocumented session-log API. If task usage is unavailable, quality and timing still work and savings remain unknown.

## Comparison workflow and consent

The first release registers a frozen manifest and ingests evidence from separately authorized execution. It does not build a second execution engine or broaden the existing bundled assessment runner.

The manifest declares project/cohort, cases, source snapshots, acceptance checks, exact model/native settings, maximum local and native calls, and consent reference. Count each distinct submitted attempt, including failed or uncertain attempts, toward the allowance. Repeated receipt delivery does not count twice. Uncertain dispatch is never permission to retry.

For paired evidence, both routes solve the same frozen case in separate contexts, without seeing the other result, under the same independent acceptance criteria. Record execution order and evaluator provenance; reject “paired” status if isolation cannot be established. Imported evidence cannot approve a model or count as a newly executed assessment.

Running new project-specific comparisons is a separate qualification step. The current bundled-fixture runner does not yet execute arbitrary project manifests. Use it only within its existing contract; missing execution support is a blocker to running a comparison, not a reason to bypass consent. The measurement release remains useful with normal work and externally coordinated authorized receipts.

## User experience and privacy

Provide `metrics report --project <id> --model <profile_id>` as JSON by default and `--format text` for a concise summary. Reports read the full ledger, not a recent-job visibility export. Default output groups incompatible cohorts separately.

Example shape, with placeholders rather than claimed results:

```text
Example project / Example model / Python changes / current environment
Quality: <passed>/<evaluated>; <pending> awaiting verification
Delivery: <unchanged>, <native edits>, <fallback>, <not integrated>
Native usage saving: unknown — comparable baseline missing
Time: <median overall>; <sample count> measured tasks
Recommendation: insufficient evidence
Coverage: <distinct tasks>; <missing receipts>; <measurement period>
```

An optional compact `measurements.json` export uses generic model/project labels and the existing visibility preference. It contains no prompts, source text, filesystem roots, remote URLs, task content, or authentication data. Disabling visibility removes this export and stops republishing it; private measurement collection continues. Delegation works without any viewer.

All raw records remain in owner-only local state. No raw project cases, private paths, or actual owner assessment evidence enters the portable repository. No automatic network telemetry. Retention/deletion UI, project merging, dashboards, energy tracking, and automatic experiment scheduling are outside v1.

## Release acceptance and next gate

- Two projects using the same model produce separate, auditable reports. Worktrees group correctly; independent clones do not.
- Native fallback success cannot become local success. Duplicate/replayed receipts cannot inflate counts or savings.
- Model/settings/environment changes retain history while separating current evidence. Old synthetic trials do not become project reliability evidence.
- Missing usage, unknown attribution, incompatible baselines, clock changes, and incomplete crash recovery produce explicit unknowns.
- Reports and exports cannot start jobs, approve models, alter native settings, or enable routing. Export failure cannot change task outcomes.
- Offline tests use fictional models, fake runtimes, and disposable state. No live calls are required to implement or test this release.

After implementation, qualify receipt capture on the actual host and run a separately consented, narrow project pilot. Measure total preparation/review/reporting overhead. Only then propose project-bound routing policy and owner approval. Do not infer broad project reliability from small synthetic cases.
