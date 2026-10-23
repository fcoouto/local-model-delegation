---
name: assess-my-model
description: Use when the owner wants to assess a local text model's abilities, resume a specific assessment, or interpret its saved assessment report on macOS.
---

# Assess my Model

Assess an already downloaded and loaded text model without onboarding it. Save a private unapproved profile and evidence. Preserve existing approvals, native settings, visibility and routing.

Read [Assessment operations](references/operations.md) before execution. Reuse the named [Setup operations](../setup/references/operations.md) sections for prerequisites, state, connection and profile preparation; do not duplicate those procedures. Missing prerequisites mean one concrete next step, not automatic Setup, installation, downloading or loading.

1. **Choose a focused ability.** Reuse the owner's choice; otherwise offer the supported focused abilities and an explicit **All supported abilities** option. Derive supported groups and counts from `assessment choices`. Never silently reduce an all-abilities request when one group is unavailable.
2. **Prepare and preview.** Identify the exact model and settings, selected coverage, synthetic context, output allowance, case/trial counts, one-slot execution and native checks. Explain that this saves evidence without approval or routing changes. Do not promise an elapsed time.
3. **Obtain consent for this run.** Record the actual owner authorization for its frozen preview. Standing assessment permission is insufficient. Reuse consent already explicit in this conversation only when it covers every preview dimension; ask only for what is missing. Never infer consent from a deadline, earlier runs or a passing result. Declining means no generation and no repeated consent request.
4. **Execute or resume the same run.** Coordinate one trial at a time through the existing queue and native verification. Reconcile saved work before continuing. Never repeat a completed, failed or possibly submitted trial. A pause requires explicit resume; stop is terminal. Submitted work remains observable and verifiable. Safety or uncertainty blocks further progress; do not use native fallback to solve a trial.
5. **Report and stop.** Show passed/evaluated alongside planned and unfinished counts, failure reasons, evidence limits and independent approval/routing state. A report request is offline by default. Do not start onboarding after success, explanation or export requests.

Only an explicit request such as **“onboard this model”** hands the selected profile/run and evidence limits to **local-model-delegation:setup**. Read Setup's skill before continuing the handoff. It reuses valid evidence and asks one missing decision at a time: operating scope first, then routing activation. Do not ask the owner to onboard merely because an assessment finished.
