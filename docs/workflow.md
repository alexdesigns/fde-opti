# Regulated Content Readiness Workflow

Export: [workflow/Regulated-Content-Readiness-Workflow.json](../workflow/Regulated-Content-Readiness-Workflow.json), live version V25, schema 1.4. The four code steps are also in [workflow/steps/](../workflow/steps) as plain Python, identical to the code in the export apart from a trailing newline, with their tests.

## Steps

### IN1 - Validate - Request Context
- **Type:** code (Python), 120 s timeout
- **Purpose:** check inputs before anything else runs.
- **Input:** `draft_content`, `market`, `audience`, `as_of_date` (Chat), or `webhook_payload` (webhook).
- **Output:** `gate` (`INPUTS_OK`, `INPUT_REQUIRED` or `DUPLICATE_DELIVERED`), the list of missing inputs, normalized market and audience, and `cited_claim_ids` taken from the draft with the pattern `[CLM-nnn]`.
- **Failure behavior:** missing or malformed input gives `INPUT_REQUIRED` and no model runs. Market must be a two-letter code; `USA` is rejected, not converted. Every value echoed into `gate` is pattern-checked, so text inside the draft cannot set the gate; the step tests include spoofing attempts.

### G1 - Gate - Inputs Complete?
- **Type:** condition
- **Purpose:** route on the IN1 gate.
- **Rows:** contains `INPUTS_OK` goes to RC1; does not contain `INPUTS_OK` goes to RC3.
- **Failure behavior:** the two rows are complementary, so every output has a route.

### RC1 - Claims - Identification & Explanation
- **Type:** Specialized Agent, Claim Identification & Explanation Agent
- **Purpose:** interpret claims.
- **Input:** draft, market, audience, as-of date, cited claim IDs.
- **Tool:** `validate_approved_claim`, called once with all cited IDs.
- **Output:** JSON with `validation_status`, per-claim results (tool outcome, reasons, approved text, required disclaimer, whether the draft wording matches) and `unresolved_candidate_claims` (claim-like statements that cite no ID).
- **Failure behavior:** the agent never changes the caller's inputs and never retries with altered values. A failed call is reported as such.

### G2 - Gate - Claim Validation Usable?
- **Type:** condition, two regex rows on `validation_status`
- **Purpose:** stop safely when governed validation is not available.
- **Rows:** `ok` or `not_called` goes to RC2; anything else goes to RC3.
- **Failure behavior:** a tool outage or an invalid request skips the review and ends as `VALIDATION_UNAVAILABLE`.

### RC2 - Review - Content Readiness
- **Type:** Specialized Agent, Content Readiness Reviewer
- **Purpose:** review the draft in context.
- **Input:** draft, market, audience.
- **Output:** `blocking_findings` and a list of findings (type, quote, issue, suggestion, blocking), with an optional `suggested_revision` on a blocking finding.
- **Failure behavior:** unreadable output becomes `VALIDATION_UNAVAILABLE` in RC3. The reviewer does not judge claim validity.

### RC3 - Decision - Readiness State
- **Type:** code, 30 s timeout
- **Purpose:** assign exactly one state by fixed rules.
- **Input:** IN1 gate and context, the full RC1 output, the full RC2 output.
- **Output:** `state`, a reason, claim and content findings, recommendations, and a Markdown report used for the Chat reply.
- **Rules, in order:**
  1. Gate is not `INPUTS_OK`: `INPUT_REQUIRED`.
  2. Claim output unreadable, validation not `ok` when IDs were cited, a status other than `not_called` when none were, or returned claim IDs that differ from the cited IDs: `VALIDATION_UNAVAILABLE`.
  3. Review output unreadable: `VALIDATION_UNAVAILABLE`.
  4. Every cited claim valid with matching wording, no uncited claim, no blocking content finding: `READY_FOR_FORMAL_REVIEW`.
  5. Anything else: `NEEDS_REVISION`.

### RC4 - Package - Readiness Result
- **Type:** code, 30 s timeout
- **Purpose:** produce the external result contract.
- **Input:** IN1 output, RC3 output, `request_id` from the webhook payload.
- **Output:** `status`, `summary`, `validation_status`, `formal_review_required: true`, `checked_at`, `findings`, and whether a callback is required.
- **Failure behavior:** if the decision cannot be read, the result is `VALIDATION_UNAVAILABLE`, never ready. A malformed `request_id` is flagged as invalid and dropped, never repaired.

### RC5 - Deliver - External Result
- **Type:** code, 120 s timeout
- **Purpose:** deliver the packaged result.
- **Input:** RC4 output, unchanged.
- **Output:** a delivery record.
- **Behavior by source:** Chat needs no callback. A webhook request with a `request_id` goes to `submit_readiness_result`. A ClickUp request writes the Content Readiness and Last Checked fields, posts one comment, then moves the task status. A repeated ClickUp event (IN1 gate `DUPLICATE_DELIVERED`) posts nothing.

## State model

| State | Meaning | Can go to formal review? |
|---|---|---|
| `INPUT_REQUIRED` | Draft, market or audience missing or malformed. Nothing was checked. | No |
| `NEEDS_REVISION` | At least one claim or content issue must be fixed. Findings say what. | No |
| `VALIDATION_UNAVAILABLE` | Claims could not be checked, or a step's output could not be trusted. | No |
| `READY_FOR_FORMAL_REVIEW` | Every cited claim valid with matching wording, no blocking content issue. | Yes, to human reviewers |

There is no automated `APPROVED` state, and the step tests check that none appears.

## Credits and timing

Only RC1 and RC2 use a model, but orchestration is not free: in early runs, a run that stopped before either agent showed 8 credits on the execution page, and runs that reached both agents showed 18. Later V25 runs showed 20 to 22. These are the figures displayed by the tenant, not a computed cost model.
