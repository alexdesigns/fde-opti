# Tool discovery

Live production tool discovery endpoint: https://lab.alexdesigns.com/fde-opti/discovery

`GET /fde-opti/discovery` returns static JSON in the shape the Optimizely AI tools SDK emits: a `functions` array, one entry per tool, each with `name`, `description`, `parameters` (name, type, description, required), a relative `endpoint` and `http_method`. Source: [app/fde-opti/discovery/route.ts](../app/fde-opti/discovery/route.ts), which serves `REGISTRY_DISCOVERY` from [shared/registry.ts](../shared/registry.ts).

## How it is registered

In Optimizely AI, one tool registry, "OptiThera Regulated Content Readiness", points at the discovery URL and holds the bearer token. Optimizely AI reads the function list, shows both tools in the registry, and calls each endpoint relative to the discovery host with `Authorization: Bearer <token>`.

## What it returns

| Tool | Endpoint | Method | Parameters |
|---|---|---|---|
| `validate_approved_claim` | `/fde-opti/tools/validate-approved-claim` | POST | `claim_ids` (array, required), `market` (string, required), `audience` (string, required), `as_of_date` (string, optional) |
| `submit_readiness_result` | `/fde-opti/tools/submit-readiness-result` | POST | `request_id`, `status`, `summary`, `validation_status` (strings, required), `formal_review_required` (boolean, required), `checked_at` (string, required), `findings` (array, required) |

Exactly these two tools. The tool descriptions are the text the agents see, so they carry the usage rules: send all cited IDs in one call, never guess a market or audience, pass the packaged result unchanged.

## Authentication

Discovery is public on purpose: it contains only tool metadata. It carries no credentials, headers, internal URLs or other tools. The tool endpoints are not public: both return 401 without the registry token.

## Checking it

```bash
curl -s https://lab.alexdesigns.com/fde-opti/discovery | python3 -m json.tool
```

A local server started from this folder returns the same JSON at `http://localhost:3000/fde-opti/discovery`; I compared the two before publishing and they were identical.
