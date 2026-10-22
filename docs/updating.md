# Guided plugin updates

Use this procedure when the owner asks to update Local Model Delegation. The agent performs the available steps and asks only for missing authorization or a required manual action. An update preserves settings, exact approvals, model results and history. It keeps routing disabled; enabling it later is a separate decision.

## 1. Inspect and select a release

Locate the installed plugin, its marketplace entry and the selected private state directory. Use the default `~/.local/state/local-model-delegation` unless the installation explicitly selects another directory. Read the installed manifest and run its read-only `doctor`. Preserve native authentication, provider, model and reasoning settings. Do not run inference or model lifecycle operations to test an update.

Find the latest published numbered release in [GitHub Releases](https://github.com/fcoouto/local-model-delegation/releases). Read its notes and `release.json`. Stage the matching tagged source in a separate directory, leaving the working checkout and installed cache untouched. Confirm the tag resolves to `source_revision` and the staged helper's `version` output matches the release's version and `package_digest`. If using the release ZIP, verify `archive_sha256` before extraction. Reject archives containing absolute paths, traversal or symbolic links. These hashes bind content; publisher trust still comes from the selected repository and release.

If no numbered release is published, report that fact. Do not silently install `main`. A separately authorized development test may stage a clean, locally tagged release and must be labelled unpublished. Do not overwrite an existing version with different bytes or downgrade.

## 2. Prepare without losing state

Inspect live helper drivers and durable jobs, attempts, fallback dispatches and model operations. Do not duplicate work, resubmit an ambiguous attempt or reset a slot for an update. Active or uncertain work must settle using its existing pinned helper. A completed rejected synthetic trial is settled only when its assessment permit, brief and canonical outcome receipt match and it has no native dispatch.

Routing and assessment admission must both be disabled. If the owner's update request requires routing to remain off, preserve that setting. When admission is enabled, stop new admission within the authorized update scope, preserve every other setting, and let active work settle before preparation. Do not disable or interrupt peer models. Record the prior admission values in private evidence; never restore them automatically.

Use the staged target helper for preparation. This is the explicit bootstrap path when an older installed helper lacks the new update commands. In the commands below, `TARGET`, `INSTALLED`, `STATE` and `RECEIPT` stand for verified absolute paths; the agent supplies them, not the owner.

```sh
python3.11 -B TARGET/delegate.py version
python3.11 -B TARGET/delegate.py --state-dir STATE prepare-update --target TARGET --installed INSTALLED
```

Preparation pins the old helper outside its mutable cache, copies private files and backs up SQLite under `STATE/updates/<id>/backup/`. The returned receipt binds both package identities and the original file/table hashes. The helper refuses unsupported state, unresolved work, reused release versions and downgrades. It does not grant approval or change settings. Keep this private backup and receipt outside the repository.

## 3. Update through the native host

Preserve the marketplace name, plugin name, other entries and installation preferences. Back up the existing catalog privately. For a Git-backed plugin, pin only this entry to the selected release's exact commit using `sha`; retain the trusted repository URL. For a local plugin, stage the numbered package in a durable folder and point only this entry at it. Never point at a disposable directory or write into the host's plugin cache.

Use native Codex plugin installation/update controls. Inspect the installed CLI's help before choosing commands. Hosts exposing `codex plugin add PLUGIN@MARKETPLACE --json` can install the selected package through that native path. `codex plugin marketplace upgrade MARKETPLACE` refreshes configured Git marketplaces; it is not a universal update command for personal local catalogs. Do not uninstall first. If native installation is unavailable, give the supported desktop action and wait.

The official [plugin packaging and marketplace guidance](https://developers.openai.com/plugins/build/plugins) describes local sources, Git selectors and desktop reload behavior. A source revision, installed cache and loaded chat skill are separate observations. Do not claim success from a changed manifest alone.

## 4. Verify and report

Locate the newly installed package through the host, then run:

```sh
python3.11 -B INSTALLED/delegate.py version
python3.11 -B INSTALLED/delegate.py --state-dir STATE verify-update --receipt RECEIPT
python3.11 -B INSTALLED/delegate.py --state-dir STATE doctor
```

Verification requires the prepared package digest and every original private file/table to remain unchanged. It rejects unexpected new tables; additive `measurement_` tables are permitted. It never restores a backup over newer evidence. If project measurements are missing, authorized update may run `metrics init` after the first successful verification, then repeat verification. Existing measurement data is never reset.

If installation or verification fails, retain the receipt and backup, keep admission off, inspect actual installed state, and report the blocker. Do not blindly repeat an ambiguous installation or roll back the database. Any recovery must preserve history created since preparation.

Report the exact package version, source revision, installed digest, preservation checks, routing state and pending host reload. Ask the owner to reopen Codex or start a fresh chat only if needed to load changed skills. Verify discovery there before claiming that part complete. Do not create a new model call to prove a package update.

## Compatibility boundary

Version 0.3.0 supports current schema-2 state and task contracts only. Removed directory discovery, aliases, schema conversion and obsolete recovery paths are not offered as update options. Historical private files and pinned bundles remain evidence; the updater does not rename their contents, transfer approval or resume unsupported jobs. Unsupported installations need a separate, explicit transition plan before installing this release.

Never-submitted waiting jobs can be preserved across an update while admission is disabled. Stop only an idle queue scheduler before preparation; never terminate inference or recovery workers to force an update. The updater backs up and verifies queued briefs byte-for-byte. Idle verified instances without recovery markers may remain closed through installation; the scheduler refreshes only approval metadata after fresh matching discovery. Active or uncertain attempts, lifecycle work, and recovery markers still block update preparation. Resume the same queued job after verification; never create a replacement to bypass its state.
