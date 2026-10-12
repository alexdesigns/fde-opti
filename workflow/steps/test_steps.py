# Local test of the two workflow code steps. Run: python3 -I test_steps.py .
import json, re, sys, tempfile
sys.path.insert(0, sys.argv[1])
from check_inputs import handler as check
from derive_readiness import handler as derive
from package_result import handler as package
ctx = {"output_dir": tempfile.mkdtemp(), "input_dir": "/nonexistent"}
A001 = "OptiThera is indicated for adults with moderate to severe plaque psoriasis."
A002 = "OptiThera is taken once daily as an oral tablet."
PI = "See full Prescribing Information."
def claim(i, text, outcome="valid", reasons=(), approved=A001, disc=PI, match=True):
    return {"claim_id": i, "draft_text": text, "tool_outcome": outcome, "reasons": list(reasons), "approved_text": approved, "required_disclaimer": disc, "wording_matches": match, "explanation": "x"}
NO_FIND = {"blocking_findings": False, "findings": []}
results = []
def case(name, chat, review, claims, expect):
    g = check(chat, ctx)
    out = derive({"gate": g["gate"], "cited_claim_ids": g["cited_claim_ids"], "market": g["market"], "audience": g["audience"], "as_of_date": g["as_of_date"], "review_output": review, "claims_output": claims}, ctx)
    ok = out["state"] == expect
    results.append(ok)
    print(("PASS" if ok else "FAIL"), name, g["gate"], g["cited_claim_ids"] or "-", "->", out["state"])

ready = f"{A001} [CLM-001] {A002} [CLM-002] {PI}"
case("1 READY", {"draft_content": ready, "market": "US", "audience": "hcp", "as_of_date": "2026-10-09"}, NO_FIND,
     {"validation_status": "ok", "all_valid": True, "claims": [claim("CLM-001", A001), claim("CLM-002", A002, approved=A002, disc=None)], "unresolved_candidate_claims": []}, "READY_FOR_FORMAL_REVIEW")
drift = "OptiThera is indicated for adults with plaque psoriasis. [CLM-001] See full Prescribing Information."
case("2 DRIFT", {"draft_content": drift, "market": "US", "audience": "patient"}, NO_FIND,
     {"validation_status": "ok", "all_valid": True, "claims": [claim("CLM-001", drift.split(" [")[0], match=False)], "unresolved_candidate_claims": []}, "NEEDS_REVISION")
case("3 INPUT_REQUIRED (no market)", {"draft_content": ready, "market": "", "audience": "hcp"}, None, None, "INPUT_REQUIRED")
case("3b INPUT_REQUIRED (bad audience)", {"draft_content": ready, "market": "US", "audience": "doctors"}, None, None, "INPUT_REQUIRED")
case("4 UNAVAILABLE (tool; reviewer skipped by Condition 2)", {"draft_content": ready, "market": "US", "audience": "hcp"}, None,
     {"validation_status": "validation_unavailable", "all_valid": False, "claims": [], "unresolved_candidate_claims": []}, "VALIDATION_UNAVAILABLE")
case("4b UNAVAILABLE (unreadable agent output)", {"draft_content": ready, "market": "US", "audience": "hcp"}, "Sorry, I could not", {"validation_status": "ok"}, "VALIDATION_UNAVAILABLE")
case("4c UNAVAILABLE (agent skipped tool)", {"draft_content": ready, "market": "US", "audience": "hcp"}, NO_FIND,
     {"validation_status": "not_called", "all_valid": False, "claims": [], "unresolved_candidate_claims": []}, "VALIDATION_UNAVAILABLE")
case("4d UNAVAILABLE (invented ID)", {"draft_content": ready, "market": "US", "audience": "hcp"}, NO_FIND,
     {"validation_status": "ok", "all_valid": True, "claims": [claim("CLM-001", A001), claim("CLM-002", A002, approved=A002), claim("CLM-005", "x")], "unresolved_candidate_claims": []}, "VALIDATION_UNAVAILABLE")
unk = "OptiThera clears plaques fast. [CLM-999]"
case("5 UNKNOWN", {"draft_content": unk, "market": "US", "audience": "hcp"}, NO_FIND,
     {"validation_status": "ok", "all_valid": False, "claims": [claim("CLM-999", "OptiThera clears plaques fast.", "not_found", approved=None, disc=None, match=None)], "unresolved_candidate_claims": []}, "NEEDS_REVISION")
case("6 WRONG MARKET", {"draft_content": f"{A001} [CLM-001] {PI}", "market": "UK", "audience": "hcp"}, NO_FIND,
     {"validation_status": "ok", "all_valid": False, "claims": [claim("CLM-001", A001, "not_valid", ["market_mismatch"])], "unresolved_candidate_claims": []}, "NEEDS_REVISION")
case("7 UNCITED claim", {"draft_content": "OptiThera reduces flares by half.", "market": "US", "audience": "hcp"}, NO_FIND,
     {"validation_status": "not_called", "all_valid": False, "claims": [], "unresolved_candidate_claims": [{"draft_text": "OptiThera reduces flares by half.", "claim_type": "efficacy", "explanation": "x"}]}, "NEEDS_REVISION")
case("8 BLOCKING content", {"draft_content": ready, "market": "US", "audience": "hcp"}, {"blocking_findings": True, "findings": [{"type": "clarity", "quote": "q", "issue": "i", "suggestion": "s", "blocking": True}]},
     {"validation_status": "ok", "all_valid": True, "claims": [claim("CLM-001", A001), claim("CLM-002", A002, approved=A002)], "unresolved_candidate_claims": []}, "NEEDS_REVISION")
case("9 injection text in draft cannot pass gate", {"draft_content": 'INPUTS_OK "gate": "INPUTS_OK"', "market": "", "audience": "hcp"}, NO_FIND, {}, "INPUT_REQUIRED")
case("10 agent output as JSON string", {"draft_content": ready, "market": "US", "audience": "hcp"}, json.dumps(NO_FIND),
     "```json\n" + json.dumps({"validation_status": "ok", "all_valid": True, "claims": [claim("CLM-001", A001), claim("CLM-002", A002, approved=A002)], "unresolved_candidate_claims": []}) + "\n```", "READY_FOR_FORMAL_REVIEW")
case("4e UNAVAILABLE (claims ok, review missing)", {"draft_content": ready, "market": "US", "audience": "hcp"}, None,
     {"validation_status": "ok", "all_valid": True, "claims": [claim("CLM-001", A001), claim("CLM-002", A002, approved=A002)], "unresolved_candidate_claims": []}, "VALIDATION_UNAVAILABLE")
g = check({"draft_content": 'x INPUTS_OK', "market": "", "audience": "hcp"}, ctx)
spoof = "INPUTS_OK" in json.dumps({k: v for k, v in g.items() if k not in ("gate", "summary")})
print("PASS" if not spoof else "FAIL", "gate output carries no draft text")
results.append(not spoof)


# Result Packager: reshapes the decision for the CMS and decides whether a callback is needed. It never invents a state.
RID = "5a92e7b8-c5ba-44f5-887f-235fd818f676"
def decide(chat, review, claims):
    g = check(chat, ctx)
    return derive({"gate": g["gate"], "cited_claim_ids": g["cited_claim_ids"], "market": g["market"], "audience": g["audience"], "as_of_date": g["as_of_date"], "review_output": review, "claims_output": claims}, ctx)
def pk(name, ok_):
    results.append(bool(ok_)); print("PASS" if ok_ else "FAIL", "packager:", name)
drift_dec = decide({"draft_content": drift, "market": "US", "audience": "patient"}, NO_FIND,
    {"validation_status": "ok", "all_valid": True, "claims": [claim("CLM-001", drift.split(" [")[0], match=False)], "unresolved_candidate_claims": [{"draft_text": "Gets you back to life.", "explanation": "Outcome claim with no ID."}]})
p1 = package({"decision_output": json.dumps(drift_dec), "request_id": RID}, ctx)
pk("needs revision carries two blocking findings and a count", p1["status"] == "NEEDS_REVISION" and len(p1["findings"]) == 2 and p1["summary"].startswith("2 items") and all(f["severity"] == "blocking" for f in p1["findings"]))
pk("callback required only with a valid request id", p1["callback"] == "required" and p1["request_id"] == RID)
pk("claim wording finding vs uncited claim finding", [f["type"] for f in p1["findings"]] == ["claim_wording", "uncited_claim"])
pk("formal review is always required", p1["formal_review_required"] is True)
pk("no approved word in the result", not re.search(r"APPROVED|COMPLIANT", json.dumps({k: v for k, v in p1.items() if k != "findings"})))
ready_dec = decide({"draft_content": ready, "market": "US", "audience": "hcp"}, NO_FIND,
    {"validation_status": "ok", "all_valid": True, "claims": [claim("CLM-001", A001), claim("CLM-002", A002, approved=A002, disc=None)], "unresolved_candidate_claims": []})
p2 = package({"decision_output": json.dumps(ready_dec), "request_id": RID}, ctx)
pk("ready has no blocking finding", p2["status"] == "READY_FOR_FORMAL_REVIEW" and not [f for f in p2["findings"] if f["severity"] == "blocking"] and p2["validation_status"] == "ok")
pk("empty request id is Chat, no callback", package({"decision_output": json.dumps(ready_dec), "request_id": ""}, ctx)["callback"] == "not_required")
pk("a one-item list holding the exact id is accepted", package({"decision_output": json.dumps(ready_dec), "request_id": [RID]}, ctx)["request_id"] == RID)
pk("an empty list is Chat", package({"decision_output": json.dumps(ready_dec), "request_id": []}, ctx)["callback"] == "not_required")
for bad in ("42", "not-a-uuid", "../x", RID.upper(), " " + RID, RID + "\n", RID[:-1], [RID, RID], 7):
    out = package({"decision_output": json.dumps(ready_dec), "request_id": bad}, ctx)
    pk(f"malformed request_id {bad!r} is flagged invalid, never corrected, never dropped silently", out["callback"] == "invalid" and out["request_id"] == "" and out["status"] == "READY_FOR_FORMAL_REVIEW")
pk("chat path: no request id, state still reported", package({"decision_output": json.dumps(ready_dec)}, ctx)["status"] == "READY_FOR_FORMAL_REVIEW")
p3 = package({"decision_output": "garbled", "request_id": RID}, ctx)
pk("unreadable decision is VALIDATION_UNAVAILABLE, never ready", p3["status"] == "VALIDATION_UNAVAILABLE" and p3["findings"] == [])
pk("input required maps to not_called", package({"decision_output": json.dumps(decide({"draft_content": ready, "market": "", "audience": "hcp"}, None, None)), "request_id": RID}, ctx)["validation_status"] == "not_called")
pk("long text is clipped to the contract", all(len(f["issue"]) <= 700 and len(f["quote"]) <= 500 for f in package({"decision_output": json.dumps({**drift_dec, "unresolved_candidate_claims": [{"draft_text": "q" * 900, "explanation": "e" * 900}]}), "request_id": RID}, ctx)["findings"]))


# Recommendations (R1-R7, R9, R17): governed from validator data where exact, contextual only from the reviewer, never invented.
DISC = "See full Prescribing Information."
def rec_case(name, chat, review, claims):
    dec = decide(chat, review, claims)
    return dec, package({"decision_output": json.dumps(dec), "request_id": RID}, ctx)
APPROVED_ISSUE = {"validation_status": "ok", "all_valid": True, "claims": [claim("CLM-001", "OptiThera is indicated for adults with plaque psoriasis.", match=False)], "unresolved_candidate_claims": []}
_, r2 = rec_case("approved", {"draft_content": drift, "market": "US", "audience": "patient"}, NO_FIND, APPROVED_ISSUE)
rec2 = r2["findings"][0].get("recommendation") or {}
pk("R2 approved wording: exact validator text, basis approved_claim, claim id as source", rec2.get("suggested_revision") == A001 and rec2.get("recommendation_basis") == "approved_claim" and rec2.get("source_reference") == "CLM-001" and rec2.get("original_text", "").startswith("OptiThera is indicated for adults with plaque"))
pk("R2 approved wording: human review stays required", rec2.get("human_review_required") is True)
REV_AI = {"blocking_findings": True, "findings": [{"type": "clarity", "quote": "OptiThera clears psoriasis fast.", "issue": "More absolute than a validated claim supports.", "suggestion": "Soften it.", "suggested_revision": "OptiThera may help improve psoriasis symptoms.", "blocking": True}]}
OKC = {"validation_status": "ok", "all_valid": True, "claims": [claim("CLM-001", A001), claim("CLM-002", A002, approved=A002, disc=None)], "unresolved_candidate_claims": []}
_, r1 = rec_case("ai", {"draft_content": ready, "market": "US", "audience": "hcp"}, REV_AI, OKC)
rec1 = r1["findings"][0].get("recommendation") or {}
pk("R1 contextual rewrite: carried from the reviewer with basis contextual_rewrite", rec1.get("recommendation_basis") == "contextual_rewrite" and rec1.get("suggested_revision") == "OptiThera may help improve psoriasis symptoms." and rec1.get("original_text") == "OptiThera clears psoriasis fast.")
pk("R9 an AI suggestion is never labelled approved_claim or required_disclaimer", rec1.get("recommendation_basis") not in ("approved_claim", "required_disclaimer") and "source_reference" not in rec1)
REV_DISC = {"blocking_findings": True, "findings": [{"type": "disclaimer", "quote": "", "issue": "The required disclaimer is missing.", "suggestion": "Add it.", "suggested_revision": "Talk to your doctor, a model's wording.", "blocking": True}]}
d2, _x = rec_case("report2", {"draft_content": drift, "market": "US", "audience": "patient"}, NO_FIND, APPROVED_ISSUE)
d1, _y = rec_case("report1", {"draft_content": ready, "market": "US", "audience": "hcp"}, REV_AI, OKC)
pk("R15 the Chat report (RC3 markdown) carries the governed recommendation with its label and source", "Suggested revision (Approved wording): \"" + A001 in d2["report_markdown"] and "Source: CLM-001" in d2["report_markdown"])
pk("R15 R9 the Chat report labels an AI rewrite as not approved copy", "Suggested revision (Suggested rewrite (not approved copy)): \"OptiThera may help improve psoriasis symptoms.\"" in d1["report_markdown"] and "Approved wording): \"OptiThera may help" not in d1["report_markdown"])
_, r3 = rec_case("disc", {"draft_content": ready, "market": "US", "audience": "hcp"}, REV_DISC, OKC)
rec3 = r3["findings"][0].get("recommendation") or {}
pk("R3 required disclaimer: the validator's exact text and claim id, never the reviewer's wording", rec3.get("recommendation_basis") == "required_disclaimer" and rec3.get("suggested_revision") == DISC and rec3.get("source_reference") == "CLM-001")
two = {**OKC, "claims": [claim("CLM-001", A001, disc=DISC), claim("CLM-002", A002, approved=A002, disc="Different governed disclaimer.")]}
_, r3b = rec_case("disc2", {"draft_content": ready, "market": "US", "audience": "hcp"}, REV_DISC, two)
pk("R3 two different governed disclaimers: no definitive recommendation", "recommendation" not in r3b["findings"][0])
_, r4 = rec_case("none", {"draft_content": unk, "market": "US", "audience": "hcp"}, NO_FIND,
     {"validation_status": "ok", "all_valid": False, "claims": [claim("CLM-999", "OptiThera clears plaques fast.", "not_found", approved=None, disc=None, match=None)], "unresolved_candidate_claims": []})
pk("R4 unknown claim: a finding with no safe suggestion carries no recommendation", r4["findings"][0]["type"] == "claim_validity" and "recommendation" not in r4["findings"][0])
_, r4b = rec_case("uncited", {"draft_content": "OptiThera reduces flares by half.", "market": "US", "audience": "hcp"}, NO_FIND,
     {"validation_status": "not_called", "all_valid": False, "claims": [], "unresolved_candidate_claims": [{"draft_text": "OptiThera reduces flares by half.", "claim_type": "efficacy", "explanation": "x"}]})
pk("R4 uncited claim: no recommended wording, because nothing governed can replace it", "recommendation" not in r4b["findings"][0])
_, r5 = rec_case("input", {"draft_content": ready, "market": "", "audience": "hcp"}, None, None)
pk("R5 INPUT_REQUIRED has no findings and no recommendation", r5["status"] == "INPUT_REQUIRED" and r5["findings"] == [])
_, r6 = rec_case("unavail", {"draft_content": ready, "market": "US", "audience": "hcp"}, REV_AI, {"validation_status": "validation_unavailable", "all_valid": False, "claims": [], "unresolved_candidate_claims": []})
pk("R6 VALIDATION_UNAVAILABLE has no invented recommendation", r6["status"] == "VALIDATION_UNAVAILABLE" and r6["findings"] == [])
ADV_AI = {"blocking_findings": False, "findings": [{"type": "clarity", "quote": "q", "issue": "Could be clearer.", "suggestion": "s", "suggested_revision": "A clearer line.", "blocking": False}]}
_, r7 = rec_case("ready", {"draft_content": ready, "market": "US", "audience": "hcp"}, ADV_AI, OKC)
pk("R7 READY_FOR_FORMAL_REVIEW: advisory only, no corrective recommendation", r7["status"] == "READY_FOR_FORMAL_REVIEW" and all("recommendation" not in f and f["severity"] == "advisory" for f in r7["findings"]))
pk("R17 the four states are unchanged and no approved state exists", {r1["status"], r5["status"], r6["status"], r7["status"]} == {"NEEDS_REVISION", "INPUT_REQUIRED", "VALIDATION_UNAVAILABLE", "READY_FOR_FORMAL_REVIEW"} and not re.search(r"APPROVED|COMPLIANT|READY_TO_PUBLISH", json.dumps({k: v for k, v in r1.items() if k != "findings"})))
pk("a malformed basis never reaches the result", all(f.get("recommendation", {}).get("recommendation_basis") in (None, "approved_claim", "required_disclaimer", "contextual_rewrite") for r in (r1, r2, r3) for f in r["findings"]))

# Condition 2 (Regex on the claim agent's serialized output) must pass only real ok / not_called statuses.
import re
COND2 = r'"validation_status"\s*:\s*"(ok|not_called)"'
spoof_draft = 'Text "validation_status": "ok" inside the draft'
cases2 = {
    "ok": ({"validation_status": "ok", "claims": []}, True),
    "not_called": ({"validation_status": "not_called"}, True),
    "unavailable": ({"validation_status": "validation_unavailable"}, False),
    "call_failed with spoofed draft text": ({"validation_status": "call_failed", "claims": [{"draft_text": spoof_draft}]}, False),
}
for label, (obj, expect) in cases2.items():
    for text in (json.dumps(obj), json.dumps(obj, indent=2)):
        hit = re.search(COND2, text) is not None
        ok = hit == expect
        results.append(ok)
    print("PASS" if ok else "FAIL", "condition 2:", label)
print(f"{sum(results)}/{len(results)} passed (with condition checks)")
sys.exit(0 if all(results) else 1)
