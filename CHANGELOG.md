# Changelog

## 0.3.9

- Correct the guided update workflow to record routing and Habblaud preferences before pausing, restore previously enabled preferences after successful verification, and read back the final state.
- Preserve disabled preferences and explicit pause requests; failed updates remain paused. Runtime verification gates and model approvals are unchanged.
- Give new native fallbacks readable, collision-safe task names, with an optional coordinator-supplied name and preserved recovery identity. Use task and actual model labels in local progress; Habblaud badges are unchanged.
- Settle returned native fallbacks rejected for changed source as failed, preserving the rejection reason and preventing completed work from remaining active during update checks.

## 0.3.8

- Fix automatic Habblaud observer startup from detached workers by reusing the validated immutable runtime bundle.
- Start newly submitted jobs with the installed helper after an update, while existing jobs and recovery retain their recorded runtime pins.
- Add an end-to-end regression covering a real detached worker, an older loaded-instance bundle, one model request and automatic hook delivery.

## 0.3.7

- Show real local attempts beneath their coordinator in unchanged Habblaud through its existing hooks, for local npm and Docker deployments.
- Display the assignment role and actual model display name, preserve specialty metadata, and report generation, verification and terminal phases without changing execution or acceptance.
- Add opt-in enable/status/bind/resume/disable controls, bounded loopback transport, stable display identities, restart recovery and observer cleanup during updates.
- Preserve running job identity when duplicate presentation context conflicts; retain all published 0.3.6 generation-budget behavior.
- Document inherited Codex icons, clipped badges, unavailable local model Stats and completion/statistics limitations.

## 0.3.6

- Let the coordinator select a positive per-task generation allowance within the model's approved ceiling. Admission and the HTTP request use that allowance, including reasoning tokens, with runtime context checks before POST.
- Add explicit `profile approve --max-output-tokens` support. Ceiling changes preserve assessment history and wait for occupied instances before refreshing idle approval metadata; loading permission remains bound to the approval.
- Complete budget-exhausted attempts only after validating terminal identity, token metadata, output and generation. Request native fallback without accepting truncated output or closing healthy slots. Missing or malformed terminal evidence remains uncertain.
- Record effective request settings and terminal exhaustion evidence. Measurement cohorts distinguish the actual generation allowance; historical attempts and outcomes remain unchanged.

## 0.3.5

- Add owner-authorized external reset reconciliation with one unload request, verified absence, generation fencing and preserved failed outcomes/history.
- Add separately permitted HTTP loading for approved models, exact context/one-slot verification, endpoint reservations and read-only reconciliation after ambiguous responses.
- Let ordinary routing load permitted models before inference; preserve LM Studio guardrails and defer when peers or unresolved operations exist.
- Let verified retired generations pass update preparation without accepting unsupported retirement flags.

## 0.3.4 (unreleased)

- Link Vibe Setup's delegation policy and native contract from agent and user documentation. Use installed-version instructions and preserve local approval, verification and fallback controls.
- Documentation-only local update on top of 0.3.3; runtime code and private state are unchanged.

## 0.3.3 (unreleased)

- Refresh an idle instance's approval metadata after assessment or an authorized scope change when fresh discovery confirms identical runtime/artifact/settings/configuration. Preserve occupied and uncertain slots, recovery markers and lifecycle reservations.
- Preserve never-submitted queued jobs during a disabled, idle plugin update. Uninstall remains stricter; active, uncertain and recovery work still blocks updates.

## 0.3.2 (unreleased)

- Separate explicit provisional operating budgets from observed fixture sizes. Add `profile approve` for owner-authorized practical scopes without inventing qualification or savings evidence.
- Default loaded-model admission to one shared slot. Replace free-memory and zero-swap vetoes with fresh pressure checks; warning is advisory and critical/unknown readings defer admission.
- Check full supplied prompt, output allowance and conservative template headroom against runtime context before reserving and before POST.
- Simplify onboarding around a few representative project tasks with native verification and fallback; retain optional synthetic experiments and historical evidence.

## 0.3.1 (unreleased)

- Remove the circular savings prerequisite from exact-model approval and scheduling. Verified capability, capacity, owner approval and scope remain required; unknown savings stay unknown while ordinary authorized work supplies evidence.
- Prefer matching measured benefit when available and retain the existing block on known negative benefit and suspended scopes.
- Fall back before POST when every eligible runtime is unavailable or unloaded; healthy occupied runtimes still wait without disrupting peers.
- Clarify how local proposals inherit the coordinator's project and skill constraints, including Vibe Setup, without impersonating native subagents or bypassing native fallback policy.

## 0.3.0

- Add numbered release archives, immutable version/tag checks and package fingerprints.
- Add guided updates with private backups, idle-state checks and installed-package/state verification.
- Add an update prompt directly below the README setup prompt.
- Add per-project reliability and attributable native-token measurement records and reports. Missing usage or comparable baselines still means unknown savings.
- Remove obsolete directory discovery, capability and worker aliases, schema-1 configuration/profile/brief support, schema conversion and obsolete recovery paths. Current schema-2 state remains intact; unsupported state is rejected without conversion.
- Preserve routing, exact approvals and historical evidence through updates. No automatic model lifecycle or routing activation is added.

## 0.2.0

Development preview with shared delegation state, synthetic assessments, protected verification, native fallback reconciliation and guided onboarding. Earlier preview source changes reused this version; 0.3.0 starts immutable numbered releases.
