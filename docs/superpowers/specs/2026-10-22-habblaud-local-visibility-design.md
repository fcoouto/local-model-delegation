# Habblaud local delegation visibility through existing hooks

Date: 2026-10-22

Status: **Adapter implemented and verified: 286 plugin tests passed, including 31 adapter tests; final Role · Model Display Name badges passed isolated Docker/npm browser checks. Both Important review findings fixed with regression tests. Not installed or enabled in the live setup.**

Owner decision: show local work as a character under its coordinator, use Habblaud's existing hooks, and leave Habblaud unchanged. The later owner instruction in the coordinated Vibe chat supersedes the original composite label: the local badge uses exactly Role · Model Display Name, without LOCAL. Specialty stays separate assignment metadata, and missing local Stats → Model is accepted. This replaces the earlier file-reader and UI-change proposal.

## Outcome and ownership

Local Model Delegation translates real local attempt observations into Habblaud's existing Codex hook events. A child badge carries the assignment role and saved local model display name. Specialty stays in assignment metadata and actual local model identity remains in plugin status; unchanged Habblaud hooks cannot populate Stats → Model. The plugin remains authoritative for execution, uncertainty, verification and acceptance.

This chat owns `local-model-delegation`. The **Assess Habblaud agent roles** chat (`01a16391-ad85-72c0-a50c-ade0215b32df`) owns Vibe Setup's role policy, declaration guard and setup instructions. Its proposed contract has been read and coordinated; no Vibe Setup files are changed here. Habblaud source, native hooks, accounts and deployment configuration remain unchanged.

The feature ships with the plugin and targets compatible Habblaud installations using npm or a locally published Docker port. It needs no personal fork, custom image, export mount, new Habblaud endpoint or fabricated Codex rollouts. This is compatibility with a tested interface, not a guarantee for every version or remote topology.

## Approaches and feasibility

| Approach | Benefit | Tradeoff | Decision |
| --- | --- | --- | --- |
| Habblaud reads the existing JSON export | Could support exact identity and neutral failure states | Habblaud changes, distribution and Docker mounts | Superseded |
| Extend the hook protocol upstream | Could provide accurate provider and lifecycle semantics | Requires upstream changes and version coordination | Outside scope |
| Plugin uses existing Codex hooks | Works with unchanged Habblaud in npm and Docker | Native provider, completion and statistics semantics remain | **Selected by the owner** |

**Feasible for appearance and descriptive activity. Unchanged Habblaud cannot provide a separate local provider badge or trustworthy success/failure semantics.** These limits are part of this design, not future implementation promises.

## How Habblaud identifies the child

`POST /api/codex/events` accepts account selection and an `event` object. For `SubagentStart`, `session_id` identifies the coordinator and `agent_id` identifies the child. Both must be valid thread-shaped UUIDs. Habblaud keys records by account and UUID and attaches the child to the root. It can create both records from hooks without a child transcript or lock file.

The first `agent_type` becomes the child's role label. Habblaud assigns character name/art and inherits the parent's Codex account/provider and room. A hook `model` field is ignored. The main-agent badge remains `Main`/`Principal`; this integration cannot rename it to Coordinator.

The first visible role is sticky. Send the full label on the first attempt event. Later role hooks or rollout metadata do not reliably relabel a visible child. Use activity events for phases.

The HTTP handler retains local Host, JSON and Origin checks. npm requires a local socket; Docker mode permits the host-published gateway path. `200 {"ok":false}` means rejection. Check HTTP status and response body.

Source references at Habblaud `faa1a012b5fbf632c66dc6801c5383e53a542406`:

- `server/codex/http.ts`, `server/http/app.ts`: envelope, account mapping and local HTTP boundary.
- `server/sources/codex/source.ts`: UUID validation, tracking, parent linkage, first role, expiry and lifecycle.
- `server/model/office.ts`: inherited account/provider and completion activity.
- `client/src/ui/widgets.ts`, `rows.ts`: role, hover and accessible text.
- `client/src/world/sim/behavior.ts`, `sim.ts`: completion animation.
- `server/history/daystats.ts`, `server/world/uplink.ts`: statistics and World projection.

## Role, specialty and model

Consume the assignment's explicit Vibe metadata:

```json
{"role":"Reviewer","specialty":"Security-sensitive work"}
```

Canonical case-sensitive roles: `Coordinator`, `Scout`, `Builder`, `Tester`, `Reviewer`, `Scribe`, `Investigator`. Role describes responsibility; specialty describes knowledge and checklist. They are independently optional for legacy assignments. New assignments supply both. A specialty can belong to several roles: do not infer role from specialty, model, capability or task name.

Carry the same declared pair through local execution and native fallback. Metadata never changes model, provider, reasoning, routing, permissions or acceptance. Native fallback appears through Habblaud's native ingestion; the adapter creates no synthetic native replacement.

Final label:

```text
Reviewer · Qwen3.8 27B Splash
```

The local badge uses exactly `Role · Model Display Name`, without LOCAL. Use the saved
local profile's `display_name` when present; otherwise split the actual `model_id` on
hyphens/underscores/whitespace, capitalize each token's first character and uppercase
a trailing numeric `b`. Preserve all other identifier content. Thus
`qwen3.8-27b-splash` becomes `Qwen3.8 27B Splash`. Clean display whitespace/control
characters only. This does not change the saved model ID or permit caller-selected
model claims. Specialty remains stored separately. Missing role uses display-only
`Unspecified role`, never inferred or stored as canonical metadata. The first
observer binding freezes assignment labels before any network attempt. Habblaud may
visually ellipsize the badge; full text remains accessible.

Retain the saved local profile after fallback and expose its actual model ID through
plugin status. Habblaud's existing Stats → Model reads `AgentInfo.model`, populated
for Codex by parsed native rollout context. Hook events ignore `model`, and no
supported Codex model-update HTTP route was found. Do not fabricate rollouts or
promise Stats model delivery. The owner accepted this gap while Habblaud remains
unchanged. Vibe Setup owns native declaration formatting and role/specialty policy.

Habblaud rejects `agent_type` containing `guardian`, case-insensitively. Report an incompatible composite label as unsupported rather than silently claiming delivery or claiming unsupported label delivery. Include receiver constraints in the compatibility check.

Vibe Setup explicitly configures role/specialty when preparing assignments. For current strict schema-2 briefs, its documented fallback places labels in `behavior_contract` before submission. These are task instructions, not structured presentation metadata. The adapter consumes a separate explicit pair through its supported interface; it never guesses by parsing prose.

## Plugin boundary and interface

Keep hook publishing separate from the existing JSON export, which remains unchanged and is not read by Habblaud. Publishing defaults off until configured/enabled. The existing global visibility-off preference also suppresses hooks; enabling Habblaud does not override it. Publishing never enables routing or model assessment.

Reuse plugin config, private storage, bounded input reads, atomic writes, detached launcher and ownership locks. Add one small transport module using the Python standard library. No dependency or machine-wide service is required.

Proposed operations, with exact command spelling left to implementation:

- Configure/enable one loopback endpoint and exact Codex account mapping per plugin state directory; provide status/disable.
- Accept optional `submit --visibility-context FILE`, analogous to measurement context. Store it before scheduling can start a worker.
- Bind an existing job to its current coordinator through a presentation operation; never resubmit the job or start inference.

Context contains `coordinator_chat_id` and optional `role`/`specialty`. Validate UUID, exact vocabulary, and nonblank specialty of at most 4,096 characters. Reject unknown keys. Derive actual model/provider from the attempt rather than accepting caller claims. Apply existing bounded file-read discipline and private permissions.

Persist context outside the brief hash/idempotency key. Preserve `origin_chat_id`, `task_key`, brief contents and acceptance evidence. Resuming in another chat changes only presentation binding. Freeze assignment labels at the first observer binding; conflicting later metadata produces a diagnostic rather than a claimed relabel. Visibility failure after submission returns the real job result with a diagnostic, never a false submission failure that encourages duplicates.

Persist a synthetic UUID per attempt and coordinator/account binding. It is a display identity, not a genuine spawned Codex thread. Repeated events use that ID. Habblaud cannot reliably reparent an existing tracker: retire the old display entry and allocate a new binding ID on explicit rebind. The old entry may remain during its normal departure grace. Preserve the underlying attempt identity separately.

Validate account selection against Habblaud's reported accounts. Never rely on its single-account fallback or guess from room/model. Default the coordinator to `origin_chat_id` only when it is a valid native UUID; otherwise require explicit binding. Hooks may materialize the explicitly bound parent without its transcript and refresh parent presence. That display does not prove a native coordinator process is alive.

## Observation and lifecycle

Use an optional job-scoped detached observer through the existing launcher/ownership pattern. Read that job and its original attempt directly, not the capped terminal-history JSON export. The observer cannot reconcile jobs, free slots, abort requests, dispatch fallback or run checks. No network request runs inside a database transaction or inference's progress monitor.

Start when a real attempt reaches `submitting`, after execution preconditions pass. Queued or merely reserved work creates no character. Read approximately once a second and emit activity on a changed observed phase; short phases may be missed. Refresh every 20 seconds while a supported local phase remains observable, below Habblaud's 60-second presence lifetime. Refresh is display presence, never progress evidence or an execution timestamp update.

| Plugin evidence | Hook behavior | Meaning and limit |
| --- | --- | --- |
| No started local attempt | No child | No fabricated worker |
| Submitting/streaming with valid execution observation | `SubagentStart`, descriptive `PreToolUse` | Starting/generating; fixed role/model display badge |
| Candidate ready or checking that candidate | Descriptive `PreToolUse` | `Awaiting verification`; generic Habblaud working state remains |
| Same observed phase | `SessionStart` with parent and child UUIDs | Refresh without repeated activity |
| Local candidate accepted | Verified activity, then `SubagentStop` | Acceptance evidence comes from the plugin |
| Failure, uncertainty, stale execution evidence, reassessment or fallback | Best-effort outcome activity, then `SubagentStop`; exit observer | Habblaud still uses completion appearance; plugin retains true outcome |
| Disable or observer loss | Stop on controlled exit; otherwise expiry | May look completed without confirmed task completion |

Use descriptive synthetic tool names such as `Generating` and `Awaiting verification`, with no command/tool payload. The tested UI renders `Using Generating`. This is presentation translation, not an executed Codex tool. Never send fake permission requests or claim native tool counts. Use child `SubagentStop`, never `SessionEnd`, which can close the parent.

Generation freshness follows existing attempt progress/stale tolerance, not publisher heartbeat. Candidate-ready/checking means verification is pending, not inference running; retain that explicit phase until the job advances or visibility is disabled. Unknown local attempt state overrides overall native success. Read the saved local profile even after fallback changes the effective route and the existing export's displayed model.

Terminal observations end the observer. Status/bind/resume may restart a missing observer for relevant local work without replaying historical terminal work. Reuse the display ID across receiver restarts. Do not repeatedly send `SubagentStart` after successful registration: resend only when the snapshot lacks the live entry or after confirmed receiver restart, then restore the observed phase.

Failed/slow requests record a compact diagnostic and leave work unchanged. Bounds: two seconds total per request, including slow headers and body, no redirects, bounded responses, retries with backoff capped at 20 seconds. Accept only loopback HTTP in this first version. Remote hosts, proxies, credentials and TLS deployment are outside scope. Forward no prompts, code, candidate text, raw errors, tokens, transcripts or secrets. Role/model display names must be non-sensitive labels. The model display name is sent in the hook badge; its original ID remains in private plugin diagnostics. Specialty is retained locally. Document the project path used for room association as metadata shared with Habblaud.

## Limits of unchanged Habblaud

1. Codex provider/account icons and ordinary controls remain. There is no local provider marker in the requested badge format.
2. The event's `model` is ignored. Local Stats → Model remains unavailable; the badge shows its display name and plugin status retains the actual local model ID. Zero token counters are unmeasured, not proof of zero usage.
3. Stop, interrupt, parent closure and expiry lead to `done`/delivery behavior. No neutral removal or accurate failed/unknown terminal state exists. Completion can immediately replace the final descriptive activity; do not depend on that text persisting.
4. Entries can affect agent counts, daily statistics and World projection. Hooks cannot selectively exclude them. Respect the existing World setting; enabling this integration does not change it. Private-only local visibility while World remains on is unsupported by this approach.
5. First roles/parents are sticky. Rebinding creates a new display entry, not a seamless move.
6. Adapter loss or receiver restart can cause disappearance/reappearance. Presence is not execution truth; this is not an audit log.

State these limits in setup/status documentation. If accurate provider/outcome semantics, statistics isolation or selective World exclusion becomes required, reconsider the unchanged-Habblaud constraint separately.

## Docker and npm evidence

Tests used disposable fixture accounts, project/state directories, World/update checks/terminal/messages disabled, no real transcripts and no inference. Live Habblaud and its settings were not changed. Tracked checkout fingerprints matched before/after, including its pre-existing modified `package-lock.json`.

| Check | npm | Docker |
| --- | --- | --- |
| Start unmodified 1.0.3 and ingest HTTP hooks | Passed | Passed |
| Fixture child attached to explicit coordinator | Passed | Passed |
| Requested badge in snapshot, Chromium DOM and accessible label | Passed | Passed |
| Character visible; sidebar clipping inspected | Passed | Passed |
| Duplicate start creates one child | Passed | Passed |
| Generating/awaiting-verification activity | Passed | Passed |
| Invalid UUID gives `200 {ok:false}`; foreign Origin gives `403` | Passed | Passed |
| 20-second refresh survives beyond 60 seconds | Passed | Passed |
| Unrefreshed sibling expires to `done` | Passed | Passed |
| Explicit stop yields `done` and completion activity | Passed | Passed |

npm used `npm run start` against an isolated copy of the installed image's `/app` runtime. Docker used a second disposable container from that image, with only fixture mounts and a random loopback port. This compares deployments on the same binary; it is not a fresh npm install/build test.

- Image: `sha256:715aca50e6664bcd99d8ab2eb0d31aa417997723ceadd8fba7cf75465a6473ff`.
- Compiled server SHA-256: `239499210645d6d6e60c89aed717aeac735cf4d6d9d69a0c7740dd5e2992b450`.
- Runtime build metadata: commit `unknown`, built 2026-10-17. Do not claim it was compiled from the inspected source revision.
- Separately: checkout Codex source/HTTP suites passed 34 tests; plugin visibility/acceptance suites passed 12 tests. The Vibe chat separately tested all seven canonical roles and first-label behavior.

The final adapter run used the public enable/bind/resume/status/disable commands and
its actual detached runtime. Both modes showed `Reviewer · Fictional Model` beneath
the fixture coordinator, exposed the full badge in DOM/accessibility text, avoided
duplicates after repeated resume, showed `Awaiting verification`, stayed present for
66 seconds, and stopped the child after accepted fixture state. Plugin status kept
`fictional-model`; Habblaud's model field remained absent as expected. Browser
screenshots confirmed the existing sidebar clipping. The exact Qwen formatting
example and saved display-name precedence passed unit tests.

Final adapter module SHA-256:
`bff8b7d95d090549d45eb47530d5a4c6ce026189cdb25e4fe07c698ac5cd5d40`.
The full plugin suite passed 286 tests (31 adapter tests). One independent
whole-branch review found two Important defects: slow headers could exceed the
request deadline, and a duplicate context conflict hid a running job's IDs. Both
were reproduced before fixes and passed afterward. Requests now have an absolute
two-second socket deadline; duplicate conflicts preserve the real job envelope and
return `visibility.error: "visibility_context_conflict"`. Documentation scenario
checks verified context, account lookup, display-name source and recovery guidance.

Raw probe scripts, reports, screenshots and logs remain private evaluation evidence outside Git. They contain fixture names and ephemeral ports, not a shipped test framework. Disposable services were stopped after testing.

## Implementation work and gates

1. **Metadata/configuration:** extend plugin CLI/storage/config and test optional context, legacy submissions, immutable identity/hash, account validation and binding IDs. Coordinate the supported interface back to the Vibe owner.
2. **Translation/observer:** add the transport module and reuse launcher/ownership without coupling HTTP to inference. Extend runtime packaging only if its existing file selection requires it. Test labels, incompatible receiver labels, phases, idempotence, stale/uncertain attempts, fallback model retention and concurrent starts.
3. **Recovery/diagnostics:** test observer loss, receiver restart, rebind, disable, offline/slow HTTP and malformed responses. Assert unchanged job state, approvals, reservations, progress, verification and idempotency under transport failures. Update/uninstall must stop only plugin-owned visibility observers.
4. **Docs/release:** update plugin skills and README with enablement, data exposure, status, compatibility limits and rollback. Vibe owns its declarations/installation flow. Run relevant plugin suites and repeat isolated Docker/npm browser checks through the implemented adapter.

Stop once these gates pass. Do not add Habblaud patches, an always-on daemon, new provider types, token estimates, custom art, a roster or routing/fallback control. Rollback disables publishing and removes only plugin-owned presentation configuration/processes; jobs/inference remain intact. Existing entries may remain until Habblaud's departure/expiry grace completes.

The adapter now has production integration, detached-runtime packaging, restart/failure tests and isolated Docker/npm browser evidence. Real local inference and fresh-install npm compatibility were not tested; no live installation/settings were changed. The implementation plan records tests and review gates.
