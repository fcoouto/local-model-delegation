# Task and native verification contracts

The delegation CLI's `--help` lists commands. State is shared at `~/.local/state/local-model-delegation`, with explicit `--state-dir` for fixtures or an existing installation. All participants must select the same queue. Routing defaults off. Profile schema 2 stores each model under `profiles/<safe-id>.json`; assessment observations never enlarge approval. Only schema-2 configuration, profiles, queues and briefs are supported.

## Coordinator policy and native subagents

The active project's instructions govern task selection, authorization, ownership
and integration. When using [Vibe Setup](https://github.com/fcoouto/vibe-setup),
read its [delegation policy and native contract](https://github.com/fcoouto/vibe-setup/blob/main/skills/vibe-setup/delegation-brief.md).
Use the destination project's installed `.codex/delegation-brief.md` and active
instructions, or source matching that installed revision; repository `main` does
not silently replace a project's reviewed policy. Do not copy Vibe's native
declaration/report schemas into this plugin or install Vibe merely to delegate.

Before submission, the coordinator reads applicable AGENTS instructions and relevant skills/plugins. Put the objective and relevant constraints in `behavior_contract`, supplied context in `files`, proposed write scope in `editable_paths`, and native verification criteria/commands in `acceptance`. Resolve dependencies and resource ownership before dispatch. Keep protected oracle tests, credentials and unnecessary context private. Every supplied constraint counts toward the approved operating input limit; do not omit a requirement to fit the model. Unsupported context, capability, tool requirements or task budgets keep work native.

The local model receives supplied text only. It cannot load installed skills, invoke plugins, run commands, write project files or attest compliance. The coordinator performs required tool actions and independently verifies each applicable requirement before integration. This is a coordinator obligation, not automatic semantic enforcement by the HTTP helper.

Local HTTP proposals do not invoke native subagent hooks. Native fallback must
satisfy the active host/project's declaration and report contract as well as this
plugin's dispatch/reconciliation protocol. If a required contract is unavailable,
retain work with the coordinator rather than guessing or bypassing it. Local
approval and routing remain governed by this plugin's contracts below.

For a new native fallback, give `fallback claim --job JOB_ID --task-name habblaud_verification` a short task description using lowercase ASCII letters, digits and underscores, starting with a letter, at most 64 characters. Omission uses the capability name. The helper appends an eight-character job suffix so recovery cannot mistake an ordinary native task with the same description for this fallback, then adds a numeric suffix on database collision. The complete name stays within 64 characters and is stored separately from the full job ID. Always dispatch and reconcile with the returned name. Repeated claims preserve the saved name/token, including older names containing job IDs. Do not rename a running or historical task to improve its banner. The native tool's task-name field cannot express parentheses, `·`, or a separate display-model field. If the name includes `via`, use the actual native model, for example `habblaud_verification_via_gpt6_1_sol` only for that selected native model. The richer `Task (via Model)` title and separate task/model values belong in chat progress; they do not create or configure the native Subagents panel.

Keep native authentication, provider, defaults, permissions and hooks unchanged. No copied skill catalog, parallel policy file or Vibe installation is needed. Read the active project's current policy at dispatch; this mapping does not pin or replace it.

## Brief and verification schema

A schema-2 brief has exactly `schema_version`, `origin_chat_id`, `task_key`, `capability`, `source_root`, `files`, `editable_paths`, `behavior_contract`, `task_requirements`, `acceptance` and `fallback`. Paths are relative to a canonical source root, with no symlinks/traversal. Supply at most eight UTF-8 files, 100,000 bytes each, mapped to `{content, sha256}`. New files must be absent at the snapshot. No deletes, renames, binary or mode changes.

- Capabilities: `python_code_change`, `code_change`, `test_writing`, `file_summary`.
- Requirements: `language`, `complexity` (`simple`, `moderate`, `complex`), `context_bucket`, `urgency` (`normal`, `urgent`), positive `wait_budget_seconds`; optional positive integer `max_output_tokens`. Match an explicitly approved operating scope; context bounds measure serialized input bytes, not guessed tokens.
- Fallback: exact `{model, reasoning_effort}`. Persist it before local selection; never read an unrelated default.
- Acceptance: `{method, criteria, protected_paths, checks}`. Method is `native_verified` for general work. Each trusted check is `{id, argv, cwd, timeout_seconds}`; executable is absolute, cwd is `.` or a safe relative directory. Checks and criteria remain outside model input.
- Protected Python verification also retains `supplied_tests`, `independent_tests` and `checks` from the [protected Python verification contract](python-checks.md), with acceptance method `python_isolated`.

`python_code_change` names the restrictive Python verification path; it does not describe the whole delegation system. Updates never transfer or widen approval. Assessment fixture updates require fresh assessments; saved evidence is retained rather than relabelled.

### Generation budgets

The profile's approved `request_settings.max_output_tokens` is the model ceiling. Set `task_requirements.max_output_tokens` to the generation allowance for this task; it includes reasoning and visible output. Omission uses the profile value, preserving saved briefs. Other request settings, including thinking, remain those approved for the model.

Choose the allowance from the task's complexity, expected answer size and comparable observations for that model. A short answer can still require substantial reasoning; input bytes and context-window size do not predict the required generation allowance. For example, an approved 32,768-token ceiling permits a 16,384-token task allowance, but those numbers are illustrative, not measured recommendations for any model. Do not silently reduce an explicit allowance to make a model eligible. An allowance above the ceiling keeps the task native unless the owner authorizes a new ceiling.

Admission and the pre-POST check require the full supplied prompt's UTF-8 byte bound, the selected generation allowance and 2,048 tokens of template headroom to fit the discovered context. No total inference deadline is added. Stale and loop monitoring remain active.

Verified budget exhaustion records terminal identity, token counts and an answer hash, completes only that generation's attempt, and requests native fallback. It does not accept a candidate or require a reset. Missing/malformed completion, mismatched output or generation, and uncertain historical attempts retain their protections. Never release old uncertain work from its reason code alone. New jobs record effective request settings; old evidence is not rewritten. A larger budget on a later authorized task does not justify replaying completed work.

Code output is `{files, summary}` with complete replacement text for allowed paths only. Summary output is `{summary, claims}`; each claim has `text`, `path`, `sha256`, `start_line` and `end_line`. Summary briefs have no editable paths or executable checks.

Candidate output may be plain JSON or one complete Markdown block fenced with three backticks, with an optional lowercase `json` label. No surrounding prose, multiple documents or partial extraction is accepted. The original byte limit, strict JSON decoder and all proposal checks still apply; saved state and receipts require plain JSON.

`verify prepare --job ID` returns a private staging path and session binding: `session_token`, `job_id`, `attempt_id`, `native_task_id`, `candidate_hash`, `source_hash`, `acceptance_hash`. `verify checks --job ID` executes declared commands in qualified macOS isolation, with credentials cleared and resource/time bounds. Native Codex independently reviews semantics and records an object containing those seven binding fields plus `criteria` (booleans in order), `checks` (ID to boolean), and `claims` (booleans in order). Every required item must be true. `verify record --job ID --receipt FILE` rechecks identity, source and attempt. This trusts native review; it does not prove semantic quality cryptographically.

Wait decisions are `{action:"extend", until:EPOCH_SECONDS, reason:TEXT}` or `{action:"fallback", reason:TEXT}`. Extensions preserve original queue age. Expiry pauses admission for native judgment; it does not cancel peers or automatically POST.

Outcome receipts contain `native_usage:{kind:"unknown"|"tokens",value:null|INTEGER}`, `coordination_tokens`, `checking_tokens`, `fallback_tokens`, `native_baseline_tokens` and `onboarding_tokens` (each integer or null), positive `latency_seconds` and `provenance`. Baseline measurements must be comparable to the same task. Amortize recorded onboarding tokens over accepted tasks for the same artifact. Unknown onboarding cost keeps benefit unknown. Token differences are usage proxies; subscription savings remain unknown. Failed scopes suspend further routing until reassessment.

Runtime binding trusts the owner-selected local index and matching discovery metadata, not weights in memory. Repetition detection flags eight identical 2,048-character reasoning windows; it misses other semantic loops and can flag legitimate repetition. No total inference deadline is imposed. Full reasoning is not stored.

## Project-bound evidence and scope

New project qualification uses exact canonical repository identity from `projects.resolve_project_identity`, shared by its ordinary worktrees. Approval scope may additionally contain `project` (`kind`, `identity`) and `assessment_id`. Project entries match only that identity plus the existing capability/language/complexity/context/input budget. Role and specialty labels cannot expand scope. Existing entries without `project` are legacy global permission, not retroactive project evidence. Preserve their meaning until explicit owner-authorized migration. Changed approval invalidates queued snapshots before execution.

Difficulty values are exact: `simple`, `moderate`, `complex`, `extra_complex`. A larger context or a passing extra-high example never promotes lower-scope approval. Project campaigns have separate unapproved profiles and permits; campaign success cannot activate ordinary routing. See the [assessment procedure](../../assess-my-model/references/operations.md#project-campaigns-default) for cycles, frozen budgets and hidden-check boundaries.
