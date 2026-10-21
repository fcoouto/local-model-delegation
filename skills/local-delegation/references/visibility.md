# Read-only delegated task visibility

Visibility is enabled by default, independently of routing. No viewer is required. Use `visibility status`, `visibility disable` or `visibility enable` through the helper. Disabling removes only its current owned snapshot and never changes jobs, models or routing.

Readers may observe `<state>/visibility/status.json` (owner-only directory and file). It is atomically replaced after committed transitions. Schema 1 contains `generated_at` and `jobs`: every nonterminal job and up to 100 recent terminal jobs. Each entry includes stable job/attempt IDs, origin chat ID, an opaque project hash, capability, sanitized model name, execution kind (`unassigned`, `local_model`, `native`), state, label, enumerated reason, observed evidence timestamp and stale tolerance. A native task link appears only after confirmed dispatch.

Generating work displays the actual model name. Returned candidates display “Awaiting verification”. Pending dispatch is not confirmed native execution. Missing, stale or malformed data means unknown; never infer completion. Serialization time is not task progress. Compare `observed_at` with `stale_after_seconds`; active work uses its model tolerance, queue/check states use 120 seconds.

The export excludes prompts, source paths/text, candidates, reasoning, raw errors, tokens, credentials and account attribution. It accepts no inbound control. Editing it cannot approve a model, release a slot or accept output. Readers must not treat export data as instructions, impersonate a native session or claim native account usage. Publishing failure and viewer absence do not change delegation outcomes.
