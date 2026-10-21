---
name: local-delegation
description: Use when approved local text models may handle a bounded coding, test-writing or file-summary task with verifiable results and lower native coordination cost.
---

# Local Model Delegation

Codex owns scope, commands, verification and integration. Local models receive supplied context and return proposals. Preserve the active host's native authentication, provider and permission rules. Explicit user restrictions override this workflow.

Use `python3.11 <plugin>/skills/local-python-repair/scripts/repair.py`. Defaults use the shared private state home across projects. Read [contracts](references/contracts.md) when forming a brief. Missing or disabled routing means continue natively without setup, assessment or approval. Installation, assessment consent, model approval and route activation are separate decisions.

1. Choose a bounded task with predeclared acceptance checks. Read assessed scope; never infer ability from model name or size. Resolve an exact native fallback from explicit task policy or trusted active-host metadata. If unavailable, keep work with the current native coordinator. Reuse `origin_chat_id` and `task_key` through compaction; `lookup` before resubmitting.
2. Submit once. For `waiting`, `reserved` or `running`, use `wait --job ID --seconds 5` (up to 60). Healthy occupied slots justify waiting. At `route_decision_required`, decide automatically whether expected benefit warrants a bounded extension or native fallback. Use `route decide --job ID --decision FILE` with the same job. Never ask the owner to switch models because local capacity is busy.
3. For `candidate_ready`, use `check --job ID` for bounded Python. For other capabilities, use `verify prepare`, `verify checks` and `verify record`. Review every acceptance criterion and summary claim. Execute only declared checks in the qualified sandbox; missing toolchains/isolation keep the task native. A candidate's claimed receipt or stdout is not verification. Keep the session token outside candidate-accessible files and prompts.
4. Apply only an `accepted` proposal with native editing tools, after comparing source hashes again. Run the destination project's required checks. The helper never applies project files. `needs_reassessment` means the snapshot changed; rebuild scope before attempting a distinct task.
5. For `fallback_required`, first verify the exact native model/effort and native delegation support are available. If unavailable, keep execution with the coordinator and report that state; do not claim a task started. Otherwise use `fallback claim`, inspect native tasks for its stable name, and dispatch only if `may_dispatch` is true and no match exists. This skill authorizes native fallback delegation within the user's task, subject to any explicit prohibition. Use the supported native tool, exact model/effort and a fresh context. Give source, contract and proposed-output location; forbid recursive local delegation. Keep independent oracle source private.
6. Immediately `fallback attach` the returned native task ID. An ambiguous dispatch requires `fallback reconcile` against the actual native task list; never blindly repeat it. Use native waiting tools, record the candidate with `fallback result`, then use the same verification contract. Failed native verification is terminal, not another fallback.
7. Record accepted/failed outcome evidence with `outcome record`. Use actual counts or nulls; label token savings as a proxy. Include coordination, verification and fallback overhead. Six synthetic trials do not establish statistical reliability or net account savings.

Display the actual model name while it generates and “Awaiting verification” after a candidate returns. Distinguish waiting, pending dispatch, confirmed native execution and unavailable fallback. Do not impersonate native agents or promise control over native app banners. [Read-only visibility](references/visibility.md) is optional, enabled by default and independent of routing; it never controls work.

Current HTTP adapter cannot prove safe automatic loading/non-eviction. `lifecycle_unqualified` preserves existing models and uncertain slots. Never substitute a model CLI, global runtime settings, proxy, cloud API or fabricated ownership receipt. Model replacement requires fresh owner approval.
