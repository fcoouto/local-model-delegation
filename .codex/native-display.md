# Native role display in Habblaud

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

The reader checks only a bounded first metadata line, never task messages. It checks
the current UTC day, adjacent days and the parent's transcript directory; unsupported
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
