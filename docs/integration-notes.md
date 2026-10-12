# Integration notes

These are secondary to the workflow. They show the same workflow, unchanged, started from ClickUp, WordPress and a browser extension as well as Chat. No surface runs it unless the user asks or has turned on auto-run, and auto-run fires only when meaningful content changed.

**Optimizely AI Chat.** The OptiThera Regulated Content Intake Skill is the entry point in Chat. It gathers the draft, market and audience, runs the workflow on a clear request or after one confirming question, and presents the workflow's result. See [instructions-and-skills.md](instructions-and-skills.md).

**ClickUp.** Moving a task to Internal Review is the deliberate trigger. A ClickUp automation calls the TR2 webhook; IN1 reads the task's Market and Audience fields and its draft Doc through the ClickUp connector, so no model picks the task or rewrites the draft. RC5 writes the Content Readiness and Last Checked fields, posts one comment with the findings and any recommendations, and moves the task to "formal review" or "changes needed". It never edits the content, and a retried event posts nothing.

**WordPress.** In the editor sidebar, a "Run Content Readiness" button runs the check manually; that is the default. An optional per-editor "Run automatically on update" setting runs it after a meaningful manual update, never on autosave, preview or unchanged content. When content changes after a result, the result is marked stale until the next run. The sidebar shows findings and recommendations with their labels and a copy button; it never edits a block or publishes. Requests go through a server-side gateway to the same TR2 webhook, and results return through `submit_readiness_result`, so the browser never holds a credential.

**Browser extension.** An explicit action: the user clicks run. It uses the same gateway and callback path, shows the result with each recommendation's label, reason and source, and offers copy buttons. It never changes the live page.
