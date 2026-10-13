# Custom tools

Both tools are served by one tool registry in Optimizely AI, named "OptiThera Regulated Content Readiness". The registry is registered with a discovery URL; Optimizely AI reads the tool list from it and calls each tool's endpoint with the registry's bearer token. Source: [05-tools/](../05-tools). Discovery: [05-tools/discovery/README.md](../05-tools/discovery/README.md).

| | `validate_approved_claim` | `submit_readiness_result` |
|---|---|---|
| Endpoint | `POST /fde-opti/tools/validate-approved-claim` | `POST /fde-opti/tools/submit-readiness-result` |
| Called by | RC1 - Claim Identification & Explanation Agent | RC5, the delivery code step |
| Decides | Governed claim facts | Nothing. It delivers. |
| Model inside | None | None |
| Hosting | Next.js route on Vercel | Next.js route on Vercel |

## Authentication

One bearer token authenticates the registry. It is stored in Optimizely AI's registry settings and in the service's `OPTITHERA_REGULATED_REGISTRY_TOKEN` environment variable, and never in this repository. Both routes compare it in constant time and fail closed: no configured token returns 503, a wrong or missing token returns 401. The token only authenticates the caller; each tool still validates its own input and writes only what it allows.

## validate_approved_claim

**Purpose.** Authoritative lookup of governed claim facts: for each cited claim ID, is it approved, in date, for this market and this audience, not superseded, and what are its approved wording and required disclaimer.

**Why a custom tool.** These questions have exact answers. A model asked "is CLM-004 still usable?" can be persuaded, can guess, or can be confidently wrong, and a regulated workflow cannot accept any of those. A lookup against the register cannot be persuaded and does not guess. Keeping it in a tool also means the model never sees the whole register, only the results for the IDs the draft cites.

**Inputs.**

| Name | Type | Required | Notes |
|---|---|---|---|
| `claim_ids` | array of strings | yes | IDs as cited in the draft, 1 to 25. Duplicates are removed. |
| `market` | string | yes | Two-letter country code. Case is folded (`us` becomes `US`); length and format are not, so `USA` is rejected, not converted. |
| `audience` | string | yes | `hcp` or `patient`, case folded |
| `as_of_date` | string | no | `YYYY-MM-DD`, must be a real date. Defaults to today (UTC). |

Optimizely AI sends `{"parameters": {...}}`; the tool also accepts the bare object.

**Outputs.** `status` (`ok`, `invalid_request`, `validation_unavailable`), `all_valid`, `as_of_date`, `error`, and per claim:
- `outcome`: `valid`, `not_valid` or `not_found`
- `reasons`, every failing rule, not just the first: `not_approved`, `not_yet_effective`, `expired`, `superseded`, `market_mismatch`, `audience_mismatch`
- `approved_text`, `required_disclaimer`, `superseded_by`

**Example request.**

```json
{"parameters": {"claim_ids": ["CLM-001", "CLM-004"], "market": "US", "audience": "patient", "as_of_date": "2026-10-09"}}
```

**Example response (HTTP 200).**

```json
{
  "status": "ok",
  "all_valid": false,
  "as_of_date": "2026-10-09",
  "results": [
    {"claim_id": "CLM-001", "outcome": "valid", "reasons": [],
     "approved_text": "OptiThera is indicated for adults with moderate to severe plaque psoriasis.",
     "required_disclaimer": "See full Prescribing Information.", "superseded_by": null},
    {"claim_id": "CLM-004", "outcome": "not_valid", "reasons": ["superseded"],
     "approved_text": "OptiThera is indicated for adults with plaque psoriasis.",
     "required_disclaimer": "See full Prescribing Information.", "superseded_by": "CLM-001"}
  ],
  "error": null
}
```

**Failure behavior.** A malformed request returns HTTP 400 with `status: invalid_request` and a plain error message, which reaches the agent. If the claims source cannot be read, HTTP 503 with `status: validation_unavailable` and no results. `all_valid` is never true on an error. The route logs claim IDs, market, audience, outcomes and duration, never draft text.

**What it does not do.** It does not perform formal MLR approval and does not read prose. It checks only IDs that are written in the draft. When a draft cites no ID, RC1 does not call it, and nothing is checked against the register for that run.

**The register.** [approved-claims.ts](../05-tools/validate-approved-claim/approved-claims.ts) is a fictional four-claim register built to exercise each rule: CLM-001 valid for US, both audiences; CLM-002 valid for US and UK, HCP only; CLM-003 expired; CLM-004 superseded by CLM-001. In a real deployment `validateClaims` takes a different `loadClaims` that reads the customer's claims system, read-only.

## submit_readiness_result

**Purpose.** Return the packaged readiness result to integrations that wait for a callback. Today those are requests that come through the server-side gateway used by WordPress and the browser extension.

**Why a custom tool.** A workflow started by webhook has no reply channel. The requester needs a way to get the result back that does not depend on a model choosing what to send. RC5 is code and calls this tool with RC4's output unchanged.

**It is delivery, not decisioning.** It cannot set or change a state. It validates and stores what the workflow decided.

**Not every source uses it.** Chat gets the result as the reply. ClickUp results are written directly to the task by RC5 through the ClickUp connector.

**Inputs.**

| Name | Type | Required | Notes |
|---|---|---|---|
| `request_id` | string | yes | UUID issued by the gateway when the request was accepted |
| `status` | string | yes | One of the four states |
| `summary` | string | yes | Up to 500 characters |
| `validation_status` | string | yes | `ok`, `not_called`, `validation_unavailable` or `invalid_request` |
| `formal_review_required` | boolean | yes | Must be true |
| `checked_at` | string | yes | ISO 8601 time |
| `findings` | array | yes | Up to 50. Each has `type`, `severity` (`blocking` or `advisory`), `quote`, `issue`, `suggestion`, optional `recommendation` |

Optimizely AI may send arrays and nested objects as JSON text and booleans as strings. The tool accepts those forms and nothing looser.

**Output.** `{"status": "ok"}` when stored, `{"status": "ok", "duplicate": true}` for an identical retry. Errors carry a `code`.

**Example request.** [examples/needs-revision-result.json](../examples/needs-revision-result.json) is a complete body, as RC4 produces it.

**Failure behavior.**

| Case | HTTP | Code |
|---|---|---|
| Body over 64 KB | 413 | |
| Not JSON, wrong shape, unknown state, `formal_review_required` not true | 400 | e.g. `invalid_status` |
| `READY_FOR_FORMAL_REVIEW` with a blocking finding, or a recommendation outside a blocking `NEEDS_REVISION` finding | 400 | `inconsistent_result` |
| No pending request with that ID | 404 | `unknown_request` |
| Request older than 24 hours | 410 | `expired` |
| A different result already stored for the ID | 409 | `conflict` |
| Store unreachable | 503 | |

**Callback security.** The controls are: the registry bearer token (held by Optimizely AI and the service environment, never by a browser, CMS page or extension), an unguessable pending `request_id` issued when the request was accepted, a strict schema, first result wins (a different second result is rejected with 409), and a 24 hour expiry. The platform does not give the tool a trustworthy signal about who is calling, so I do not claim the callback is verified as coming from Optimizely. Authorized tenant users, and Chat, can read run inputs, so "Enabled in Chat" being off is not a security boundary.

**Result store.** Only the normalized result is stored, never the draft. Production uses a private Vercel Blob store with create-if-absent writes and compare-and-swap completion, so one request ID is completed at most once. Local runs use a file store. Delivery is at most once per request ID, not exactly once end to end.

## Not included

The gateway that WordPress and the extension call (it accepts the CMS request, issues the `request_id`, creates the pending record, calls TR2 and serves the result) is part of a separate application and is not in this repository. Its contract with the workflow is the TR2 body in [examples/request-example.json](../examples/request-example.json) and the result shape above.
