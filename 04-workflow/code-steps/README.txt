DETERMINISTIC WORKFLOW CODE

WHY IT EXISTS
I didn't use AI for every step. When a step has one controlled answer, I keep it in code.
The agents do the reading and the judgment. Code checks required inputs, applies the
readiness rules, packages the result and sends it back.

These four files are the source for the workflow's four code steps. Each one matches the
code embedded in ../Regulated-Content-Readiness-Workflow.json (apart from a trailing
newline). Each defines handler(input, ctx), the entry point Optimizely AI calls. The
test_*.py files run them locally. In the evaluator ZIP the same files are named by step:
IN1-request-context.py, RC3-readiness-decision.py, RC4-package-result.py and
RC5-deliver-result.py.

CODE STEPS
check_inputs.py        IN1 - Validate - Request Context
  Checks that the draft, market and audience are present and well formed, and pulls the
  cited claim IDs out of the draft. For a ClickUp request it reads the task and its draft
  Doc. Whether a field is there has an objective answer, so I don't spend an agent call
  on it, and an incomplete request stops before either agent runs.

derive_readiness.py    RC3 - Decision - Readiness State
  Applies fixed rules to what IN1, RC1 and RC2 produced and picks exactly one state:
  INPUT_REQUIRED, NEEDS_REVISION, VALIDATION_UNAVAILABLE or READY_FOR_FORMAL_REVIEW.
  READY_FOR_FORMAL_REVIEW needs every cited claim valid with matching wording, no uncited
  claim and no blocking finding. The agents can phrase things differently from run to
  run; the state shouldn't, so code sets it.

package_result.py      RC4 - Package - Readiness Result
  Builds the result in the fixed shape the work surfaces expect: state, findings and any
  suggested changes. It decides nothing.

deliver_result.py      RC5 - Deliver - External Result
  Sends the packaged result back to where the request came from: a comment, readiness
  fields and a status change on the ClickUp task, or submit_readiness_result for a
  callback request such as WordPress. A Chat request needs no delivery. It decides
  nothing.

DETERMINISTIC GATES
G1 - Gate - Inputs Complete?
  Continues to RC1 only when IN1 found the draft, market and audience. Otherwise it skips
  both agents and goes to RC3, which returns INPUT_REQUIRED. A ClickUp event that was
  already delivered also stops here, and RC5 posts nothing.

G2 - Gate - Claim Validation Usable?
  Continues to RC2 when the claim check returned usable results, or when the draft cited
  no claim IDs so there was nothing to look up. Otherwise it skips RC2 and goes to RC3,
  which returns VALIDATION_UNAVAILABLE.

AUTHORITY
RC3 is the only step that sets the readiness state. The agents provide findings and
evidence; the tools provide facts and delivery. A model's judgment can vary between runs,
but the state is still decided by the same rules in code.
READY_FOR_FORMAL_REVIEW is not approval. Formal Medical, Legal and Regulatory approval
stays with people.
