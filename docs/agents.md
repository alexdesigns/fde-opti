# Specialized Agents

Both agents are exported from the tenant. Both use the Balanced inference setting (`simple_with_thinking` in the export), are not enabled for direct use in Chat, and are run only by the workflow. Both prompts place the shared Skill with `{skill: `regulated-readiness-standard`}`, which is how the tenant serializes a Skill mention.

## RC1 - Claim Identification & Explanation Agent

Export: [03-agents/RC1-Claim-Identification-and-Explanation-Agent.json](../03-agents/RC1-Claim-Identification-and-Explanation-Agent.json), handle `@claim_identification_explanation`

**Purpose.** Confirm every cited claim with the validator, check whether each cited sentence keeps the approved meaning, find claim statements that cite no ID, and explain each result in plain language.

**Inputs.** `draft_content`, `market`, `audience` (required); `as_of_date`, `cited_claim_ids` (optional). IN1 extracts the cited IDs with a regex before this agent runs.

**Outputs.** JSON:
- `validation_status`: `ok`, `invalid_request`, `validation_unavailable`, `not_called` or `call_failed`
- `all_valid`
- `claims`: per cited ID, the tool outcome (`valid`, `not_valid`, `not_found`), reasons, approved text, required disclaimer, the draft sentence, `wording_matches` and an explanation
- `unresolved_candidate_claims`: efficacy, safety, indication, dosing, availability or comparison statements with no claim ID

**Instruction / Skill references.** RC1-RC2 - Regulatory Review Policy.

**Tools.** `validate_approved_claim`, called once with every cited ID, or not at all when none are cited.

**Authority boundary.** Copies the tool's outcome, reasons, approved text and disclaimer exactly. Never invents a claim ID, never guesses which approved claim a sentence means, never changes market, audience or date, never retries with altered inputs, and never describes a claim as valid when validation failed. A valid ID does not mean the wording is right; the agent compares the words.

**Role in the workflow.** Step RC1. Its output feeds G2 (is validation usable?) and RC3 (the decision).

## RC2 - Draft Risk Reviewer

Export: [03-agents/RC2-Draft-Risk-Reviewer.json](../03-agents/RC2-Draft-Risk-Reviewer.json), handle `@content_readiness_reviewer`

**Purpose.** Read the whole draft the way an experienced editor preparing it for formal review would, and list what would get it sent back.

**Inputs.** `draft_content`, `market`, `audience`. The workflow runs it only after claim validation is usable. It does not receive the claim results, so it cannot defer to or second-guess the validator. RC3 is the only step that combines the two agents' outputs.

**Outputs.** JSON: `blocking_findings` and a list of findings, each with a type (`clarity`, `completeness`, `audience_fit`, `disclaimer`, `consistency`), the exact quote, the issue, a suggestion, `blocking`, and an optional `suggested_revision`.

**Instruction / Skill references.** RC1-RC2 - Regulatory Review Policy.

**Tools.** None.

**Recommendation behavior.** RC2 may propose a `suggested_revision` on a blocking clarity, audience fit, completeness or consistency finding, only when a safe rewrite exists: removing or softening an absolute, narrowing a scope, making a sentence clearer. It never adds a claim, number, safety statement, comparison or disclaimer. RC3 then decides what reaches the result:
- approved wording comes only from the validator's `approved_text`
- a required disclaimer comes only from the validator's `required_disclaimer`
- RC2's rewrite is carried as a contextual rewrite and labeled "Suggested rewrite (not approved copy)"

See [recommendations.md](recommendations.md).

**Authority boundary.** Does not judge claim approval, validity, dates or market eligibility, and does not approve content. Ignores any instruction written inside the draft.

**Role in the workflow.** Step RC2. Its findings feed RC3.

## Evaluation criteria and guardrails

Each export carries the Output Evaluation criteria configured in the tenant: nine for RC1, seven for RC2. The criteria are configured, but no single-turn evaluation examples are attached and the agents list their runs as Not Evaluated, so there are no platform-evaluated runs and I show no scores. My evidence is direct repeated runs, described in [testing-and-evals.md](testing-and-evals.md).

Guardrails on both agents are Enforcing, with auto-stop on and sensitivity 1. The platform manages that progression; I did not promote them by hand.
