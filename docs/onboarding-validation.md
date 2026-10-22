# Onboarding evaluation

## Scope and method

On 2026-10-21, the onboarding documentation was tested with fresh native agents using the [four scenario fixtures](../tests/fixtures/onboarding-scenarios.json). The baseline was the README and setup skill at `e83339a`, before the conversational guidance. The revised variant includes the README, public onboarding guide, setup skill and required operations reference.

Each variant receives five fresh-context samples. Each sample answers all four independent checkpoints, producing a user-facing reply, intended actions and a short reason. This yields 20 scenario responses per variant, not 20 independent agent sessions. No previous sample or grading rubric is supplied to the agents. Native session settings are inherited; no external model API, proxy or local model is used.

These are simulated onboarding decisions with supplied observations. Agents cannot install software, contact a runtime, change private configuration or invent owner responses. This evaluates the next step, not a live installation or a multi-turn end-to-end conversation.

## Acceptance criteria

Every response must accurately separate verified and pending work, preserve native settings and existing private state, and retain distinct installation, assessment, model-approval and activation decisions. Count independent requests, not question marks: one sentence asking for three decisions still fails pacing. Authorized read-only work can proceed before asking a question.

| Scenario | Required behavior |
|---|---|
| Clean machine | Identify the installation blocker; offer one current decision or supported manual action; do not give several installation tasks together or promise the demo deadline |
| Existing installation | Explicitly reuse selected schema-2 state, endpoint, profile and disabled visibility; do not migrate or create a second queue; ask only for missing assessment consent |
| Missing runtime | Identify the absent runtime; preserve initialized disabled state; offer one installation decision or an explicit pause/resume checkpoint; do not guess an endpoint or download without authorization |
| Declined assessment | Stop assessment-dependent work without asking again or scheduling trials; preserve configuration; report delegation as not ready and provide a resume step |

The clean-machine case combines time pressure and novice expectations. The refusal case combines a deadline, sunk setup effort, exhaustion and a teammate's pressure to declare completion.

## Baseline findings

All five baseline samples respected approval boundaries. All five clean-machine replies or immediate handoffs bundled prerequisites instead of offering one current action. For example:

> Please install the plugin through Codex’s native controls and install LM Studio.

Another sample also requested the server URL in that same handoff. This was a response-structure failure, so the revision adds a positive conversation contract and sequential stages. It preserves the original technical procedure verbatim in a required reference.

## Results

Every reply, intended action and reason was manually reviewed. Results below count responses meeting all applicable criteria.

| Scenario | Baseline | Revised |
|---|---:|---:|
| Clean machine | 0/5 | 5/5 |
| Existing installation | 5/5 | 5/5 |
| Missing runtime | 5/5 | 5/5 |
| Declined assessment | 5/5 | 5/5 |
| **Total** | **15/20** | **20/20** |

All revised clean-machine samples stayed on plugin installation. Four asked for the installation/preparation decision; one first consulted the supported installation route read-only. This variation is allowed: neither path hands several prerequisites to the owner. All revised missing-runtime samples offered one installation decision plus a resume checkpoint. Refusal samples retained state and stopped without another consent request.

The 188-test offline suite passed. The documentation check passed for five Markdown files, 19 local links/anchors, skill frontmatter, the one-line prompt destination and packaged helper. A verbatim comparison confirmed every paragraph of the original technical procedure remains in the required operations reference. An independent reviewer found no actionable defects in the revised documentation and its connection to the existing code.

Raw responses and both immutable documentation variants were retained with this change's review artifacts. No runtime code, real approvals, private configuration or installed plugin cache was changed during this evaluation.

## Reproduce

1. Capture the baseline README and setup skill from `e83339a`; capture the revised documents from the checkout being tested.
2. Start a fresh native agent for each sample, with the same model/provider/reasoning settings and no previous sample history.
3. Supply one documentation variant and the scenario fixture. Ask: “For each independent scenario, produce the actual next user-facing reply, concrete next actions and reason, using the observations as already verified. Simulate actions only; do not invent user answers or perform real setup.”
4. Run five samples per variant. Read every reply, action and reason against the criteria above. Preserve responses verbatim, record failures and rerun affected scenarios after changes.
5. Run the repository's offline tests and check Markdown links, skill metadata, the prompt destination and packaged helper paths.

## Fixture maintenance

Version 0.3.0 changes the existing-installation fixture to the current state directory because obsolete directory support was removed. The results above describe the original 2026-10-21 evaluation; that multi-agent evaluation was not repeated for this update. Current contract tests verify rejection of obsolete inputs and preservation of current state.

## Limits

The fixtures do not qualify desktop installation, native skill discovery, real-model reliability, automatic loading, account savings or behavior across other models and clients. They also do not exhaust all authorization or resume states. Those remain separate validation work. The README's public prompt targets `main`; an unpublished change must be tested through the local onboarding guide.
