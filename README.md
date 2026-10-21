# Codex Local Repairs

Personal, HTTP-only delegation for bounded pure-Python repairs. Routing is disabled by default. No model is approved or skill installed by this repository.

Requires Python 3.11+ and macOS for isolated candidate execution. No third-party packages.

Run offline checks from this source root:

```sh
python3.11 -B -m unittest discover -s tests -t . -v
```

## Commands and installation boundary

The source skill is `skills/local-python-repair/`. Run it directly without installation:

```sh
python3.11 -B skills/local-python-repair/scripts/repair.py --help
python3.11 -B skills/local-python-repair/scripts/repair.py --state-dir /absolute/private/state submit --brief /absolute/private/brief.json
python3.11 -B skills/local-python-repair/scripts/repair.py --state-dir /absolute/private/state lookup --chat origin-id --task-key stable-key
```

Read the skill and its brief contract before use. With missing or disabled configuration, submission returns `not_eligible` without creating state, connecting to a model or starting a process. The proposed personal state home is `~/.local/state/codex-local-repairs`; no live configuration is shipped. Its future `profiles.json` starts as:

```json
{"schema_version":1,"routing_enabled":false,"preferred_by_capability":{},"profiles":{}}
```

Do not install the skill, approve a real artifact or activate routing as part of building or testing this repository. Later installation would link the source skill into the owner's skill directory, after explicit authorization. No command here performs installation or activation. `profile inspect` hashes a separately supplied artifact; `profile record-approval` records an actual owner's confirmation reference in that supplied private profile file. Never infer or invent that confirmation from benchmark results. Approval records and routing activation are separate.

## Behavior and limits

Each owner-selected local profile supplies its model identifier, enumerated artifact files, approved capability/request settings, explicit OpenAI fallback model/effort, and one positive `stale_tolerance_seconds`. Qwen's intended settings are thinking ON, 120-second silence tolerance, and `gpt-6.1-sol` / `medium` fallback; they are not installed defaults or an approval. Capability evidence is optional. Actual artifact bytes are hashed; API names alone do not identify a version. Hashing is conservative and currently repeated at eligibility checks, which adds unmeasured I/O latency.

Live capacity comes from HTTP model discovery. Shared SQLite reservations account only for participating Codex callers. A new unknown loaded instance stays closed until controlled recovery verifies the approved artifact. Busy requests do not POST into a model queue. In-flight uncertain slots remain reserved until verified reset; healthy peers finish first. Changing runtime configuration outside the helper between discovery and POST remains a race.

Detached observers retain job/attempt IDs, answer hashes and activity counts, not full reasoning. A model fragment or valid forward phase change refreshes its stale clock; observer heartbeats do not. Active inference has no total timeout. Keepalives, empty fragments and repeated percentages cannot prevent staleness. A socket close is not proof of cancellation.

Native OpenAI fallback is orchestrated by Codex, not by Python. Claims persist before native dispatch, and task identifiers persist afterward. An ambiguous dispatch is reconciled or reported `dispatch_uncertain`; it is never blindly repeated or silently changed to another model. Compaction may defer native dispatch until Codex resumes. A stopped Codex app cannot dispatch cloud work until native execution resumes.

Candidate checking protects supplied tests, runs independent oracles separately from model tests, verifies effective regressions against the buggy source, and checks original source hashes. The helper does not apply project files. MacOS candidate isolation denies network, private file reads and writes outside disposable fixtures. It permits reads of the Python installation and public system libraries, plus root-directory metadata/listing needed by the runtime. The supported structural subset is intentionally narrow; it is not an arbitrary-code runner. Check processes have a separate 60-second deadline and resource limits.

## Qualification

Offline tests use fictional model approvals and an actual loopback fake server; they never contact a real model. They exercise cross-process reservations, monitor death, detached observation, lost lifecycle replies, healthy-peer protection, native dispatch records, and real macOS candidate isolation.

Actual approved-model end-to-end operation and automatic desktop-host continuation through compaction remain separate activation gates. Native task model/effort declarations are requested settings, not independent serving-model attestation. No net subscription saving is claimed. Keep private benchmark evidence outside this portable source repository.

`tests/live_acceptance.py` provides explicit `inspect` (HTTP discovery only), `native-prepare` (fictional local profile; no local HTTP), and `native-verify` (attach/check an actual native result) cases. It refuses non-temporary state paths and never approves a real model. Native model repair tests are functional qualification, not independent code review. Native task listings can reconcile canonical task names; an absent listing cannot prove a lost dispatch never happened.

The bundled skill-format validator currently requires unavailable PyYAML on this machine. The source has no such dependency; its simple frontmatter/name/links and Python syntax are checked directly. Host-level automatic skill selection and desktop compaction continuity remain unqualified while the skill is uninstalled.
