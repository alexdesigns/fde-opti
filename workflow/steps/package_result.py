import json
import re
from datetime import datetime, timezone

# Turns the Readiness Decision output into the CMS-facing result and says whether a callback is needed.
# It decides nothing: the state comes from the Readiness Decision step, unchanged. It only reshapes.
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
STATES = ("INPUT_REQUIRED", "NEEDS_REVISION", "READY_FOR_FORMAL_REVIEW", "VALIDATION_UNAVAILABLE")


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


def finding(kind, severity, quote, issue, suggestion, recommendation=None):
    out = {"type": clip(kind, 40) or "other", "severity": severity, "quote": clip(quote, 500),
           "issue": clip(issue, 700) or "See the readiness report.", "suggestion": clip(suggestion, 700)}
    if recommendation:
        out["recommendation"] = recommendation
    return out


# RC3 builds recommendations once, from governed validator data or the reviewer's contextual suggestion. RC4 only carries
# a well formed one through to the external result and drops anything else, so a malformed or misplaced one never ships.
BASES = ("approved_claim", "required_disclaimer", "contextual_rewrite")


def carried(rec):
    if not isinstance(rec, dict) or rec.get("recommendation_basis") not in BASES:
        return None
    revised = clip(rec.get("suggested_revision"), 700).strip()
    source = clip(rec.get("source_reference"), 80).strip()
    # Governed wording must name its source. Without one it cannot be called governed.
    if not revised or (rec["recommendation_basis"] != "contextual_rewrite" and not source):
        return None
    out = {"suggested_revision": revised, "reason": clip(rec.get("reason"), 400) or "See the finding.",
           "recommendation_basis": rec["recommendation_basis"], "human_review_required": True}
    if clip(rec.get("original_text"), 500).strip():
        out["original_text"] = clip(rec.get("original_text"), 500)
    if source:
        out["source_reference"] = source
    return out


def read_request_id(value):
    # The id is never corrected. Empty means no external caller (Chat). An exact UUID is delivered.
    # Anything else was meant as an id but cannot be trusted, so delivery fails instead of silently skipping.
    if isinstance(value, list):
        if len(value) > 1:
            return "", "invalid"
        value = value[0] if value else ""
    if value is None or (isinstance(value, str) and value == ""):
        return "", "not_required"
    if isinstance(value, str) and UUID.fullmatch(value):
        return value, "required"
    return "", "invalid"


TASK_ID = re.compile(r"[A-Za-z0-9]{4,20}")
KEY = re.compile(r"[0-9a-f]{16}")


def read_intake(value):
    # The intake step says where the request came from. A ClickUp source must carry a well-formed task and delivery key,
    # or delivery would act on an identifier nobody can trust, so the run fails instead.
    intake = as_obj(value) or {}
    if intake.get("source") != "clickup":
        return {"source": "direct"}
    task_id, key = intake.get("task_id"), intake.get("delivery_key")
    missing = intake.get("missing") if isinstance(intake.get("missing"), list) else []
    if not (isinstance(task_id, str) and TASK_ID.fullmatch(task_id)):
        raise RuntimeError("Packaging failed: the ClickUp task id is not valid.")
    if not (isinstance(key, str) and KEY.fullmatch(key)):
        raise RuntimeError("Packaging failed: the ClickUp delivery key is not valid.")
    # The draft ref is the first 8 characters of the draft's SHA-256 from IN1. It tells a reader which text was checked.
    # Empty when there was no draft to hash. Never the full hash.
    sha = intake.get("draft_sha256")
    draft_ref = sha[:8] if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{64}", sha) else ""
    return {"source": "clickup", "task_id": task_id, "task_name": clip(intake.get("task_name"), 200), "delivery_key": key, "draft_ref": draft_ref,
            "duplicate": intake.get("duplicate") is True, "missing": [clip(m, 40) for m in missing]}


def handler(input, ctx):
    rid, callback = read_request_id(input.get("request_id"))
    source = read_intake(input.get("intake_output"))
    decision = as_obj(input.get("decision_output"))
    state = decision.get("state") if decision else None
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if state not in STATES:
        # If the decision cannot be read, say so. Never guess a state, never report ready.
        return {**source, "callback": callback, "request_id": rid, "status": "VALIDATION_UNAVAILABLE",
                "summary": "The readiness decision could not be read, so nothing is reported as ready.",
                "validation_status": "validation_unavailable", "formal_review_required": True, "checked_at": now, "findings": []}

    findings = []
    if state == "NEEDS_REVISION":
        for c in decision.get("claim_issues") or []:
            wording_only = c.get("tool_outcome") == "valid"
            rec = carried(c.get("recommendation")) if wording_only else None
            findings.append(finding(
                "claim_wording" if wording_only else "claim_validity", "blocking", c.get("draft_text"), c.get("explanation"),
                "Change the wording to match the approved claim, or remove the statement." if wording_only
                else "Use an approved claim for this market and audience, or remove the statement.", rec))
        for u in decision.get("unresolved_candidate_claims") or []:
            findings.append(finding("uncited_claim", "blocking", u.get("draft_text"), u.get("explanation"),
                                    "Cite an approved claim, or rewrite it as non-claim copy."))
    for f in decision.get("findings") or []:
        # Recommendations ride only on blocking findings of a NEEDS_REVISION result.
        rec = carried(f.get("recommendation")) if state == "NEEDS_REVISION" and f.get("blocking") else None
        findings.append(finding(f.get("type"), "blocking" if f.get("blocking") else "advisory", f.get("quote"), f.get("issue"), f.get("suggestion"), rec))

    blocking = sum(1 for f in findings if f["severity"] == "blocking")
    if state == "NEEDS_REVISION":
        summary = f"{blocking} item{'s' if blocking != 1 else ''} to resolve before formal review."
    elif state == "READY_FOR_FORMAL_REVIEW":
        summary = "No blocking issues found. Ready for formal review."
    elif state == "INPUT_REQUIRED":
        summary = "The draft, market or audience was missing, so nothing was checked."
    else:
        summary = "The claims could not be checked, so the draft is not sent on."
    validation = "validation_unavailable" if state == "VALIDATION_UNAVAILABLE" else ("not_called" if state == "INPUT_REQUIRED" else "ok")

    return {**source, "callback": callback, "request_id": rid, "status": state, "summary": summary,
            "validation_status": validation, "formal_review_required": True, "checked_at": now, "findings": findings}
