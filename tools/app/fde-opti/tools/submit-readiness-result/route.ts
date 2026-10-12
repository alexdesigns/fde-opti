// POST /fde-opti/tools/submit-readiness-result: the Optimizely AI workflow reports one finished result.
// Authenticated with the Regulated Content registry bearer token, separate from the CMS gateway token.
// Writes only a normalized result against a request_id the gateway issued and is still waiting on.
// It accepts no draft text, decides nothing and publishes nothing.
import { registryAuth } from "../../../../shared/registry";
import { parseSubmission } from "../../../../submit-readiness-result/readiness-result";
import { resultStore } from "../../../../submit-readiness-result/readiness-store";

export async function POST(request: Request) {
  const started = Date.now();
  const log = (outcome: string, extra: Record<string, unknown> = {}) =>
    console.log(JSON.stringify({ tool: "submit_readiness_result", outcome, duration_ms: Date.now() - started, ...extra }));
  const reply = (status: number, body: Record<string, unknown>) => Response.json(body, { status, headers: { "cache-control": "no-store" } });

  const auth = registryAuth(request.headers.get("authorization"));
  if (auth === "not_configured") {
    log("callback_not_configured");
    return reply(503, { status: "error", error: "The result store is not configured." });
  }
  if (auth === "unauthorized") {
    log("unauthorized");
    return reply(401, { status: "error", error: "Unauthorized." });
  }

  const raw = await request.text();
  if (new TextEncoder().encode(raw).length > 64 * 1024) return reply(413, { status: "error", error: "Body too large." });
  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return reply(400, { status: "error", error: "Body is not valid JSON." });
  }

  const parsed = parseSubmission(body);
  if (!parsed.ok) {
    // Shape only, never content: findings can quote the draft.
    const p = typeof body === "object" && body !== null && "parameters" in body ? (body as { parameters: unknown }).parameters : body;
    const f = typeof p === "object" && p !== null ? (p as Record<string, unknown>).findings : undefined;
    const first = Array.isArray(f) ? f[0] : undefined;
    log(parsed.code, {
      findings_type: typeof f,
      findings_is_array: Array.isArray(f),
      findings_len: Array.isArray(f) ? f.length : typeof f === "string" ? f.length : null,
      first_item_type: typeof first,
      first_item_keys: first && typeof first === "object" ? Object.keys(first) : null,
      param_keys: typeof p === "object" && p !== null ? Object.keys(p) : null,
    });
    return reply(400, { status: "error", error: parsed.message, code: parsed.code });
  }

  let stored;
  try {
    stored = await resultStore().complete(parsed.value);
  } catch {
    log("store_unavailable", { request_id: parsed.value.request_id });
    return reply(503, { status: "error", error: "The result store is unavailable." });
  }
  log(stored, { request_id: parsed.value.request_id, result_status: parsed.value.status, findings: parsed.value.findings.length });
  if (stored === "stored") return reply(200, { status: "ok" });
  if (stored === "duplicate") return reply(200, { status: "ok", duplicate: true });
  if (stored === "conflict") return reply(409, { status: "error", error: "A different result was already stored for this request.", code: "conflict" });
  if (stored === "expired") return reply(410, { status: "error", error: "This request has expired.", code: "expired" });
  return reply(404, { status: "error", error: "No pending request with that id.", code: "unknown_request" });
}
