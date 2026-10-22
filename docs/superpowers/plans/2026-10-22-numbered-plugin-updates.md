# Numbered releases and guided updates

Owner authorization: implement numbered releases, guided updates and README instructions; remove obsolete compatibility; test the installed plugin update while preserving settings, approvals and history, with routing disabled. Native implementation and self-review; no additional reviewer loop or model execution.

## Design and scope

Use semantic release `0.3.0` for this pre-1.0 breaking cleanup. Each release has a matching Git tag, changelog entry and package fingerprint. Reuse native Codex installation; do not write its cache directly or add an updater service. Keep release artifacts separate from private state. Public publication is distinct from testing a local release candidate.

The guided flow identifies installed and target packages, checks quiescence and disabled admission, creates a private state backup and verification receipt, asks the native host to install the selected package, then checks installed identity and exact preservation. Completed synthetic rejection receipts may establish settled work without altering job history. Unknown work remains blocking. A failed or interrupted install is reconciled by inspecting installed contents; never roll back private state.

Remove the former state-directory detection, old capability and script aliases, schema-1 profile/configuration migration and execution, and schema-1 lifecycle recovery. Retain current protected Python verification within schema-2 task briefs. Historic private evidence and pinned bundles are retained as data, not rewritten or resumed through compatibility code. Explicit custom state directories remain supported.

## Implementation tasks

1. Add failing boundary tests, remove obsolete paths, and adapt current fixtures to schema 2. Preserve verification, approval binding, capacity gates and durable fallback semantics. Run affected tests and full suite.
2. Add package identity, numbered release validation, safe update preparation/verification and preservation tests. Test unknown work, completed assessment rejection, package mismatch, changed state, replay and interrupted verification. Native installation remains a host action.
3. Add the README update section directly after the start prompt section, exact update operations, release notes and a release workflow. Validate source skills and Markdown links. Run full offline suite and native self-review.
4. Commit a coherent release candidate. Back up real private state, verify no live driver or uncertain work, stage the exact candidate outside the cache, update through native Codex controls, and verify package identity plus unchanged settings/approval/history. Keep routing and assessment disabled; no inference, model lifecycle, provider/default or authentication changes. Preserve unrelated work.

## Review focus and stop condition

- Legacy rejection cannot silently create a new queue or bypass approval.
- A matching version with different package bytes is not a verified update.
- A recorded failed assessment is settled only when its receipt, brief and permit match; active/uncertain attempts or dispatches always block.
- Backups and replay never overwrite newer history or enable routing.
- Release artifacts contain only portable source, never private state or checkout metadata.

Finish with source revision, release/install provenance, test results, preservation proof and any host reload/publication step still outstanding. Desktop reload is not claimed merely from replacing cache files.
