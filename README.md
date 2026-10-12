# OptiThera Regulated Content Readiness

Built by Alex Harris for the Optimizely Forward Deployed Engineer take-home. A governed agent workflow in Optimizely AI that finds regulated claims, checks them against governed claim records, reviews the draft in context and returns one of four readiness states before formal Medical, Legal and Regulatory (MLR) review.

OptiThera is a fictional pharmaceutical brand. Every claim, market and draft in this repository is fictional.

- Live documentation and demo: https://lab.alexdesigns.com/fde-opti
- Release with the full evaluator ZIP and the PDF write-up: https://github.com/alexdesigns/fde-opti/releases/tag/v1.2-fde-final

## Problem

Marketing teams often find claim, context and readiness issues after briefs, copy and page work are already underway. Formal review then rejects the draft for an unapproved claim, wording that drifted from the approved version, or a missing disclaimer. The work goes back, and reviewers spend time on content that was never ready for them.

## Solution

I moved the readiness check upstream, into the places marketers already work: Optimizely AI Chat, ClickUp and WordPress. One governed workflow identifies claims, verifies them against an approved-claims source, reviews the draft in context and returns the result.

The split that matters:

- AI interprets the content: which sentences are claims, and whether the draft reads right for its audience.
- Tools verify governed facts: whether a claim is approved, in date and allowed for this market and audience, and what its approved wording and disclaimer are.
- Workflow code controls validation, routing and state.
- People approve. `READY_FOR_FORMAL_REVIEW` is not approval. There is no approved state, and formal MLR approval stays with people.

## Architecture

```
TR1 - Trigger - Chat                  TR2 - Trigger - Webhook
(Optimizely AI Chat, IN0)             (ClickUp, WordPress, other systems)
            \                          /
             IN1  Validate - Request Context           code
             G1   Gate - Inputs Complete?              condition ── no ──┐
             RC1  Claims - Identification & Explanation                  │
                    agent, calls validate_approved_claim once            │
             G2   Gate - Claim Validation Usable?      condition ── no ──┤
             RC2  Review - Content Readiness           agent             │
             RC3  Decision - Readiness State           code  <───────────┘
             RC4  Package - Readiness Result           code
             RC5  Deliver - External Result            code
                    submit_readiness_result, ClickUp connector, or Chat reply
```

The step names are the live names in the tenant. IN0 is the Chat instruction. IN1 is the first workflow step. RC1 and RC2 are the two specialized agents, and RC3 to RC5 are the code steps that decide, package and deliver. G1 and G2 are the two gates. There are eight steps: two agents, two gates and four code steps (IN1, RC3, RC4, RC5), plus two triggers.

Details: [docs/architecture.md](docs/architecture.md) and [docs/workflow.md](docs/workflow.md).

## States

RC3 returns exactly one of four states, set by fixed rules in code:

| State | Meaning |
|---|---|
| `INPUT_REQUIRED` | Draft, market or audience missing or malformed. Nothing was checked. |
| `NEEDS_REVISION` | At least one claim or content issue must be fixed. Findings say what. |
| `VALIDATION_UNAVAILABLE` | Claims could not be checked, so nothing is reported as ready. |
| `READY_FOR_FORMAL_REVIEW` | Every cited claim valid with matching wording, no blocking content issue. |

## Assignment-to-component mapping

The take-home uses the terms Instructions, Main Agent, Specialized Agents, Agent Workflows and Tools. The Optimizely AI interface calls Instructions "Skills". Names and versions below are exactly as built in the tenant.

| Assignment concept | Component (exact name) | Version | File |
|---|---|---|---|
| Instructions / Main Agent | IN0 - OptiThera Content Intake (primary Skill, shortcut `/content-readiness`) | V16 | [instructions/IN0-OptiThera-Content-Intake.txt](instructions/IN0-OptiThera-Content-Intake.txt) |
| Instructions (supporting) | RC1-RC2 - Regulatory Review Policy (Skill, `@regulated-readiness-standard`) | V4 | [instructions/RC1-RC2-Regulatory-Review-Policy.txt](instructions/RC1-RC2-Regulatory-Review-Policy.txt) |
| Specialized Agent | RC1 - Claim Identification & Explanation Agent | V5 | [agents/RC1-Claim-Identification-and-Explanation-Agent.json](agents/RC1-Claim-Identification-and-Explanation-Agent.json) |
| Specialized Agent | RC2 - Draft Risk Reviewer | V7 | [agents/RC2-Draft-Risk-Reviewer.json](agents/RC2-Draft-Risk-Reviewer.json) |
| Agent Workflow | Regulated Content Readiness Workflow | V25 | [workflow/Regulated-Content-Readiness-Workflow-V25.json](workflow/Regulated-Content-Readiness-Workflow-V25.json) |
| Custom Tool | `validate_approved_claim` | one registry | [tools/validate-approved-claim](tools/validate-approved-claim) |
| Custom Tool | `submit_readiness_result` | one registry | [tools/submit-readiness-result](tools/submit-readiness-result) |

The workflow export has the TR2 webhook `auth_key` replaced with `REDACTED`; nothing else was changed.

## How a request runs

1. In Chat, IN0 gathers the draft, market and audience and starts the workflow through TR1 when the marketer uses `/content-readiness`. A bare "yes" does not start it. ClickUp and WordPress start it through TR2. Both converge at IN1.
2. IN1 checks the draft, market and audience. G1 stops early if something is missing: `INPUT_REQUIRED`.
3. RC1 finds claims and calls `validate_approved_claim` once with every cited ID. G2 stops if validation could not run: `VALIDATION_UNAVAILABLE`.
4. RC2 reviews the full draft in context and returns findings. It never sets the state.
5. RC3 applies fixed rules and sets exactly one state.
6. RC4 packages the result. RC5 returns it to where the request came from: a ClickUp comment and status, a callback through `submit_readiness_result`, or a Chat reply.
7. A person reviews. Formal approval happens outside the workflow.

## Known limits

- Reviewer judgment can vary on borderline drafts. Routing and state rules do not, because code owns them.
- When a draft cites no claim ID the validator is not called, and the packaged validation status still reads `ok`. Nothing was checked against the register in that case. Uncited claims still produce `NEEDS_REVISION`.
- The callback endpoint is protected by a bearer token, an unguessable pending request ID, a strict schema, first-result-wins and a 24 hour expiry. The platform gives no trustworthy caller-identity signal, so I do not claim verified Optimizely origin.
- Chat starts the check on `/content-readiness` or a clear request such as "run content readiness". A bare "yes" is not a reliable trigger on this platform, so it does not start a run.
- Chat input is not guaranteed byte-preserving: some Chat runs normalized whitespace, while every word and its order stayed intact in the tested drafts. Chat can also fill an as-of date the user did not give.
- Output evaluation criteria are configured on both agents (nine on RC1, seven on RC2), but no single-turn examples are attached and the current versions list their runs as Not Evaluated. I validated with direct repeated runs and UAT.
- Success measures in the write-up are targets, not measured business results.

## Repository contents

| Folder | What is in it |
|---|---|
| [docs/](docs) | Architecture, workflow, agents, instructions, tools, recommendations, testing, integrations, assignment mapping |
| [instructions/](instructions) | Text of both instructions (Skills) |
| [agents/](agents) | Both specialized agents, exported from the tenant |
| [workflow/](workflow) | The V25 export and the four code steps as Python with their tests |
| [tools/](tools) | Source for both custom tools and the discovery route, as a small Next.js service |
| [examples/](examples) | A webhook request and two results produced by the workflow's own code steps |
| [submission/](submission) | The two-page write-up |

Each assignment requirement, mapped to where it is met: [docs/assignment-mapping.md](docs/assignment-mapping.md).

## License

[MIT](LICENSE). The code was written for this take-home.
