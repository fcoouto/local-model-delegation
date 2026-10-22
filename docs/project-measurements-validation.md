# Project measurements: offline validation

Date: 2026-10-22. Status: source implementation complete. The initial implementation record below predates installation; live savings and project reliability remain unqualified.

Implementation started at `63cc02ba6ef9eb7b3dd372fa726a7e479be65b2c` on the isolated `feat/project-model-measurements` branch. See the [design](superpowers/specs/2026-10-22-project-model-measurements-design.md), [implementation plan](superpowers/plans/2026-10-22-project-model-measurements.md), and [receipt contracts](../skills/local-delegation/references/measurements.md). This record is versioned with the implementation it describes.

## Delivered

- Private project identities and an additive, independently versioned SQLite ledger. Linked Git worktrees share history; separate clones remain separate.
- Job-bound model and environment evidence, preserved local verification outcomes, append-only corrections, and reconciliation without inference or dispatch.
- Reports for acceptance, delivery, fallback, reported incidents, latency, admission resource samples, and evidence coverage. Missing data stays unknown.
- Native usage and savings calculations with explicit attribution, comparable baselines, failed-work costs, and one-time overhead allocation. Savings are token proxies, not account quota or currency claims.
- Consent-bound comparison evidence registration and imports, including visible budget violations. These commands do not execute comparisons or grant permission.
- CLI reports, optional sanitized visibility exports, and source skill/onboarding documentation. Measurement collection does not update routing, approval, or model-global benefit fields.

## Checks and findings

The baseline suite passed 188 tests. The completed tree passed **219 tests**, including 31 new project/measurement tests:

```sh
python3.11 -B -m unittest discover -s tests -t . -q
git diff --check
```

Focused tests failed before the corresponding implementation. Coverage includes identity boundaries, immutable context, event replay and corrections, local rejection followed by native rescue, archived-verdict recovery, incompatible or incomplete usage, negative savings, overhead allocation, consent limits and revocation, read-only reports, and disabled or failed exports. A fictional pair exercises the actual ledger and verifier through a 600-token net proxy; reconciliation preserves its result without another attempt.

Native self-review found and corrected five additional defects, each reproduced with a failing regression:

| Finding | Disposition |
| --- | --- |
| A second usage correction conflicted with superseded span records. | Compare current span ownership and preserve the full correction chain. |
| Terminal failures without delivery receipts escaped the closed-task denominator. | Include durable terminal failures without inventing delivery or success. |
| An unverified local task could claim unchanged local delivery. | Require accepted canonical local work and a bound successful local verdict. |
| Generic candidate-format rejection omitted its local verdict. | Archive rejection before fallback can replace current evidence. |
| A comparison receipt could label an unfinished local attempt completed. | Require canonical attempt completion and matching submission time where recorded. |

CLI help, local Markdown links, and fenced examples were checked. The existing offline suite also covers package installation fixtures, recovery, queue behavior, and verification. Tests used disposable state and fictional profiles. No independent reviewer or live skill trial was run.

Real configuration and model-profile hashes matched their pre-implementation values. Routing and assessment remained disabled; model approval remained null. No model inference, lifecycle operation, plugin installation, provider/default change, or authentication change occurred. The installed plugin cache and unrelated loading work were left untouched.

## Implementation adjustments

- Pure report calculations and comparison bookkeeping use `measurement_reports.py` and `measurement_comparisons.py`, keeping the public ledger interfaces in `measurements.py`.
- New regression coverage is concentrated in `test_projects.py` and `test_measurements.py`; the full existing suite verifies connected callers.
- Inference duration uses a monotonic interval. Other phase durations require coordinator evidence and remain unknown when absent. Resource reports reuse existing admission samples rather than adding probes or claiming inference-wide measurements.
- Excess or duplicate comparison attempts remain in the audit as violations and cannot qualify pairs. Importing evidence cannot retroactively prevent excess execution.
- Usage collection accepts trusted, attributable receipts. Automatic capture from a host telemetry source remains unqualified; no undocumented log scraper or billing integration was added.

## Remaining qualification

The initial run could not execute the bundled skill validator because PyYAML was unavailable. On 2026-10-22, the owner authorized installing PyYAML. Version 6.0.3 was installed in the user's Python 3.11 package directory, preserving the managed interpreter files. A parsing smoke check and the bundled `quick_validate.py` checks for both `skills/local-delegation` and `skills/setup` passed. This closes the structural-validation gap; it does not establish live skill behavior or add a plugin runtime dependency.

Before claiming project reliability or savings, qualify a supported native usage source, real project outcomes, collection continuity, and total native overhead/net benefit. Exact model approval and routing can precede savings qualification so ordinary authorized work can produce evidence. Extra comparison calls require separate bounded authorization and an executor that enforces it. Counts and fictional arithmetic do not establish real savings or statistical reliability.

Project-aware adaptive routing, arbitrary project comparison execution, automatic loading, parallel capacity, and desktop compaction continuity remain separate work. Runtime identity still trusts the local index and discovery metadata; it does not attest weights in memory.

## Approval bootstrap correction

Version 0.3.1 separates capability/capacity approval from savings evidence. Four failing regressions reproduced rejection of approval and ordinary scheduling solely because benefit was unknown. They pass after the correction; missing evidence stays unknown and the helper does not write a positive benefit record. Known negative benefit, suspended scope, exact identity, owner confirmation, memory and verification gates remain in force.

The full suite exposed runtime-discovery failures that had been hidden by the old benefit gate. A second failing regression confirmed an unloaded model waited without useful work. Both now fall back before POST; a healthy occupied runtime still retains its peer and waiter. Test fixtures now mark unqualified profiles explicitly instead of using absent savings as a substitute.

The updated offline suite passes 226 tests. Both skills pass the installed structural validator. The coordinator-policy mapping was checked against Vibe Setup's native declaration contract and capability-selection policy: local responses remain proposals; active instructions, tools, acceptance, ownership and native fallback requirements stay with the coordinator. This is not proof of native hook interception, automatic skill adoption, semantic policy enforcement or real-model execution. No additional independent reviewer or live model trial was run for this correction.

## Practical admission correction (0.3.2)

Five focused regressions reproduced the fixture-size approval coupling, warning/swap/free-memory rejection, absent default single-slot admission, heavy pre-POST resource sampling, and missing runtime context screening. The corrected path has seven focused checks, including Unicode/prompt/output budgeting and prevention of automatic synthetic concurrency expansion. The full offline suite passes 233 tests. Both bundled skills pass the validator with PyYAML installed.

Default admission now samples only fresh macOS pressure. Explicit provisional approval records operating budgets separately from historical observations. Critical/unknown pressure, exact identity, source integrity, shared/uncertain slots and native verification remain enforced. Optional strict capacity experiments retain their original meaning. These are offline and author-reviewed results; they do not establish real-model quality, exact tokenization, independent review, net savings or desktop continuity.

## Approval transition correction (0.3.3)

A live admission attempt, before any inference POST, exposed that a newly approved scope closed an idle instance left by synthetic assessment. Failing fictional regressions reproduced the idle approval transition, disruption of an occupied peer, and inability to preserve a never-submitted queued task through a disabled update. The fix refreshes only approval metadata with identical runtime/profile bindings and fresh matching discovery. It retains uncertain slots, changed settings/context, recovery markers and unfinished lifecycle operations. Updates preserve untouched queued briefs while uninstall remains strict. The full offline suite passes 238 tests.
