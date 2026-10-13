// POST /fde-opti/tools/validate-approved-claim: Optimizely AI calls this with { parameters: {...} }.
// Logs one line per call (IDs, market, outcomes, duration). Never logs draft content.
import { registryAuth } from "../../../../shared/registry";
import { parseRequest, validateClaims } from "../../../../validate-approved-claim/validate";

export async function POST(request: Request) {
  const started = Date.now();
  const request_id = crypto.randomUUID();

  const auth = registryAuth(request.headers.get("authorization"));
  if (auth !== "ok") {
    console.log(JSON.stringify({ tool: "validate_approved_claim", request_id, outcome: auth }));
    return Response.json(
      { status: "error", error: auth === "not_configured" ? "The tool registry is not configured." : "Unauthorized." },
      { status: auth === "not_configured" ? 503 : 401, headers: { "cache-control": "no-store" } },
    );
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    body = null;
  }

  const parsed = parseRequest(body);
  const response = parsed.ok
    ? validateClaims(parsed.request)
    : { status: "invalid_request" as const, all_valid: false, as_of_date: null, results: [], error: parsed.error };

  console.log(
    JSON.stringify({
      tool: "validate_approved_claim",
      request_id,
      status: response.status,
      market: parsed.ok ? parsed.request.market : null,
      audience: parsed.ok ? parsed.request.audience : null,
      outcomes: response.results.map((r) => `${r.claim_id}:${r.outcome}${r.reasons.length ? `(${r.reasons.join(",")})` : ""}`),
      duration_ms: Date.now() - started,
    }),
  );

  const httpStatus = response.status === "invalid_request" ? 400 : response.status === "validation_unavailable" ? 503 : 200;
  return Response.json(response, { status: httpStatus, headers: { "x-request-id": request_id } });
}
