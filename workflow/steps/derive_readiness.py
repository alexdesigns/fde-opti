import json
from datetime import datetime, timezone

DISCLAIMER = "This is a readiness check before formal review. It is not regulatory approval."
BASES = ("approved_claim", "required_disclaimer", "contextual_rewrite")
BASIS_LABEL = {"approved_claim": "Approved wording", "required_disclaimer": "Required disclaimer", "contextual_rewrite": "Suggested rewrite (not approved copy)"}


def as_obj(value):
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        start, end = value.find("{"), value.rfind("}")
        if start != -1 and end > start:
            try:
                parsed = json.loads(value[start:end + 1])
                return parsed if isinstance(parsed, dict) else None
            except ValueError:
                return None
    return None


def clip(value, n):
    return str(value or "")[:n]


# A recommendation is advisory text for the content owner. It is never approval and never a state. It exists only when
# something supports it: exact governed wording or a governed disclaimer from the validator, or a contextual rewrite the
# reviewer proposed. Unapproved or uncited claims get no suggested wording, because nothing governed can replace them.
def recommendation(basis, original, revised, reason, source=""):
    revised = clip(revised, 700).strip()
    if basis not in BASES or not revised:
        return None
    rec = {"suggested_revision": revised, "reason": clip(reason, 400) or "See the finding.", "recommendation_basis": basis, "human_review_required": True}
    if clip(original, 500).strip():
        rec["original_text"] = clip(original, 500)
    if clip(source, 80).strip():
        rec["source_reference"] = clip(source, 80)
    return rec


def reviewer_recommendation(f, disclaimers):
    # Disclaimer wording is governed text: only the validator's exact disclaimer may be recommended, never a model's version.
    if f.get("type") == "disclaimer":
        texts = sorted({d.get("required_disclaimer") for d in disclaimers if isinstance(d, dict) and isinstance(d.get("required_disclaimer"), str)})
        if len(texts) != 1:
            return None
        ids = ", ".join(sorted({d.get("claim_id") for d in disclaimers if d.get("required_disclaimer") == texts[0] and d.get("claim_id")}))
        return recommendation("required_disclaimer", "", texts[0], f.get("issue"), ids)
    revised = f.get("suggested_revision")
    if isinstance(revised, str) and revised.strip():
        return recommendation("contextual_rewrite", f.get("quote"), revised, f.get("issue"))
    return None


def rec_lines(rec):
    if not isinstance(rec, dict) or not rec.get("suggested_revision"):
        return []
    label = BASIS_LABEL.get(rec.get("recommendation_basis"), "Suggestion")
    out = [f"  - Suggested revision ({label}): \"{rec['suggested_revision']}\"", f"  - Why: {rec.get('reason')}"]
    if rec.get("source_reference"):
        out.append(f"  - Source: {rec['source_reference']}")
    return out


def report(state, reason, context, claims, unresolved, findings):
    lines = [f"# Readiness: {state}", "", reason, "", context, ""]
    if claims:
        lines.append("## Claims")
        for c in claims:
            why = ", ".join(c.get("reasons") or []) or c.get("tool_outcome", "")
            lines.append(f"- {c.get('claim_id')}: {c.get('explanation')} ({why})")
            if c.get("wording_matches") is False and c.get("approved_text"):
                lines.append(f"  - Draft: \"{c.get('draft_text')}\"")
                lines.append(f"  - Approved: \"{c.get('approved_text')}\"")
            lines += rec_lines(c.get("recommendation"))
        lines.append("")
    if unresolved:
        lines.append("## Claim statements with no claim ID")
        lines += [f"- \"{u.get('draft_text')}\". {u.get('explanation')}" for u in unresolved]
        lines.append("")
    if findings:
        lines.append("## Content findings")
        for f in findings:
            tag = "Blocking" if f.get("blocking") else "Advisory"
            lines.append(f"- {tag}, {f.get('type')}: \"{f.get('quote')}\". {f.get('issue')} {f.get('suggestion')}")
            lines += rec_lines(f.get("recommendation"))
        lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def finish(state, reason, ctx, inp, claims=(), unresolved=(), findings=(), blocking=(), disclaimers=()):
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    context = f"Market: {inp.get('market') or 'not given'}. Audience: {inp.get('audience') or 'not given'}. Claims checked as of: {inp.get('as_of_date') or 'run date'}. Generated: {stamp}."
    md = report(state, reason, context, list(claims), list(unresolved), list(findings))
    try:
        with open(f"{ctx['output_dir']}/readiness-report.md", "w") as fh:
            fh.write(md)
    except Exception:
        pass  # the file is a convenience; the state is the result
    return {"state": state, "reason": reason, "claim_issues": list(claims), "unresolved_candidate_claims": list(unresolved),
            "blocking_findings": list(blocking), "findings": list(findings), "governed_disclaimers": list(disclaimers),
            "report_markdown": md, "summary": f"{state}: {reason}"}


def handler(input, ctx):
    if input.get("gate") != "INPUTS_OK":
        return finish("INPUT_REQUIRED", "The draft, market or audience was missing or malformed. Nothing was checked.", ctx, input)

    claims = as_obj(input.get("claims_output"))
    if claims is None:
        return finish("VALIDATION_UNAVAILABLE", "The claim check result could not be read. Do not send the draft to formal review on this result.", ctx, input)
    cited = [i for i in (input.get("cited_claim_ids") or "").split(",") if i]
    status = claims.get("validation_status")
    returned = [c.get("claim_id") for c in claims.get("claims", [])]
    if cited and status != "ok":
        return finish("VALIDATION_UNAVAILABLE", f"Claim validation did not complete (status: {status}). Run the check again later.", ctx, input)
    if not cited and status != "not_called":
        return finish("VALIDATION_UNAVAILABLE", f"Unexpected validation status with no cited IDs (status: {status}).", ctx, input)
    if sorted(set(returned)) != sorted(set(cited)):
        return finish("VALIDATION_UNAVAILABLE", "The claim results do not match the cited claim IDs, so they cannot be trusted.", ctx, input)

    review = as_obj(input.get("review_output"))
    if review is None:
        return finish("VALIDATION_UNAVAILABLE", "The content review result could not be read. Run the check again.", ctx, input)

    findings = review.get("findings", [])
    blocking = [f for f in findings if f.get("blocking")]
    if review.get("blocking_findings") is True and not blocking:
        blocking = [{"type": "unspecified", "quote": "", "issue": "The reviewer flagged a blocking issue without detail.", "suggestion": "Run the check again.", "blocking": True}]
        findings = findings + blocking
    claim_issues = [c for c in claims.get("claims", []) if c.get("tool_outcome") != "valid" or c.get("wording_matches") is not True]
    unresolved = claims.get("unresolved_candidate_claims", [])
    validated = (not cited) or claims.get("all_valid") is True

    if validated and not claim_issues and not unresolved and not blocking:
        return finish("READY_FOR_FORMAL_REVIEW", "Every cited claim is valid with matching wording, there is no uncited claim and no blocking content finding.", ctx, input,
                      claims=claims.get("claims", []), findings=findings)
    # Exact governed disclaimers from the validator, for the claims it returned. Quoted unchanged, never rewritten.
    disclaimers = [{"claim_id": c.get("claim_id"), "required_disclaimer": c.get("required_disclaimer")}
                   for c in claims.get("claims", []) if isinstance(c.get("required_disclaimer"), str) and c.get("required_disclaimer").strip()]
    # Recommendations ride only on blocking findings of a NEEDS_REVISION result. Exact approved wording comes from the validator.
    claim_issues = [{**c, "recommendation": rec} if (rec := recommendation("approved_claim", c.get("draft_text"), c.get("approved_text"), c.get("explanation"), c.get("claim_id"))
                                                        if c.get("tool_outcome") == "valid" and c.get("wording_matches") is False else None) else c for c in claim_issues]
    findings = [{**f, "recommendation": rec} if f.get("blocking") and (rec := reviewer_recommendation(f, disclaimers)) else f for f in findings]
    blocking = [f for f in findings if f.get("blocking")]
    return finish("NEEDS_REVISION", "Fix the items below and run the check again.", ctx, input,
                  claims=claim_issues, unresolved=unresolved, findings=findings, blocking=blocking, disclaimers=disclaimers)
