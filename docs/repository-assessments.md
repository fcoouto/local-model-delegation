# Repository assessment execution

Repository assignments use execution schema 2 inside new project campaigns (campaign schema 2), with brief schema 3. Existing supplied-file briefs and saved campaigns retain their original contracts. This mode supports `code_change` and `test_writing` with native semantic acceptance. It is assessment-only: ordinary routing rejects schema 3, and repository evidence cannot mint legacy supplied-file approvals (`repository_delegation_scope_not_qualified`). Qualifying ordinary repository delegation is a separate boundary.

## Preparation contract

Each execution has exactly `schema_version`, `source`, `public_assets`, `private_assets`, `setup_source`, `environment`, `editable_paths`, `criteria`, `public_checks`, `private_checks`, `reference_edits`, `review_reference`, `max_cycles`, and `budget`.

A frozen directory descriptor is `{root, manifest}`. The absolute canonical `root` contains exactly the manifest's regular UTF-8 text files. The manifest is `{schema_version: 1, files: {path: {size, sha256}}, digest}`; `digest` hashes the canonical `files` object. Source limits are 4 MiB per file, 128 MiB total and 8,192 files. Symlinks, special files, secret paths, traversal and case/Unicode aliases are rejected. Export only an explicitly reviewed allowlist of Git blobs; never copy a live checkout wholesale. `repository_context.snapshot` creates the frozen copy and `validate_snapshot` rechecks it.

`source` contains public task inputs. `public_assets` contains only public evaluator code/data. `private_assets` contains held-out evaluator code/data. Do not put hidden tests or golden references in public evaluator assets. `setup_source` is either null or a separately frozen trusted source used to create a disposable database before candidate execution. Candidate changes must never supply administrator setup code. `reference_edits` uses the exact submission format below. Keep source, fixtures, solutions and all evidence outside tracked plugin files.

`environment` has exactly `schema_version: 1`, absolute `docker_binary`, local Unix-socket `endpoint`, immutable `image`, optional immutable `postgres_image`, and `limits`. Image identities are `sha256:` plus 64 lowercase hex digits. Limits are integer `memory_bytes`, `cpus`, `pids`, `storage_bytes` and `output_bytes`. Freeze values qualified by real reference checks; image availability alone does not establish isolation.

Each check has exactly `id`, `argv`, `timeout_seconds`, `expected_tests`, and `setup_argv`. Commands begin with `/usr/local/bin/python` and execute frozen evaluator assets under `/evaluator`, with the candidate tree mounted read-only at `/source`. Writable scratch is `/work` and `/tmp`. `setup_argv` is null without PostgreSQL; database checks require a trusted setup command and source. Expected test IDs are nonempty and unique. One strict `LMD_TEST_RESULT={"tests":{"exact.test.id":"passed"}}` line must account for every expected test. `failed` and `error` fail; missing, duplicated, skipped or unexpected tests cannot pass. Candidate code shares an interpreter with framework checks, so native semantic review remains mandatory.

`max_cycles` is 1–3 proposals. The budget retains the existing exact-runtime fields: `context_length`, `output_ceiling`, `prefill_seconds`, `decode_tokens_per_second`, `measurement_reference`. Missing measurements block preparation; do not invent a budget or generate calibration responses without permission. Source size and model output limits are separate.

Use the existing `assessment project-preview` and `assessment prepare` commands. Preparation validates every reference and requires a meaningful held-out base failure. It pins source, assets, Docker executable/engine/images, model/settings and helper identity. Consent binds the returned preview. Docker dependency acquisition happens separately during authorized preparation; checks never pull images or install packages.

## Bounded source and edit protocol

The model receives the task, edit allowlist, workspace digest, initial paginated source index and remaining context allowance. It can return one of:

```json
{"action":"list","directory":"","offset":0}
{"action":"read","path":"module.py","offset":0}
{"action":"search","paths":["module.py"],"query":"literal text","offset":0}
{"action":"submit","summary":"Change description","edits":[{"path":"module.py","sha256":"base-file-hash","changes":[{"old":"unique exact fragment","new":"replacement"}]}]}
```

Read cursors are UTF-8 byte offsets; list/search cursors are result indexes. Each serialized response is at most 32 KiB, including escaping and metadata. Huge single lines remain addressable without splitting UTF-8 characters. Search is literal and limited to 64 named public files. Only the latest two views are retained, without native summaries; the model can reread evicted source.

Each edit's old text must occur exactly once in the same base file; edits cannot overlap. A new explicitly allowed file uses `sha256: null` and one change with empty `old`. No fuzzy matching, deletion, rename, mode change or binary output is supported. Full candidate files are composed natively for review and execution.

Use `assessment advance --assessment-id ID --job JOB` for both context requests and public proposal feedback. It uses the existing campaign lock, queue, attempt fencing and durable parent receipts. Invalid context actions consume a context turn. At most twelve context operations apply across the entire assignment, without reset after a proposal. Invalid proposals consume proposal cycles. Eight assignments therefore allow at most 24 proposals plus 96 context operations: 120 generation requests, not 120 assignments. Actual requests can be fewer.

Public feedback contains only deterministic public-check results and survives subsequent source requests within the proposal cycle. Submitting edits resets old views to the updated index. Starting final checks writes the durable finalization barrier before private assets become accessible; no later feedback is permitted. Exhausted context/output or infrastructure interruption is unfinished, not evidence of incapability. Slower correct work still passes. Comparison contestants receive the same public source operations and one proposal; disclose unenforced limits and other asymmetries.

## Isolation and recovery

Checks use pinned images, network none, non-root users, read-only root/source/evaluator mounts, dropped capabilities, no-new-privileges, bounded CPU/memory/PIDs/storage/output/time and no Docker or host service socket. PostgreSQL exposes only an owned Unix socket, uses fresh data and distinct administrator/candidate credentials, and gives the candidate DML access without database/role creation, schema creation or server file/program privileges. Trusted setup finishes before candidate startup. Public and final checks get fresh databases.

The private `container-checks/<operation>/operation.json` journal precedes resource creation. Recovery inspects labels and exact names, removes only owned resources and verifies absence. `container_checks.reconcile_operation(path)` refuses active-owner cleanup. Uncertain or failed cleanup blocks another check; never use shared pruning or assume killing the Docker CLI stopped its container. Private observations include setup diagnostics, bounded output, discovery results and timing. Offline unit tests do not prove host isolation; require disposable real canaries and actual PostgreSQL concurrency checks.
