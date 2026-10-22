# Measurements per project

Measurements are private observations, not approval or routing input. They never run models, change native settings, release slots, or apply candidates. Use the existing shared state directory.

## Commands

Invoke with `python3.11 -B <plugin>/delegate.py [--state-dir PATH]`.

1. Fresh authorized setup initializes the additive ledger. Existing installations use `metrics init` after authorized update. Reports never initialize or migrate state.
2. `metrics register --root ROOT --label NAME` returns a private project ID. Worktrees share their Git common-directory identity; independent clones/repositories remain separate. Non-Git workspaces use their canonical root. Moves are not silently merged.
3. Before authorized local work, supply `submit --brief BRIEF --measurement-context CONTEXT`. For native-only work, `metrics begin --task UUID --context CONTEXT` starts a measurement, not inference. `--job ID` can associate existing work, but cannot recreate missing execution provenance.
4. The helper preserves local verifier results. After destination checks or factual verification of a summary, use `metrics record --task TASK_ID --receipt RECEIPT` for delivery, usage, or incidents. Never pass model-authored receipts as evidence.
5. `metrics reconcile` recovers observations from durable jobs and immutable check archives. It never retries inference or native dispatch. Investigate conflicts; never invent missing successes.
6. `metrics report --project PROJECT_ID [--model PROFILE_ID] [--format json|text]` reads all relevant records. JSON is default. Model, environment, scope, native settings, and evidence-origin cohorts stay separate.

Do not automatically also call legacy `outcome record`. It retains model-global benefit/suspension side effects; its records remain unscoped legacy evidence. Metrics do not update those fields. Project-aware automatic routing is not part of this release.

## Context

Every field is required; unknown optional values use null:

| Field | Contract |
| --- | --- |
| `project_id` | Registered project ID |
| `origin` | `normal_work`, `synthetic_assessment`, `authorized_comparison`, or `legacy_unscoped` |
| `scope` | `capability`, `language`, `complexity`, `context_bucket`, `input_bytes`, `file_count` |
| `environment_manifest` | Object describing selected instruction hashes, toolchain versions, lockfiles and verification configuration, or null |
| `environment_digest` | SHA-256 of canonical environment JSON, or null with its manifest |
| `native_binding` | `host`, `provider`, `model`, `reasoning`, `boundary`, or null |
| `source_revision` | Revision identifier or null |
| `case_id`, `case_hash` | Stable case identifier and hash of frozen source/contract/check definition; repetitions retain the same hash |

Job-bound scope and source-root identity must match the durable brief. `input_bytes` is the UTF-8 size of canonical JSON with `contract`, `files`, and `editable_paths`, as sent by the helper. `file_count` counts supplied files. Synthetic jobs cannot be labelled normal work.

Canonical JSON uses sorted keys, compact separators, UTF-8, and finite numbers. The package provides `contracts.canonical` and `contracts.digest`. Do not expose independent oracle source to the model.

## Receipt envelope

Required keys: `schema_version: 1`, `producer`, `source_key`, `kind`, `observed_at`, `payload`. Optional `supersedes` references an earlier event ID. Stable producer/source keys make retries idempotent; changed data under an existing key is a conflict. Corrections use a new key and preserve the earlier event. Cross-task corrections are forbidden.

Public kinds are `delivery`, `incident`, and `usage`. Job observations, local verdicts, and comparison runs use their dedicated bound interfaces.

### Delivery and incidents

Delivery payload: `outcome`, `artifact_hash`, `checks_hash`, `native_task_id` (or null), and `durations`. Outcomes: `unchanged_local`, `native_edited`, `native_fallback`, `not_integrated`, `native_only`. Hash the delivered artifact and actual destination-check evidence; summaries use the verified answer hash. Acceptance alone is not integration.

`durations` may contain `queue`, `inference`, `verification`, `integration`, `fallback`, and `overall` seconds. Use measured intervals or null, never invented durations across restarts/clock changes. The helper records monotonic inference duration; other phases require coordinator evidence.

Incident payload: `delivery_event`, `evidence_hash`, `disposition` (`confirmed|withdrawn`). Withdrawal corrects the prior incident through `supersedes`. No incident report means only that none was reported, not defect-free output.

### Usage

Required payload shape (fictional values):

```json
{
  "native_binding":{"host":"example","provider":"example","model":"native","reasoning":"medium","boundary":"whole_task"},
  "source_run_id":"example-run", "span_id":"example-span",
  "start":1, "end":10, "phase":"whole_task",
  "usage_schema":"input_output_v1",
  "tokens":{"input":200,"output":100,"cached_input":150,"reasoning_output":80},
  "complete":true, "attribution":"exclusive",
  "evidence_hash":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "group_id":"whole-task", "role":"total", "expected_spans":1,
  "overhead_complete":true, "allocations":null
}
```

`input_output_v1` defines cached input and reasoning output as subsets. The example totals 300, not 530. Map the host's actual semantics before choosing this schema; unknown schemas cannot establish savings. Never infer tokens from characters, streaming chunks, elapsed time, or account quota percentages.

`attribution` is `exclusive|shared|unknown`. Counts and times may be null. A complete authoritative total takes precedence over explanatory components from the same producer/run/group. Without a total, all components must declare the same expected span count, be complete/non-overlapping, and share one group. Shared context, missing spans, clock reversal, or mixed native bindings makes usage unknown.

Allowed phases: `whole_task`, `briefing`, `coordination`, `verification`, `rewriting`, `integration`, `fallback`, `measurement`, `onboarding`, `assessment`, `comparison`. Include all coordinator overhead and unsuccessful work. `overhead_complete` explicitly attests that applicable one-time costs are accounted for, including an evidenced zero; never set it merely to obtain a saving.

One-time overhead uses a total span in phase `onboarding|assessment|comparison` and `allocations` mapping measured task IDs to fractions. Fractions cannot sum above 1. Charge each unique span once; retain incomplete allocation as unknown and negative savings as negative. Do not resubmit setup spans under different producer/run identities for each project.

Native telemetry is optional. Use actual attributable counts with known semantics and evidence hashes. This release does not scrape undocumented session logs, read authentication files, or add API billing. Missing usage leaves savings unknown while quality/timing remain useful.

## Separately authorized comparisons

`metrics comparison-register --manifest FILE` records evidence; it does not authorize execution. The external executor must enforce separate consent and call allowance before POST. The bundled assessment runner retains its existing fixture contract; no arbitrary project-case runner is added.

Manifest fields: `project_id`, `scope`, `environment_digest`, `local_binding`, `native_binding`, `method` (`paired|observational`), `limits` (`local`, `native` call allowances), `consent_reference`, `consent_at`, `expires_at`, `cases`. Each case contains `case_id`, `case_hash`, `source_hash`, `checks_hash`, `contract_hash`. Local binding contains `profile_id`, `artifact_digest`, `runtime_digest`, `settings_digest`, `helper_digest` from actual execution provenance.

`metrics comparison-record --comparison ID --receipt FILE` accepts: `case_id`, `route` (`local|native`), `task_id`, `attempt_id`, `state` (`submitted|uncertain|completed|failed`), `submitted_at`, `recorded_at`, `source_hash`, `checks_hash`, `contract_hash`, `order`, `isolated`, `isolation_hash`, `evaluator`.

Local runs must bind durable attempts and model identity. Native-only runs cannot be fallback jobs. Paired runs use separate contexts and identical frozen cases/checks; retain isolation and evaluator evidence. Never relabel existing non-blind work as a blind pair.

Each distinct uncertain/failed submission consumes allowance. Receipt replay does not. Over-budget and duplicate-case attempts remain visible as violations and are excluded from comparisons. Importing receipts cannot retroactively prevent unauthorized calls.

`metrics comparison-revoke --comparison ID --at TIMESTAMP --evidence-hash SHA256` records revocation. Submissions outside the consent interval remain visible but cannot qualify pairs. Revocation does not cancel running work or authorize resetting slots.

## Interpretation and privacy

First-candidate acceptance and local delivery have separate denominators. Native rescue is not local success. Pending/missing outcomes remain visible. Reports show case diversity, lifetime counts, and the last 30 closed tasks. P95 needs at least 20 observations; counts are not statistical reliability guarantees.

Savings are native-token proxies against comparable baselines, including overhead/fallback. Subsets show coverage and selection-bias limits. Actual subscription, currency, quota and energy savings remain unknown. Recommendations never grant approval, expand scope, or bypass checks.

Resource samples reuse admission observations, not inference-wide measurements. Host swap intervals may overlap, so reports show the maximum observed delta, not a sum. Admission memory estimates are not measured model residency. Historical jobs without execution/checker provenance remain unqualified for comparisons.

Records stay in owner-only local state. Optional `visibility/measurements.json` exports compact IDs, model labels, counts and numerical summaries, excluding source/prompts/paths/remotes/credentials. The existing visibility switch removes both exports when disabled; direct reports and collection continue. Export failure cannot change task outcomes.
