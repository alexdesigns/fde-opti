# Quick start: run the workflow

Run these in Optimizely AI Chat in the instance where the take-home was built. Every example below was run there on 16 October 2026.

## Run it

1. Start a new Chat conversation.
2. Paste an example below and send it. Keep the line break between the first line and the draft.
3. Wait a few minutes. The reply shows the readiness state and the findings.
4. Open **Agents, then Executions**, and open the newest *Regulated Content Readiness Workflow* run to see each step.

Start the message with `@regulated_content_readiness_workflow`, or with the `/content-readiness` shortcut. Both start the same workflow. A reply such as "yes" or "go ahead" does not.

## Good example

Expected: `READY_FOR_FORMAL_REVIEW`

```text
@regulated_content_readiness_workflow Market: US. Audience: hcp. As-of date: 2026-10-09.
Draft: OptiThera is indicated for adults with moderate to severe plaque psoriasis. [CLM-001] OptiThera is taken once daily as an oral tablet. [CLM-002] See full Prescribing Information.
```

Both cited claims are approved for US and hcp, and the wording matches the approved text. Execution `38a57c1c`.

## Bad example

Expected: `NEEDS_REVISION`

```text
@regulated_content_readiness_workflow Market: US. Audience: patient. As-of date: 2026-10-09.
Draft: OptiThera is indicated for adults with plaque psoriasis. [CLM-001] See full Prescribing Information.
```

CLM-001 is a valid claim ID, but the approved wording says "moderate to severe" and this draft dropped it. The validator accepts the ID, the wording check catches the change, and the result suggests the approved wording. A valid claim ID alone is not enough. Execution `e80af3a7`.

## What to look for

- **The state at the top of the reply.** It should match the expected state.
- **Each finding's quote.** Compare it with the approved wording. The finding names what changed.
- **The execution graph.** Each step shows as run or skipped, and the claim check runs once.
- **The wording.** No result says approved, compliant or cleared. `READY_FOR_FORMAL_REVIEW` means a person reviews it next.

## Two more inputs

- **No market.** Chat asks "Which market (as a two-letter country code, for example US or UK) is this draft for?" and starts no run until you answer.
- **`Market: USA`.** From Chat this returns `READY_FOR_FORMAL_REVIEW` (execution `8e74b304`). The intake Instruction passed `US` to the workflow, so the workflow's own check never saw `USA`. IN1 itself accepts only a two-letter market (`check_inputs.py`), so the gap is in the Chat intake, not the workflow. The Chat conversion is an open finding: IN0 says never to guess a market, and this run shows it still normalizes one.

## Run the tests

```bash
cd 04-workflow/code-steps && for t in test_steps test_delivery test_clickup test_examples; do python3 -I $t.py .; done
cd 05-tools && npm install && npm test
```
