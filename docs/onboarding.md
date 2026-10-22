# Guided onboarding

This is the public entry point for setting up Local Model Delegation, including before its plugin is installed. The agent does the available work and guides the owner through one decision at a time.

## Instructions for the agent

Follow the stages below using the owner's existing authorization. Each progress reply states what you verified, the next step and why, and one question or one manual action when input is needed. Wait for that input before dependent work; continue independent authorized checks. Reuse information already discovered instead of asking the owner to repeat it.

The owner should not have to assemble commands, fill in profiles or answer a questionnaire about later stages. Keep technical details in your working context and explain decisions in plain language.

### 1. Check what exists

Inspect the host, local file/terminal access, Python version, plugin availability, existing private state and runtime configuration. Current support is Codex on macOS, Python 3.11+ and LM Studio over HTTP on literal `127.0.0.1` or `::1`. Preserve native provider, model, reasoning and authentication settings.

If the host or agent is unsupported, explain that blocker and the next supported action. If local computer access is unavailable, offer instructions and clearly mark checks as unperformed. Do not claim installation from reading this page.

For an installed plugin, locate its packaged setup skill and helper through the host. Resume with that version's [setup skill](../skills/setup/SKILL.md); avoid mixing commands from a newer checkout with an older installed helper. Preserve existing state and preferences. For a newer release, use the [update procedure](updating.md); it explicitly bootstraps update checks from the staged target package.

### 2. Install the plugin if missing

Explain the proposed installation and obtain any missing authorization. Use available native plugin controls and the [official local plugin installation guidance](https://developers.openai.com/plugins/build/plugins#install-a-local-plugin-manually). This development preview is not guaranteed to appear in the public directory.

If a local marketplace is needed, prepare a source checkout and the documented marketplace entry within the authorized scope, preserving existing entries. A clone is source code, not an installed plugin. Use the host's installation controls; do not write directly into plugin caches or substitute standalone skill copies.

When installation requires owner interaction, give the single next action supported by the current host and wait. If no supported installation path is available, report that blocker and a resume step. Do not ask the owner to install the plugin, install LM Studio, choose a model and supply an endpoint together.

Verify that the host discovers the installed setup skill and its packaged helper. Then follow that skill and its required operations reference. A read-only `doctor` check comes before private state initialization; missing Python or failed isolation is a prerequisite to resolve, not a check to bypass.

### 3. Connect the local runtime

If LM Studio is absent, offer help with installation from its [official download](https://lmstudio.ai/download). Obtain authorization before software or model downloads. If it is installed but the server is stopped, guide the owner to **Developer → Start server**, as described in the [server guide](https://lmstudio.ai/docs/developer/core/server).

Reuse an explicit saved endpoint. Otherwise ask for the server URL shown by LM Studio, using its selected port and a supported literal loopback address. Do not guess the port or scan for servers. Keep any authentication requirement; ask for the owner-selected environment-variable name, never a secret value in chat.

The setup skill handles discovery, exact model identity, private profiles and verification. A missing model or unsupported automatic load is a named blocker. Do not use a CLI workaround or change runtime-wide settings to bypass it.

### 4. Let the owner decide at each stage

The setup skill is the source of truth for the remaining procedure:

| Decision | What it authorizes |
|---|---|
| Install and initialize | Make the plugin available and prepare private state |
| Optional standing assessment consent | Run package-owned synthetic assessments; consent is revocable |
| Exact-model approval | Approve the exact model/settings and a bounded provisional operating scope |
| Routing activation | Allow eligible project tasks to use approved local models |

Setup grants none of the later decisions. If the owner declines synthetic assessments, do not run them. Offer the practical representative-task path only if useful; it still needs explicit exact-model provisional approval. Declining all model use leaves new profiles unapproved. Offer a resume step without repeating the consent request. A successful assessment does not authorize activation.

### 5. Verify and hand back a checkpoint

Report four items: **verified**, **pending or blocked**, **routing state**, and **resume step**. Distinguish an installed plugin, a connected server, an assessed model, an approved scope and enabled routing. Claim a successful local task only after observing its execution and native verification.

The owner can paste the README prompt again, or say “Resume Local Model Delegation setup.” Read current state and continue at the first unfinished step. Preserve completed decisions; never create a second active queue to restart onboarding.

The project remains a development preview. Desktop installation and real-model end-to-end qualification are separate from the [simulated onboarding evaluation](onboarding-validation.md); net subscription savings are not established.

## Project measurements

After authorized setup/update, the agent can register project measurement context and record ordinary work without extra inference. Fresh setup initializes the ledger; existing state uses `metrics init`. [Measurement contracts](../skills/local-delegation/references/measurements.md) explain the commands and optional telemetry. Candidate acceptance, destination delivery, and later reported corrections remain distinct. Reports cannot approve a model or enable routing. Additional comparisons need separate bounded consent; missing usage or baselines leaves savings unknown.

See the [practical qualification runbook](qualification.md) for realistic context budgets, one-slot admission and evidence that grows through normal work.
