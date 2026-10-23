# Guided plugin updates

Use this procedure when the owner asks to update Local Model Delegation. The agent performs the available steps and asks only for missing authorization or a required manual action. An update preserves settings, exact approvals, model results and history. Routing and agent representation publishing pause for verification, then return to their saved operational state. Restoring an already-enabled control is part of the authorized update; first-time activation remains a separate decision.

## 1. Inspect and select a release

Locate the installed plugin, its marketplace entry and the selected private state directory. Use the default `~/.local/state/local-model-delegation` unless the installation explicitly selects another directory. Read the installed manifest and run its read-only `doctor`. Preserve native authentication, provider, model and reasoning settings. Do not run inference or model lifecycle operations to test an update.

Find the latest published numbered release in [GitHub Releases](https://github.com/fcoouto/local-model-delegation/releases). Read its notes and `release.json`. Stage the matching tagged source in a separate directory, leaving the working checkout and installed cache untouched. Confirm the tag resolves to `source_revision` and the staged helper's `version` output matches the release's version and `package_digest`. If using the release ZIP, verify `archive_sha256` before extraction. Reject archives containing absolute paths, traversal or symbolic links. These hashes bind content; publisher trust still comes from the selected repository and release.

If no numbered release is published, report that fact. Do not silently install `main`. A separately authorized development test may stage a clean, locally tagged release and must be labelled unpublished. Do not overwrite an existing version with different bytes or downgrade.

## 2. Prepare without losing state

Inspect live helper drivers and durable jobs, attempts, fallback dispatches and model operations. Do not duplicate work, resubmit an ambiguous attempt or clear a slot to bypass an update. Active work must settle using its existing pinned helper. If that helper cannot reconcile an uncertain external runtime, separately authorized [verified reset recovery](model-loading.md#recover-an-uncertain-inference-slot) may use a newer tested source before installation; this is recovery work, not an update test. A completed rejected synthetic trial is settled only when its assessment permit, brief and canonical outcome receipt match and it has no native dispatch.

Before changing configuration, save an owner-only copy of the selected state's configuration under `STATE/updates/`, together with the state path, target package identity and any explicit request to remain paused. This records the original `routing_enabled`, assessment admission, `visibility_enabled`, and complete agent representation configuration, retaining its existing stored namespace. Associate it with the preparation receipt when available. On resuming an interrupted update, reuse this original record; the already-paused configuration and preparation backup do not establish the owner's prior operational state.

Routing and assessment admission must both be disabled during preparation and verification. Pause new admission within the authorized update scope, preserve every other setting, and let active work settle before preparation. Do not disable or interrupt peer models. Previously disabled controls remain disabled; an explicit owner request to remain paused takes precedence over restoration. Assessment admission is not automatically restarted by an update.

For **Assess my Model**, use `assessment pause --assessment-id ID` for each authorized run, including runs without queued jobs. Global standing policy does not revoke per-run permission. Preparation refuses active run permission and malformed records. Preserve submitted/uncertain attempts and private evidence. Never restore per-run permission automatically; explicit resume rechecks frozen helper/fixture/model settings and rejects changed bindings. [Assessment operations](../skills/assess-my-model/references/operations.md) defines the controls.

Use the staged target helper for preparation. This is the explicit bootstrap path when an older installed helper lacks the new update commands. In the commands below, `TARGET`, `INSTALLED`, `STATE` and `RECEIPT` stand for verified absolute paths; the agent supplies them, not the owner.

```sh
python3.11 -B TARGET/delegate.py version
python3.11 -B TARGET/delegate.py --state-dir STATE prepare-update --target TARGET --installed INSTALLED
```

Preparation pins the old helper outside its mutable cache, disables agent representation publishing, waits for its observers, copies private files and backs up SQLite under `STATE/updates/<id>/backup/`. The returned receipt binds both package identities and the paused file/table hashes. The helper refuses unsupported state, unresolved work, reused release versions and downgrades. It does not grant approval. Keep the original state record, private backup and receipt outside the repository.

## 3. Update through the native host

Preserve the marketplace name, plugin name, other entries and installation preferences. Back up the existing catalog privately. For a Git-backed plugin, pin only this entry to the selected release's exact commit using `sha`; retain the trusted repository URL. For a local plugin, stage the numbered package in a durable folder and point only this entry at it. Never point at a disposable directory or write into the host's plugin cache.

Use native Codex plugin installation/update controls. Inspect the installed CLI's help before choosing commands. Hosts exposing `codex plugin add PLUGIN@MARKETPLACE --json` can install the selected package through that native path. `codex plugin marketplace upgrade MARKETPLACE` refreshes configured Git marketplaces; it is not a universal update command for personal local catalogs. Do not uninstall first. If native installation is unavailable, give the supported desktop action and wait.

The official [plugin packaging and marketplace guidance](https://developers.openai.com/plugins/build/plugins) describes local sources, Git selectors and desktop reload behavior. A source revision, installed cache and loaded chat skill are separate observations. Do not claim success from a changed manifest alone.

## 4. Verify while paused

Locate the newly installed package through the host, then run:

```sh
python3.11 -B INSTALLED/delegate.py version
python3.11 -B INSTALLED/delegate.py --state-dir STATE verify-update --receipt RECEIPT
python3.11 -B INSTALLED/delegate.py --state-dir STATE doctor
```

Verification requires the prepared package digest and every original private file/table to remain unchanged. It rejects unexpected new tables; additive `measurement_` tables are permitted. It never restores a backup over newer evidence. If project measurements are missing, authorized update may run `metrics init` after the first successful verification, then repeat verification. Existing measurement data is never reset.

If installation or verification fails, retain the receipt and backup, keep admission off, inspect actual installed state, and report the blocker. Do not blindly repeat an ambiguous installation or roll back the database. Any recovery must preserve history created since preparation.

Ask the owner to reopen Codex or start a fresh chat only if needed to load changed skills. Verify discovery there before claiming that part complete. Do not create a new model call to prove a package update.

## 5. Restore operational state and report the final state

After all package/state verification succeeds and `doctor` reports supported state, restore the saved routing preference without asking for the same authorization again. Read the current configuration and atomically change only `routing_enabled` to the recorded value, unless the owner requested it remain off. Preserve approvals, model settings, visibility and all unrelated fields. Do not copy the old configuration over current state. If settings changed unexpectedly since verification or the original state record is missing, reconcile that evidence before restoring; report the update as incomplete rather than guess.

If agent representation publishing was previously enabled and the owner did not request it remain off, run `representation enable` with its recorded endpoint and account. Preserve the global visibility preference. Previously disabled publishing stays disabled. An unavailable receiver does not revoke restored routing; report publishing restoration as pending without changing the endpoint or account.

Finish with read-only `doctor` and `representation status`, and save their final routing/publishing values alongside the original state record and update receipt. The helper's `verify-update` result describes the paused checkpoint; it does not perform restoration. Finish any repeated verification or `metrics init` before restoring operational state. Do not edit receipt hashes or rerun its paused-state comparison after restoration. Report exact version/revision/digest, preservation and discovery evidence, and actual final operational state, including any remaining pause or publishing failure. Successful installation alone is not a completed update when state restoration is still pending.

## Compatibility boundary

Version 0.3.0 supports current schema-2 state and task contracts only. Removed directory discovery, aliases, schema conversion and obsolete recovery paths are not offered as update options. Historical private files and pinned bundles remain evidence; the updater does not rename their contents, transfer approval or resume unsupported jobs. Unsupported installations need a separate, explicit transition plan before installing this release.

Never-submitted waiting jobs can be preserved across an update while admission is disabled. Stop only an idle queue scheduler before preparation; never terminate inference or recovery workers to force an update. The updater backs up and verifies queued briefs byte-for-byte. Idle verified instances without recovery markers may remain closed through installation; the scheduler refreshes only approval metadata after fresh matching discovery. Active or uncertain attempts, lifecycle work, and recovery markers still block update preparation. Resume the same queued job after verification; never create a replacement to bypass its state.

An externally loaded instance with an uncertain attempt requires [verified reset reconciliation](model-loading.md#recover-an-uncertain-inference-slot). Version 0.3.5 recognizes a retired generation only when its completed reset receipt proves absence and the generation advance. The original failed job and attempt audit remain intact. Keep routing and assessment off throughout recovery and update verification; manual state edits or a runtime restart alone cannot satisfy this gate.
