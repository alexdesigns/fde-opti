# Architecture

## The principle

The workflow has eight steps: two specialized agents (RC1, RC2), two gates (G1, G2) and four code steps (IN1, RC3, RC4, RC5), started by two triggers (TR1 Chat, TR2 webhook). Step names are the live names in the tenant.

The hard part was deciding where AI actually belongs. I settled on this split:

- **AI interprets.** Two Specialized Agents read the draft: one for claims, one for the content as a whole.
- **Tools verify governed facts.** Whether a claim is approved, in date, for this market and audience, and what its exact wording and disclaimer are, comes from `validate_approved_claim`. No model decides it.
- **Code controls state and routing.** Two gates (conditions) and four Python code steps check inputs, route around failures, set the readiness state and deliver the result.
- **People keep approval.** The best outcome is `READY_FOR_FORMAL_REVIEW`. Formal MLR approval happens outside this system.

Only RC1 and RC2 are Specialized Agents. They return structured findings; code sets the state from them, and every rule it applies is testable without a model. The platform fills each code step's parameters from earlier outputs (marked `predicted` in the export), so the code re-checks what it receives: IN1 pattern-checks the values it echoes into the gate, RC3 refuses unreadable agent output, and RC4 refuses a malformed `request_id`.

## Entry points

| Trigger | Type | Used by |
|---|---|---|
| TR1 - Trigger - Chat | message | Optimizely AI Chat, through IN0 - OptiThera Content Intake (the `/content-readiness` shortcut) |
| TR2 - Trigger - Webhook | webhook, bearer auth | Any external system. ClickUp calls it directly; WordPress and a browser extension call it through a small server-side gateway (see [integration-notes.md](integration-notes.md)) |

The workflow does not know which product sent a request. A webhook caller sends `draft_content`, `market`, `audience`, optional `as_of_date` and an optional `request_id` ([example](../examples/request-example.json)). IN1 also recognizes a ClickUp automation body and reads the task and draft itself through the ClickUp connector.

## Core path

| Step | Type | Why it exists |
|---|---|---|
| IN1 - Validate - Request Context | code | Fail fast. A missing draft, a market that is not a two-letter code or an audience other than `hcp` or `patient` stops the run before either agent runs. It also extracts the cited claim IDs (`[CLM-001]`) with a regex, so no model picks them. |
| G1 - Gate - Inputs Complete? | condition | Routes `INPUTS_OK` to RC1 and everything else straight to RC3. Two explicit rows (contains / not contains) so no output can fall outside both. |
| RC1 - Claims - Identification & Explanation | Specialized Agent (RC1 - Claim Identification & Explanation Agent, V5) | Calls `validate_approved_claim` once with the cited IDs, compares each cited sentence with the approved wording, lists claim-like statements that cite no ID, and explains each result. |
| G2 - Gate - Claim Validation Usable? | condition | If validation status is not `ok` or `not_called`, skip review and go to RC3, which returns `VALIDATION_UNAVAILABLE`. Unknown is never treated as valid. |
| RC2 - Review - Content Readiness | Specialized Agent (RC2 - Draft Risk Reviewer, V7) | Reviews the whole draft for clarity, completeness, audience fit, missing safety or prescribing references and internal consistency. Can propose a suggested rewrite on a blocking finding. |
| RC3 - Decision - Readiness State | code | Applies fixed rules to the gate, the claim results and the review findings and returns one of the four states. Attaches recommendations only where they are supported. |
| RC4 - Package - Readiness Result | code | Normalizes the decision into the external result contract and checks that any `request_id` is a well-formed UUID. A malformed ID is flagged, never corrected. |
| RC5 - Deliver - External Result | code | Chat: nothing to deliver, the reply is the result. Webhook with a `request_id`: calls `submit_readiness_result`. ClickUp: writes fields, a comment and the task status through the ClickUp connector. |

## Delivery is not decisioning

RC5 passes every field exactly as RC4 packaged it. `submit_readiness_result` validates the shape and refuses inconsistent results (for example `READY_FOR_FORMAL_REVIEW` with a blocking finding), but it cannot change a state. ClickUp delivery moves a task to "changes needed" or "formal review"; a person still does the formal review.

## Where the controls sit

- Authority: RC3 is the only step that sets a readiness state. The agents return findings; they never set it.
- Callback security: `submit_readiness_result` is protected by the registry bearer token, an unguessable pending `request_id`, a strict schema, first-result-wins (a conflicting second result is rejected) and a 24 hour expiry. The platform gives no trustworthy signal about who is calling, so I do not claim the callback is verified as coming from Optimizely. Authorized tenant users, and Chat, can read run inputs, so turning "Enabled in Chat" off for a tool is not a security boundary.
- Variance: RC2's judgment on a borderline draft can vary between runs. The routing and the state rules do not, because they are code.
- Guardrails: both agents are Enforcing with auto-stop on and sensitivity 1, progressed by the platform.

## What is not here

- No automated approval and no publish step.
- No model call inside the validator, the gates or the code-step logic.
- The approved-claims register in this repo is a small fictional data set. In a real deployment the tool would read the customer's claims system, read-only.
