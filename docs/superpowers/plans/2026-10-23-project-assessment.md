# Project Assessment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Prepare and execute project-grounded local model assessments, report demonstrated scope and workload coverage, and bind new approvals to the tested project.

**Architecture:** Extend the current assessment entry point and shared queue. A native coordinator creates a project pack from verified source evidence; deterministic Python validates and freezes it. Existing isolation and native verification remain authoritative; no additional inference service or provider is introduced.

**Tech Stack:** Python 3.11 standard library, existing SQLite queue, current LM Studio/Bionic adapter, unittest.

**Spec:** `docs/superpowers/specs/2026-10-23-historical-assessment-design.md`

## Global Constraints

- Preserve existing profiles, approvals, reports, routing and native provider/authentication settings.
- New assessment runs require a selected canonical project and exact preview consent; preparing a preview never generates responses.
- Per domain: 6–10 distinct tasks, default eight with 2 light / 3 medium / 2 high / 1 extra high. Six: 1/2/2/1; seven: 2/2/2/1; nine: 2/3/3/1; ten: 2/4/3/1.
- Use `simple`, `moderate`, `complex`, `extra_complex` as exact difficulty values, preserving legacy semantics.
- Preserve eight supplied files per assignment, 100,000 UTF-8 bytes per file, strict candidate parsing and native verification.
- At most three cycles; hidden checks never become repair hints. Time is separate from correctness, unknown termination retains the slot.
- No source from PHIOON, live model identity, credentials or private evidence in product fixtures or commits.
- Inference and installation await their concrete authorized preview; implementation permission is already explicit.

## Review Focus

- Equal project names and same languages must not transfer approval across different identities: test in Task 3.
- Changed source evidence, malformed manifests and renamed duplicate tasks must fail before inference: test in Task 1.
- Clock expiry, interrupted generation and repeated submit must not release uncertain work or regenerate: test in Task 2.
- Small curated samples and missing workload weights must not produce a reliability/savings percentage: test in Task 3.
- A native-assisted repair or hidden-check feedback must not become an unassisted local pass: test cycle lineage and finalization in Task 2.

## Task 1: Project-grounded task preparation

**Files:** Create `local_model_delegation/project_assessment.py`, `tests/test_project_assessment.py`; modify `local_model_delegation/cli.py`, `contracts.py`, `onboarding.py` and relevant skill operations.

**Interfaces:** `difficulty_distribution(count: int) -> dict`; `project_preview(project_root: Path, pack: dict, owner_reference: str) -> dict`. Packs describe domains, assignments and exact source evidence. Preview returns canonical project identity, pack digest, coverage and resource/verification readiness without creating model jobs. A missing executable assessment bundle is visibly draft, never runnable.

- [x] Write tests for 6–10 mixes, strict extra-high separation, project permission, unsafe/changed source paths, distinct task IDs and repeated scenario rejection, honest unknown weights and no runtime calls.
- [x] Run `python3.11 -B -m unittest tests.test_project_assessment -q`; confirm failures identify missing behavior.
- [x] Implement strict private pack validation and offline preview; expose `assessment project-preview --project PATH --selection FILE --owner-reference REF` and distribution choices. Source files are data, never executable setup instructions.
- [x] Run focused tests and `git diff --check`; commit this complete preparation layer.

## Task 2: Frozen project runs and bounded cycles

**Files:** Modify `project_assessment.py`, `onboarding.py`, `worker.py`, `validation.py`, `cli.py`; create `tests/test_project_assessment_runs.py`.

**Interfaces:** Extend `prepare_assessment(..., project_root=None)` for reviewed executable project packs; preserve legacy selection semantics. Add project-cycle/finalization operations through the same assessment record, permits and queue. Each cycle binds parent candidate, source, public feedback, deadline and allowance; no unbounded dynamic consent.

- [x] Write failing fake-runtime tests for source/pack freeze, no POST before matching consent, exact original source profile, context-derived finite output allowance, terminal exhaustion as incomplete, deadline uncertainty, cycle cap, duplicate submissions and no hidden-check feedback.
- [x] Run the new tests and confirm the missing behavior.
- [x] Implement executable-pack validation/reference evidence, immutable campaign preview, cycle lineage and public-check staging, and worker deadline observation retaining uncertain ownership. Keep legacy records untouched. Reuse current verification receipts for final acceptance.
- [x] Verify native comparison records use identical frozen tasks/feedback rules and explicitly report unenforced token limits; do not spawn native baselines automatically.
- [x] Run project-run tests plus `tests.test_assessment_runs`, `tests.test_worker`, `tests.test_generation_budgets`, `tests.test_validation`; commit.

## Task 3: Project approvals and useful coverage reports

**Files:** Modify `project_assessment.py`, `profiles.py`, `onboarding.py`, `scheduler.py`, `cli.py`, relevant store admission paths; create `tests/test_project_approvals.py` and report tests.

**Interfaces:** Extend approval with explicit project grants bound to existing exact-model identity/settings; `scope_matches` must check project identity for new grants. Preserve existing legacy approvals and record their provenance. Project reports expose counts by domain/difficulty/origin, recommendation, provisional weighted task coverage, unknown share and paired timing separately.

- [x] Write failing tests for same-model separate projects, canonical worktrees, role-label bypass attempts, approval mutation/revocation while queued, unchanged legacy approvals, sparse success and missing weights, unfinished denominator, native assistance and comparison asymmetry.
- [x] Implement separate project grant permission using current ownership and atomic state patterns; do not duplicate model profiles just to represent project grants.
- [x] Implement report aggregation with explicit samples and workload assumptions. Extra-high one-case success is exploratory, not a broad operating grant.
- [x] Run project approval/report tests plus profile, scheduler, store and measurement suites; commit.

## Task 4: Entry points, PHIOON preview and independent review

**Files:** Update `skills/assess-my-model/`, `skills/setup/`, `skills/local-delegation/references/contracts.md`, `README.md`, qualification docs and tests that validate entry-point contracts. PHIOON artifacts stay outside the repository.

- [ ] Update both flows to select/authorize a project, inspect actual work, construct grounded tasks with native reference review, preview, consent and report. Preserve offline legacy reporting; no generic evidence is relabeled as project evidence.
- [ ] Inspect the owner-selected PHIOON repository and relevant local instructions. Produce an eight-task-per-selected-domain draft with exact paths/revisions, difficulty rationales, expected checks and remaining readiness gates. No PHIOON mutations or Qwen inference yet.
- [ ] Run `python3.11 -B -m unittest discover -s tests -t . -q` and `git diff --check`; complete skill validation where applicable.
- [ ] Obtain independent native whole-branch review under unchanged native settings; fix material findings with regression tests and rerun affected checks.
- [ ] Follow the repository lifecycle for reviewed draft publication; do not merge or install without applicable authorization. Present the PHIOON task preview and exact remaining run-consent dimensions before Qwen submissions.

## Execution record

The owner authorized updating the plan and implementation in one request. Execute inline with native settings preserved and one independent final review; do not repeat a plan-approval question. This change spans evidence/permission boundaries beyond the approved simple local scopes, so implementation remains native. Keep progress and interface rulings in the plan-specific private ledger. Four phases/checkpoints at most. Use existing verified worktree/task binding `9c5a1e72-97e7-4bcc-bc97-52a265ab08ee`.

Implementation ruling: The first native comparison integration uses paired first-cycle cases with one opportunity per contestant. Multi-cycle local completion remains separate; no equal-opportunity final native comparison is claimed. The current comparison ledger stores individual attempt pairs. Project campaigns export exact hashes and measurement bindings for that existing ledger. A later multi-cycle native comparison needs its own equally frozen opportunity plan.
