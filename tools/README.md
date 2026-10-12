# Custom tool service

The source for `validate_approved_claim`, `submit_readiness_result` and the discovery route, as a small Next.js app. These are the files that run in production. What changed for this repository: import paths, the bearer-token check moved from a larger module into `shared/token.ts` unchanged, unrelated service names removed from one test, and a test that guards the published examples. In production they run inside my Lab app at lab.alexdesigns.com, which is why the code and the live tool descriptions refer to "the Lab".

```
app/fde-opti/discovery/route.ts                        GET  /fde-opti/discovery
app/fde-opti/tools/validate-approved-claim/route.ts    POST /fde-opti/tools/validate-approved-claim
app/fde-opti/tools/submit-readiness-result/route.ts    POST /fde-opti/tools/submit-readiness-result
validate-approved-claim/   the claim rules and the fictional register
submit-readiness-result/   the result contract and the result store
shared/                    the registry manifest, bearer-token check, example guards
discovery/                 what discovery returns and how it is registered
```

Tool specifications: [docs/tools.md](../docs/tools.md).

## Prerequisites

Node.js 20 or later, npm.

## Run locally

```bash
cd tools
npm install
cp .env.example .env.local      # then set OPTITHERA_REGULATED_REGISTRY_TOKEN to any long random value
npm test                        # 55 unit tests, no network, no model
npm run build && npm start      # serves on port 3000
```

## Try it

Export the same token value in the shell you call from:

```bash
export OPTITHERA_REGULATED_REGISTRY_TOKEN=<the value in .env.local>
curl -s http://localhost:3000/fde-opti/discovery

curl -s -X POST http://localhost:3000/fde-opti/tools/validate-approved-claim \
  -H "Authorization: Bearer $OPTITHERA_REGULATED_REGISTRY_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"parameters":{"claim_ids":["CLM-001","CLM-004"],"market":"US","audience":"patient","as_of_date":"2026-10-09"}}'
```

Expected: HTTP 200, `all_valid: false`, CLM-001 `valid`, CLM-004 `not_valid` with reason `superseded` and `superseded_by: "CLM-001"`. The full response is in [docs/tools.md](../docs/tools.md#validate_approved_claim). The same call with `"market":"USA"` returns HTTP 400 `invalid_request`, and any call without the token returns 401.

## Deploy on Vercel

Import the repository with `tools` as the root directory. Set `OPTITHERA_REGULATED_REGISTRY_TOKEN` in the project's environment variables. To keep callback results across function instances, connect a private Vercel Blob store, which sets `BLOB_READ_WRITE_TOKEN`; without it results go to the instance's temporary disk, which is fine locally and not durable on serverless. Then add a tool registry in Optimizely AI with `https://<your-domain>/fde-opti/discovery` as the discovery URL and the same token as the bearer credential.
