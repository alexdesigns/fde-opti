# validate_approved_claim

Checks the claim IDs cited in a draft against the approved-claims register for one market, one audience and an as-of date. Only the Claim Identification & Explanation Agent calls it, once per run with every cited ID. No model runs inside it.

Inputs, outputs, examples and failure behavior: [docs/tools.md](../../docs/tools.md#validate_approved_claim).

| File | Role |
|---|---|
| [validate.ts](validate.ts) | Request parsing, the rules, and the tool's discovery entry |
| [approved-claims.ts](approved-claims.ts) | The fictional four-claim register. Replace `loadClaims` to read a real claims system |
| [validate.test.ts](validate.test.ts) | Unit tests: every rule, input rejection, `USA` stays invalid, failure never reports valid |
| [../app/fde-opti/tools/validate-approved-claim/route.ts](../app/fde-opti/tools/validate-approved-claim/route.ts) | The HTTP route: authenticates, validates, logs IDs and outcomes, never draft text |
