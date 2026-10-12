// Source of truth for the FDE take-home: a small fictional approved-claims register for the
// OptiThera scenario. In production this is the customer's claims system (read-only); the
// validator never writes here and no model ever sees the whole register.

export type Audience = "hcp" | "patient";

export interface ApprovedClaim {
  claim_id: string;
  claim_text: string;
  product: string;
  markets: string[]; // ISO country codes the claim is approved for
  audiences: Audience[];
  approval_status: "approved" | "withdrawn";
  effective_date: string; // YYYY-MM-DD, first day the claim may be used
  expiry_date: string; // YYYY-MM-DD, last day the claim may be used
  version: number;
  superseded_by: string | null;
  required_disclaimer: string | null;
  source_reference: string;
}

export const APPROVED_CLAIMS: ApprovedClaim[] = [
  {
    // Claim A: approved and valid for US, both audiences.
    claim_id: "CLM-001",
    claim_text: "OptiThera is indicated for adults with moderate to severe plaque psoriasis.",
    product: "OptiThera",
    markets: ["US"],
    audiences: ["hcp", "patient"],
    approval_status: "approved",
    effective_date: "2026-01-01",
    expiry_date: "2027-12-31",
    version: 2,
    superseded_by: null,
    required_disclaimer: "See full Prescribing Information.",
    source_reference: "PI-2026-01 section 1",
  },
  {
    // Claim B: approved and valid, US and UK, HCP audience only.
    claim_id: "CLM-002",
    claim_text: "OptiThera is taken once daily as an oral tablet.",
    product: "OptiThera",
    markets: ["US", "UK"],
    audiences: ["hcp"],
    approval_status: "approved",
    effective_date: "2026-01-01",
    expiry_date: "2027-12-31",
    version: 1,
    superseded_by: null,
    required_disclaimer: null,
    source_reference: "PI-2026-01 section 2",
  },
  {
    // Approved once, expired since.
    claim_id: "CLM-003",
    claim_text: "OptiThera is available in a 30-day starter pack.",
    product: "OptiThera",
    markets: ["US"],
    audiences: ["hcp", "patient"],
    approval_status: "approved",
    effective_date: "2025-01-01",
    expiry_date: "2025-12-31",
    version: 1,
    superseded_by: null,
    required_disclaimer: null,
    source_reference: "PACK-2025-02",
  },
  {
    // Earlier wording of Claim A, replaced by the current CLM-001 wording.
    claim_id: "CLM-004",
    claim_text: "OptiThera is indicated for adults with plaque psoriasis.",
    product: "OptiThera",
    markets: ["US"],
    audiences: ["hcp", "patient"],
    approval_status: "approved",
    effective_date: "2025-01-01",
    expiry_date: "2027-12-31",
    version: 1,
    superseded_by: "CLM-001",
    required_disclaimer: "See full Prescribing Information.",
    source_reference: "PI-2025-01 section 1",
  },
];
