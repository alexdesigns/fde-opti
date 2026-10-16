# OptiThera Regulated Content Readiness

A pre-review workflow built in Optimizely AI that catches regulated-content issues before formal Medical, Legal and Regulatory (MLR) review. Optimizely Forward Deployed Engineer take-home by Alex Harris.

## Start here

To run it yourself, with a good and a bad example, see [QUICK-START.md](QUICK-START.md).

1. `01-writeup/AlexHarris_OpalAgentSolution.pdf`: the two-page write-up.
2. `02-instructions/`: how the system is instructed, including the trigger text for the main Instruction.
3. `03-agents/`: the two Specialized Agents, where AI judgment is used.
4. `04-workflow/`: how the agents, two deterministic gates and four code steps fit together. The code for each code step, with its tests, is in `04-workflow/code-steps/`.
5. `05-tools/`: the claim lookup tool and the result delivery tool, as a small Next.js service with tests.
6. The evaluator ZIP and the PDF are attached to the [latest release](https://github.com/alexdesigns/fde-opti/releases/latest).

## The problem

Marketing content often reaches formal MLR review with problems that could have been caught earlier: a claim that isn't approved, wording that drifted from the approved text, a missing disclaimer, or copy that doesn't fit the audience. The draft goes back, formal review slows down, and MLR teams spend time on work that wasn't ready.

## What I built

A readiness check that runs earlier, in the places marketers already work: Optimizely AI Chat, ClickUp and WordPress. Every request goes through one workflow and ends in one of four states: `INPUT_REQUIRED`, `NEEDS_REVISION`, `VALIDATION_UNAVAILABLE` or `READY_FOR_FORMAL_REVIEW`. `READY_FOR_FORMAL_REVIEW` means the draft can go to human MLR review. It is not approval, and there is no approved state.

## Why this architecture

I didn't use AI for every step. The two agents do the work that needs reading and judgment: spotting claims in marketing copy and reviewing a whole draft in context. Whether a claim is approved is a fact, so a tool looks it up. Checking required inputs, setting the final state, packaging the result and sending it back each have one controlled answer, so those are code. A model's judgment can vary from run to run, while the readiness state is set by fixed rules in code. Formal approval stays with people.

Built in Optimizely AI: 2 instructions, 2 specialized agents, 2 custom tools, 1 workflow, 4 code steps, 2 deterministic gates, 2 triggers.

## Components (exact names in the Optimizely AI instance)

| Type | Exact name | File |
|---|---|---|
| Instruction (main) | IN0 - OptiThera Content Intake | `02-instructions/IN0-OptiThera-Content-Intake.txt` and `.json` |
| Instruction (used by both agents) | RC1-RC2 - Regulatory Review Policy | `02-instructions/RC1-RC2-Regulatory-Review-Policy.txt` and `.json` |
| Specialized Agent | RC1 - Claim Identification & Explanation Agent | `03-agents/RC1-Claim-Identification-and-Explanation-Agent.json` |
| Specialized Agent | RC2 - Draft Risk Reviewer | `03-agents/RC2-Draft-Risk-Reviewer.json` |
| Agent Workflow | Regulated Content Readiness Workflow | `04-workflow/Regulated-Content-Readiness-Workflow.json` |
| Custom tools | `validate_approved_claim`, `submit_readiness_result` (one tool registry) | `05-tools/` |
| Existing tools | ClickUp tools (read the task and its draft, post the result) | used by the IN1 and RC5 code steps |

Optimizely AI lists Instructions under Skills.

## What is real and what is fictional

OptiThera, its product, claims and drafts are fictional. The Instructions, agents, workflow, code, tools and the ClickUp and WordPress connections are the actual build.

Every `.json` file is an unchanged platform export, except the workflow. The TR2 webhook auth_key is replaced with REDACTED.

## Also in this repository

- `docs/`: longer notes on the architecture, each component, the tools, testing and the assignment mapping.
- `examples/`: a webhook request and two results produced by the workflow's own code.
- Tests: `python3 test_steps.py .` (and the other `test_*.py` files) in `04-workflow/code-steps/`; `npm test` in `05-tools/`.
