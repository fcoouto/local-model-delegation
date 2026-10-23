# Repository-backed assessment harness

Date: 2026-10-23. Status: approved for inline implementation on 2026-10-23. No model generation is authorized.

## Intent and acceptance

Support the owner's complete eight-assignment backend portfolio without reducing task scope or replacing real framework and database verification. Preserve two light, three medium, two high and one extra-high assignments. Prepare the frozen Qwen campaign after all references and deliberately failing bases are verified. Preparation does not generate model responses, approve new delegation scope or change routing.

This extends the approved project-assessment design. Three current limits prevent faithful evaluation: the supplied-file boundary is eight files of 100,000 bytes each; models return whole replacement files; executable checks deny all networking and lack a qualified database environment. A larger file limit alone does not solve prompt capacity, large replacement output or real concurrency verification.

Completion requires all eight assignments to have complete source/dependency environments, executable public and hidden checks, passing references, meaningful failing bases, independent semantic review, exact provenance and measured runtime budgets. Unsupported or unmeasured prerequisites remain blockers, never model failures. The final frozen preview must be ready for run consent, with no assessment inference performed during preparation.

## Approaches

1. **Increase inline file limits and allow local database ports.** Smallest diff, but it leaves oversized prompts, wasteful whole-file output and access to unrelated local services. Rejected: it does not satisfy the task or preserve isolation.
2. **Extend native macOS isolation around a host PostgreSQL process.** Can preserve the current runner, but requires a new qualified filesystem/socket/process boundary across a host database and its dependency tree. Retained as a possible later adapter, not required for this portfolio.
3. **Frozen repository fixtures, bounded source access and container-isolated checks.** Recommended. Reuse the current queue, campaign coordination and native acceptance. Add a versioned repository-task protocol and an explicit Docker verification backend. Docker and PostgreSQL images are already available on the owner's host; their presence is inventory evidence, not security qualification.

The coordinator proposes option 3. It is a larger change than raising constants because it addresses the actual context, output and verification barriers. The following choices are proposed implementation decisions, not previously granted run consent.

## Frozen source and dependency environments

Materialize an explicitly reviewed allowlist of regular Git blobs at a full commit into private assessment storage. Do not export the working directory wholesale. Reject symlinks, submodules, special files, traversal, case-colliding names and paths outside the selected repository. Exclude Git metadata, credentials, environment files, local databases, caches, build artifacts and unrelated private documents. Never follow imports into the owner's live checkout to fill a missing dependency.

Every assignment has a source manifest containing path, byte count and SHA-256, plus canonical repository identity and base/reference revisions. A constructed task records the exact reviewed regression against its source commit. The fixture can contain complete large modules and framework dependencies without embedding all of them in each model prompt. An initial limit of 4 MiB per regular text source file, 128 MiB total fixture contents and 8,192 regular files is proposed. These are host storage/verification bounds, independent of model context and output bounds. Validate limits before allocation and during materialization. Missing essential sources fail preparation; never truncate a module to fit.

Separate three manifests:

- Public task source, existing public tests and permitted documentation available to the model.
- Public evaluator assets available only when running public checks, with no reference solution or hidden criteria.
- Final evaluator assets and reference replacements, private to reference validation and final verification.

Reference commits, future solution-bearing history and hidden fixtures must never enter the model-readable tree. Public checks run without hidden assets mounted. Final checks never feed their output into a later model request. Environments and snapshots are frozen by digest and revalidated before use; changes invalidate remaining consent. Disposable candidate trees never modify the original repository or frozen source.

Use a reviewed, digest-pinned Python dependency image. Build only from a small explicit dependency context and pinned packages; do not send a repository, home directory, Docker credential store or live environment into an image build. Reuse qualified existing artifacts when their complete provenance matches. Dependency acquisition/build happens during preparation, separately from candidate execution. No host Python package installation or service reconfiguration is required. Missing private dependency access remains an explicit blocker.

## Bounded model workspace protocol

Introduce a new versioned project execution/brief contract. Existing schema-1 fixture assessments, schema-2 project campaigns, ordinary briefs, approvals and saved responses retain their validation and behavior. Do not globally relax their limits or silently upgrade saved runs. The implementation plan must enumerate every admission, worker, resume, verification, reporting and approval caller that recognizes the new contract.

The model receives the task, permitted edit paths, a public source index and a bounded initial context selected before the run. It can request only deterministic operations over the frozen public manifest:

- List entries under a validated relative directory, with explicit pagination.
- Read a validated text file through a bounded UTF-8 byte window, returning its whole-file hash, exact byte offsets, line positions and whether either boundary is a partial line. Requests must begin at a UTF-8 character boundary; responses never split a character. The continuation cursor identifies the next byte offset, so a line larger than the response cap remains completely addressable across requests.
- Search a bounded subset of public files for a literal string, with explicit result and byte limits. No regular-expression execution or shell commands.
- Submit exact source edits for native checking.

No arbitrary shell, HTTP, package installation, database access, host filesystem access or native-generated advice is exposed to the model. Source content remains untrusted data. The coordinator executes these narrow operations; it never chooses a fix or summarizes missing code on the model's behalf.

Each serialized context response is capped at 32 KiB, including JSON escaping and metadata; list/search responses indicate truncation and a continuation cursor. Search returns byte offsets and bounded snippets, not an unbounded matching line. All public source remains addressable, including a single line approaching the file-size limit. Test multibyte UTF-8 boundaries, oversized lines, escaping expansion and exact continuation without gaps or duplicate bytes. A prompt must fit the existing conservative UTF-8 context bound unless exact tokenization is separately qualified for the bound runtime. Keep the task, edit policy, current candidate hash and requested view; retain prior context only within the bound. Eviction is deterministic and disclosed, never a native semantic summary. The model may reread evicted source within its allowance.

Edit proposals contain the whole-file base hash and exact nonempty old/new text replacements for allowed paths. Each old fragment must match exactly once against the same frozen/current file version. Reject stale hashes, overlapping edits, ambiguous anchors, undeclared paths, duplicate JSON keys, NULs and output/source-size violations. New files require explicitly allowed creation paths. Never use fuzzy patch matching. Compose the complete candidate natively; review and execute that complete file. The reference and native comparison use the same edit/context contract.

Allow at most three submitted proposal cycles per assignment, preserving the existing limit. Propose up to twelve additional context-operation turns across the entire assignment, not twelve per cycle. Invalid actions consume a turn; they do not reset allowances. Eight assignments therefore permit at most 24 patch submissions and 96 context turns: at most 120 local generation requests, generally fewer. This is still eight assignments, not 120 capability trials. The eventual frozen preview must disclose these counts before run consent. No new generation allowance is granted by approving this design.

Persist every operation, input/output digest, parent turn, remaining allowance and result before scheduling the next request. Reuse the existing one-slot queue, job ownership, uncertain-request recovery and runtime pins. Resume cannot replay a submitted/uncertain action, reset a cycle allowance or replace an invalid proposal with a native solution. Exhausted context, output or time remains unfinished/inconclusive.

## Isolated framework and PostgreSQL checks

Add an explicit Docker backend for repository checks; retain the current macOS backend for existing tasks. Containers use exact image IDs, `--pull=never`, `--network=none`, read-only root filesystems, non-root runtime users, all capabilities dropped, no-new-privileges and Docker's default seccomp protection. Do not grant privileged mode, host PID/network namespaces, devices or the Docker socket. Bound memory, PIDs, CPU allocation, writable storage, output and wall time in the frozen verification manifest. Keep the existing legacy checker limits unchanged.

Mount only owned disposable fixture/check assets. Public source and evaluator inputs are read-only. Candidate edits are composed before execution. Provide bounded scratch directories for Python and Django. Never mount the live repository, home, state root, environment files, SSH agents or host service sockets. Use an explicit test environment; never import production configuration to obtain database credentials. The native coordinator remains the only component that controls Docker.

For PostgreSQL cases, use a separate per-check PostgreSQL container with a fresh cluster and an owned Docker volume holding only its Unix socket. Both containers have networking disabled; PostgreSQL sets `listen_addresses=''` and publishes no host ports. The candidate/check container mounts the socket volume only, never database data or the administrator's credentials. Use PostgreSQL local authentication and a dedicated test role restricted to its disposable database. It has no superuser, database-creation, role-creation, replication, server-file or program-execution grants. No `trust` rule may let the candidate impersonate an administrator. A trusted setup phase creates the database and applies the existing reviewed migration graph before candidate code runs. Never author migrations or run `makemigrations` for these fixtures.

Candidate database permissions must support the real operation under test while withholding schema/role administration unless a specific assignment requires it. Run fixture setup and cleanup under separate trusted control. If a real Django runner needs privileges incompatible with that boundary, resolve the runner arrangement; do not grant the candidate administrator access. PostgreSQL locks and uniqueness are tested using separate real connections and observable synchronization, not timing sleeps or SQLite substitutes.

Use disposable service and evaluator containers for each base/reference/candidate verification boundary. Keep public and final checks separate, with fresh database state. Freeze selected test labels and expected discovery; no discovered tests, unexpected skips or missing concurrency assertions cannot pass. Capture exit status, discovered/executed counts, failures, skips and infrastructure errors. Native semantic review remains mandatory; container isolation is not proof that adversarial Python cannot manipulate an in-process test framework.

Qualification must demonstrate denied host-canary reads, denied writes to source/evaluator inputs, unavailable Docker socket, no external/host TCP access, restricted database role, denied SQL program/file access, successful owned-socket access and real concurrency behavior. Tests must prove a declared isolation violation blocks execution rather than falling back to an unrestricted host runner.

Name and label all containers and volumes with an owned operation ID. Persist identities before running dependent work. Reconcile timeout, interruption and restart through inspected container state; do not release ownership while execution may continue. Stop only task-owned resources, collect bounded evidence, remove them and verify absence. Cleanup failure is visible and prevents reuse. Never prune shared Docker resources.

## All-eight preparation and fair comparison

Keep the exact eight original assignment contracts. Full application/API/bootstrap cases must execute their actual relevant routing, permissions, model validation and transaction paths. A narrow projection or policy-only slice cannot substitute for the broader assignment. Keep golden fixtures and new adversarial cases private. Review all base/reference changes independently; require each reference to pass mandatory checks and each base to fail a meaningful hidden behavior check.

The private portfolio tracks per-case source completeness, public/hidden test labels, real framework/database environment, mutation/reference hashes, discovery counts, semantic review, required concurrency evidence and budget qualification. Repair an invalid fixture before grading a model. Historical reference failures remain visible; do not rewrite their outcome as a local model failure or silently change the task.

Retain the planned moderate and complex native comparison subset. Both contestants receive identical public source access and one initial proposal opportunity, including the same bounded context operations. Native comparison contexts must not inherit reference/evaluator material. Record any unenforced limit or tool asymmetry. Local multi-cycle completion remains a separate result. No fresh native comparison runs automatically during preparation.

Freeze the exact loaded Qwen identity, settings, current context and a generous runtime-supported output ceiling. Bind prefill/decode measurements and generation deadlines to that runtime; do not infer throughput or maximum output from parameter count, context size or old unrelated trials. Separate generation, context operations, checks, queue wait and human review time. Slower correct work passes. Runtime calibration that requires new generation needs explicit bounded consent; missing measurement cannot be filled with invented numbers.

The final preparation result must include all eight runnable assignments, maximum context/proposal request counts, public-feedback policy, actual resource bounds, native comparison subset and outstanding run consent. If runtime evidence is the sole missing gate, report that precise blocker and the smallest calibration proposal; do not claim a runnable frozen campaign yet.

## Verification, delivery and builder choices

The implementation needs regression tests for old contracts plus adversarial tests for manifests, paths, sizes, patch parsing, hashes, context pagination/eviction, hidden-source denial, turn accounting, queue recovery, stopped/revoked campaigns, false-pass prevention and cleanup ownership. Run the complete existing offline suite. Run separately marked real Docker/PostgreSQL qualification and all eight reference/base checks; skipped Docker tests cannot establish readiness. Obtain independent R2 security and semantic review before READY. Preserve native model/provider/reasoning/authentication and all existing approvals.

Keep project source, assessment fixtures, dependency images' private provenance and reports outside the plugin's tracked files. The plugin contains generic implementation, fictional tests and portable documentation only. The proposed execution method is inline implementation by the current coordinator, with independent final security and code review. Publish a new reviewed PR through the existing lifecycle. Do not merge, release or install this follow-up automatically under the previous release's authorization.

The builder chooses module boundaries, exact manifest field names, pagination cursor encoding and qualified container resource values. These choices must preserve the constraints above and be frozen in the final preview. Defaults should be based on observed reference checks, not guessed limits. The proposed context-turn maximum may be reduced only before consent and only if every assignment remains supported; increasing it requires a new preview.

## Sources and evidence limits

Inspected plugin source: `de2757d5390b12f7d2b69d2556ac46e2bd8e746c`. Existing code locations: `contracts.py`, `project_runs.py`, `validation.py`, `worker.py`, project reports and campaign/approval tests. Owner-selected portfolio feasibility and one verified Django fixture are recorded privately.

Documentation checked through Context7 on 2026-10-23: [Docker none network driver](https://docs.docker.com/engine/network/drivers/none/), [Docker run reference](https://docs.docker.com/reference/cli/docker/container/run/), [PostgreSQL connection settings](https://www.postgresql.org/docs/17/runtime-config-connection.html), and [PostgreSQL roles](https://www.postgresql.org/docs/17/user-manag.html). These support the proposed controls; they do not prove this host's complete isolation path. Actual qualification is a delivery gate.

Independent builder review completed on 2026-10-23. One consequential long-line access contradiction was corrected using bounded UTF-8 byte windows; focused rereview confirmed resolution. No other major planning questions remained. This is design review only, not implementation or runtime qualification.
