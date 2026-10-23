---
name: setup
description: Use when onboarding, resuming setup, explicitly approving local model use, updating or removing the Local Model Delegation plugin on macOS.
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
4. **Select a project and assess if requested.** Installation and connection may precede project selection. Assessment and new project qualification require the owner's selected repository and inspection permission. Reuse matching project evidence from a supplied assessment ID; generic 100% results or another repository's results do not qualify this project. Use **local-model-delegation:assess-my-model** and its [project campaign procedure](../assess-my-model/references/operations.md#project-campaigns-default). Ground every task in actual project work, default eight per selected specialty. Never repeat completed generations because the entry point changed. Confirm workload frequencies before estimating the fraction of usual tasks; otherwise report coverage as unknown.
5. **Approve for this project, then activate.** Explain the demonstrated role/specialty/difficulty/context and provisional limits. Obtain explicit permission for the exact model/settings and project scope; reuse authorization already granted. Use `profile approve --project PATH --assessment-id ID` with matching evidence. Ordinary tasks still need native verification. Routing activation remains a separate decision. Existing global approvals remain explicitly legacy; never convert, broaden or revoke them automatically. An owner-authorized legacy provisional path retains its prior semantics, not project qualification. A package update cannot approve a model or establish actual client execution.

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
