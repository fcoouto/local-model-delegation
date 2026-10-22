# Model loading and verified recovery

The plugin can load an **approved model** through LM Studio's [HTTP load API](https://lmstudio.ai/docs/developer/rest/load). Loading permission is separate from model approval, inference routing and assessment consent. It does not approve another model, change defaults or run a prompt. Unapproved onboarding models still require the existing explicit assessment/manual-load procedure.

Use `python3.11 -B <plugin>/delegate.py` with the existing private state directory. For a model whose loading the owner has authorized:

```sh
python3.11 -B <plugin>/delegate.py models permit-load --profile-id MODEL_PROFILE --owner-reference CONSENT_REFERENCE --context-length CONTEXT_TOKENS
python3.11 -B <plugin>/delegate.py models load --profile-id MODEL_PROFILE
```

The permission lives in private `config.json` under `loading_policy`, bound to the current approval digest, context length and one parallel slot. A changed approval invalidates it. The coordinator records actual owner authorization; the string is an audit reference, not proof that consent occurred. Removing that profile's policy revokes future loads without changing inference approval.

After permission, ordinary routing can load the model when discovery finds it unloaded. Already loaded matching models are reused. New loads require no other loaded model on that endpoint, no unresolved helper work and a fresh acceptable pressure reading. LM Studio keeps responsibility for its loading guardrails. No free-memory estimate, global setting change, download or synthetic inference is required. The API does not document a parallel-setting request field; the helper verifies the resulting runtime has one slot and the requested context. A mismatch remains blocked.

The plugin persists intent before POST. It validates the load response and fresh discovery before admission. A lost response or interrupted operation retains an endpoint reservation; another call does not repeat the POST. Use the returned operation ID for a read-only reconciliation:

```sh
python3.11 -B <plugin>/delegate.py models reconcile-load --operation-id OPERATION_ID
```

Only exact approved identity, context, one slot and no peer can settle that operation. Observed presence after a lost response does **not** establish that the plugin owns the model. If the model is absent or mismatched, the reservation remains uncertain and requires investigation; this command never retries loading.

## Recover an uncertain inference slot

Version 0.3.6 settles new budget-exhausted requests without reset when it validates a matching terminal response and generation. It releases only that attempt's slot and requests native fallback. Older uncertain attempts without that saved terminal evidence still require the procedure below; an `output_budget_exhausted` reason alone is insufficient. No outcome or history is rewritten.

Get owner authorization to unload the exact affected instance. Disable routing and assessment admission, and let healthy helper work finish. Do not repeatedly submit the original task. Then invoke:

```sh
python3.11 -B <plugin>/delegate.py models reset --instance-key INSTANCE_KEY --owner-reference RESET_CONSENT_REFERENCE
```

The helper verifies the approved artifact/index/discovery binding, checks for healthy endpoint work and holds observer/checker locks. It records the original instance, generation and attempts before sending at most one unload request. A fresh valid model listing must show the exact instance absent and other loaded instances unchanged. A lost unload response can be reconciled from that verified absence. Repeating the same command/reference never repeats the unload.

After verification, only uncertain attempts from that generation become released with an explicit reset-resolution record. The generation advances and the old instance is retired. Job status, failure, candidate, native fallback and measurement history remain unchanged. This is resource retirement, not successful inference. A reused LM Studio instance ID cannot reactivate an old attempt. Reload through `models load` after separately authorized loading permission; no new assessment prompt is needed.

Verified retired instances no longer block the guided updater. A manually edited `retired` flag is insufficient: update checks require the matching completed reset receipt. When recovering for an update, keep admission off through installation and `verify-update`. A new tested source version may perform the reset before installation; retain its exact source/package identity and private evidence. Do not alter a staged immutable version or bypass update preparation.

## Limits

Automatic background reset is still unavailable. This procedure cannot prove that unrelated applications are idle or prevent them racing a load/unload; owner authorization covers interruption of the selected instance. The plugin serializes participating helper clients, refuses observed peers during loading and preserves peers during reset. It never changes LM Studio's JIT, Auto-Evict or loading-guardrail settings. [JIT can automatically evict other JIT-loaded models](https://lmstudio.ai/docs/developer/core/ttl-and-auto-evict); this path uses a separate explicit load operation before inference.

Runtime identity relies on the owner-trusted local index, artifact hashes and matching discovery metadata. It does not attest weights in memory. Loading and reset verification do not establish task quality, token savings, cross-client isolation or higher concurrency.
