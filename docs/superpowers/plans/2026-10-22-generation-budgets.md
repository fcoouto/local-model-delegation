# Generation budgets and terminal exhaustion implementation plan

Execute directly under the owner's implementation authorization, with regression tests and no additional reviewer loop.

**Goal:** Let the coordinator choose a task's generation allowance within the model's approved ceiling, and finish verified exhausted requests without stranding slots.

**Design:** Keep the profile's approved `request_settings.max_output_tokens` as the model ceiling. Add optional positive integer `task_requirements.max_output_tokens`; absent values retain the saved profile budget. Choose this allowance from task complexity, expected answer size and that model's reasoning observations, not source bytes converted to tokens. Reject unsupported budgets before POST; never silently shrink an explicitly requested allowance. Check the selected allowance against available runtime context. Persist effective settings and separate measurement cohorts by the settings actually sent. Raising the ceiling uses explicit owner-authorized profile approval, preserving historical evidence and invalidating old loading permission normally.

A valid `chat.end` must match the selected instance, have valid token metadata and supported output, and agree with streamed answer text. Budget-exhausted output is not accepted. Record its terminal evidence and atomically complete that generation's attempt and request native fallback; keep the instance available. Malformed/missing completion, stale streams, fencing and repeated reasoning retain uncertainty protections. Do not retroactively release historical uncertain attempts without their missing terminal evidence or verified reset.

**Constraints:** Python 3.11 standard library; one slot; native verification/fallback; no live inference, installation, approval change, reset or history rewrite for this implementation. Preserve unrelated visibility work. Prepare v0.3.6 source, without modifying published v0.3.5 bytes.

## Tasks

- [x] Reproduce task-budget selection and terminal slot retention with fictional HTTP fixtures.
- [x] Implement brief validation, selection/admission/POST enforcement, approval CLI support and effective measurement binding.
- [x] Implement atomic terminal exhaustion settlement, evidence and generation fencing.
- [x] Check invalid budgets, changed approval, context boundaries, malformed terminal data, replay and healthy peers.
- [x] Update operating docs and verify the source as recorded below.

After the coherent source commit, update the PHIOON pilot chat with its exact revision, checks and rollout boundaries. Preserve completed fallback deliveries and the unresolved historical slot. Record the handoff in the chat, without putting private job evidence in the portable repository.

The pilot's remaining tasks have already been delivered through native fallback. This change does not authorize replaying them or consuming unused allowance as a new experiment.

## Verification and dispositions

The initial 13 regression tests produced five failures and five errors before implementation. They reproduced the absent task-budget contract, fixed-profile context/measurement behavior and slot retention after terminal exhaustion. Follow-up failing regressions reproduced approval-ceiling changes closing occupied instances and absent new metadata changing historical observation shapes. Both were corrected at their shared layers.

The final focused module has 18 tests covering selection, context, invalid allowances, real fictional HTTP requests, terminal exhaustion with and without visible output, malformed completion, missing start, peers, generation fencing, replay, approval refresh, the CLI and measurement provenance/history. The full offline suite passes 273 tests. Both bundled skills pass the validator with PyYAML present; changed documentation links and `git diff --check 950c12dd763f2ecbc905ab9c034a1b3376503edb` pass.

Validation uses disposable fixtures. No real inference, lifecycle operation, plugin installation or approval/settings change was performed. This is direct author verification, not an independent review or live skill-behavior qualification. Installed workers and historical uncertain attempts are unaffected; live rollout, a deliberate approved ceiling and meaningful future project evidence remain separate gates. Missing native usage or a comparable baseline still means unknown savings.
