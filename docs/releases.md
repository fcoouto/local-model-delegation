# Numbered releases

`plugin.json` is the package version authority. Use `MAJOR.MINOR.PATCH`, with a matching immutable Git tag `vMAJOR.MINOR.PATCH`. Never move a published tag or reuse a version for different package bytes. During the pre-1.0 preview, breaking contract removal increments the minor version. Patch releases contain compatible corrections.

## Build and publish

1. Update `plugin.json` and `CHANGELOG.md`. Review the full change, run the offline suite, validate both skills, and check the diff. Keep private state, credentials and model evidence outside the repository.
2. Commit all intended release files. Create the matching annotated tag on that exact commit. The builder rejects dirty checkouts and mismatched tags.
3. Run `python3.11 -B scripts/release.py --tag v0.3.0 --output /absolute/path/outside/repository/release-0.3.0` with the actual release number and a new output directory. It uses `git archive` and a package allowlist. It writes a ZIP and `release.json` containing the source revision, package digest and archive hash. It never publishes.
4. Extract the archive into a disposable directory, verify its package identity, and test an authorized native update using [the update guide](updating.md). Retain private preservation evidence locally. Qualify desktop skill discovery separately.
5. After approval to publish, push the commit and matching tag, create a GitHub release, and attach the generated ZIP and `release.json`. Use the changelog for release notes. A merge alone is not publication.

Users select the published release through guided updates. Existing installed caches do not update because a PR merged. Marketplace pins should identify the selected commit, not mutable `main`. A locally tested unpublished package must be reported as such; public delivery remains pending until publication succeeds.

No background updater, new inference service or direct cache writer is included. Codex owns installation and reload. The helper owns content/state verification and private update receipts.
