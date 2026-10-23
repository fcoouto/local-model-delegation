# Separate assessment runtime storage

The owner selected separate runtime storage on 2026-10-23. Assessment dependencies
must not be deleted or silently excluded from evidence to make plugin updates pass.

## Approach

Deferring every update leaves the storage conflict unresolved. Backing up arbitrary
dependency trees requires a larger symlink/archive contract. The selected approach
keeps reproducible runtimes and temporary reference-check workspaces outside the
selected plugin state directory. Reports, approvals, manifests, frozen briefs and
verification receipts remain durable evidence under their existing paths.

`assessment storage` reports a private sibling workspace named
`<state-directory-name>-assessment-workspaces`, with `runtimes` and
`reference-checks` children. Deriving it from the selected canonical state path
keeps custom states separate and avoids dependence on worker-overridden `HOME`.
Inspection creates nothing. Creation uses the existing owner-only directory checks.
Symlink aliases and a workspace containing another plugin state's configuration
or database are rejected. Existing external qualified runtimes need not move.

New project reference checks use this external workspace. Durable job sources,
verification stages and pinned plugin helper bundles retain their current storage
and update gates. A running or uncertain inference, active assessment permission,
or changing durable state still blocks a plugin update. Independent external
dependency preparation does not participate in the plugin backup transaction.

The updater keeps its strict evidence backup and symlink rejection. It reports a
specific error for misplaced `node_modules`, `.venv` or `venv` directories before
observer shutdown or backup creation. It neither skips nor deletes these trees.
Its traversal prunes existing excluded transaction/lock directories instead of
descending through them. Unsupported state remains blocked with a concrete remedy.

## Existing assessment recovery

Coordinate with the owning chat before moving a runtime. Check its writers and
frozen references; preserve original reports and replay scripts. Record original
and destination paths and hashes in a separate private migration receipt. Rebuild
missing dependencies only from the saved lockfile with the recorded available
toolchain, then compare against the saved file map. Missing original executable
fingerprints remain an explicit qualification gap. Never replay model generation
or rewrite historical evidence to make reconstructed files match.

Relocation uses a verified copy followed by an atomic move of the original runtime
to a private external archive. Preserve that archive for rollback. Do not leave a
symlink under plugin state. Rollback restores the original directory only after
checking stopped writers and an absent original destination; it does not overwrite
newer evidence. A future historical replay must use a separately reviewed script
with explicit relocated paths and renewed isolation qualification.

## Acceptance

Tests prove external storage is stable, private and distinct for custom states;
temporary reference checks stay outside state; external dependency changes and
symlinks cannot affect update preservation; misplaced runtime trees fail before
mutation; arbitrary state symlinks, changed evidence and active work still block.
Run the full offline suite and independent security review. No package installation,
release, model approval or real inference is part of this change.
