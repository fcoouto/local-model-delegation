# Update validation

## Preference-restoration workflow

The update reference previously directed a consuming agent to leave previously enabled routing and Habblaud publishing off and ask for activation again. A fresh-context application test reproduced that behavior before correction. With the revised reference, an independent agent restored both preferences after successful verification without asking again, preserved initially disabled preferences and routing-only pause requests, reused original evidence after interruption, and kept failed verification paused. It also identified missing preference evidence as a reconciliation requirement and an unavailable receiver as pending publishing restoration without revoking restored routing.

These were read-only instruction-application scenarios, not native installation or inference tests. The unchanged runtime suite passed all 306 tests; both packaged skills passed structural validation. The correction is in the agent workflow: `verify-update` still verifies a paused checkpoint, and the coordinator performs restoration afterward.

## Original numbered-update qualification

Version 0.3.0 was checked with Python 3.11 on macOS. The full offline suite passed 218 tests. Both packaged skills passed the bundled structural validator using PyYAML 6.0.3. All 42 local Markdown links and anchors resolved, and `git diff --check 950c12dd763f2ecbc905ab9c034a1b3376503edb` passed before this record was added.

## Regression coverage

- Obsolete directory discovery, capability/worker aliases and schema-1 inputs no longer route or convert state. Existing unversioned databases are rejected without rewriting their bytes. New reservations retain the brief's explicit fallback, and saved obsolete briefs cannot bypass scope authorization.
- Update preparation requires disabled routing/assessment admission and settled durable work. Uncertain attempts and ambiguous native dispatches remain blocked. Completed rejected assessment trials count as settled only with matching permit, brief and canonical receipt evidence.
- Private backups preserve configuration, approval bytes, evidence, SQLite rows and schema objects. Changes to history, audit files or triggers fail verification; missing state is never initialized by verification. Repeated verification is safe.
- Package verification rejects changed installed bytes, same-version replacement and downgrade. Release building requires a clean matching tag and checks that the extracted archive has the same package identity as the source.
- Existing protected Python checks, native verification, capacity admission, durable fallback and project measurements remain covered by the full suite. Tests for removed schema conversion and obsolete automatic recovery were replaced with rejection/no-lifecycle guards.

Material cases were reproduced failing before correction. Fixtures use fictional models and approvals; no real model call or lifecycle operation was needed. The update procedure follows native installation controls and does not write directly into plugin caches.

## Qualification boundary

Offline tests do not prove desktop skill reload or publication. A native installation test against an existing installation must record its exact release revision, installed digest, before/after private state, native settings/authentication preservation and routing state. Keep that evidence private. Do not add private paths, profiles or assessment output to the release archive.

The earlier onboarding language evaluation was not repeated for these reference/command changes. Real project reliability and savings, approved-model end-to-end behavior, automatic lifecycle and compaction continuity remain separate qualification gates.
