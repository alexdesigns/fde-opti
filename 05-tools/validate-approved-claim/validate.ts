// validate_approved_claim: the governed claim check, a custom Optimizely AI tool.
// Deterministic by design. No model call happens here: approval, dates, market, audience and
// supersession are business rules, so code decides them and the agent only explains the result.

import { APPROVED_CLAIMS, type ApprovedClaim, type Audience } from "./approved-claims";

export interface ValidationRequest {
  claim_ids: string[];
  market: string;
  audience: Audience;
  as_of_date: string; // YYYY-MM-DD; defaults to today (UTC) so a run can be replayed exactly
}

export type Reason =
  | "not_approved"
  | "not_yet_effective"
  | "expired"
  | "superseded"
  | "market_mismatch"
  | "audience_mismatch";

export interface ClaimResult {
  claim_id: string;
  outcome: "valid" | "not_valid" | "not_found";
  reasons: Reason[];
  approved_text: string | null; // lets the agent compare draft wording to the approved wording
  required_disclaimer: string | null;
  superseded_by: string | null;
}

export interface ValidationResponse {
  status: "ok" | "invalid_request" | "validation_unavailable";
  all_valid: boolean; // false unless every claim was checked and passed; never true on error
  as_of_date: string | null;
  results: ClaimResult[];
  error: string | null;
}

const MAX_CLAIMS = 25;
const DATE = /^\d{4}-\d{2}-\d{2}$/;

// Date.parse rolls 2026-02-31 forward to March, so check that the date survives a round trip.
function isRealDate(iso: string): boolean {
  const d = new Date(`${iso}T00:00:00Z`);
  return !Number.isNaN(d.getTime()) && d.toISOString().slice(0, 10) === iso;
}

/** Accepts the Optimizely AI `{ parameters: {...} }` envelope or a bare object. Rejects anything ambiguous. */
export function parseRequest(
  body: unknown,
  today = new Date().toISOString().slice(0, 10),
): { ok: true; request: ValidationRequest } | { ok: false; error: string } {
  const raw = (body as { parameters?: unknown })?.parameters ?? body;
  if (!raw || typeof raw !== "object") return { ok: false, error: "Request body must be a JSON object." };
  const p = raw as Record<string, unknown>;

  if (!Array.isArray(p.claim_ids) || p.claim_ids.length === 0)
    return { ok: false, error: "claim_ids must be a non-empty array of claim IDs." };
  if (p.claim_ids.length > MAX_CLAIMS)
    return { ok: false, error: `claim_ids accepts at most ${MAX_CLAIMS} IDs per call.` };
  if (!p.claim_ids.every((id) => typeof id === "string" && id.trim() !== ""))
    return { ok: false, error: "Every claim ID must be a non-empty string." };

  // `USA` is invalid on purpose. The caller's market must not be silently changed to `US`.
  const market = typeof p.market === "string" ? p.market.trim().toUpperCase() : "";
  if (!/^[A-Z]{2}$/.test(market))
    return { ok: false, error: "market is required as a two-letter country code, for example US." };

  const audience = typeof p.audience === "string" ? p.audience.trim().toLowerCase() : "";
  if (audience !== "hcp" && audience !== "patient")
    return { ok: false, error: "audience is required: hcp or patient." };

  const asOf = p.as_of_date ?? today;
  if (typeof asOf !== "string" || !DATE.test(asOf) || !isRealDate(asOf))
    return { ok: false, error: "as_of_date must be YYYY-MM-DD." };

  const claim_ids = [...new Set((p.claim_ids as string[]).map((id) => id.trim().toUpperCase()))];
  return { ok: true, request: { claim_ids, market, audience, as_of_date: asOf } };
}

/** Checks one claim against the register. Every failing rule is reported, not just the first. */
function checkClaim(id: string, claim: ApprovedClaim | undefined, req: ValidationRequest): ClaimResult {
  if (!claim)
    return { claim_id: id, outcome: "not_found", reasons: [], approved_text: null, required_disclaimer: null, superseded_by: null };

  const reasons: Reason[] = [];
  if (claim.approval_status !== "approved") reasons.push("not_approved");
  // Dates are validated as ISO YYYY-MM-DD, so lexicographic comparison is intentional.
  if (req.as_of_date < claim.effective_date) reasons.push("not_yet_effective");
  if (req.as_of_date > claim.expiry_date) reasons.push("expired");
  if (claim.superseded_by) reasons.push("superseded");
  if (!claim.markets.includes(req.market)) reasons.push("market_mismatch");
  if (!claim.audiences.includes(req.audience)) reasons.push("audience_mismatch");

  return {
    claim_id: id,
    outcome: reasons.length === 0 ? "valid" : "not_valid",
    reasons,
    approved_text: claim.claim_text,
    required_disclaimer: claim.required_disclaimer,
    superseded_by: claim.superseded_by,
  };
}

/**
 * Validates every requested claim. `loadClaims` is the source-of-truth read; if it fails the
 * response is validation_unavailable with all_valid false. Unknown never becomes approved.
 */
export function validateClaims(
  req: ValidationRequest,
  loadClaims: () => ApprovedClaim[] = () => APPROVED_CLAIMS,
): ValidationResponse {
  let register: ApprovedClaim[];
  try {
    register = loadClaims();
  } catch {
    return {
      status: "validation_unavailable",
      all_valid: false,
      as_of_date: req.as_of_date,
      results: [],
      error: "The approved-claims source could not be read. No claim was validated.",
    };
  }

  const results = req.claim_ids.map((id) => checkClaim(id, register.find((c) => c.claim_id === id), req));
  return {
    status: "ok",
    all_valid: results.every((r) => r.outcome === "valid"),
    as_of_date: req.as_of_date,
    results,
    error: null,
  };
}

/** The tool's discovery entry, in the shape @optimizely-opal/opal-tools-sdk emits from /discovery. */
export const TOOL_ENDPOINT = "/fde-opti/tools/validate-approved-claim";

export const DISCOVERY = {
  functions: [
    {
      name: "validate_approved_claim",
      description:
        "Validates explicit claim IDs cited in draft content (for example CLM-001) against the approved-claims register for one market and audience, optionally as of a given date. Returns, per claim, valid or not and every reason it is not (not found, not approved, not yet effective, expired, superseded, wrong market, wrong audience), plus the approved wording and any required disclaimer. The result is authoritative: do not override it or infer approval any other way. Use only for IDs written in the draft; do not use it to find, match or guess claims from prose.",
      parameters: [
        { name: "claim_ids", type: "array", description: "Claim IDs exactly as cited in the draft, for example [\"CLM-001\", \"CLM-002\"]. Send all cited IDs in one call, at most 25. Never include an ID that is not written in the draft.", required: true },
        { name: "market", type: "string", description: "Two-letter country code where the content will run, for example US. Required; do not guess it.", required: true },
        { name: "audience", type: "string", description: "Who the content is for: hcp (healthcare professional) or patient. Required; do not guess it.", required: true },
        { name: "as_of_date", type: "string", description: "Date to evaluate eligibility on, YYYY-MM-DD. Optional; defaults to today.", required: false },
      ],
      endpoint: TOOL_ENDPOINT,
      http_method: "POST",
    },
  ],
};
