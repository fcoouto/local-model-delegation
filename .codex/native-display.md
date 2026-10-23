# Native role display in Habblaud

Read this guide only for an explicit request to set up or test Habblaud. Ordinary
upgrades validate hooks and native dispatch through `qualification.md` beside the
installed Vibe Setup helper; resolve its location from the project instructions.
They do not mention, require, discover or connect to this consumer.

The optional `.codex/hooks/native_display.py` adapter wraps the existing Habblaud
`SubagentStart` hook. It changes only the event copy sent to Habblaud. It does not
change Habblaud files, native session logs, model, reasoning, provider,
authentication, permissions or agent profiles. The regular component installer
copies the adapter as an inert asset; it does not enable this integration.

## Runtime selection

1. If the incoming event has a non-null `agent_role`, preserve it. Do not read a
   declaration or calculate a replacement, including for an empty or invalid value.
2. Otherwise, locate the real child's first session metadata record in the selected
   Codex account. Match its UUID, parent UUID and working directory to the hook.
   Prefer a non-null native `agent_role` in that metadata, without deriving a role.
3. Only when both native sources lack a role, use the native `agent_path` to select
   the exact `.codex-delegations/<task_name>.json` declaration. Validate the complete
   declaration with the guard and use its canonical `role`.
4. Add the derived `agent_role` only to the outgoing copy. Supply the selected
   nonblank string as Habblaud's `agent_type` display field. This field is never sent
   to a native spawn or used to select a runtime profile.

Selection is recalculated on every invocation; no derived role cache can override
a role supplied by a later runtime version. Missing, ambiguous, malformed or
unbound evidence leaves the event unchanged. Specialties remain in the declaration;
this adapter displays the role only. Non-`SubagentStart` events pass through unchanged.

The shared badge policy calls for `<Role> · <Model Display Name>`. This adapter
currently supplies only the role; it does not yet implement that complete format.
The native model remains visible through Habblaud's existing session statistics.

The reader checks only bounded first metadata lines, never task messages. It checks
the current UTC day, adjacent days, the parent's transcript directory and, for native
UUIDv7 identities, the identity's creation day and adjacent days. Unsupported
layouts or unavailable rollout metadata retain the original label. No session logs
are rewritten. Declarations use the guard's bounded, no-symlink regular-file reader.

## Explicit setup

Review the adapter and its tests. Inspect the active Codex account's existing
Habblaud hook command and preserve a recoverable copy of that configuration.
Keep `native_display.py` and the matching `subagents.py` together in a durable,
reviewed installation directory. The latter is imported for validation; this does
not activate the Vibe guard in that account or project.

Wrap only the existing Habblaud `SubagentStart` command, preserving its other
settings and unrelated hooks. For an original command `node /path/to/hook.mjs`,
the replacement has this shape, with absolute paths and proper shell quoting:

```sh
python3 -B /path/to/native_display.py --codex-home /path/to/codex-home -- node /path/to/hook.mjs
```

The original executable and arguments run directly, without another shell. Their
stdout, stderr and exit status are preserved. Malformed or oversized input bypasses
enrichment and reaches the original hook unchanged. Do not wrap or replace the
permission hook; this integration needs no permission-policy changes.

By default, declarations come from the native rollout's `cwd`, without searching
ancestor Git roots. If a known umbrella harness owns the declarations, add
`--harness-root /absolute/harness` before `--`. The native cwd must be within that
explicit root. Do not guess a different declaration root when the record is missing.

For a shared account hook serving both an umbrella and unrelated projects, use
`--umbrella-root /absolute/umbrella` instead of `--harness-root`. This explicit mapping
asserts that sessions originating at that exact canonical root use its guard. For
a worker inside the umbrella, the adapter follows the bound native parent chain to
the originating session's initial cwd. It selects the umbrella declarations only
when that cwd equals the configured root. A standalone session originating in a
child repository retains its existing worker-cwd lookup. Other projects retain
that lookup without ancestry reads, even if the unrelated umbrella directory is
unavailable. The two options are mutually
exclusive; existing strict `--harness-root` behavior is unchanged.

For example, a non-Git `/workspace/product` may own the active guard and
`/workspace/product/.codex-delegations/reader.json`, while a worker starts in its
child repository `/workspace/product/docs`. Configure the reviewed shared wrapper:

```sh
python3 -B /path/to/native_display.py --codex-home /path/to/codex-home --umbrella-root /workspace/product -- node /path/to/hook.mjs
```

Use an absolute canonical umbrella path without symlinks or `..`. Confirm that
this root owns the active guard for sessions originating there; native metadata
does not attest which guard a client loaded. Arbitrary configurations where a
session's initial cwd differs from its guard root need a separately scoped
integration. A bound umbrella-owned child uses the umbrella declaration, even if a
nearer repository has a declaration with the same task name. A standalone child-repo
session never borrows an umbrella declaration. Missing, invalid or unsafe selected
declarations leave the event unchanged;
they never fall back to a child repository. Prefix siblings and symlink paths
resolving outside the umbrella cannot borrow its declarations. No Git repository
is required at the umbrella root, and no declarations are copied or searched for
in ancestor directories. Parent IDs and nested task paths must agree at every
ancestry step. The lookup is limited to 16 parent records and recognized native
root sources (`cli`, `exec`, `vscode`). Missing, ambiguous, cyclic, unsafe or
unsupported ancestry leaves covered events unchanged; it does not trigger a
declaration fallback. No ownership cache can outlive the current native evidence.

Package updates leave this integration inert. Adoption requires separately
updating the reviewed shared adapter and its existing hook command, preserving
unrelated hooks and client trust. Do not restart or interrupt active workers to
apply this repair. Verify delivery with a future authorized fresh worker; existing
Habblaud labels remain subject to the first-observation limitation below.

Review and trust the changed hook through the client's supported interface when
required. Never write trust hashes. Existing sessions may need a supported refresh
before new hook definitions run. Replacing the command back with its recorded
original disables the adapter; preserve other edits made since installation.

## Verification and limits

Run `python3 -B -m unittest discover -s tests -p test_native_display.py -v` from this
package, then its full test suite. Tests cover role precedence, a later native role,
binding mismatches, unlisted specialties, malformed and unsafe records, independent
children, inert installation, and preservation of the original hook behavior.

For live qualification, create fresh declarations and real native workers. Observe
their assigned roles in Habblaud and compare native model, effort, provider and
permissions with the parent. Confirm the declaration, native log and Habblaud files
were not rewritten. A fabricated hook event is not actual-client evidence.

Local qualification on 2026-10-22 used Codex CLI 0.163.0 and Habblaud 1.0.3.
Two real native workers displayed their declared `Scout` and `Reviewer` roles in
the live sidebar. Both retained the parent's model, reasoning, provider and
permission settings; their native metadata still had a null `agent_role`.
Habblaud's files and the permission hook were unchanged. The already-running
desktop chat did not invoke the newly trusted wrapper; a fresh native session did.
Hook discovery/trust, adapter unit tests and successful CLI display do not establish
that an existing desktop session has refreshed its hooks.

Habblaud 1.0.3 fixes a child's badge on first observation. An already visible child
will not be relabeled. A competing hook or filesystem observation can win that race,
and missing or not-yet-flushed metadata leaves the original label unchanged. Report
that outcome rather than inventing workers or claiming guaranteed delivery. Native
metadata remains authoritative when Habblaud sees it first; the adapter does not
provide main-agent `Coordinator` badges or broad specialist certification.

## Explicit client badge qualification

Only an explicit user request for a Habblaud test permits setting
`display_required: true` in `prepare-probe` and adding a client `display` outcome
to the update plan. Keep previously frozen requests intact; do not remove an
explicitly requested display gate from an existing receipt during an upgrade.

Start a bounded read-only Habblaud observer before `begin-probe`. Record its start
time and observe the real child. Never emit synthetic hook events or rewrite
native or consumer state as live qualification. Pass `display_evidence` alongside
the native child log and dispatch capture to `record-probe`. Missing evidence
leaves the explicitly requested display outcome incomplete.

The observation uses actual Unix-second timestamps and exact native identities:

```json
{
  "client": "app",
  "parent_thread_id": "native-parent-thread-id",
  "child_thread_id": "actual-child-thread-id",
  "role": "Tester",
  "observed_label": "Tester",
  "observer_started_at": 1000.0,
  "observed_at": 1010.0,
  "source": "habblaud",
  "snapshot": "/private/update/actual-api-or-ui-snapshot.json"
}
```

Retain the bounded actual API/UI snapshot. Python validates correlation, timing
and artifact hashes; it does not independently attest the external observation.
Keep display separate from native execution and first-report validity. A consumer
label cannot override supplied native roles or certify a model's specialty.

## Consumer compatibility reference

Role declarations guide agents; they do not automatically populate a dashboard.
The optional [native display adapter](native-display.md) forwards a bound assignment
role through the existing Habblaud hook when native `agent_role` is absent or null.
It preserves any supplied native role and does not change Habblaud or execution
settings. Installation and live delivery require separate qualification.
Keep Habblaud unchanged and qualify its existing input path separately. Inspection
and disposable source/DOM probes against Habblaud 1.0.3
([`faa1a012`](https://github.com/marmottajr/habblaud/tree/faa1a012b5fbf632c66dc6801c5383e53a542406))
on 2026-10-22 established the following behavior; recheck it when the installed version changes:

| Path | Observed behavior |
| --- | --- |
| Native child rollout | Habblaud reads `agent_role` or `agent_type` from supported spawn metadata; role text is limited to 40 characters. |
| Existing Codex hook endpoint | A child's first `agent_type` can supply the visible role. A longer composite survives the hook path. |
| Already visible child | The displayed role stays fixed. Later hooks or newly discovered rollout role metadata do not relabel it. A rollout role seen first takes precedence over the hook label. |
| Main agent | Source and badge rendering use fixed main-agent labels. `Coordinator` is an assignment role, but this version cannot display it as the main badge through these inputs. |

The [rollout parser](https://github.com/marmottajr/habblaud/blob/faa1a012b5fbf632c66dc6801c5383e53a542406/server/sources/codex/rollout.ts),
[Codex source](https://github.com/marmottajr/habblaud/blob/faa1a012b5fbf632c66dc6801c5383e53a542406/server/sources/codex/source.ts)
and [badge renderer](https://github.com/marmottajr/habblaud/blob/faa1a012b5fbf632c66dc6801c5383e53a542406/client/src/ui/widgets.ts)
are the compatibility references. These fixtures establish parsing and rendering,
not delivery from every Codex client or a live Docker/Node installation.

Inspect the active client's actual spawn schema. A native `agent_type` may select
a configuration profile with different models or permissions; never use one just
to obtain a badge. When a client exposes no independent role metadata field,
retain the role in the declaration/instructions. The optional adapter can supply
the missing display label; without observed delivery, report it as unverified.
Do not invent spawn parameters, rewrite session logs,
change native profiles or emit synthetic workers to conceal that limitation.

Native and local workers use the same display format:
`<Role> · <Model Display Name>`, for example `Reviewer · Qwen3.8 27B Splash`.
Use the explicit assignment role and the human-readable name of the actual
attempt's model: display `Qwen3.8 27B Splash`, not `qwen3.8-27b-splash`. Prefer
existing model display metadata; otherwise format the actual model identifier
for display without changing its stored identity or selection. Do not add a
`LOCAL` marker, provider, route or specialty to the badge. Keep role and specialty
separate in assignment metadata. For legacy assignments without a role, display
`Unspecified role`; this is a display placeholder, not a stored role value.
Do not infer the role from the model name or execution route.

For local workers, the plugin owns the existing-hook adapter and sends the full
display label on the first observation of the real attempt. Pass the canonical
role and specialty separately to that adapter. Keep the complete values in the
assignment metadata: Habblaud can visually ellipsize long badges from the right,
and native rollout parsing has the 40-character limit above. Hover text retains
the full hook label. These transport limits do not authorize a different label
format for local and native workers.

Native session data can also populate the agent's **Stats > Model** field.
The existing Codex hook endpoint ignores the event's `model` field, so hook-only
local workers cannot populate it through that path. Keep Habblaud unchanged and
report local model Stats as unavailable; the badge's model display name does not
establish Stats support. Do not fabricate native session data to fill that field.

Existing hooks still attach local characters to the Codex provider/account.
Stop, interruption and expired hook presence can
look like successful completion. A role label does not fix these identity or
lifecycle limitations; the plugin must document them and own transport testing.
Vibe neither installs that adapter nor changes local routing. Coordinator badge
support remains unavailable under the unchanged-Habblaud constraint.
