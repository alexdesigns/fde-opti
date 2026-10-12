# OptiThera Regulated Content Readiness

A governed agent workflow built in Optimizely AI (Opal) that identifies regulated claims, verifies them against governed claim records, reviews the draft in context and returns a controlled readiness state before formal Medical, Legal and Regulatory (MLR) review.

This is my submission for the Optimizely Forward Deployed Engineer take-home. OptiThera is a fictional pharmaceutical brand, and every claim, market and draft in this repository is fictional.

## Problem

Marketing teams often find claim, context and readiness issues after briefs, content and page work are already underway. A brief gets written, copy gets drafted, a page gets built, and only then does formal review find an unapproved claim, wording that drifted from the approved version, or a missing disclaimer. The work goes back, and MLR reviewers spend time on drafts that were never ready for them.

## Solution

I moved a readiness check upstream, into the places marketers already work, and split the job by what each part is good at:

- AI interprets the content: which sentences are claims, and whether the draft reads right for its audience.
- Tools verify governed facts: whether a claim is approved, in date and allowed for this market and audience, and what its approved wording and disclaimer are.
- Workflow code controls state and routing: four allowed states, decided by fixed rules.
- Formal approval stays with people. Nothing here approves content.

## Architecture

```
Optimizely AI Chat (TR1)        Webhook: ClickUp, WordPress, other systems (TR2)
            \                      /
             IN1  Validate request context          code
             G1   Inputs complete?                  condition ── no ──┐
             RC1  Claim Identification & Explanation Agent            │
                    └─ validate_approved_claim (custom tool)          │
             G2   Claim validation usable?          condition ── no ──┤
             RC2  Content Readiness Reviewer                          │
             RC3  Decide readiness state            code  <───────────┘
             RC4  Package readiness result          code
             RC5  Deliver result                    code
                    └─ submit_readiness_result (custom tool), ClickUp connector, or Chat reply
```

RC3 returns exactly one of four states: `INPUT_REQUIRED`, `NEEDS_REVISION`, `VALIDATION_UNAVAILABLE`, `READY_FOR_FORMAL_REVIEW`. There is no approved state. Details: [docs/architecture.md](docs/architecture.md) and [docs/workflow.md](docs/workflow.md).

## Components

The take-home uses the terms Instructions, Main Agent, Specialized Agents, Agent Workflows and Tools. The current Optimizely AI interface calls Instructions "Skills". This table maps one to the other.

| Assignment concept | Component (exact name) | Purpose | Artifact |
|---|---|---|---|
| Instruction (Main Agent entry behavior) | OptiThera Regulated Content Intake (Skill) | Gathers draft, market and audience in Chat and runs the workflow only on a clear request | [instructions/OptiThera-Regulated-Content-Intake.txt](instructions/OptiThera-Regulated-Content-Intake.txt) |
| Shared Instruction | Regulated Content Review Standard (Skill) | One review standard and authority boundary used by both agents | [instructions/Regulated-Content-Review-Standard.txt](instructions/Regulated-Content-Review-Standard.txt) |
| Specialized Agent 1 | Claim Identification & Explanation Agent | Validates cited claim IDs with the tool and explains each result | [agents/Claim-Identification-Explanation-Agent.json](agents/Claim-Identification-Explanation-Agent.json) |
| Specialized Agent 2 | Content Readiness Reviewer | Reviews the full draft in context and returns structured findings | [agents/Content-Readiness-Reviewer.json](agents/Content-Readiness-Reviewer.json) |
| Agent Workflow | Regulated Content Readiness Workflow | Orders the steps, gates on inputs and validation, sets the state in code | [workflow/Regulated-Content-Readiness-Workflow.json](workflow/Regulated-Content-Readiness-Workflow.json) |
| Custom Tool 1 | `validate_approved_claim` | Deterministic lookup of governed claim facts | [tools/validate-approved-claim](tools/validate-approved-claim) |
| Custom Tool 2 | `submit_readiness_result` | Returns the packaged result to callback-based integrations | [tools/submit-readiness-result](tools/submit-readiness-result) |

## Repository contents

| Folder | What is in it |
|---|---|
| [docs/](docs) | Architecture, workflow, agents, Skills, tools, recommendations, testing and evals, integrations, and the assignment mapping |
| [instructions/](instructions) | The live text of both Skills |
| [agents/](agents) | Both Specialized Agents, exported from the live tenant |
| [workflow/](workflow) | The workflow export and the four code steps as Python files with their tests |
| [tools/](tools) | Source for both custom tools and the discovery route, runnable as a small Next.js service |
| [examples/](examples) | A webhook request and two results, generated by the workflow's own code steps |
| [submission/](submission) | The two-page write-up submitted with the take-home |

## Human approval boundary

`READY_FOR_FORMAL_REVIEW` means the draft can go to formal review. It is not approval. Medical, Legal and Regulatory approval stays with the human reviewers, outside this workflow.

## Take-home alignment

Each requirement, mapped to where it is met: [docs/assignment-mapping.md](docs/assignment-mapping.md).

## Supporting references

Everything needed to evaluate the submission is in this repository and the PDF. Two extra links:

- Optional visual walkthrough / supporting documentation: https://lab.alexdesigns.com/fde-opti
- Live production tool discovery endpoint: https://lab.alexdesigns.com/fde-opti/discovery

## License

[MIT](LICENSE). The code was written for this take-home.
