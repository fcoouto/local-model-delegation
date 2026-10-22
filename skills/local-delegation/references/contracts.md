# Task and native verification contracts

The delegation CLI's `--help` lists commands. State is shared at `~/.local/state/local-model-delegation`, with explicit `--state-dir` for fixtures or an existing installation. All participants must select the same queue. Routing defaults off. Profile schema 2 stores each model under `profiles/<safe-id>.json`; assessment observations never enlarge approval. Only schema-2 configuration, profiles, queues and briefs are supported.

## Coordinator policy and native subagents

The active coordinator policy decides whether a task should be delegated. This plugin supplies a proposal path for approved local models; it does not replace project instructions or a native subagent selection policy. Under Vibe Setup, keep its task-based capability choice, ownership, permission, verification and integration rules. Its native provider/model authorization does not itself approve a local model; local approval and routing activation remain separate gates.

Before submission, the coordinator reads applicable AGENTS instructions and relevant skills/plugins. Put the objective and relevant constraints in `behavior_contract`, supplied context in `files`, proposed write scope in `editable_paths`, and native verification criteria/commands in `acceptance`. Resolve dependencies and resource ownership before dispatch. Keep protected oracle tests, credentials and unnecessary context private. Every supplied constraint counts toward the assessed input limit; do not omit a requirement to fit the model. Unsupported context, capability, tool requirements or task budgets keep work native.

The local model receives supplied text only. It cannot load installed skills, invoke plugins, run commands, write project files or attest compliance. The coordinator performs required tool actions and independently verifies each applicable requirement before integration. This is a coordinator obligation, not automatic semantic enforcement by the HTTP helper.

Local HTTP calls do not invoke native `SubagentStart`/`SubagentStop` hooks. Do not create a fake native agent or treat a local response as a native delegation report. Native fallback must use the active harness's actual declaration/report contract and authorized model/effort. When Vibe's guard applies, create its bounded declaration at the active harness root using the claimed fallback task name, include its exact pointer in the native message, and preserve the stable dispatch/reconciliation identity. If that native route is unavailable or disallowed, the coordinator retains the task.

Keep native authentication, provider, defaults, permissions and hooks unchanged. No copied skill catalog, parallel policy file or Vibe installation is needed. Read the active project's current policy at dispatch; this mapping does not pin or replace it.

## Brief schema

A schema-2 brief has exactly `schema_version`, `origin_chat_id`, `task_key`, `capability`, `source_root`, `files`, `editable_paths`, `behavior_contract`, `task_requirements`, `acceptance` and `fallback`. Paths are relative to a canonical source root, with no symlinks/traversal. Supply at most eight UTF-8 files, 100,000 bytes each, mapped to `{content, sha256}`. New files must be absent at the snapshot. No deletes, renames, binary or mode changes.

- Capabilities: `python_code_change`, `code_change`, `test_writing`, `file_summary`.
- Requirements: `language`, `complexity` (`simple`, `moderate`, `complex`), `context_bucket`, `urgency` (`normal`, `urgent`), positive `wait_budget_seconds`. Match an assessed approval scope; context bounds measure serialized input bytes, not guessed tokens.
- Fallback: exact `{model, reasoning_effort}`. Persist it before local selection; never read an unrelated default.
- Acceptance: `{method, criteria, protected_paths, checks}`. Method is `native_verified` for general work. Each trusted check is `{id, argv, cwd, timeout_seconds}`; executable is absolute, cwd is `.` or a safe relative directory. Checks and criteria remain outside model input.
- Protected Python verification also retains `supplied_tests`, `independent_tests` and `checks` from the [protected Python verification contract](python-checks.md), with acceptance method `python_isolated`.

`python_code_change` names the restrictive Python verification path; it does not describe the whole delegation system. Updates never transfer or widen approval. Assessment fixture updates require fresh assessments; saved evidence is retained rather than relabelled.

Code output is `{files, summary}` with complete replacement text for allowed paths only. Summary output is `{summary, claims}`; each claim has `text`, `path`, `sha256`, `start_line` and `end_line`. Summary briefs have no editable paths or executable checks.

`verify prepare --job ID` returns a private staging path and session binding: `session_token`, `job_id`, `attempt_id`, `native_task_id`, `candidate_hash`, `source_hash`, `acceptance_hash`. `verify checks --job ID` executes declared commands in qualified macOS isolation, with credentials cleared and resource/time bounds. Native Codex independently reviews semantics and records an object containing those seven binding fields plus `criteria` (booleans in order), `checks` (ID to boolean), and `claims` (booleans in order). Every required item must be true. `verify record --job ID --receipt FILE` rechecks identity, source and attempt. This trusts native review; it does not prove semantic quality cryptographically.

Wait decisions are `{action:"extend", until:EPOCH_SECONDS, reason:TEXT}` or `{action:"fallback", reason:TEXT}`. Extensions preserve original queue age. Expiry pauses admission for native judgment; it does not cancel peers or automatically POST.

Outcome receipts contain `native_usage:{kind:"unknown"|"tokens",value:null|INTEGER}`, `coordination_tokens`, `checking_tokens`, `fallback_tokens`, `native_baseline_tokens` and `onboarding_tokens` (each integer or null), positive `latency_seconds` and `provenance`. Baseline measurements must be comparable to the same task. Amortize recorded onboarding tokens over accepted tasks for the same artifact. Unknown onboarding cost keeps benefit unknown. Token differences are usage proxies; subscription savings remain unknown. Failed scopes suspend further routing until reassessment.

Runtime binding trusts the owner-selected local index and matching discovery metadata, not weights in memory. Repetition detection flags eight identical 2,048-character reasoning windows; it misses other semantic loops and can flag legitimate repetition. No total inference deadline is imposed. Full reasoning is not stored.
