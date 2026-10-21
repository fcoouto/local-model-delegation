# Local Model Delegation

Delegate bounded text and code work to assessed local models, with native verification and fallback. The shared core is host-agnostic; this first plugin targets **Codex on macOS with LM Studio over HTTP**. Claude integration is future work.

**Development preview. Routing stays disabled by default.** Cloning this repository installs nothing, approves no model and changes no provider or authentication settings. MIT licensed.

## What it does

- Assesses package-owned synthetic tasks before recommending a narrowly scoped model approval.
- Supports Python repairs, test writing, small code changes and file summaries. Contracts support other languages; bundled assessment coverage currently includes simple Python, JavaScript and text cases.
- Shares a durable queue and measured per-instance slots across projects. Healthy work can finish while other tasks wait.
- Detects silence, a defined repeated-reasoning pattern and exhausted output budgets. It has no total inference deadline.
- Stages proposals for protected Python checks or trusted native verification. The helper never applies project files.
- Keeps exact native fallback settings and durable dispatch claims. Ambiguous dispatch is reconciled, never blindly repeated.
- Exports optional read-only task visibility, enabled by default independently of routing. No viewer is required.

The objective is lower native usage without lower quality. **No net subscription saving is qualified yet.** Token differences are labelled proxies and include coordination, verification and fallback overhead.

## Clone and inspect

Requires Python 3.11+, macOS and a qualified `sandbox-exec` boundary for executable candidates. Source runtime uses only the standard library.

```sh
git clone https://github.com/fcoouto/local-model-delegation.git
cd local-model-delegation
python3.11 -B skills/local-python-repair/scripts/repair.py --help
python3.11 -B skills/local-python-repair/scripts/repair.py doctor
```

Doctor is read-only and does not contact LM Studio unless `--inspect-runtime` is explicitly requested with a configured loopback endpoint. It does not install dependencies.

The root [plugin manifest](plugin.json) packages the [setup skill](skills/setup/SKILL.md), [delegation workflow](skills/local-delegation/SKILL.md) and retained Python helper. Use native Codex plugin installation controls when ready to install; no separate installer or daemon is provided. The package follows the [official plugin format](https://developers.openai.com/plugins/build/plugins). Public source availability is separate from plugin-directory publication or live qualification.

After authorized installation, `setup` initializes disabled private state. Installation, standing assessment consent, exact-model approval and routing activation remain separate decisions. Current builds/tests do none of those on the developer's real machine.

## Shared state and updates

All projects use `~/.local/state/codex-local-repairs` by default, preserving the existing helper's state location. Override `--state-dir` only deliberately, such as disposable fixtures. Schema 2 separates `config.json` from `profiles/<profile_id>.json`. Profiles, approvals, database, model results and receipts stay private; weights remain where LM Studio manages them.

`migrate` backs up exact legacy configuration bytes and SQLite state, disables the old entry point, and refuses unresolved work. Migration never enables routing. `prepare-update` refuses unsettled work. Detached workers use verified content-addressed helper bundles outside mutable plugin caches; retain those bundles while jobs depend on them. No database rollback command can erase newer job history. `prepare-uninstall` disables admission and removes the current visibility export only after work settles; models, history and visibility preference remain. Native package removal follows that preparation.

## Contracts and trust

Read [task/verification contracts](skills/local-delegation/references/contracts.md) and [visibility format](skills/local-delegation/references/visibility.md). Keep origin/task keys stable through compaction. Wait-policy expiry requests an automatic native routing decision, not an owner model-selection prompt. The coordinator applies only accepted proposals after checking current source hashes.

Approval binds artifact hashes, runtime key/index metadata, settings and permitted scope. Replacing bytes or identity requires fresh confirmation. Runtime identity trusts LM Studio/Bionic's owner-selected local index and matching discovery metadata; it does **not** attest weights in memory. Missing or ambiguous identity stays closed. Per-model profiles may reference a token environment-variable name; never store tokens in profiles or evidence.

Capacity comes from measured correct batches tied to machine, artifact, settings and runtime context, capped by discovered concurrency and fresh resource observations. Disk size is not a thread limit. Shared reservations cover participating callers; unrelated runtime clients remain outside the helper's slot accounting. Existing external instances are never adopted for unloading.

**Automatic loading/reloading is gated.** The documented [HTTP load API](https://lmstudio.ai/docs/developer/rest/load) does not establish a memory-estimation/non-eviction contract. The adapter returns `lifecycle_unqualified` without a load POST. No CLI workaround or global-setting change is used. Schema-2 uncertain slots stay closed without a verified reset. Legacy schema-1 recovery is retained for compatibility; migration requires it to be settled first.

Python checking retains strict import/member/mutation guards, separate protected tests and private result markers. General code checks run predeclared commands with cleared credentials in qualified macOS isolation; missing toolchains stay native. A private receipt binds the proposal, source, checks, attempt/native ID and session token. Semantic acceptance trusts native review; model output cannot certify itself.

Reasoning monitoring retains counts and hashes, not full reasoning. Eight identical 2,048-character reasoning windows trigger suspected looping; other loops can escape detection and legitimate repetition can trigger it. Known budget exhaustion rejects completion. A closed socket never proves model cancellation.

## Offline verification and remaining gates

```sh
python3.11 -B -m unittest discover -s tests -t . -q
git diff --check 950c12dd763f2ecbc905ab9c034a1b3376503edb
```

Tests use fictional approvals, disposable state and loopback fake servers. They include real macOS Python/JavaScript isolation canaries. Private historical evidence stays outside this repository.

Still unqualified: real approved-model end-to-end execution, automatic model lifecycle, thinking-enabled two-slot recovery, native host dispatch/automatic compaction continuity, install/update behavior in the target desktop, broader language/model reliability and net account savings. No real inference should be run merely to replay a saved candidate.

The bundled skill validator currently cannot run under Python 3.11 because PyYAML is absent. This does not add a runtime dependency. Offline tests validate package paths and behavior; they do not substitute for live skill-selection or desktop qualification.
