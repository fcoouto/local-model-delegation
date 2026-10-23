# Delegation policy and execution contract

This is an agent-facing policy and native delegation contract, with an overview
for users. Setup installs it as `.codex/delegation-brief.md` and links it from
`AGENTS.md`; agents must read the applicable instructions before delegation.
The hooks validate JSON declarations/reports, not this Markdown file.

Vibe Setup owns route preference, coordinator responsibilities and the native
contract below. [Local Model Delegation](https://github.com/fcoouto/local-model-delegation)
owns local model discovery, assessment, capacity, execution and verification.
Its procedures stay in that project. The user's authorization and active project
instructions govern both routes; availability alone grants no authority.

- [Choose the execution route](#choose-the-execution-route)
- [Difficulty-based worker selection](#difficulty-based-worker-selection)
- [Role and specialty](#role-and-specialty)
- [Task and specialty guide](#task-and-specialty-guide)
- [Native role metadata](#native-role-metadata)
- [Demonstrated ability versus runtime capacity](#demonstrated-ability-versus-runtime-capacity)
- [Discover models and check capacity](#discover-models-and-check-capacity)
- [Local proposal and native fallback workflow](#local-proposal-and-native-fallback-workflow)
- [What enforces each rule](#what-enforces-each-rule)
- [See the effective policy and current work](#see-the-effective-policy-and-current-work)
- [Native dispatch and report contract](#native-codex-delegation-contract)

## Choose the execution route

Codex remains the coordinator: it owns scope, required tool actions, acceptance
checks and integration. Delegate a bounded task when independent work,
specialization or context isolation justifies the coordination cost.

**Prefer eligible local models over paid/native model execution for suitable
delegated tasks.** Local eligibility requires installed and enabled routing,
owner approval, demonstrated ability for the task, safe runtime capacity and
supported verification. Resolve eligibility through the plugin's own contract.
Do not infer ability
from a model's name, parameter count or advertised context window. A discovery
result, installed plugin or assessment result alone is not approval.

If local routing is disabled or the plugin cannot qualify the task, retain
authorized native execution. For busy capacity or recovery, follow the plugin's
current workflow rather than inventing a separate Vibe scheduler. Keep small tasks
with the coordinator when delegation overhead is not justified.

Explicit local prohibitions or native-only instructions override this preference.
Preserve the coordinator's native model, reasoning, provider, authentication and
permissions. Reuse existing approvals; ordinary task delegation does not authorize
installation, assessment, new approvals or route activation. Do not weaken task
requirements to fit a local model, or claim savings without evidence.

## Difficulty-based worker selection

The Coordinator owns classification, selection, acceptance and integration. Keep
its model, reasoning, provider, authentication and permissions unchanged. With
explicit project/task authorization, choose each worker's model and reasoning
through the actual client's supported controls. Roles and specialties do not
select native profiles. Never change global defaults, install a proxy, introduce
API billing or inspect credentials to obtain another model.

Worker selection is opt-in. Record it independently of lifecycle preferences in
`.codex/vibe-workflow.toml`:

```toml
[worker_selection]
enabled = true
authorization_ref = "reference to the user's scoped authorization"
```

Absent settings or `enabled=false` retain the existing authorized route. Setup
does not activate selection for other projects, approve local models or expand
benchmark authority. Preserve explicit model restrictions and task overrides.
Available models are discovered from the current authenticated host; portable
instructions never hard-code a commercial model list.

### Classify difficulty and risk

Rate reasoning complexity, ambiguity, dependency coupling and context burden
from 0 to 3, with one concrete reason for each. Use the maximum, not an average;
file count and diff size alone do not establish difficulty.

| Tier | Required reasoning | Initial search, subject to qualification |
| --- | --- | --- |
| D0 | Explicit retrieval/transformation, bounded context, deterministic checks. | Direct tool/Coordinator first; otherwise lightweight capability, low effort. |
| D1 | Known contract/cause, bounded implementation or focused tests. | Lightweight/balanced capability, medium effort. |
| D2 | Interacting components/state, substantial context or uncertain diagnosis. | Reasoning-capable model, high effort. |
| D3 | Architecture, deep ambiguity, concurrency or adversarial judgment. | Best demonstrated pair for the exact scope; higher supported effort only when justified. |

These are search starting points, not certified model mappings. Effort labels
are not equivalent across models. Risk is separate: R0 is negligible-impact
read-only/reversible work; R1 is ordinary behavior change; R2 covers security,
privacy, authorization, irreversible data effects or comparable impact. R2 raises
the tier to at least D2 and requires domain-specific evidence and independent
review. Read-only security review can be R2. A one-line authorization edit is
not a cheap mechanical task. Uncertainty takes the higher plausible tier until
investigation resolves it.

Define acceptance checks before selection. If a result cannot be independently
verified, narrow the assignment or keep judgment with the Coordinator. A larger
model does not supply missing verification. Review qualification needs evidence
of finding defects and avoiding unsupported findings; successful implementation
alone does not qualify a reviewer.

### Prefer qualified local execution

First keep tasks with deterministic tools or the Coordinator when delegation
cannot justify its overhead. Otherwise prefer a local model when its exact
approved scope/settings match the entire task, routing is enabled, the plugin
admits capacity, and verification is supported. Match language/domain, specialty,
difficulty, risk, context, tool and output needs; do not infer capability from a
name, parameter count or a broad specialty label.

Unknown savings alone does not disqualify an eligible local route. A documented
hard deadline or comparable measured harmful outcomes may justify native work;
record that evidence and the rejected local option. Do not prefer a paid model
merely because its isolated call appears faster. Preserve the plugin's waiting,
reservation and recovery rules; never clear an uncertain reservation to obtain
capacity. Local runtime/thinking settings stay within approved assessed profiles.

When local execution is ineligible, select an authorized native pair with matching
qualification. Compare full expected cost: briefing, attempts, verification,
repair/fallback and integration. Without comparable cost data, call the ranking
provisional, not cheapest. If no pair qualifies, retain the existing authorized
inherited route or the Coordinator and disclose the evidence gap.

Select model and effort together. Full-history forks in clients that require
inheritance cannot carry overrides: use a fresh context with the task's complete
bounded brief and explicit supported model/effort fields. Inspect native profile
and default precedence. Record requested and observed settings separately. A
mismatch fails selection: stop/reconcile that worker before replacement and
preserve partial work. If observations or overrides are unavailable, retain the
authorized inherited route and mark model-selection qualification unverified.

### Qualification states and finite recovery

Qualification binds exact observable model/version, reasoning, client/tool path,
role/specialty, language/domain, tier/risk and context/output bounds. Local records
also bind artifact/runtime/settings digests. An alias without immutable version
information carries a dated observation and freshness limit, not invented identity.

| State | Permitted execution |
| --- | --- |
| Not assessed | Separately authorized bounded evaluation only; entry records Pilot only. |
| Pilot only | Authorized evaluation; capped canary only after the case gate and scoped canary authorization. |
| Qualified | Matching ordinary work with current evidence and all authorization/capacity gates. |
| Suspended | No ordinary work; diagnosed, newly authorized reassessment must pass before promotion. |

The preserved inherited route is the baseline/fallback exception, not blanket
competence certification. These states never bypass local plugin approval or
assessment gates; an ordinary local submission cannot relabel itself a pilot.

Initial qualification defaults per narrow scope: 12 distinct paired cases
(four ordinary, four boundary, four difficult/failure), one candidate pair versus
the preserved inherited baseline; 24 worker invocations plus separately budgeted
evaluation. Freeze inputs, checks, tool permissions and context policy; separate
contexts and counterbalance order. Hidden oracles are not worker context. Require
all mandatory criteria, no critical violations, and dedicated cases for D2/D3/R2.
Baseline failures remain failures. Then permit a scoped ten-task canary: ten
candidate deliveries must pass without escalation, Coordinator rewriting or major
attributable regression. Rescue completes work but never qualifies that candidate.
These are operational gates, not statistical reliability guarantees. A failed
cohort cannot silently restart until a reviewed scope and budget authorize it.

Ordinary task budget defaults to at most two dispatch/submission attempts total:
initial plus one justified repair/escalation. Stricter project/task limits win;
a denied dispatch consumes an attempt. Record a concrete deadline/output allowance
before dispatch. Diagnose failure before changing one justified variable; no
identical retries, cascading agent trees or implicit budget resets. Unknown worker
state requires reconciliation, not duplicate execution. Coordinator rescue remains
inside the task budget and measured costs. Workers do not choose replacements.

Suspend affected qualifications on critical violations, confirmed major missed
defects, repeated settings mismatches or material source/client/model changes.
Retain negative evidence and unaffected qualifications. Benchmark allowance defaults
to zero; ordinary delegation never authorizes extra comparisons or assessments.

### Decision records, validation and savings

Keep private records outside Git: policy/task/attempt IDs, source/contract/check
hashes, classification reasons/risk, authorization and qualification references,
client-supported pairs, Coordinator baseline, candidate/rejection reasons, exact
requested/observed settings, child/local job identity, budgets, checks and outcomes.
Unknown values remain unknown. Do not add fields to the strict native declaration
or seven-field report: reference private decisions through existing context or
instructions. Existing hooks validate structure; they do not enforce model choice,
time limits, truth, sandboxing or the whole policy and can fail open.

Use `workflow.py plan-delegation ROOT` for deterministic planning and
`report-delegation ROOT` to reconcile observations and measurement evidence.
These helpers make no model calls, change no settings and grant no authority.
They validate attributed input evidence, not its truth. Actual local execution and
measurements remain with the installed plugin; do not create a duplicate scheduler
or registry. Native/native comparison records are separate from the plugin's
local/native comparison interface. See the package README for request contracts.

Test policy boundaries deterministically, then qualify App and VS Code separately
with the [native qualification](https://github.com/fcoouto/vibe-setup/blob/main/skills/vibe-setup/qualification.md) procedure from the installed
package. A selected worker must demonstrably use the requested model/effort while
the Coordinator remains unchanged. Inherited smoke tests, CLI runs, unit fixtures,
installation and display labels cannot establish that client result. Model-control
qualification also does not establish task competence or savings.

Compare identical delegated assignments with inherited versus selected workers to
isolate selection. A separate comparison against direct Coordinator execution is
needed to claim delegation itself saves resources. Keep context and verification
requirements equal; changing context and model together does not isolate either.

Maintain three accounts: operating difference (matched baseline minus candidate,
including all attempts/overhead); experiment investment (both disposable arms,
evaluation, setup and qualification); and delivered-work net estimate (matched
baseline-referenced differences on delivered work minus investment). A disposable
100-unit baseline and 60-unit candidate show a 40-unit operating difference but
spend 160 units and deliver no production saving. Ten subsequent matched delivered
tasks costing 60 instead of baseline 100 give a 240-unit net estimate after that
160-unit investment, before other overhead. This is a counterfactual resource
estimate, not a subscription saving.

Deduplicate authoritative spans; totals take precedence over their components;
charge each span once to task costs or investment. Include unsuccessful work,
rescue, measurement overhead and unallocated investment in cumulative reports.
No amortization over hypothetical tasks. Preserve negative savings. Zero baseline
makes percentages not applicable. Missing/incomplete attribution or incomparable
baselines makes full-task savings unknown, never zero cost.

Report case counts/diversity, first-attempt acceptance, delivery, missed defects,
false-positive findings, fallback rate, timing and usage coverage by scope and
model. Keep local failures separate from native rescue. Cached input/reasoning
subsets are not extra tokens. Never infer usage from characters, elapsed time,
quota percentages or badges. Tokens are proxies; currency requires applicable
billing evidence or clearly labeled estimates, never API prices applied to a
subscription. Local energy/runtime costs remain unknown unless measured.

Show end-to-end latency separately from summed parallel runtime; include failures
and timeouts. P95 requires at least 20 observations. Proposed optimization target:
10% full-cost improvement with no mandatory quality regression. Repeatable-savings
claims need at least 20 distinct matched cases and a positive lower 95% confidence
bound under a frozen case-cluster analysis; sample count alone is insufficient.
Additional trials require their own budget. Observational work is not a causal
comparison. Without telemetry, report quality/timing and savings unknown.

Rollback disables worker selection, retains inherited execution and all evidence,
and preserves in-flight ownership. Do not mutate local approvals or uncertain jobs.

## Role and specialty

Assign a **Role** for responsibility and a **Specialty** for the knowledge and
checklist the assignment needs. Keep **Status** separate: a Builder running tests
is still a Builder. Roles belong to assignments, not permanently to models or
people. Use these exact, case-sensitive role names:

| Role | Responsibility |
| --- | --- |
| Coordinator | Own scope, delegation, acceptance and integration. |
| Scout | Explore code and map dependencies. |
| Builder | Implement changes. |
| Tester | Verify behavior and edge cases. |
| Reviewer | Independently inspect changes. |
| Scribe | Maintain documentation. |
| Investigator | Diagnose failures and evaluate approaches. |

The existing main agent is the Coordinator; do not spawn a placeholder child to
give it a badge. Choose one role per assignment and keep it stable for that
assignment. Multiple roles can share a specialty, for example Builder and Reviewer
with Security-sensitive work. Independent review still requires a different
agent from the writer; changing a writer's label does not supply independence.

A role describes responsibility, not demonstrated competence, authority or an
execution profile. It never selects a model, provider, reasoning effort, routing,
authentication, tools or permissions. Preserve the approved execution settings.
This vocabulary does not create a fixed agent roster or require delegation.

For new native declarations, supply `role` and `specialty` alongside the existing
fields. The guard accepts legacy declarations without either field; missing
metadata means unspecified, not inferred from a task name or model. Before using
the new fields in a destination project, check its installed guard: older guards
reject extra keys. Review and update the guard and guide together, preserving
customizations. Until then, put the labels in existing `instructions` text without
claiming structured metadata or badge delivery. Do not edit an active declaration.

### Local-model handoff

The coordinator carries the same assignment metadata to local execution and native
fallback: `{"role": "Reviewer", "specialty": "Security-sensitive work"}`. This is
a portable handoff pair, not a new local brief schema or capability identifier.
Keep it separate from the actual model, source/provider, assessment and task state.
The local plugin owns storage, visibility transport and any presentation binding.

Use only fields supported by the installed plugin. For schema-2 local briefs
without dedicated metadata support, include `Role: Reviewer. Specialty:
Security-sensitive work.` in the existing `behavior_contract`; do not add unknown
top-level keys. Include it before submission, within the approved input budget;
do not rewrite a submitted brief or its identity/hash to change a badge. A plugin
adapter may consume the explicit pair through its own supported interface, but
Vibe does not infer a role from the model or duplicate the plugin's job registry.
Local proposals still require native verification; a role grants no capability.

## Task and specialty guide

A specialty identifies the knowledge and checklist a task needs. It does not
name a model, grant tools or certify competence. Use this guide to describe the
actual assignment, then match it to the model's recorded assessment scope.

The default status below is **Not assessed** because this portable guide supplies
no per-model assessment evidence. It is not a live inventory or a claim that every
installed model lacks these abilities. Update a model/task pair's status in the
private setup record only from matching evidence; do not certify an entire
specialty from one narrow success.

| Common role | Specialty | Representative task | Required demonstration | Default evidence status |
| --- | --- | --- | --- | --- |
| Scout | Code exploration | Explain supplied code and its callers. | Source-grounded claims, correct relationships and explicit context limits. | **Not assessed** |
| Scribe | Documentation | Update a function's usage example. | Accurate behavior, preserved constraints and checked examples. | **Not assessed** |
| Builder | Implementation | Fix a known defect with a clear contract. | Regression fixed, surrounding behavior preserved and relevant checks passed. | **Not assessed** |
| Tester | Test engineering | Add boundary and failure-case tests. | Tests derived from requirements that detect relevant faulty behavior, not merely pass. | **Not assessed** |
| Reviewer | Code review | Find regressions in a bounded change. | Known defects detected, missed defects and false positives evaluated, with connected callers considered. | **Not assessed** |
| Investigator | Diagnosis and design | Investigate an ambiguous failure or compare structural changes. | Evidence-backed hypotheses, alternatives and independently checked conclusions. | **Not assessed** |
| Reviewer | Security-sensitive work | Review authorization or possible data exposure. | Dedicated domain assessment with adversarial cases; generic coding results are insufficient. | **Not assessed** |

Classify the concrete task's complexity, ambiguity, dependencies, context needs
and verification effort. Consider risk separately: a one-line authorization
change can require more scrutiny than a larger mechanical edit. These rows are
task guidance, not new plugin capability identifiers or a fixed agent roster.
The common roles are examples, not an exclusive mapping between role and specialty.

For example, a frontend label change, a state-synchronization fix and an
authentication-boundary redesign need different demonstrations. Approval for the
first does not establish ability for the others. Successful implementation also
does not establish review ability. A bounded subtask can qualify without granting
the model a broad specialist title.

## Native role metadata

Role declarations guide agents. The native dispatch must carry the exact
`task_name` and bind the resulting child to its parent and harness root. Keep the
canonical role and nonempty specialty in the declaration; unknown roles are
rejected and custom specialties remain **Not assessed** without matching evidence.

Normal setup and upgrades validate the trusted project hook definitions and
scripts, complete dispatch arguments, actual child identity, declaration reads,
first report and inherited execution settings. Use `qualification.md` beside the
installed Vibe Setup `workflow.py` for that bounded producer check; resolve the
installed helper location from this project's setup instructions. This establishes the inputs a downstream consumer
can read; it does not establish that a consumer received or displayed them.

If an existing optional event adapter is installed, verify its input contract
with the package's adapter tests. Derive `agent_role` only when absent or null;
any supplied value wins, including a value provided by a later runtime. Validate
parent/child/task binding and preserve unrelated fields and execution settings.
These disposable contract tests are separate from actual native execution.
Do not install or activate a consumer integration as part of an ordinary upgrade.

Inspect the active client's actual spawn schema. A native `agent_type` may select
a configuration profile; never use it solely to label an assignment. Do not invent
spawn parameters, rewrite session logs or emit synthetic live workers. If the
native interface lacks independent role metadata, preserve the declaration and
report the producer limitation without changing model, reasoning or permissions.

Only load the [optional consumer compatibility guide](native-display.md) when the
user explicitly requests that consumer's setup or test. Keep that result separate
from the ordinary hooks and subagent dispatch validation. Do not introduce named
consumer products into default upgrade messages or completion requirements.

## Demonstrated ability versus runtime capacity

| Dimension | Question it answers | Evidence to use |
| --- | --- | --- |
| Role | What responsibility does this assignment carry? | Its explicit assignment and ownership; no competence claim. |
| Specialty | What knowledge and checklist does this assignment require? | The task, domain constraints and acceptance criteria. |
| Demonstrated ability | Has this model met comparable requirements within this scope? | Matching model/version assessment results, including task type, language, complexity, context limits and failures. |
| Runtime capacity | Can the approved model safely execute this task now? | The plugin's current admission and resource evidence. |

Free memory or an idle slot does not demonstrate ability. A qualified model can
still be temporarily busy. Neither dimension grants approval or enables routing.
Prefer local execution only when task fit, approval, enabled routing, verification
and runtime admission all satisfy the current plugin contract.

Read Local Model Delegation's [assessment workflow](https://github.com/fcoouto/local-model-delegation/blob/main/skills/setup/SKILL.md)
and [assessment/verification contracts](https://github.com/fcoouto/local-model-delegation/blob/main/skills/local-delegation/references/contracts.md)
at the installed version to locate and interpret evidence. Published assessment
cases describe what can be tested; saved per-model results establish what was
demonstrated. Neither a fixture nor passing package unit tests proves that a model
passed the assessment. Assessment procedures and results remain owned by the plugin.

When reporting a model/task match, show the specialty and concrete scope, evidence
source/version, observed result and limits, approval/routing state, and runtime
availability separately. Use **Not assessed** when matching evidence is absent;
this means unknown, not incapable. Report failed, stale or out-of-scope evidence
explicitly rather than presenting it as a pass. No matching evidence means no
local qualification for that task; retain authorized native execution. Do not run
new assessments without the required consent or infer a model's level from its name.

## Discover models and check capacity

### Native models

Inspect the active client's actual spawn tool, supported model/effort choices,
and effective session, subagent-default and role settings. A client model catalog
can help discover choices, but the actual spawn interface determines which are
supported for delegation. Never copy a model list from another machine or client.
Use a task-authorized model and reasoning effort; otherwise preserve the active
session's settings. Where supported, set both explicitly when preservation is
required. Where the host requires inheritance, use that supported path and inspect
effective defaults. An omitted model is not proof of inheritance when defaults or
roles override it. Report settings that the host cannot expose as unverified.

Vibe's installer preserves existing model/effort choices. Its default limit of
three native children is a native concurrency setting, not a local model capacity
measurement. The hook neither discovers models nor checks the selected model.

### Local models

Read Local Model Delegation's [agent workflow](https://github.com/fcoouto/local-model-delegation/blob/main/skills/local-delegation/SKILL.md)
and [task/verification contracts](https://github.com/fcoouto/local-model-delegation/blob/main/skills/local-delegation/references/contracts.md).
They define discovery, approval scope, model capability, input limits, capacity,
queueing, runtime support and current limitations. Vibe does not maintain copies
of their commands, schemas, model inventories or release-specific restrictions.

The links are repository entry points. For execution, use the installed plugin's
bundled docs and command help, or the repository revision matching that release.
Do not apply `main` instructions to an older installation without checking
compatibility. Record the inspected version/source in the existing private setup
record. If matching instructions or eligibility evidence are unavailable, retain
native execution and report the gap; do not guess or upgrade implicitly.

## Local proposal and native fallback workflow

Follow the linked plugin workflow for submission, waiting, verification, recovery
and fallback bookkeeping. Vibe's coordinator supplies the active project constraints,
resolves dependencies and file ownership, verifies results, and owns integration.
Local output remains a proposal until verified; the project's required checks
and independent review still apply before accepting the overall change.

If that workflow selects native fallback, obey the [native contract below](#native-codex-delegation-contract)
in addition to the plugin's dispatch/reconciliation protocol. Use the permitted
native model/effort and preserve the plugin's task identity; do not create a second
job or bypass either contract. If a permitted native worker is unavailable, the
coordinator retains the task and reports the limitation.

## What enforces each rule

The native hooks apply only when trusted, loaded and actually invoked by the
client. **Local HTTP proposals do not invoke native subagent hooks.** Do not create
a fake native task or force local output into the native report format.

| Rule | Automated check | Coordinator must verify |
| --- | --- | --- |
| Native dispatch brief | `PreToolUse` checks a safe task name, bounded JSON schema and readable declaration. | Assignment agreement, freshness, useful scope, dependencies and the worker's observed read. |
| Worker instructions | `SubagentStart` supplies the read/report procedure; it cannot veto the start. | Worker follows the scope; compare trusted task identity when available, otherwise disclose unverified binding. |
| Native final report | `SubagentStop` checks structure and requests one correction when the retry flag permits. | Truth of changes, checks, blockers and completion. |
| Model selection | Native client validates supported requests. Local eligibility is governed by the linked plugin contract. Vibe hooks do not check model choice. | Authorization, actual model/effort, full task fit, relevant constraints and any unavailable evidence. |
| Writes, budgets and ownership | Native declarations have structural consistency/bounds; they are not access controls, timers or cross-worker locks. | Disjoint writers, real permissions, budgets, safe takeover, source freshness and final integration. |
| Quality and safety | Native hooks check report structure only; local verification follows the linked plugin contract. | Semantic correctness, independent review when required, security/accessibility and destination checks. |

Hook failures, untrusted definitions or unsupported client paths can leave native
spawns unguarded. Unit tests establish handler behavior, not Desktop/VS Code
interception. Local plugin discovery, approved-model execution, fallback and
verification also need their own observed evidence. Neither route's evidence
qualifies the other; do not claim end-to-end enforcement from installation alone.

## See the effective policy and current work

In a destination project, start at `AGENTS.md` and follow its link to
`.codex/delegation-brief.md`. Setup must also link this guide from the project's
existing documentation entry point; the installer does not edit those files.
Keep a dated summary in the existing private setup/quality record: client/plugin
versions, permitted routes, native model/effort evidence, local routing state,
approved scopes and capacity evidence, active hook root/trust, tested behavior
and unresolved gaps. Keep machine-specific model inventories out of this package.

Users can ask: “Show this project's effective delegation policy, eligible local
models and assessed limits, native fallback, and which controls were actually
tested.” Answer from current evidence, marking missing information unknown.
During work, distinguish selected route/model, waiting, verification and completion.
For local status and visibility, follow the plugin's current workflow; missing
evidence means unknown.

## Native Codex delegation contract

Use native subagents with the active client's provider, authentication and
permissions. Inherit the coordinator's model and reasoning unless the user
authorizes task-based worker selection or a scoped capability choice. Under the
selection policy above, choose explicit supported worker settings; the Coordinator
remains unchanged. The cleanup profile below remains independently bounded.
Before dispatch, the coordinator creates a plain JSON declaration
at the active harness root's `.codex-delegations/<task_name>.json`. This directory
is beside
`.codex`, outside the protected configuration directory. `task_name` must contain
1–64 lowercase ASCII letters, digits or underscores and match the native spawn's
`task_name` exactly. Formats without that visible field are explicitly unsupported
and denied; the hook does not fall back to interpreting the message.

The hook validates declaration structure only. It does not inspect, decrypt or
rewrite the native message. A valid file does **not** prove that its content
matches the message, that the child can identify itself or that the worker read
or followed the declaration. The coordinator must check those conditions.
`SubagentStart` instructs the worker to require one exact coordinator-supplied
declaration pointer in its native task message: harness-root-relative
`.codex-delegations/<task_name>.json`, where the name matches `[a-z0-9_]{1,64}`.
The worker reads that record and compares objective, writable scope, dependencies
and checks with the assigned task. A missing, ambiguous, unsafe, unreadable or
inconsistent pointer/record means `blocked` without task work.

When trusted host metadata exposes the worker's native task identity, compare it
with the record. For canonical `/root/reader`, use final component `reader`;
a mismatch blocks work. Some isolated children do not receive caller-bound
identity metadata. When it is unavailable, do not fabricate identity from freeform
text: continue only the authorized declared scope and report
`native identity binding unverified` in the existing `risks` field. The explicit
pointer is a coordinator task instruction, not identity attestation. The
coordinator independently checks the actual native spawn name, exact declaration,
observed read and resulting diff. Missing host identity alone is not a new task gate.
Actual behavior still requires a real client fixture.

## Prepare each dispatch

1. Identify the active harness root that owns the executing
   `.codex/hooks/subagents.py`. Create its ordinary `.codex-delegations` directory
   beside `.codex`; do not use a symlink. This can be a non-Git coordination root
   above the software repository, rather than that repository's Git root.
2. Choose a native task name, such as `parser_fix`. Write the complete declaration
   below into `.codex-delegations/parser_fix.json` as **raw JSON**, without Markdown
   fences. Assign its role and specialty; keep the task name as the unique task
   identity. Finish writing before dispatch; keep it unchanged until the worker ends.
3. Prepare the native tool arguments before calling it. `task_name` is a required
   top-level argument, even if the client's tool schema makes it optional. A name
   in the message or declaration filename does not supply this argument. Its task message
   must name the harness root and include exactly one declaration pointer, for example:
   `Harness root: <absolute harness root>. Read .codex-delegations/parser_fix.json before work.`
   Name the software repository and command directory separately. State the base
   of writable/read paths and resource paths in existing `context`/`instructions`.
   Changing directory for software work must not reinterpret the declaration pointer.
   Keep model/provider/authentication and permissions under native control.
4. Verify the actual native spawn name and declaration, the child's observed read,
   and its actual diff/checks/report. Compare trusted child identity when available;
   otherwise retain the explicit unverified-binding risk. A structurally valid
   record or report is not evidence of successful work.
   Retain the native child ID, parent/task binding and inherited worktree attachment
   in existing private task evidence for later native cleanup; names and cwd alone
   do not establish ownership.

Use this required argument shape, replacing the example name and root together:

```json
{
  "task_name": "parser_fix",
  "message": "Harness root: /absolute/harness. Read .codex-delegations/parser_fix.json before work."
}
```

Before the first tool call, check the actual argument object: its top-level
`task_name` matches `[a-z0-9_]{1,64}`, the declaration filename and the one pointer
in `message`; the declaration is complete and readable under the active harness
root. Inspect the current native tool schema before adding client-specific fields.
If that tool cannot carry `task_name`, report an unsupported dispatch format without
trying it. For inherited execution, omit model, reasoning and profile overrides.
These are coordinator checks; the existing hook remains the independent guard.

For a single-attempt qualification, a rejected tool call consumes the attempt even
when no child starts. Record the denial and stop that run. A later authorized run
gets a fresh declaration and separate evidence; do not turn a retry into a pass.
Report required role, specialty and directory observations inside `summary` or
`checks`, using only the seven report fields below. Additional fields such as
`observed` invalidate the report.

The coordinator owns these transient inputs, avoids task-name reuse between
active workers and excludes them from publication using the setup recipe.
The hook does not write, consume or delete records, track timestamps or freshness,
create a ledger or schedule retries. Old valid records can still pass validation;
the coordinator remains responsible for their relevance and cleanup. Do not place
credentials or secrets in declarations.

For an umbrella guard at `workspace/.codex/hooks/subagents.py`, a service task reads
`workspace/.codex-delegations/name.json`, while software checks run in
`workspace/service`. Declare paths such as `service/src/parser.py` as relative to
the harness root. A standalone service guard instead uses
`workspace/service/.codex-delegations/name.json`. Inspect the client's active hook
sources if both guards might load; matching hooks accumulate. Do not mirror records
or fall back to another declaration root. The examples below assume the software
repository and harness root coincide, with all paths relative to that root.

A writer's `.codex-delegations/parser_fix.json`:

```json
{
  "role": "Builder",
  "specialty": "Implementation",
  "objective": "Fix the parser's empty-list regression.",
  "context": "Read src/parser.py and tests/test_parser.py. Empty lists currently fail.",
  "instructions": "Read local instructions. Preserve other input handling and unrelated edits.",
  "allowed_files": ["src/parser.py", "tests/test_parser.py"],
  "mutable_resources": [],
  "dependencies": [],
  "acceptance": ["Empty lists parse; existing validation remains intact."],
  "checks": ["python3 -m unittest discover -s tests"],
  "read_only": false,
  "budget": {"minutes": 15, "attempts": 2}
}
```

An independent reader's `.codex-delegations/parser_review.json` for native
`task_name: "parser_review"`:

```json
{
  "role": "Reviewer",
  "specialty": "Code review",
  "objective": "Review the parser change for regressions.",
  "context": "Read the working diff, src/parser.py and tests/test_parser.py.",
  "instructions": "Read local instructions. Report actionable findings with locations; make no writes. Avoid checks that create artifacts.",
  "allowed_files": [],
  "mutable_resources": [],
  "dependencies": ["The writer has stopped and supplied its exact revision or diff."],
  "acceptance": ["Review connected callers, validation, tests and semantic documentation impact."],
  "checks": ["Inspect the changed branch and relevant callers; report evidence and any checks not run."],
  "read_only": true,
  "budget": {"minutes": 10, "attempts": 1}
}
```

## Lightweight cleanup worker

After confirmed merge or recorded supersession, queued cleanup runs directly in
Python over every eligible pending retirement handoff in the same Git repository.
Startup never runs cleanup. Do not spawn a worker, model turn, timer or poll for
that queue pass. Unsupported managed removals remain pending for their native owner.
The profile below applies only when cleanup delegation is separately needed.

Terminal-task cleanup must remain inexpensive. When delegating, use one bounded native worker on a
lightweight compatible model available in the current authenticated client.
Choose from the host's supported models and reasoning settings; do not hard-code
a model family or version. Keep the coordinator's model/settings unchanged. Never
add a provider, proxy, API billing path or credentials to obtain a cheaper model.
If no suitable native choice is available, report the limitation and offer the
helper's manual invocation; do not silently upgrade to an expensive worker.

Python performs the factual safety checks and ordered deletions. The worker runs
one lifecycle `cleanup` invocation from outside the target worktree, using its
existing task ID and a fresh report of worktree ownership and stopped writers.
An existing event ID can still use `resume`. The helper confirms merged PRs or
recorded supersession, checks ownership and heads, and applies independent default-ON
`delete_remote_branches` / `delete_worktrees` options. It deletes eligible remote
refs before local removal when both actions are enabled; either option may be
opted out independently. Closed-unmerged PRs retain remote branches and worktrees unless explicitly
superseded. Local refs remain as the recovery copy. Native worktrees return an
owner action; the coordinator first follows `native_action.preflight` in the installed
helper's `task-lifecycle.md`. Only verified completed task children with inherited
attachments may be archived; running, unfinished or uncertain children stay intact.
The coordinator performs the owner action and a bounded follow-up
`cleanup` verifies path and Git-registration absence. Queued archives stay pending.
The worker must never substitute its own recursive deletion, force push, stale
receipt or approval assertion.

Declare a three-minute, one-attempt budget. Scope writable resources to the exact
task and eligible queued retirement handoffs within the same Git common directory,
their recorded remote refs and lifecycle records;
use `read_only=false` because cleanup has authorized mutations. Keep unmarked, active, foreign and ambiguously owned resources, the primary
checkout and local branch refs outside that scope. Respect
`delete_remote_branches=false`, `delete_worktrees=false`, the legacy
`auto_cleanup=false` master opt-out and whole-lifecycle opt-out before deletion.

Do not inspect the codebase, rerun project tests/builds, repeat independent review,
spawn other workers, poll GitHub or create a recurring task for cleanup. Trigger
only when reconciliation confirms merge or recorded supersession, including after
a human report of that transition. Each closure visits all eligible queued retirement
handoffs in that repository once and reports `pending_cleanup.tasks`. Startup never
runs cleanup; it only cancels retirement before checkout reuse. On a pending result, report the precise manual
action and stop; retry only after new evidence or the requested action. Completed cleanup uses its recorded
result and does not start another worker merely to recheck unchanged state.

Return the existing compact report schema: observed merged/superseded PR counts, remote refs
confirmed absent, worktree removal status, evidence reference and any pending
action. The coordinator reads that result and the bounded helper evidence; it does
not repeat the full cleanup investigation with a larger model. These are workflow
instructions, not hook-enforced model routing or proof of host ownership.

## Declaration schema

The object requires all fields shown except `role` and `specialty`, which are
optional for compatibility with existing declarations. New assignments should
include both. When present, `role` is one exact name from the role table and
`specialty` is a nonblank string of at most 4,096 characters. Either may be omitted
independently. Unknown keys remain rejected; neither field changes native input,
write scope, required checks or report validation. The guard validates their
structure only, not assignment truth, model ability or dashboard delivery.

Duplicate keys, comments, non-finite numbers, unknown fields and trailing commas
are rejected. `objective`,
`context` and `instructions` are nonblank strings. `allowed_files`,
`mutable_resources`, `dependencies`, `acceptance` and `checks` are string arrays;
only `acceptance` and `checks` must be nonempty. All strings have at most 4,096
characters; each array has at most 64 entries. The file is at most 128 KiB.

`allowed_files` means **writable** files; read inputs belong in `context` or
`instructions`. `mutable_resources` names other owned writable resources, such
as a disposable service or port. Keep ownership disjoint; the coordinator owns
shared configuration, lockfiles and integration. `read_only` is a JSON boolean:
`true` requires both writable arrays empty; `false` requires at least one writable
file or resource. These declarations are instructions, not access controls;
contradictory prose and actual writes require coordinator review.

`budget` contains exactly integer `minutes` (1–120) and integer `attempts` (1–5).
Booleans and fractions do not count. These are declared guardrail bounds, not a
wall-clock or attempt scheduler; the worker and coordinator must honor them.

## Final report

The final message contains exactly one standalone, unindented JSON fence tagged
`delegation-report` or `json`. Both tags use the same exact schema and limits.
Multiple accepted fences, including one of each tag, are ambiguous and rejected;
plain unfenced JSON is not accepted. Examples inside outer backtick or tilde
fences do not count. The object
has exactly `status`, `summary`, `changed_files`, `checks`, `risks`, `blockers`
and `next_action`. `status` is `done`, `blocked` or `needs_context`;
`summary` and `next_action` are nonblank strings. Other fields are string arrays
using the declaration's entry and string limits. Only `checks` must be nonempty:
record each command/procedure, actual result and evidence, or say it was not run
and why. Empty arrays mean none. A blocked report is valid:

```delegation-report
{
  "status": "blocked",
  "summary": "The coordinator supplied no exact declaration pointer.",
  "changed_files": [],
  "checks": ["Declaration read: not performed; no exact pointer was supplied. No task work performed."],
  "risks": ["Native identity binding unverified."],
  "blockers": ["Missing explicit declaration pointer."],
  "next_action": "Coordinator supplies the exact safe harness-root-relative record path."
}
```

## Hook behavior and limits

Merge supplied `.codex/hooks.json` entries without replacing existing hooks.
Copy `.codex/hooks/subagents.py` into the project and this contract to
`.codex/delegation-brief.md`. The commands use Python 3.11+ as `python3` and a
quoted Git-root path, supporting starts inside subdirectories. Explicit non-Git
installation uses the quoted absolute script path for that harness root, including
when its command runs from a nested child Git repository. The safe reader
requires POSIX directory-relative opens, `O_NOFOLLOW`, `O_DIRECTORY` and
`O_NONBLOCK`; unsupported platforms are denied. The declaration directory and
leaf file cannot be symlinks; nonregular files, including FIFOs, are denied
without waiting for a writer. Declaration paths derive from the executing script's
own harness root, not the software Git root, payload `cwd` or session working directory.

Review and trust hook definitions through the client's supported UI; never
write trust hashes. Changed definitions may require renewed trust. Roll back by
removing only these three entries and their unused script/contract, preserving
other hooks. Handle transient declarations separately; see the setup recipe.

- `PreToolUse` matches complete names `spawn_agent`, `Agent`,
  `collaboration.spawn_agent`, `collaborationspawn_agent`,
  `multi_agent_v1spawn_agent` and `multi_agent_v2spawn_agent`. Configuration and
  handler use the same anchored pattern. Canonical/compatibility names follow
  official source; defensive flattened variants reflect namespace concatenation.
  These names alone do not prove actual host interception. Unrelated suffix
  names are ignored. The hook validates the visible `tool_input.task_name` and
  its declaration. Missing, unreadable, oversized, malformed or contradictory
  declarations produce a fixed supported `permissionDecision: deny` without
  echoing input. Valid declarations emit `{}`. It never approves permissions,
  inspects the native message, rewrites input or changes model/provider/auth.
- `SubagentStart` supplies the pointer/read procedure and final-report instructions
  through supported `additionalContext`. It cannot veto a start, inspect/decrypt
  the task message or establish identity binding. Missing host identity requires
  an explicit unverified-binding report, while a bad declaration pointer blocks work.
- `SubagentStop` checks the final report's structure only. An invalid report
  in either accepted fence with `stop_hook_active: false` requests one correction
  via `decision: block`.
  A subsequent `true` flag always emits `{}`; missing or invalid retry flags also
  emit `{}` to avoid loops. No transcript is read or claim verified.

Stdin and the declaration file each have a 128 KiB limit plus one detection byte.
Malformed configured PreToolUse input is denied. Start/Stop parse failures,
oversized input, non-object payloads and missing/non-string event names emit
`{}`. Full host envelopes are not validated: an object naming Start receives
context; Stop with an explicit false retry flag requests correction if needed.
Unknown events and unrelated tools are no-ops. The handler performs only bounded
input reads and the named declaration read: no network, subprocesses, transcript
reads, state writes or raw input logging. Hook commands resolve Git root without
changing Git state. Their three-second timeout depends on host enforcement.
Interpreter/startup failures, skipped/untrusted hooks, unsupported paths and host
errors may leave the tool unguarded. This is **not globally fail-closed**.

From the template root, run:

```sh
python3 -m unittest discover -s tests -p test_subagents.py -v
```

Tests use disposable projects and three-second subprocess timeouts. They cover
missing/invalid declarations, strict JSON/schema, bounds, traversal, symlinks,
nonregular files/FIFOs, opaque-message preservation, readers/writers, unrelated
tools, both report tags, ambiguous fences and Start/Stop behavior. They establish
local guard behavior, not actual
CLI/Desktop interception, native child identity, message binding, worker reading,
result truth, sandbox enforcement or host failure semantics. Those conditions
need separate real-client fixtures before claiming enforcement or completion.
