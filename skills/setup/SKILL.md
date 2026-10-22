---
name: setup
description: Use when onboarding, resuming setup, assessing models, updating or removing the Local Model Delegation plugin on macOS.
---

# Set up Local Model Delegation

Guide the owner from the current verified state to the next decision. Installation, assessment consent, exact-model approval and routing activation are separate decisions.

## Conversation contract

Each progress reply has three parts: **what is verified**, **the next step and why**, and **one question or one manual action if owner input is required**. Wait for that answer before dependent work. Continue authorized checks yourself. Reuse answers and consent already recorded in this session; ask only for missing information. Keep later stages in the background until their turn.

Example after detecting a missing runtime: “The plugin is installed; delegation is off. LM Studio is missing, so there is no local server to connect. Would you like help installing LM Studio now?”

## Follow the current stage

1. **Inspect.** Check macOS, Codex access, Python 3.11+, installed plugin location and existing state before changes. Use the packaged `../../delegate.py`; run read-only `doctor` first. Reuse verified observations. Preserve native model, provider, reasoning and authentication settings. If the plugin is absent, follow the [public onboarding guide](../../docs/onboarding.md) before invoking packaged commands.
2. **Resume or initialize.** Reuse the selected state, endpoint, profiles and visibility preference. Only schema-2 state is supported; reject unsupported state without rewriting it. After authorized installation/setup, initialize missing private state with routing disabled. Read [Setup operations](references/operations.md) before executing this or later stages; it is the required technical procedure.
3. **Connect.** If LM Studio is missing, offer help with that installation as the next decision. If present but stopped, guide one start-server action. Use the recorded endpoint; otherwise ask for the loopback URL shown by LM Studio. Discover read-only and prepare an unapproved profile. Resolve one missing prerequisite at a time.
4. **Assess.** Follow the practical qualification runbook in the operations reference. Start with a few representative tasks at a realistic context budget, one slot and native verification. Reuse explicit consent; keep synthetic assessment consent separate. Report observed scope, failures and unknowns.
5. **Approve, then activate.** Explicit owner permission permits a bounded provisional scope even when reliability and savings remain under assessment. Explain that limit and ask the owner to approve the exact model/settings and operating scope. Reuse explicit approval already granted. Routing activation is a separate decision; reuse it when already authorized. Verify both gates independently; a local task is verified only when its execution and native acceptance were observed. Do not fabricate benefit evidence to activate a model.

## Pauses and common mistakes

| Observed condition | Next action |
|---|---|
| Native plugin installation unavailable | Give one supported manual installation action; wait for completion |
| Existing setup | Resume its first unfinished stage; preserve preferences and the selected queue |
| Runtime or model unavailable | Name the blocker and one next action; keep affected work pending |
| Assessment declined | Preserve configuration and stop assessment-dependent work; do not ask again or schedule trials |

At completion or a pause, report **verified**, **pending/blocked**, **routing state**, and **resume step**. A saved setup is not operational delegation. “Resume Local Model Delegation setup” resumes from the saved checkpoint.

For updates, follow the [guided update procedure](../../docs/updating.md), including release staging, private backup, native installation, verification and restoration of saved routing/publishing preferences. An update request includes restoring previously enabled preferences after successful verification; disabled preferences and explicit requests to remain paused stay off. For removal, follow [Setup operations](references/operations.md) before native plugin controls.

Fresh authorized setup also initializes private measurement tables. Existing installations use `metrics init` after authorized update; see [measurements](../local-delegation/references/measurements.md). Reports and comparison registrations do not approve models, authorize extra inference, or enable routing. Missing native telemetry means savings remain unknown.


## Optional Habblaud appearance

When the owner requests this integration, read
[the visibility guide](../local-delegation/references/visibility.md) for the exact
commands, metadata handoff and limitations. Reuse `habblaud status` and saved
settings; do not enable hooks merely because Habblaud or Vibe Setup is installed.
Habblaud stays unchanged. Vibe Setup owns assignment role/specialty policy; this
plugin owns context storage, transport and observation. Setup for appearance never
approves a model, activates routing or changes native authentication/settings.
