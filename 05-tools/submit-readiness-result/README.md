# submit_readiness_result

The workflow's delivery step (RC5) calls this to return a finished result to a request that arrived through the server-side gateway. It decides nothing about readiness: it checks the result's shape and consistency and stores it for the requester. An identical retry is acknowledged as a duplicate; a different result for the same request is rejected.

Inputs, outputs and failure behavior: [docs/tools.md](../../docs/tools.md#submit_readiness_result).

| File | Role |
|---|---|
| [readiness-result.ts](readiness-result.ts) | The result contract and its validation, the store interface with file and Vercel Blob implementations, and the tool's discovery entry |
| [readiness-store.ts](readiness-store.ts) | Chooses the store: Vercel Blob when `BLOB_READ_WRITE_TOKEN` is set, a local file store otherwise |
| [readiness-blob.ts](readiness-blob.ts) | The Vercel Blob client, kept apart so tests never import the SDK |
| [readiness-result.test.ts](readiness-result.test.ts) | Contract, consistency and store tests, including compare-and-swap and expiry |
| [../app/fde-opti/tools/submit-readiness-result/route.ts](../app/fde-opti/tools/submit-readiness-result/route.ts) | The HTTP route |

The callback only completes a request that is already pending. The gateway that creates pending requests is not part of this repository, so a local call with an unknown `request_id` returns 404 `unknown_request`. The tests exercise the full create, complete, duplicate, conflict and expiry cycle against both stores.
