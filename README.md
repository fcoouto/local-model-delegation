# Local Model Delegation

**Let your agent set up local delegation with you, one step at a time.**

Local models handle tasks they have demonstrated they can do. Your native agent checks their work and provides fallback.

## Start with one prompt

Open **Codex on your Mac** with access to local files and a terminal, then paste:

```text
Read https://raw.githubusercontent.com/fcoouto/local-model-delegation/main/docs/onboarding.md and guide me through setup on this computer, reusing what is already configured, asking one question at a time when needed, and verifying each completed step.
```

Your agent checks the environment, handles the available setup steps, and asks for your input when it reaches a decision. If a step needs a click in another app, it gives you that single action and continues when you return. You do not need to prepare configuration files yourself.

**Already started? Use the same prompt to resume.** The agent reuses your installation, settings and shared state instead of starting over.

The link reads the version published on `main`. To try an unpublished checkout, ask your agent to read its local `docs/onboarding.md` instead. A chat without local computer access can explain setup but cannot perform or verify it.

**Development preview. Routing stays disabled by default.** Installation, permission for model assessments, approval of a tested model and task scope, and activation are separate decisions. You can pause and resume later.

## Update your plugin

Already installed? Open Codex with local computer access and paste:

```text
Read https://raw.githubusercontent.com/fcoouto/local-model-delegation/main/docs/updating.md and guide me through updating Local Model Delegation to the latest published numbered release. Preserve my settings, approvals and history, and verify the installed version and saved state.
```

The agent checks your installed version, stages the release, backs up private state, updates through Codex's native plugin installer, and verifies the result. It pauses for active or uncertain tasks. Updating never approves a model or enables delegation. A merged PR does not update installed plugins; a numbered release must be published first.

Reopen Codex or start a fresh chat if the host needs to reload skills. The agent distinguishes verified package files from verified skill discovery. See the [update guide](docs/updating.md) for details and [release notes](CHANGELOG.md) for changes.

## Choose where to start

| Your situation | Start here | What happens |
|---|---|---|
| New to local delegation | Paste the prompt above | The agent checks prerequisites and guides installation and setup |
| Partly configured | Paste the setup prompt | The agent resumes at the first unfinished step |
| Want the latest plugin version | Paste the update prompt | The agent preserves state and verifies a numbered update |
| Want to inspect the project first | [Clone and inspect](#clone-and-inspect) | Read the source and run a read-only check |
| Want the technical details | [Shared state](#shared-state-and-updates) · [Contracts](#contracts-and-trust) | Review storage, approvals, verification and limits |

## What onboarding looks like

1. **Check:** detect supported tools, an existing installation and saved configuration.
2. **Prepare:** install missing prerequisites with your authorization and connect to your selected local server.
3. **Assess:** with your consent, test a candidate model on package-owned synthetic tasks and report what passed.
4. **Decide:** approve the exact demonstrated scope, then separately choose whether to enable delegation.
5. **Verify:** report what was checked, what remains pending and how to resume. “Installed” does not mean “ready to delegate.”

**Supported today:** Codex on macOS, Python 3.11+, and LM Studio over a loopback HTTP connection. Executable candidates require qualified macOS isolation. The shared core is host-agnostic; Claude integration, other runtimes and non-text tasks are future work. Automatic model loading remains unavailable until qualified; the agent reports a model-loading blocker instead of bypassing it.

Read the [onboarding guide](docs/onboarding.md) for the agent's workflow and [onboarding evaluation](docs/onboarding-validation.md) for what has been tested. Cloning this repository installs nothing, approves no model and changes no provider or authentication settings.

## What it does

- Assesses package-owned synthetic tasks before recommending a narrowly scoped model approval.
- Supports code changes, test writing and file summaries. Contracts support multiple languages and complexity levels; bundled assessment coverage currently includes simple Python, JavaScript and text cases.
- Shares a durable queue and measured per-instance slots across projects. Healthy work can finish while other tasks wait.
- Detects silence, a defined repeated-reasoning pattern and exhausted output budgets. It has no total inference deadline.
- Stages proposals for protected Python checks or trusted native verification. The helper never applies project files.
- Keeps exact native fallback settings and durable dispatch claims. Ambiguous dispatch is reconciled, never blindly repeated.
- Exports optional read-only task visibility, enabled by default independently of routing. No viewer is required.

The objective is lower native usage without lower quality. **No net subscription saving is qualified yet.** Token differences are labelled proxies and include coordination, verification and fallback overhead.

## Measurements per project

Private scorecards separate each project, model version, and task scope: candidate acceptance, delivery without native rewriting, fallback, reported corrections, timing, admission observations, and attributable native-token savings. Synthetic trials stay separate. Missing usage or comparable baselines means savings remain unknown.

Use `python3.11 -B delegate.py metrics report --project PROJECT_ID --format text` after recording evidence. Fresh authorized setup initializes collection; existing state uses `metrics init`. [Commands and receipt contracts](skills/local-delegation/references/measurements.md) cover registration, delivery, usage, and separately authorized comparisons. These commands never execute comparisons or alter routing/approval. Optional visibility follows the existing switch.

Automatic native usage capture and real-project savings still require host qualification. The scheduler retains its earlier model-global benefit policy; project-aware automatic routing is not implemented by these reports.

## Clone and inspect

Requires Python 3.11+, macOS and a qualified `sandbox-exec` boundary for executable candidates. Source runtime uses only the standard library.

```sh
git clone https://github.com/fcoouto/local-model-delegation.git
cd local-model-delegation
python3.11 -B delegate.py --help
python3.11 -B delegate.py doctor
```

Doctor is read-only and does not contact LM Studio unless `--inspect-runtime` is explicitly requested with a configured loopback endpoint. It does not install dependencies.

The root [plugin manifest](plugin.json) packages the [setup skill](skills/setup/SKILL.md), [delegation workflow](skills/local-delegation/SKILL.md) and shared [delegation core](local_model_delegation/). The core is implemented in Python; that does not limit delegated tasks to Python. Use native Codex plugin installation controls when ready to install; no separate installer or daemon is provided. The package follows the [official plugin format](https://developers.openai.com/plugins/build/plugins). Public source availability is separate from plugin-directory publication or live qualification.

After authorized installation, `setup` initializes disabled private state. Installation, standing assessment consent, exact-model approval and routing activation remain separate decisions. Current builds/tests do none of those on the developer's real machine.

## Shared state and updates

All projects use `~/.local/state/local-model-delegation` by default. Override `--state-dir` deliberately, such as for disposable fixtures or an existing installation. All participating projects must select the same state directory. Schema 2 separates `config.json` from `profiles/<profile_id>.json`. Profiles, approvals, database, model results and receipts stay private; weights remain where the runtime manages them.

Only current schema-2 configuration, profiles, queues and task briefs are supported. Obsolete directory detection, task aliases, worker script aliases and schema conversion commands have been removed. Unsupported state is rejected without rewriting its evidence. Custom directories remain explicit; do not move saved state or create a second active queue for the same runtime.

### Server connection and supported runtimes

The plugin does not scan ports or automatically locate the server. Select its loopback HTTP URL during setup. Optional `endpoint` and `token_env` fields in shared `config.json` supply `doctor --inspect-runtime`; `discover --endpoint URL` uses its explicit argument without saving it. Each model profile also contains an `endpoint`, which is the authoritative connection for that model's requests and is bound into its approval. Changing the shared discovery URL does not move existing profiles. Changing a profile's URL requires renewed assessment and approval. The coordinator manages these files; ordinary delegated tasks do not require manual configuration.

Only the `lmstudio_v1` adapter is implemented. It uses the native `/api/v1/models` and `/api/v1/chat` APIs plus the owner-trusted local model index. GGUF, MLX and Splash text models can be assessment candidates; discovery does not qualify or approve them. Other inference platforms are unsupported, even when they offer OpenAI-compatible chat endpoints. They need adapters with verified discovery, identity, progress, capacity and lifecycle behavior. Current endpoints accept only `http` on literal `127.0.0.1` or `::1`; remote servers, non-text tasks and unrestricted model tools are outside this version.

Numbered updates follow the [guided update procedure](docs/updating.md). `prepare-update --target PATH` backs up settings, approvals and history, binds the target package digest, and refuses unsettled work. `verify-update --receipt FILE` checks the installed bytes and preserved state. Detached workers use content-addressed helper bundles outside mutable plugin caches; retain those bundles while jobs depend on them. No database rollback command can erase newer history. `prepare-uninstall` disables admission and removes the current visibility export only after work settles; models, history and visibility preference remain. Native package removal follows that preparation.

## Contracts and trust

The **host agent** prepares context, chooses tasks, verifies results and applies accepted work. The **runtime** serves local models. A model's approved **capabilities** describe which task families and operating limits it has demonstrated. A **task brief** contains the supplied context and acceptance requirements; a **candidate** is the proposed output awaiting verification. These terms apply across task types and host integrations.

Read [task/verification contracts](skills/local-delegation/references/contracts.md) and [visibility format](skills/local-delegation/references/visibility.md). Keep origin/task keys stable through compaction. Wait-policy expiry requests an automatic native routing decision, not an owner model-selection prompt. The coordinator applies only accepted proposals after checking current source hashes.

Protected Python tasks use `python_code_change` within the delegation workflow and its [Python verification contract](skills/local-delegation/references/python-checks.md). Approval remains bound to the exact recorded scope. A package update never transfers or widens approval.

Approval binds artifact hashes, runtime key/index metadata, settings and permitted scope. Replacing bytes or identity requires fresh confirmation. Runtime identity trusts LM Studio/Bionic's owner-selected local index and matching discovery metadata; it does **not** attest weights in memory. Missing or ambiguous identity stays closed. Per-model profiles may reference a token environment-variable name; never store tokens in profiles or evidence.

Capacity comes from measured correct batches tied to machine, artifact, settings and runtime context, capped by discovered concurrency and fresh resource observations. Disk size is not a thread limit. Already-loaded requests retain a 4 GiB host reserve and budget the measured additional memory per task. New loads retain the larger `max(4 GiB, 20% of RAM)` reserve. Both paths reject elevated pressure, increasing swap-outs and stale observations. Synthetic calibration starts with one task and at least 1 GiB of extra headroom. Native samples compare host availability and runtime-process memory against their pre-request baseline; the request budget adds the larger of 50% or 256 MiB to the observed peak. Sampled peaks are provisional observations, not guaranteed upper bounds. Active and uncertain requests retain their recorded memory reservations, and workers recheck resources after artifact authorization before posting. Shared reservations cover participating callers; unrelated runtime clients remain outside the helper's slot accounting. Existing external instances are never adopted for unloading.

**Automatic loading/reloading is gated.** The documented [HTTP load API](https://lmstudio.ai/docs/developer/rest/load) does not establish a memory-estimation/non-eviction contract. The adapter returns `lifecycle_unqualified` without a load POST. No CLI workaround or global-setting change is used. Schema-2 uncertain slots stay closed without a verified reset.

Python checking retains strict import/member/mutation guards, separate protected tests and private result markers. General code checks run predeclared commands with cleared credentials in qualified macOS isolation; missing toolchains stay native. A private receipt binds the proposal, source, checks, attempt/native ID and session token. Semantic acceptance trusts native review; model output cannot certify itself.

Reasoning monitoring retains counts and hashes, not full reasoning. Eight identical 2,048-character reasoning windows trigger suspected looping; other loops can escape detection and legitimate repetition can trigger it. Known budget exhaustion rejects completion. A closed socket never proves model cancellation.

## Offline verification and remaining gates

```sh
python3.11 -B -m unittest discover -s tests -t . -q
git diff --check 950c12dd763f2ecbc905ab9c034a1b3376503edb
```

Tests use fictional approvals, disposable state and loopback fake servers. They include real macOS Python/JavaScript isolation canaries. Private historical evidence stays outside this repository.

Still unqualified: real approved-model end-to-end execution, automatic model lifecycle, thinking-enabled two-slot recovery, native host dispatch/automatic compaction continuity, fresh desktop skill discovery after updates, broader language/model reliability and net account savings. No real inference should be run merely to replay a saved candidate.

Skill validation uses the bundled validator with Python 3.11 and PyYAML 6.0.3. PyYAML is a validation dependency, not a plugin runtime dependency. Both source skills pass structural validation; see the [validation record](docs/project-measurements-validation.md). These checks do not install skills or substitute for live skill-selection or desktop qualification.

## Credits and license

The prompt-first entry and guided setup structure are inspired by the [Vibe Coding Toolkit README](https://github.com/soumatheusgomes/vibe-coding-toolkit). Local Model Delegation is [MIT licensed](LICENSE).
