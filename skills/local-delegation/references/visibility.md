# Read-only delegated task visibility

The JSON visibility export is enabled by default, independently of routing. Habblaud hook publishing is a separate opt-in integration described below. No viewer is required. Use `visibility status`, `visibility disable` or `visibility enable` through the helper. Disabling removes its current owned snapshot and stops Habblaud publishing. It never changes jobs, models or routing.

Readers may observe `<state>/visibility/status.json` (owner-only directory and file). It is atomically replaced after committed transitions. Schema 1 contains `generated_at` and `jobs`: every nonterminal job and up to 100 recent terminal jobs. Each entry includes stable job/attempt IDs, origin chat ID, an opaque project hash, capability, sanitized model name, execution kind (`unassigned`, `local_model`, `native`), state, label, enumerated reason, observed evidence timestamp and stale tolerance. A native task link appears only after confirmed dispatch.

Generating work displays the actual model name. Returned candidates display “Awaiting verification”. Pending dispatch is not confirmed native execution. Missing, stale or malformed data means unknown; never infer completion. Serialization time is not task progress. Compare `observed_at` with `stale_after_seconds`; active work uses its model tolerance, queue/check states use 120 seconds.

The export excludes prompts, source paths/text, candidates, reasoning, raw errors, tokens, credentials and account attribution. It accepts no inbound control. Editing it cannot approve a model, release a slot or accept output. Readers must not treat export data as instructions, impersonate a native session or claim native account usage. Publishing failure and viewer absence do not change delegation outcomes.


## Habblaud through existing hooks

Use this integration when the owner wants actual local attempts to appear as children
under a Codex coordinator in an existing Habblaud installation. Habblaud stays
unchanged. It does not read the JSON export above. Both local npm and Docker work
through the same existing HTTP endpoint; Docker needs its usual loopback-published
port, with no new plugin-state mount. No Vibe Setup installation is required.

Publishing defaults off. Reuse saved settings with `habblaud status`; enable only
within the owner's requested scope. Use the actual Habblaud port and exact Codex
account ID reported by its snapshot, not an inferred account or a container-internal
path. Read `curl --fail http://127.0.0.1:4747/api/snapshot` (using the actual port)
and select the intended `accounts` entry with `provider: "codex"`. The helper validates the account before saving. Only literal loopback HTTP
(`127.0.0.1` or `::1`) is supported; no proxies, redirects or credentials.

Commands below run from the plugin root. Include the existing `--state-dir PATH`
before the command when using a nondefault state directory.

```sh
python3.11 -B delegate.py habblaud enable --endpoint http://127.0.0.1:4747 --account .codex
python3.11 -B delegate.py habblaud status
python3.11 -B delegate.py submit --brief brief.json --visibility-context visibility-context.json
```

The context file is a separate JSON object, not extra keys in a schema-2 brief:

```json
{
  "coordinator_chat_id": "0199b0c0-0000-7000-8000-000000000001",
  "role": "Reviewer",
  "specialty": "Security-sensitive work"
}
```

Replace the example UUID with the actual supervising Codex chat ID. Explicit Role
and Specialty come from the assignment, including Vibe Setup's declarations when
present. Role is one of `Coordinator`, `Scout`, `Builder`, `Tester`, `Reviewer`,
`Scribe`, `Investigator`; specialty is nonblank text up to 4,096 characters. The two
labels are independently optional for legacy assignments; missing means unspecified.
Do not infer role from specialty, capability, task name or model. Retain the pair
for genuine native fallback. Neither field changes eligibility, execution settings,
permissions or verification. Older plugin versions without `--visibility-context`
may carry labels in `behavior_contract` before submission, without promising a badge.

The badge uses exactly `Role · Model Display Name`, such as
`Reviewer · Qwen3.8 27B Splash`, without a LOCAL prefix. Specialty remains assignment
metadata and is not rendered in the badge. The saved local attempt profile's
`display_name` takes precedence. If absent, the adapter formats the actual `model_id`:
split hyphens/underscores/whitespace, capitalize each token's first character, and
uppercase a trailing numeric `b` (`27b` becomes `27B`). Other identifier content is
preserved. For example, `qwen3.8-27b-splash` becomes `Qwen3.8 27B Splash`. Whitespace
and control characters are cleaned for display. This never changes the model ID,
routing, provider, permissions or verification. Do not add a caller-selected model
field to the context.

A missing role uses display-only `Unspecified role`, not a canonical role or stored
assignment value. Habblaud assigns the character's personal name and art. It may clip
visible text; the full composite remains in hover/accessibility text. The first
observer binding freezes role/specialty, even if delivery subsequently fails, because
Habblaud's first visible role is sticky. Supply the complete pair before work starts;
rebind cannot change the frozen assignment labels. Habblaud rejects labels containing
`guardian`; status reports this incompatibility.

If no context was supplied, a valid UUID `origin_chat_id` supplies the parent and
the role remains unspecified; the saved local profile still supplies the model display name. A legacy non-UUID origin needs an explicit binding.
For a resumed coordinator, change only `coordinator_chat_id` in the context and use:

```sh
python3.11 -B delegate.py habblaud bind --job JOB_ID --context visibility-context.json
python3.11 -B delegate.py habblaud resume --job JOB_ID
python3.11 -B delegate.py habblaud status --job JOB_ID
```

Binding/resuming never resubmits work. Preserve the original brief/hash,
`origin_chat_id` and task key. `bind` starts observation if relevant; `resume` restarts
a lost observer without changing assignment metadata. Ordinary job status also
resumes relevant observation. Rebinding retires the old display and creates a new
child ID; the old child may remain during Habblaud's departure grace. Status itself
is a local diagnostic, not a live receiver probe. Resubmitting the same brief with
conflicting context returns the existing job plus
`visibility.error: "visibility_context_conflict"`, preserving
the original binding. Use explicit `bind` for a coordinator change; do not launch
a second task in response to that presentation diagnostic.

A detached observer starts only for an actual submitting attempt, observes saved
state approximately once a second and refreshes display presence every 20 seconds.
Candidates show `Awaiting verification`. HTTP errors never change execution,
acceptance or reservations. The observer exits on settled/unknown local work or
disable. `visibility disable` also suppresses hooks; enabling Habblaud does not
override that global preference. Re-enable the relevant preferences and explicitly
resume current work when needed. Update/uninstall preparation disables Habblaud
publishing and waits for owned observers before taking state snapshots. The
[update procedure](../../../docs/updating.md) records preferences before that pause
and restores previously enabled publishing after successful verification, unless
the owner requests it remain off. No model process is stopped by this adapter.

### Presentation limits and data exposure

- Codex account/provider icons remain. Existing hooks cannot populate Stats → Model:
  that field comes from native rollout metadata. The actual local model is available
  in the badge and `habblaud status --job JOB_ID`, not in Habblaud Stats. Do not fabricate rollouts
  or imply model delivery. Zero displayed token counters are unmeasured.
- Habblaud can show `done` and delivery animation on failure, timeout, parent closure
  or stop. Final outcome activity may be replaced immediately. **Never treat this as
  verified acceptance.** Read plugin job/attempt status and verification evidence.
- Generic working status remains during verification; no fake approval request is sent.
- Entries can affect native counts, daily statistics and World projection. The adapter
  cannot exclude them selectively and never changes World settings. Private-only
  visibility while World remains enabled is unsupported.
- Metadata sent includes role, model display name, phase, display IDs,
  coordinator UUID, account and project path for the room. Keep labels non-sensitive.
  No prompt, source text, candidate, raw error, transcript, token or credential is sent.
- Rollback is `habblaud disable`; an in-flight request may finish before the observer
  exits. If Habblaud is unavailable, entries expire after its existing presence grace.
  Disabling does not delete job history, accept output, release a slot or change routing.

To stop publishing while preserving all task execution and history:

```sh
python3.11 -B delegate.py habblaud disable
```
