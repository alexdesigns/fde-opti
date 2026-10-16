# Testing and evals

I tested at three layers. Deterministic tests check the rules. Output evaluation looks at what the agents wrote. Execution tracing shows what actually ran; it is how I caught two answers that looked right and came from the wrong place.

## 1. Deterministic tests

The gates, the state rules, packaging, delivery and both tools are code, so they are tested without a model or a network.

| Suite | Count | Covers |
|---|---|---|
| [04-workflow/code-steps/test_steps.py](../04-workflow/code-steps/test_steps.py) | 61 | IN1, RC3 and RC4: every state, gate spoofing from draft text, unreadable agent output, invented claim IDs, malformed `request_id`, recommendation rules, no approved state |
| [04-workflow/code-steps/test_delivery.py](../04-workflow/code-steps/test_delivery.py) | 16 | RC5 routing by source: Chat, callback, ClickUp |
| [04-workflow/code-steps/test_clickup.py](../04-workflow/code-steps/test_clickup.py) | 96 | The ClickUp path end to end against a stubbed connector: reading the task and draft Doc, fields, comment, status, duplicate events |
| [04-workflow/code-steps/test_examples.py](../04-workflow/code-steps/test_examples.py) | 1 | The published request example passes IN1 |
| `npm test` in [05-tools/](../05-tools) | see `npm test` output | Validator rules and input rejection, result contract, store create, complete, duplicate, conflict and expiry, registry auth, the published result examples |

Run them:

```bash
cd 04-workflow/code-steps && for t in test_steps test_delivery test_clickup test_examples; do python3 -I $t.py .; done
cd 05-tools && npm install && npm test
```

What the tests and the live runs establish, by behavior:

- **Trigger and non-trigger.** In Chat this lives in IN0 (see [instructions-and-skills.md](instructions-and-skills.md)). On ClickUp, only a move to Internal Review starts a run. On WordPress, autosave, an unchanged save and a double-click do not start extra runs.
- **Input validation.** Missing draft, market or audience gives `INPUT_REQUIRED` before either agent runs. IN1 accepts only a two-letter market, so `USA` is not converted there. From Chat, the IN0 intake converted `USA` to `US` before starting the workflow in a 16 October run; see [QUICK-START.md](../QUICK-START.md).
- **Canonical states.** Exactly four. The step tests check that no approved state is produced.
- **Delivery.** Chat needs no callback; a webhook with a valid `request_id` calls `submit_readiness_result`; ClickUp writes fields, then the comment, then the status.
- **Duplicate suppression.** A retried ClickUp event is recognized by a delivery key in the task's comments and posts nothing. An identical callback is acknowledged as a duplicate; a different result for the same request is rejected.
- **Stale results.** In WordPress a meaningful edit marks the last result stale; with auto-run on, the next update replaces it with a fresh result. A request and its result expire 24 hours after the request was accepted; a late callback gets 410 `expired`.

I also ran the main cases (a ready draft, wording drift, missing input) against the live workflow from Chat, the webhook gateway, ClickUp and WordPress, and checked the trigger matrix on a private, unpublished test page in the production WordPress installation: no run with auto-run off, one run per meaningful update with it on, none on an unchanged save or an autosave, and one run for a double-click. Run counts come from Optimizely AI execution history.

## 2. Output evaluation and direct regression testing

Optimizely AI has a built-in Output Evaluation feature that scores agent runs against criteria. I configured criteria on both agents: nine on RC1 and seven on RC2. They ship in the agent exports and cover grounding, never inventing claim IDs, passing inputs unchanged, telling HCP and patient language apart, and never implying approval.

No single-turn evaluation examples are attached, and the agents list their runs as Not Evaluated. There are no platform-evaluated runs and I show no scores. I would rather say that than imply a number.

What I did instead was test the agents directly and read the outputs against each case:

- Five identical controlled ClickUp runs of the same draft returned `READY_FOR_FORMAL_REVIEW` 5 of 5, with RC1 correct 5 of 5, identical routing, and one workflow invocation and one validator call per run.
- An RC2 safety regression of six controlled cases passed.
- Earlier on the same draft, RC2 once returned a conservative `NEEDS_REVISION` on the safety section. I recorded it as reviewer judgment variance and did not tune for it. See the known limits below.

This is evidence from direct runs. It is not a platform quality score.

## 3. Execution tracing

Two real findings came from reading execution history rather than results.

**A. RC1 rewrote an invalid market.** Given market `USA`, the trace showed the agent calling `validate_approved_claim` with `US` instead and returning valid claims. The final answer looked reasonable. It was wrong: the caller's input had been silently corrected, and the final answer did not show it. Fix: the agent prompt now says to pass market, audience and date exactly as given, never to change, normalize or correct them, and never to retry a failed call with altered inputs. The validator already rejects `USA`, and inside the workflow IN1 rejects it before any agent runs, so the prompt rule protects direct use of the agent and any future caller. Re-run: `USA` (and later `GBR`) returned `invalid_request` with one tool call and no retry.

**B. Chat produced a readiness verdict without running the workflow.** Once, Chat answered a readiness request with a plausible verdict of its own. The reply looked like a real result. Execution history showed no workflow run behind it: no IN1, no validator call, no RC3. Fix: IN0 now says the workflow agent is the only way to run the check, forbids writing its own readiness summary, status or claim table, and says plainly when the workflow cannot be run. Proof: after the change, Chat readiness requests appear in execution history as workflow runs, and the reply carries the workflow's own state, findings and closing line.

The rule I took from both: for any result that matters, check that a matching execution exists and that it called what it should have.

## 4. Guardrails

Guardrails in Optimizely AI watch each agent's behavior. Both agents are Enforcing, with auto-stop on and sensitivity 1. I did not promote them by hand. The platform progressed them on its own as run history built up; RC2 moved from its earlier monitoring stage to Enforcing during final verification. I did not tune sensitivity.

One observation: a stalled run made a second validator call on its own. I read that as platform retry behavior.

## Known limits

- The required disclaimer is checked by RC2, not by code. A deterministic presence check is a next step.
- RC2's judgment varies on borderline drafts. The routing and the state rules are code and do not vary. I make no claim that model judgment is deterministic.
- When a draft cites no claim ID, the validator is not called and the packaged `validation_status` still reads `ok`. Nothing was checked against the register in that case. Uncited claims still produce `NEEDS_REVISION`.
- The callback has no trustworthy caller-provenance signal from the platform. Its controls are the bearer token, an unguessable pending request ID, a strict schema, first-result-wins and a 24 hour expiry.
- Authorized tenant users, and Chat, can read run inputs, including inbound webhook headers, in execution logs. "Enabled in Chat" off is not a security boundary.
- Delivery is at most once per request ID, not exactly once end to end.
- Built-in output evaluation criteria are configured, but there are no platform-scored runs.
- Chat starts the check on `/content-readiness` or a clear request. A bare "yes" after the intake has the inputs is not a reliable trigger on this platform, so it does not start a run.
- Chat input is not guaranteed byte-preserving. Some Chat runs normalized whitespace, while every word and its order stayed intact in the tested drafts. The ClickUp path and the WordPress gateway to workflow path matched their sources byte for byte in the verified runs.
- Chat can fill an as-of date the user did not give. The workflow uses whatever date reaches it.
- The target success measures (fewer late-stage revisions, shorter time to formal review, higher first-pass readiness) are targets, not measured results.
