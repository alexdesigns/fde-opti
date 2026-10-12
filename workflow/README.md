# Workflow export

[Regulated-Content-Readiness-Workflow.json](Regulated-Content-Readiness-Workflow.json) is the Regulated Content Readiness Workflow, exported from the Optimizely AI tenant with the platform's own export (Download Agent, Copy as JSON). It embeds both specialized agents.

Credential values are intentionally omitted. The export included the TR2 webhook trigger's `auth_key`; that one field is replaced with `REDACTED`. A few code comments and one error message were lightly reworded for this package; the logic, the trigger's auth header name and format, and everything else are as exported. To import it, set a new webhook key on TR2 after import.

[steps/](steps) holds the four code steps (IN1, RC3, RC4, RC5) as plain Python, identical to the code inside the export apart from a trailing newline, with their tests. See [docs/workflow.md](../docs/workflow.md) and [docs/testing-and-evals.md](../docs/testing-and-evals.md).
