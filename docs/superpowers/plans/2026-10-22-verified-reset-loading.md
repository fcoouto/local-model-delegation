# Verified reset and HTTP model loading implementation plan

> Execute directly with regression tests. The owner authorized implementation and the required Qwen unload/reload; no new inference is part of recovery.

**Goal:** Settle an uncertain external-runtime reservation with verified unload evidence, preserve its failed outcome, and support approved model loading before delegation.

**Architecture:** Reuse SQLite `model_operations`, exact profile validation, HTTP discovery/load/unload, generation fencing and native plugin updates. Keep lifecycle permission separate from inference approval and routing. The prior assessment-only JIT experiment is preserved at `c63d806` on `feat/assessment-jit`; this branch starts from the immutable 0.3.4 staging source. Use explicit HTTP load before inference so loading does not consume a trial or produce an unverifiable pending candidate.

**Boundaries:** macOS, Python 3.11, standard library, HTTP only. No provider/authentication/default changes, download, extra model calls, historical outcome rewrite, or reused version bytes. LM Studio retains its loading guardrails. All live admission stays disabled through update verification. Runtime identity trusts the local index and discovery, not in-memory attestation.

## Design and acceptance

- Reset requires owner reference, disabled routing/assessment, an exact instance/generation, no live observers or healthy endpoint peers, and a fresh identity-bound discovery. Record intent before the one permitted unload POST. A resumed operation never repeats that POST. Confirm target absence and unchanged peers before releasing only that generation's uncertain attempts; preserve previous state and the full reset audit. Never change job outcomes.
- Loading requires separate profile-specific permission bound to the current approval and requested context. Reuse an already matching loaded instance. Otherwise require an empty endpoint, no unresolved lifecycle/inference work, and fresh acceptable pressure. Persist intent before one load POST, verify response and discovery, and require one parallel slot. Ambiguous loads remain held and are never reposted.
- Shared admission checks lifecycle reservations; the scheduler tries authorized loading before selecting native fallback. Loading failures never silently change model configuration or approvals.
- Reconciled retired instances are settled for updates and can be readmitted only through fresh verified discovery after generation fencing.
- The helper cannot lock unrelated LM Studio clients. Document external load/unload races and fail closed when observed. The HTTP API does not expose a reliable cross-client idle lease.

## Tasks

- [x] Add failing regressions for external reset, lost acknowledgment, healthy peers, observer ownership, unchanged outcomes, replay, retired update state and reused instance IDs.
- [x] Implement durable reset/reconciliation and CLI. Run focused recovery/update tests.
- [x] Add failing regressions for consent-bound load, changed approval, peers, pressure, ambiguous load replay, loaded configuration and scheduler admission.
- [x] Implement HTTP loading through existing capacity/scheduler seams; run affected tests and the full offline suite.
- [x] Update skills/runbooks and version to a fresh 0.3.5; validate skills, package and whitespace. Commit coherent source changes.
- [x] Back up live state. Execute the authorized Qwen reset once; verify history preservation. Stage/install through native controls and verify the update with routing off. Reload Qwen through the new supported HTTP path, verify one slot and exact identity, and report gates honestly. Private receipts retain the execution and preservation evidence; public release publication remains pending.

## Review focus

Lost responses and interrupted drivers must not duplicate requests. Profile replacement invalidates loading permission. A live checker/observer or healthy peer blocks reset. Same instance ID after reload must not revive old attempts. Missing/malformed discovery is not proof of absence. Retired-state update exemptions require a real verified reset receipt.

Offline validation: 255 tests passed, including 17 lifecycle regressions. Both bundled skills validated with PyYAML; 32 affected local links and whole-branch whitespace passed. Direct review also reproduced and corrected malformed load acknowledgment handling and replay mutation of a completed reconciliation receipt. No additional independent reviewer was dispatched. Live execution/update outcomes belong in private receipts, not this portable plan or an immutable release rewrite.

## Documentation sources

- https://lmstudio.ai/docs/developer/rest/load
- https://lmstudio.ai/docs/developer/rest/unload
- https://lmstudio.ai/docs/developer/core/ttl-and-auto-evict

These interfaces were checked on 22 October 2026. JIT can evict other JIT-loaded models; this implementation uses a separate load call and conservatively refuses loading beside any existing peer.
