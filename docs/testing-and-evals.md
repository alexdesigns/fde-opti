# Testing and evals

I tested at three layers. Deterministic tests check the rules. Output evaluation looks at what the agents wrote. Execution tracing shows what actually ran; it is how I caught two answers that looked right and came from the wrong place.

## 1. Deterministic tests

The gates, the state rules, packaging, delivery and both tools are code, so they are tested without a model or a network.

| Suite | Count | Covers |
|---|---|---|
| [workflow/steps/test_steps.py](../workflow/steps/test_steps.py) | 61 | IN1, RC3 and RC4: every state, gate spoofing from draft text, unreadable agent output, invented claim IDs, malformed `request_id`, recommendation rules, no approved state |
| [workflow/steps/test_delivery.py](../workflow/steps/test_delivery.py) | 16 | RC5 routing by source: Chat, callback, ClickUp |
| [workflow/steps/test_clickup.py](../workflow/steps/test_clickup.py) | 96 | The ClickUp path end to end against a stubbed connector: reading the task and draft Doc, fields, comment, status, duplicate events |
| [workflow/steps/test_examples.py](../workflow/steps/test_examples.py) | 1 | The published request example passes IN1 |
| `npm test` in [tools/](../tools) | 55 | Validator rules and input rejection, result contract, store create, complete, duplicate, conflict and expiry, registry auth, the published result examples |

Run them:

```bash
cd workflow/steps && for t in test_steps test_delivery test_clickup test_examples; do python3 -I $t.py .; done
cd tools && npm install && npm test
```

What the tests and the live runs establish, by behavior:

- **Trigger and non-trigger.** In Chat this lives in the Intake Skill (see [instructions-and-skills.md](instructions-and-skills.md)). On ClickUp, only a move to Internal Review starts a run. On WordPress, autosave, preview and unchanged content do not.
- **Input validation.** Missing draft, market or audience gives `INPUT_REQUIRED` before any model runs. `USA` is rejected, not converted.
- **Canonical states.** Exactly four. The step tests check that no approved state is produced.
- **Delivery.** Chat needs no callback; a webhook with a valid `request_id` calls `submit_readiness_result`; ClickUp writes fields, then the comment, then the status.
- **Duplicate suppression.** A retried ClickUp event is recognized by a delivery key in the task's comments and posts nothing. An identical callback is acknowledged as a duplicate; a different result for the same request is rejected.
- **Stale results.** In WordPress a meaningful edit marks the last result stale; with auto-run on, the next update replaces it with a fresh result. A request and its result expire 24 hours after the request was accepted; a late callback gets 410 `expired`.

I also ran the main cases (a ready draft, wording drift, missing input) against the live workflow from Chat, the webhook gateway, ClickUp and WordPress, and checked the trigger matrix on a private, unpublished test page in the production WordPress installation.

## 2. Output evaluation

Optimizely AI's Output Evaluation scores agent runs against criteria with a model as judge. I configured criteria on both agents (nine for the Claim agent, seven for the Reviewer; they ship in the agent exports) covering grounding, never inventing claim IDs, passing inputs unchanged, telling HCP and patient language apart, and never implying approval.

In this tenant, scoring did not run with criteria alone; it needed an example attached to the agent. Examples attach to the agent, not to a case, so the judge compared every run with that one example. A correct empty result was marked down for missing another draft's findings. A correct no-ID result scored 15% for "missing" a claim that was not in the input. A quote that was in the draft was called a hallucination. With one unrelated HCP example attached, the judge marked a patient run down for treating the content as patient-facing.

So I treated eval scores as evidence to inspect, not as truth. I read the outputs directly against each case. On that reading the Claim agent was correct on all seven cases in the first round and all six in the second, including the `USA` regression and the no-ID case, and the Reviewer was correct on five of six cases in the first round. The sixth was one draft where it repeatedly raised a patient-audience finding whose blocking flag varied between identical runs. I recorded that as draft-specific variance and did not tune for it. Semantic quality, authority boundaries and recommendation framing were judged the same way: by reading what the agent wrote against the criteria.

## 3. Execution tracing

Two real findings came from reading execution history rather than results.

**A. The Claim agent rewrote an invalid market.** Given market `USA`, the trace showed the agent calling `validate_approved_claim` with `US` instead and returning valid claims. The final answer looked reasonable. It was wrong: the caller's input had been silently corrected, and the final answer did not show it. Fix: the agent prompt now says to pass market, audience and date exactly as given, never to change, normalize or correct them, and never to retry a failed call with altered inputs. The validator already rejects `USA`. Re-run: `USA` (and later `GBR`) returned `invalid_request` with one tool call and no retry.

**B. Chat produced a readiness verdict without running the workflow.** Once, Chat answered a readiness request with a plausible verdict of its own. The reply looked like a real result. Execution history showed no workflow run behind it: no IN1, no validator call, no RC3. Fix: the Intake Skill now says the workflow agent is the only way to run the check, forbids writing its own readiness summary, status or claim table, and says plainly when the workflow cannot be run. Proof: after the change, Chat readiness requests appear in execution history as workflow runs, and the reply carries the workflow's own state, findings and closing line.

The rule I took from both: for any result that matters, check that a matching execution exists and that it called what it should have.

## 4. Guardrails

Guardrails in Optimizely AI watch agent behavior per agent version, moving from Learning to Watching to Enforcing as run history builds up. I left the defaults. The direct agent runs I checked show Learning (one Reviewer run shows Passed), and runs inside the workflow show no guardrail value. No tenant-level Input Guardrails are configured. Each new agent version restarts learning, and the Reviewer was on V5 when exported.

So I claim no guardrail enforcement. Take-home volume is not enough history for the platform to learn normal behavior, and I did not raise sensitivity to make the feature look active. One observation for when it matters: a stalled run made a second validator call on its own. I read that as platform retry behavior, and it is the kind of thing Watching mode should flag. Moving beyond Learning is on my list of next steps, once there is real run history.

## Known limits

- The required disclaimer is checked by the Reviewer, not by code. A deterministic presence check is a next step.
- Reviewer wording varies between runs on the same draft.
- Delivery is at most once per request ID, not exactly once end to end.
- Authorized tenant users can read run inputs, including inbound webhook headers, in execution logs.
