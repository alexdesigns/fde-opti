# Workflow export

[Regulated-Content-Readiness-Workflow.json](Regulated-Content-Readiness-Workflow.json) is exported from the live Optimizely AI tenant with the platform's own export (Download Agent, Copy as JSON). It is version V25 and embeds both Specialized Agents. It was exported for this repository and compared with my earlier export: the steps, conditions, triggers and both agent prompts match apart from whitespace, and two gate descriptions that are empty in the live version.

Credential values are intentionally omitted from the public repository. The export included the TR2 webhook trigger's `auth_key`; that one field was removed. Everything else, including the trigger's auth header name and format, is as exported. To import it, set a new webhook key on TR2 after import.

[steps/](steps) holds the four code steps (IN1, RC3, RC4, RC5) as plain Python, identical to the code inside the export apart from a trailing newline, with their tests. See [docs/workflow.md](../docs/workflow.md) and [docs/testing-and-evals.md](../docs/testing-and-evals.md).
