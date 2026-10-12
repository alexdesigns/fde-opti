# Assignment mapping

Each take-home requirement, where it is implemented, and the artifact that shows it. The two-page PDF is the authoritative narrative; this repository adds engineering detail.

## Requirements

| Take-home requirement | Implementation | Repo artifact |
|---|---|---|
| Identify a real-world problem | Regulated-content issues found late, after briefs, content and pages are underway, causing rework and slower formal MLR review | [README](../README.md#problem), PDF page 1 |
| Instructions (Main Agent): additional context | OptiThera Regulated Content Intake (inputs, the four states, how to run the check, rules) and the shared Regulated Content Review Standard (authority boundaries, finding format, recommendation framing) | [instructions/](../instructions), [instructions-and-skills.md](instructions-and-skills.md) |
| Instructions (Main Agent): trigger instructions | The Intake Skill's keyword trigger description, plus its run rules: explicit request runs, complete draft asks once, revision asks again, missing input asks first, no duplicate run | [instructions-and-skills.md](instructions-and-skills.md#optithera-regulated-content-intake) |
| 2+ Specialized Agents: purpose | Claim Identification & Explanation Agent; Content Readiness Reviewer | [agents.md](agents.md) |
| Specialized Agents: inputs | Claim agent: draft, market, audience, as-of date, cited IDs. Reviewer: draft, market, audience | [agents.md](agents.md), parameters in each export |
| Specialized Agents: outputs | Claim agent: validation status, per-claim results, uncited claims. Reviewer: structured findings with optional suggested revision | [agents.md](agents.md), output schema in each export |
| Tool integration (existing and custom tools) | The Claim agent calls `validate_approved_claim`; RC5 calls `submit_readiness_result`; RC5 and IN1 use the ClickUp connector | [tools.md](tools.md), [workflow.md](workflow.md) |
| Agent Workflow | Regulated Content Readiness Workflow: two triggers, IN1, G1, RC1, G2, RC2, RC3, RC4, RC5 | [workflow/](../workflow), [workflow.md](workflow.md) |
| Optional custom tool: need | Claim facts have exact answers a model must not guess; webhook requests need a governed way back | [tools.md](tools.md) |
| Optional custom tool: purpose | Deterministic claim validation; result delivery | [tools.md](tools.md) |
| Optional custom tool: input types | Arrays, strings, a boolean, an array of finding objects | [tools.md](tools.md), [tools/discovery/README.md](../tools/discovery/README.md) |
| Optional custom tool: output | Per-claim outcome, reasons, approved wording, disclaimer; store acknowledgement | [tools.md](tools.md) |
| Optional custom tool: how its output is used | RC1 copies the validator's status, outcome, reasons, approved text and disclaimer unchanged; G2 routes on that status; RC3 sets the state from the outcomes and builds the Approved wording and Required disclaimer recommendations from the validator's own text | [workflow.md](workflow.md), [recommendations.md](recommendations.md) |
| Optional custom tool: hosting | Next.js routes on Vercel, one bearer-token registry, public discovery endpoint | [tools/README.md](../tools/README.md) |
| Optional custom tool: integration | One Optimizely AI tool registry registered from the discovery URL | [tools/discovery/README.md](../tools/discovery/README.md) |

## Deliverables

| Deliverable | Where |
|---|---|
| Exact names of Instructions, Specialized Agents and Workflow | [README assignment-to-component mapping](../README.md#assignment-to-component-mapping) |
| Main Agent (Instruction) text | [instructions/OptiThera-Regulated-Content-Intake.txt](../instructions/OptiThera-Regulated-Content-Intake.txt), [instructions/Regulated-Content-Review-Standard.txt](../instructions/Regulated-Content-Review-Standard.txt) |
| Specialized Agent JSON | [agents/Claim-Identification-Explanation-Agent.json](../agents/Claim-Identification-Explanation-Agent.json), [agents/Content-Readiness-Reviewer.json](../agents/Content-Readiness-Reviewer.json) |
| Workflow JSON | [workflow/Regulated-Content-Readiness-Workflow.json](../workflow/Regulated-Content-Readiness-Workflow.json) |
| Custom tool source on GitHub | [tools/](../tools) in this public repository |
| Two-page write-up | [submission/AlexHarris_OpalAgentSolution.pdf](../submission/AlexHarris_OpalAgentSolution.pdf) |

## Evaluation criteria

Where a reviewer can look for each one. I do not score myself.

| Criterion | Where to look |
|---|---|
| Clarity | README, the PDF, [architecture.md](architecture.md) |
| Functionality and completeness | The exports, the tool source, the tests in [testing-and-evals.md](testing-and-evals.md), the live discovery endpoint |
| Logical cohesion | How the Skills, agents, gates and code steps hand off: [workflow.md](workflow.md) |
| Practicality and efficiency | Fail-fast input checks before either agent runs, one batched validator call, only two agent steps, the prompt structure and evaluation criteria in each agent export, the credit figures in [workflow.md](workflow.md#credits-and-timing) |
| Understanding of Optimizely AI concepts | Skill triggers and mentions, Specialized Agent parameters and output schemas, Conditions, code steps, webhook and Chat triggers, tool registries, Output Evaluation, Guardrails: [agents.md](agents.md), [testing-and-evals.md](testing-and-evals.md) |
| Communication | The PDF and this repository |
