# Assessment Runtime Storage Implementation Plan

> Execute inline with superpowers:executing-plans; use one independent final review.

**Goal:** Separate assessment dependencies and temporary checks from plugin backups.

**Architecture:** A small storage helper reports and validates a private sibling
workspace. Project reference checks reuse it; the updater detects misplaced
dependency trees without deleting or excluding evidence.

**Tech Stack:** Python 3.11 standard library and existing offline unittest fixtures.

**Spec:** `docs/superpowers/specs/2026-10-23-assessment-runtime-storage-design.md`

## Constraints and review focus

- Preserve saved evidence, job identities, approvals, live writers and native settings.
- Reject unsafe aliases and workspace/state overlap; preserve update quiescence.
- Keep original historical scripts and reports immutable during relocation.
- Do not infer toolchain equivalence from matching dependency locks alone.

## Steps

- [ ] Add failing storage, reference-check and update-boundary tests.
- [ ] Implement `assessment_storage.py`, `assessment storage`, external reference
  checks and updater preflight/traversal changes; update operational guidance.
- [ ] Coordinate and restore the historical runtime outside state, compare saved
  hashes and record relocation/rollback evidence without generating responses.
- [ ] Run focused/full tests, current security gates and independent review; publish
  a ready PR and send the owning assessment chat the final supported paths.
