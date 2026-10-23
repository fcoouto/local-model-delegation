# Setup operations

All helper paths below are relative to `skills/setup/SKILL.md`, not this reference. Read this procedure before running setup, assessment, update or removal commands.

## Inspection and state

Use the packaged `../../delegate.py` with Python 3.11+. Run `doctor` first; runtime inspection requires `doctor --inspect-runtime` and an explicit configured loopback endpoint. Do not scan ports or change native credentials/provider/default settings.

Installation uses native Codex plugin controls. This skill does not install itself. After authorized setup, `setup` initializes private shared state at `~/.local/state/local-model-delegation` with routing disabled and visibility enabled. Only schema-2 state is supported. Preserve explicit custom state selection; never move saved state or silently create another queue. Unsupported state requires a separate owner-reviewed transition, not automatic conversion. Never copy private profiles/evidence into the plugin.

Explain and separate the four decisions: plugin installation, consent for one frozen synthetic-assessment run, one-time approval of an exact model/scope, and routing activation. Setup itself grants none of the later decisions. A dedicated assessment request permits minimal private state initialization when missing, with routing disabled; it does not authorize installation. Visibility can be enabled or disabled independently with `visibility` commands; no viewer is needed.

## Connection

For onboarding, use `discover --endpoint URL` (read-only). Create a private per-model profile with exact artifact inventory, owner-trusted local index, supported request settings, capability candidates and explicit native fallback. Keep approval null and qualification `needs_assessment`. Unsupported identity/protocol information remains ineligible. Tokens use an owner-selected environment-variable name, never literal secret fields.

`discover --endpoint URL` does not accept a token environment-variable argument. When the server requires authentication, retain that requirement: configure the owner-selected `endpoint` and `token_env` in private shared configuration, then use `doctor --inspect-runtime`. Each model profile needs its own authoritative connection fields. Ask for the environment-variable name, never the token value.

## Unapproved profile preparation

Both Setup and Assess my Model use this procedure. Preserve the selected state and current native fallback settings. Build a schema-2 private profile with a safe unique `profile_id`, `adapter`, `endpoint`, optional `token_env`, `model_id`, `runtime_catalog`, exact `artifact` inventory/fingerprint, explicit candidate `capabilities`, `request_settings`, `fallback`, and `stale_tolerance_seconds`. Reuse `fingerprint_artifact`, `model_identity`, and `validate_profile_fields` from the packaged core; `profile inspect --file FILE` reports the saved profile and current artifact identity. Do not fabricate approval to validate an unapproved profile.

For reassessment of an approved profile, copy only those connection/artifact/runtime/settings/candidate/fallback/stale-tolerance fields into a separate record. Set `approval:null`, `scope:[]`, and `qualification_status:"needs_assessment"`. Omit loading permission, capacity/benefit/assessment/outcome evidence, suspended scopes, ownership hints, and every other authority field. Preserve the original file byte-for-byte. If request settings differ, make that difference explicit in the assessment preview. Reuse a matching unapproved candidate only when its full fields and intended identity match; never overwrite a profile needed by another run. Pass the explicitly selected original ID as `assessment prepare --source-profile-id ID`; never infer provenance from a shared model name.

Use `atomic_json` to save the unapproved record under the selected state's `profiles/`. Profile creation grants neither inference consent nor operating permission. A missing downloaded/loaded model remains a prerequisite; do not silently download, load or reset it for assessment.

## Synthetic assessment runs

Use **local-model-delegation:assess-my-model** and [Assessment operations](../../assess-my-model/references/operations.md) for focused selection, previews, per-run consent, submission, verification, pause/resume and offline reports. Both actions call the existing onboarding functions and share the same fixture pack and queue. A completed run never approves a model or enables routing. When the owner explicitly requests onboarding from a report, reuse its selected profile/run, check freshness, and ask only for missing approval/activation decisions.

## Legacy standing-consent assessments

This compatibility path applies to existing unversioned runs; it is not the dedicated action's default. New versioned runs cannot inherit standing consent or use legacy `assessment approve`/`assessment capacity`.

An authorized standing assessment policy in private configuration has `enabled:true` and the actual `owner_reference`. `assessment begin --profile-id ID --owner-reference REF` produces package-owned synthetic trials. Submit a selected trial with `assessment submit --assessment-id ID --trial-id TRIAL`; use the normal checking contract, then `assessment trial --assessment-id ID --receipt FILE` with `{trial_id,job_id}`. No project task can reuse this permit. Revoke the standing policy to stop further assessments. Three distinct cases twice per bucket provide provisional evidence only. Unsupported or absent buckets remain unknown.

The default path is the [practical qualification runbook](../../../docs/qualification.md). Use one slot and a few representative real tasks under explicit provisional approval. The fixture pack is optional; do not require all 36 toy calls or use their maximum input size as the model ceiling. Keep completed synthetic evidence immutable and separate from real project measurements.

## Approval and activation

`profile approve --profile-id ID --owner-reference REF --scope FILE` records explicit provisional operating permission. Scope is a nonempty array of `{capability,language,complexity,context_bucket,max_input_bytes}`; capabilities must be profile candidates, complexity is `simple`, `moderate` or `complex`, and the positive byte budget cannot exceed 800,000. Use the owner's actual authorization, exact artifact/settings binding and deliberate budgets. Never invoke this command merely because discovery, an assessment or an update succeeded. It preserves assessment evidence and does not enable routing or claim savings. Legacy `assessment approve` remains available for exactly its fixture-tested scope.

Add `--max-output-tokens N` to `profile approve` only when the owner authorizes that positive integer generation ceiling. Omission preserves the current ceiling. Individual tasks may select a smaller allowance without reapproval through [the brief contract](../../local-delegation/references/contracts.md#generation-budgets). A changed ceiling preserves historical evidence, invalidates the old approval-bound loading permission, and waits for occupied slots before refreshing an idle unchanged runtime. It cannot clear uncertain slots or recovery state. Rebind loading permission only under applicable owner authorization. Keep one slot and native verification while collecting evidence at new budgets; a higher ceiling is not qualification.

No capacity campaign is required for one slot. Fresh lightweight pressure checks admit normal/warning states and defer critical/unknown states. Detailed `resources` observations and the existing strict `assessment capacity` receipts remain optional diagnostics and evidence for separately authorized higher concurrency; they do not impose free-memory or swap vetoes on single-slot inference. Approved models can receive separate loading permission; follow [model loading and verified recovery](../../../docs/model-loading.md). This procedure records consent, uses HTTP loading, preserves runtime guardrails and verifies one slot/context. Unapproved assessment loading and unattended reset are not enabled by that permission.

For updates, follow the [guided update procedure](../../../docs/updating.md). Save original preferences before pausing, stage a numbered release, run its `prepare-update --target PATH --installed PATH`, use native installation, then run the installed `verify-update --receipt FILE`. Complete the guide's restoration and final readback after verification; the helper itself leaves the checkpoint paused. Never-submitted queued work can be preserved with admission disabled and its idle scheduler stopped. Active work stays with its recorded helper bundle. An uncertain external instance may be retired through the owner-authorized verified reset procedure from a newer tested source before installation; preserve the failed outcome and original bundle. Never roll back a database over new history. Detached workers pin helper code outside mutable plugin caches. Retain old bundles while jobs depend on them. Before native uninstall, run `prepare-uninstall`; this disables new routing and refuses unsettled work, preserves models/history and visibility preference, and removes only the current visibility export. Then use native removal controls. Force-removing files outside this workflow cannot guarantee continuation.

Pause every authorized versioned assessment before update/uninstall preparation, even when no trial is queued. Keep uncertainty and submitted-work reconciliation intact. Updates never restore per-run permission automatically; an explicit resume checks the frozen bindings and may require a new run after helper changes.

## Connection and activation details

Savings are not an approval prerequisite. The owner can approve an exact provisional operating scope while `expected_savings` remains `unknown`. Ordinary authorized work then supplies project measurements; comparisons still require separate bounded consent. Approval and activation do not create benefit evidence. Scheduling prefers credible benefit only within its measured scope, permits unknown benefit within approved scope, and retains existing negative-benefit and suspension blocks.

There is no routing-enable CLI command. After separate owner authorization, the coordinator sets `routing_enabled` in the selected private `config.json`, preserving all other fields, and reads it back with `doctor`. The `route decide` command concerns an individual waiting job, not global activation. Activation does not prove a successful local task.
