# Local test of the ClickUp path: intake (IN1), packager (RC4) and delivery (RC5) with a stubbed opal_tms_sdk. Run: python3 -I test_clickup.py .
import hashlib, json, sys, types
sys.path.insert(0, sys.argv[1])

calls, state = [], {}


class OpalTmsSdkError(Exception):
    pass


def wrap(body):
    return {"response_type": "application/json", "response": {"success": True, "result": json.dumps(body)}}


def fresh():
    calls.clear()
    state.clear()
    state.update(
        task={"id": "86a0test1", "name": "Patient Campaign Landing Page", "list": {"id": "L1"}, "custom_fields": [
            {"name": "Market", "type": "drop_down", "value": 0, "type_config": {"options": [{"name": "US", "orderindex": 0}, {"name": "Canada", "orderindex": 2}]}},
            {"name": "Audience", "type": "drop_down", "value": 0, "type_config": {"options": [{"name": "Patient", "orderindex": 0}, {"name": "HCP", "orderindex": 1}]}},
            {"name": "Product / Offering", "type": "short_text", "value": "Lumetria"},
            {"name": "Campaign / Initiative", "type": "tasks", "value": [{"name": "Patient Education Campaign"}]},
            {"id": "F-READY", "name": "Content Readiness", "type": "drop_down", "type_config": {"options": [
                {"id": "O-NC", "name": "Not Checked"}, {"id": "O-IR", "name": "Input Required"}, {"id": "O-NR", "name": "Needs Revision"},
                {"id": "O-VU", "name": "Validation Unavailable"}, {"id": "O-RF", "name": "Ready for Formal Review"}]}},
            {"id": "F-CHECKED", "name": "Last Checked", "type": "date"}]},
        docs=[{"id": "D1", "type": "doc", "name": "Patient Campaign Landing Page: Draft Copy", "pageId": "P1", "dateUpdated": "99", "hierarchy": {"subcategory": {"id": "L1"}}}],
        draft="Take OptiThera. [CLM-001]\nSee full Prescribing Information.\n", comments=[], fail=set(), cursor_pages=None)


class FakeTools:
    def call(self, name, **kw):
        calls.append((name, kw))
        if name in state["fail"]:
            return {"response_type": "error", "response": {"message": "nope", "status_code": 500}}
        if name == "clickup_get_task":
            return wrap(state["task"]) if state["task"] else {"response_type": "error", "response": {}}
        if name == "clickup_search":
            return wrap({"results": state["docs"], "next_cursor": None})
        if name == "clickup_get_document_pages":
            return wrap({"pages": [{"id": kw["page_ids"][0], "content": state["draft"]}]})
        if name == "clickup_get_task_comments":
            return wrap({"comments": state["comments"]})
        if name == "clickup_create_comment":
            if "notify_all" in kw and "no_notify_all" in state["fail"]:
                return {"response_type": "error", "response": {"message": "unsupported option", "status_code": 400}}
            state["comments"].append({"comment_text": kw["comment_text"], "notify_all": kw.get("notify_all")})
            return wrap({"id": "c1"})
        if name == "clickup_update_task":
            return wrap({"id": kw["task_id"], "status": kw.get("status")})
        raise AssertionError(name)


sdk = types.ModuleType("opal_tms_sdk")
sdk.tools, sdk.OpalTmsSdkError = FakeTools(), OpalTmsSdkError
sys.modules["opal_tms_sdk"] = sdk
from check_inputs import handler as intake
from package_result import handler as package
from deliver_result import handler as deliver

results = []


def check(name, ok):
    results.append(bool(ok))
    print("PASS" if ok else "FAIL", name)


def raises(fn):
    try:
        fn()
    except RuntimeError as e:
        return str(e)
    return None


def hook(task_id="86a0test1", name="Patient Campaign Landing Page", fired="2026-10-10T02:26:11.646Z", wrap_text=False):
    body = {"date": fired, "auto_id": "a:main", "payload": {"id": task_id, "name": name, "status": {"status": "internal review"}, "fields": [], "docs": []}}
    return ("Here is the payload:\n" + json.dumps(body)) if wrap_text else body


def run(payload, **extra):
    return intake({"webhook_payload": payload, **extra}, {})


# --- intake
fresh()
out = run(hook())
check("intake: source is clickup", out["source"] == "clickup")
check("intake: task id parsed from the payload by code", out["task_id"] == "86a0test1")
check("intake: market and audience come from the task fields", out["market"] == "US" and out["audience"] == "patient")
check("intake: gate is INPUTS_OK", out["gate"] == "INPUTS_OK" and out["missing"] == [])
check("intake: draft is returned exactly, not stripped", out["draft_content"] == state["draft"])
check("intake: hash matches the draft", out["draft_sha256"] == hashlib.sha256(state["draft"].encode()).hexdigest())
check("intake: cited ids read from the Doc text", out["cited_claim_ids"] == "CLM-001")
check("intake: doc identity and revision recorded", out["doc_id"] == "D1" and out["doc_updated"] == "99")
check("intake: no write was attempted", not [c for c in calls if c[0] in ("clickup_create_comment", "clickup_update_task")])
check("intake: search is scoped to docs and the exact name", any(c[0] == "clickup_search" and c[1]["filters"]["asset_types"] == ["doc"] and c[1]["keywords"] == "Patient Campaign Landing Page: Draft Copy" for c in calls))
fresh()
check("intake: JSON wrapped in prose still parses", run(hook(wrap_text=True))["task_id"] == "86a0test1")

fresh()
k1 = run(hook())["delivery_key"]
fresh()
check("key: identical event and draft repeats the key", run(hook())["delivery_key"] == k1)
fresh()
check("key: a new Automation firing changes the key", run(hook(fired="2026-10-10T03:00:00.000Z"))["delivery_key"] != k1)
fresh()
state["draft"] += "More."
check("key: an edited draft changes the key", run(hook())["delivery_key"] != k1)

fresh()
state["comments"].append({"comment_text": f"old\n\nReadiness ref: {k1}"})
out = run(hook())
check("dedupe: a recorded key makes the gate DUPLICATE_DELIVERED, so review is skipped", out["gate"] == "DUPLICATE_DELIVERED" and out["duplicate"] is True)

fresh()
state["task"]["custom_fields"][0]["value"] = None
out = run(hook())
check("missing market: INPUT_REQUIRED naming market, nothing inferred", out["gate"] == "INPUT_REQUIRED" and out["missing"] == ["market"] and out["market"] == "")
fresh()
state["task"]["custom_fields"][0]["value"] = 2
check("market not a two-letter code is not normalized", run(hook())["missing"] == ["market"])
fresh()
state["task"]["custom_fields"][1]["value"] = None
check("missing audience: INPUT_REQUIRED naming audience", run(hook())["missing"] == ["audience"])
fresh()
state["docs"] = []
out = run(hook())
check("no draft Doc: INPUT_REQUIRED naming the draft, review never starts", out["gate"] == "INPUT_REQUIRED" and "draft" in out["missing"] and out["delivery_key"])
fresh()
state["docs"] = state["docs"] * 2
check("two matching Docs: ambiguous, treated as no draft", "draft" in run(hook())["missing"])
fresh()
state["docs"][0]["hierarchy"]["subcategory"]["id"] = "OTHER"
check("a same-named Doc in another list is ignored", "draft" in run(hook())["missing"])
fresh()
state["docs"][0]["name"] = "patient campaign landing page: draft copy"
check("the Doc name must match exactly", "draft" in run(hook())["missing"])

fresh()
state["fail"] = {"clickup_get_task"}
check("fail closed: an unreadable task raises", raises(lambda: run(hook())) is not None)
fresh()
state["fail"] = {"clickup_search"}
check("fail closed: an unavailable Doc search raises", raises(lambda: run(hook())) is not None)
fresh()
state["fail"] = {"clickup_get_document_pages"}
check("fail closed: an unreadable Doc raises", raises(lambda: run(hook())) is not None)
fresh()
check("fail closed: payload name that disagrees with the task raises", raises(lambda: run(hook(name="Another task"))) is not None)
fresh()
out = run(hook(task_id="../etc"))
check("fail closed: a malformed task id is INPUT_REQUIRED and reads nothing", out["gate"] == "INPUT_REQUIRED" and not calls)

# --- sources other than ClickUp are unchanged
fresh()
out = intake({"draft_content": "x [CLM-001]", "market": "us", "audience": "HCP"}, {})
check("direct: Chat or Lab input behaves as before and reads nothing", out["gate"] == "INPUTS_OK" and out["source"] == "direct" and not calls and out["draft_content"] == "")
out = intake({"webhook_payload": {"request_id": "x", "draft_content": "d"}, "draft_content": "d", "market": "US", "audience": "hcp"}, {})
check("direct: a Lab-shaped webhook body is not mistaken for ClickUp", out["source"] == "direct")

# --- packager
DECISION = {"state": "NEEDS_REVISION", "claim_issues": [{"claim_id": "CLM-001", "draft_text": "Take OptiThera.", "tool_outcome": "valid", "explanation": "Wording differs.", "wording_matches": False}], "unresolved_candidate_claims": [], "findings": []}


def intake_for(**over):
    fresh()
    out = run(hook())
    out.update(over)
    return json.dumps(out)


pkg = package({"request_id": "", "decision_output": json.dumps(DECISION), "intake_output": intake_for()}, {})
check("package: carries the ClickUp source and keys", pkg["source"] == "clickup" and pkg["task_id"] == "86a0test1" and len(pkg["delivery_key"]) == 16)
check("package: no Lab callback for a ClickUp run", pkg["callback"] == "not_required")
check("package: state is unchanged by the source", pkg["status"] == "NEEDS_REVISION")
check("package: no draft text travels", "draft_content" not in pkg)
direct = package({"request_id": "", "decision_output": json.dumps(DECISION), "intake_output": json.dumps({"source": "direct"})}, {})
check("package: a direct run carries source direct only", direct["source"] == "direct" and "task_id" not in direct)
check("package: a bad task id fails the run", raises(lambda: package({"request_id": "", "decision_output": json.dumps(DECISION), "intake_output": intake_for(task_id="a b")}, {})) is not None)
check("package: a bad delivery key fails the run", raises(lambda: package({"request_id": "", "decision_output": json.dumps(DECISION), "intake_output": intake_for(delivery_key="zz")}, {})) is not None)

# --- delivery
def packaged(state_name, findings=(), missing=(), duplicate=False):
    d = {**DECISION, "state": state_name}
    p = package({"request_id": "", "decision_output": json.dumps(d), "intake_output": intake_for(missing=list(missing), duplicate=duplicate)}, {})
    p["findings"] = list(findings) if findings else p["findings"]
    return p


fresh()
p = packaged("NEEDS_REVISION")
out = deliver({"packager_output": json.dumps(p)}, {})
writes = [c for c in calls if c[0] in ("clickup_create_comment", "clickup_update_task")]
check("deliver: NEEDS_REVISION writes fields, then one comment, then changes needed", [w[0] for w in writes] == ["clickup_update_task", "clickup_create_comment", "clickup_update_task"] and writes[2][1]["status"] == "changes needed" and "custom_fields" in writes[0][1] and "status" not in writes[0][1])
text = writes[1][1]["comment_text"]
check("deliver: comment is marketer-readable and carries the key", text.startswith("CONTENT READINESS\n\nNeeds Revision") and "Blocking findings:\nFinding 1: " in text and f"Readiness ref: {p['delivery_key']}" in text)
check("deliver: comment has no raw JSON or step names", "{" not in text and "RC" not in text and "claim_issues" not in text)
check("deliver: comment uses the entity form the connector accepted", writes[1][1]["entity_type"] == "task" and writes[1][1]["entity_id"] == "86a0test1")
check("deliver: result says delivered", out["delivery"] == "delivered" and out["comment"] == "posted")

fresh()
p = packaged("READY_FOR_FORMAL_REVIEW")
deliver({"packager_output": json.dumps(p)}, {})
check("deliver: READY posts the fixed sentence and sets formal review", "Automated readiness is complete." in state["comments"][0]["comment_text"] and "Human approval is still required." in state["comments"][0]["comment_text"] and ("clickup_update_task", {"task_id": "86a0test1", "status": "formal review"}) in calls)

fresh()
p = packaged("INPUT_REQUIRED", missing=["market"])
deliver({"packager_output": json.dumps(p)}, {})
check("deliver: INPUT_REQUIRED names market and does not reach formal review", "Input Required" in state["comments"][0]["comment_text"] and "Missing:\n- Market" in state["comments"][0]["comment_text"] and not any(c[0] == "clickup_update_task" and c[1].get("status") == "formal review" for c in calls))
fresh()
p = packaged("VALIDATION_UNAVAILABLE")
deliver({"packager_output": json.dumps(p)}, {})
check("deliver: VALIDATION_UNAVAILABLE says temporarily unavailable and does not advance", "Validation Unavailable" in state["comments"][0]["comment_text"] and "could not complete" in state["comments"][0]["comment_text"] and not any(c[0] == "clickup_update_task" and c[1].get("status") == "formal review" for c in calls))
statuses = {c[1].get("status") for c in calls if c[0] == "clickup_update_task"}
check("deliver: both non-ready states set changes needed so a retry is a real status change", all(c[1].get("status") == "changes needed" for c in calls if c[0] == "clickup_update_task" and c[1].get("status")))
check("deliver: approved, published and live are never set", not statuses & {"approved", "published", "live"})

fresh()
p = packaged("NEEDS_REVISION")
deliver({"packager_output": json.dumps(p)}, {})
n = len(state["comments"])
calls.clear()
out = deliver({"packager_output": json.dumps(p)}, {})
check("idempotent: a retried delivery adds no second comment", len(state["comments"]) == n == 1 and out["comment"] == "already present")
check("idempotent: the retry still ensures the status", any(c[0] == "clickup_update_task" for c in calls))

fresh()
p = packaged("NEEDS_REVISION", duplicate=True)
calls.clear()
out = deliver({"packager_output": json.dumps(p)}, {})
check("duplicate event: nothing is posted or moved", out["delivery"] == "skipped" and not calls)

fresh()
p = packaged("NEEDS_REVISION")
calls.clear()
state["fail"] = {"clickup_create_comment"}
check("write failure: a refused comment raises and sets no status", raises(lambda: deliver({"packager_output": json.dumps(p)}, {})) is not None and not any(c[0] == "clickup_update_task" and c[1].get("status") for c in calls))
state["fail"] = {"clickup_update_task"}
msg = raises(lambda: deliver({"packager_output": json.dumps(p)}, {}))
check("write failure: a refused status change raises", msg is not None and "status" in msg)
state["fail"] = set()
out = deliver({"packager_output": json.dumps(p)}, {})
check("write failure: the retry finishes the status without a second comment", out["delivery"] == "delivered" and len(state["comments"]) == 1)
check("write failure: delivery never calls the review steps' tools", not any(c[0] in ("validate_approved_claim",) for c in calls))
fresh()
p = packaged("NEEDS_REVISION")
state["task"] = {"id": "OTHER"}
check("fail closed: a task that does not match the key is not written to", raises(lambda: deliver({"packager_output": json.dumps(p)}, {})) is not None and not any(c[0] == "clickup_create_comment" for c in calls))


# --- readiness field, Last Checked, comment formats, draft ref (finalization pass)
FIELD_OPTION = {"INPUT_REQUIRED": "O-IR", "NEEDS_REVISION": "O-NR", "VALIDATION_UNAVAILABLE": "O-VU", "READY_FOR_FORMAL_REVIEW": "O-RF"}
ADV = {"type": "tone", "severity": "advisory", "quote": "", "issue": "Consider a softer headline.", "suggestion": ""}
BLK = {"type": "claim_validity", "severity": "blocking", "quote": "Take OptiThera.", "issue": "Wording differs from CLM-001.", "suggestion": ""}
for st, kw in (("INPUT_REQUIRED", {"missing": ["audience"]}), ("NEEDS_REVISION", {}), ("VALIDATION_UNAVAILABLE", {}), ("READY_FOR_FORMAL_REVIEW", {})):
    fresh()
    p = packaged(st, **kw)
    deliver({"packager_output": json.dumps(p)}, {})
    field_call = next(c for c in calls if c[0] == "clickup_update_task" and "custom_fields" in c[1])
    values = {f["id"]: f["value"] for f in field_call[1]["custom_fields"]}
    check(f"fields: {st} writes Content Readiness = {FIELD_OPTION[st]}", values.get("F-READY") == FIELD_OPTION[st])
    check(f"fields: {st} also writes Last Checked from the packaged completion time", values.get("F-CHECKED") == p["checked_at"][:10] + " " + p["checked_at"][11:16])
    if st == "READY_FOR_FORMAL_REVIEW":
        check("fields: only formal review is reached by READY and only READY reaches it", [c[1]["status"] for c in calls if c[0] == "clickup_update_task" and c[1].get("status")] == ["formal review"])
    else:
        check(f"fields: {st} leaves the task in changes needed", [c[1]["status"] for c in calls if c[0] == "clickup_update_task" and c[1].get("status")] == ["changes needed"])

fresh()
p = packaged("READY_FOR_FORMAL_REVIEW", findings=[ADV])
deliver({"packager_output": json.dumps(p)}, {})
t = state["comments"][0]["comment_text"]
check("comment READY: exact pattern with advisories and the human approval line",
      t.startswith("CONTENT READINESS\n\nReady for Formal Review\n\nAutomated readiness is complete.\n\nAdvisories:\n- Consider a softer headline.\n\nHuman approval is still required.\n\nNext step:\nSend the content to formal Medical, Legal and Regulatory review. Assign this task to the appropriate Medical, Legal and Regulatory reviewer.\n\nReadiness ref: "))
fresh()
p = packaged("READY_FOR_FORMAL_REVIEW")
p["findings"] = []
deliver({"packager_output": json.dumps(p)}, {})
t = state["comments"][0]["comment_text"]
check("comment READY: Advisories section omitted when there are none", "Advisories" not in t and "Human approval is still required." in t)

# R10: a ClickUp comment carries a compact recommendation with its provenance label, and an AI rewrite never reads as approved wording.
fresh()
REC_APPROVED = {**BLK, "recommendation": {"suggested_revision": "OptiThera is indicated for adults with moderate to severe plaque psoriasis.", "reason": "Wording differs from the approved claim.", "recommendation_basis": "approved_claim", "source_reference": "CLM-001", "human_review_required": True}}
REC_AI = {"type": "clarity", "severity": "blocking", "quote": "OptiThera clears psoriasis fast.", "issue": "More absolute than a validated claim supports.", "suggestion": "Soften the wording.",
          "recommendation": {"suggested_revision": "OptiThera may help improve psoriasis symptoms.", "reason": "More absolute than a validated claim supports.", "recommendation_basis": "contextual_rewrite", "human_review_required": True}}
p = packaged("NEEDS_REVISION", findings=[REC_APPROVED, REC_AI, ADV])
deliver({"packager_output": json.dumps(p)}, {})
t = state["comments"][0]["comment_text"]
check("R10 comment: numbered findings with a suggested revision, why and basis", "Finding 1: Wording differs" in t and "Suggested revision (approved wording): OptiThera is indicated" in t and "Why: Wording differs from the approved claim." in t and "Basis: approved claim, CLM-001" in t)
check("R9 comment: the AI rewrite is labelled a suggested rewrite, never approved wording", "Suggested rewrite (not approved copy): OptiThera may help" in t and "approved wording): OptiThera may help" not in t)
check("R10 comment: the Doc is never edited and the comment says suggestions are not approval", not any(c[0] in ("clickup_update_document_page", "clickup_create_document_page") for c in calls) and "Suggestions are guidance, not approval." in t)

fresh()
p = packaged("NEEDS_REVISION", findings=[BLK, ADV])
deliver({"packager_output": json.dumps(p)}, {})
t = state["comments"][0]["comment_text"]
check("comment NEEDS_REVISION: blocking findings listed, advisories shown, next step is to move the task to Internal Review",
      "Blocking findings:\nFinding 1: Wording differs from CLM-001. (\"Take OptiThera.\")" in t and "Advisories:\n- Consider a softer headline." in t and "move the task to Internal Review when ready to check again" in t)
p["findings"] = [BLK]
fresh()
deliver({"packager_output": json.dumps(p)}, {})
check("comment NEEDS_REVISION: Advisories omitted when empty", "Advisories" not in state["comments"][0]["comment_text"])

fresh()
p = packaged("INPUT_REQUIRED", missing=["market", "audience"])
deliver({"packager_output": json.dumps(p)}, {})
t = state["comments"][0]["comment_text"]
check("comment INPUT_REQUIRED: lists what is missing and tells the marketer how to resubmit",
      t.startswith("CONTENT READINESS\n\nInput Required\n\nMissing:\n- Market\n- Audience\n\nNext step:\nAdd the missing context and move the brief back into Internal Review."))
fresh()
p = packaged("VALIDATION_UNAVAILABLE")
deliver({"packager_output": json.dumps(p)}, {})
check("comment VALIDATION_UNAVAILABLE: says the governed step could not complete and to retry or escalate",
      "The governed validation step could not complete." in state["comments"][0]["comment_text"] and "Retry the readiness check or escalate the integration issue." in state["comments"][0]["comment_text"])

fresh()
p = packaged("NEEDS_REVISION")
ref1 = p["draft_ref"]
deliver({"packager_output": json.dumps(p)}, {})
check("draft ref: 8 characters, taken from the draft hash, and in the comment", len(ref1) == 8 and ref1 == hashlib.sha256(state["draft"].encode()).hexdigest()[:8] and f"Draft ref: {ref1}" in state["comments"][0]["comment_text"])
check("draft ref: never the full hash", hashlib.sha256(state["draft"].encode()).hexdigest() not in state["comments"][0]["comment_text"])
fresh()
state["draft"] += "One more sentence.\n"
changed = package({"request_id": "", "decision_output": json.dumps(DECISION), "intake_output": json.dumps(run(hook()))}, {})
check("draft ref: changes when the draft changes", changed["draft_ref"] and changed["draft_ref"] != ref1)

for bad in ("APPROVED", "READY_TO_PUBLISH", "REGULATORY_APPROVED", "Ready"):
    fresh()
    p = packaged("NEEDS_REVISION")
    p["status"] = bad
    check(f"fail closed: {bad} is not deliverable and writes nothing", raises(lambda: deliver({"packager_output": json.dumps(p)}, {})) is not None and not [c for c in calls if c[0] in ("clickup_create_comment", "clickup_update_task")])
check("no state maps to approved, scheduled, live, complete or a publish status",
      not {"approved", "scheduled", "live", "complete", "ready to publish"} & set(__import__("deliver_result").STATUS_AFTER.values()))

fresh()
p = packaged("READY_FOR_FORMAL_REVIEW")
state["fail"] = set()
orig = sdk.tools.call
def flaky(name, **kw):
    if name == "clickup_update_task" and "custom_fields" in kw:
        calls.append((name, kw))
        return {"response_type": "error", "response": {"message": "field write refused"}}
    return orig(name, **kw)
sdk.tools.call = flaky
out = deliver({"packager_output": json.dumps(p)}, {})
sdk.tools.call = orig
check("field failure: the readiness result is unchanged and still delivered",
      out["delivery"] == "delivered" and out["status"] == "READY_FOR_FORMAL_REVIEW" and out["readiness_fields"] == "failed")
check("field failure: the comment is still posted and the task still moves to formal review",
      len(state["comments"]) == 1 and [c[1]["status"] for c in calls if c[0] == "clickup_update_task" and c[1].get("status")] == ["formal review"])
p = packaged("NEEDS_REVISION")
state["task"]["custom_fields"] = [f for f in state["task"]["custom_fields"] if f["name"] not in ("Content Readiness", "Last Checked")]
out = deliver({"packager_output": json.dumps(p)}, {})
check("field missing in ClickUp: delivery still completes and says the fields were skipped", out["delivery"] == "delivered" and out["readiness_fields"].startswith("skipped") and len(state["comments"]) == 1)

fresh()
p = packaged("READY_FOR_FORMAL_REVIEW")
deliver({"packager_output": json.dumps(p)}, {})
calls.clear()
out = deliver({"packager_output": json.dumps(p)}, {})
check("replay of a delivered result: no second comment", len(state["comments"]) == 1 and out["comment"] == "already present")


# --- notification and human handoff
fresh()
p = packaged("NEEDS_REVISION")
state["task"]["assignees"] = [{"id": 1, "username": "Owner"}]
out = deliver({"packager_output": json.dumps(p)}, {})
check("notify: the readiness comment asks ClickUp to notify the task's assignees", state["comments"][0]["notify_all"] is True and out["notified"] == "task assignees")
fresh()
out = deliver({"packager_output": json.dumps(packaged("NEEDS_REVISION"))}, {})
check("notify: with no assignee the result says nobody was notified instead of inventing a recipient", out["notified"].startswith("nobody"))
fresh()
p = packaged("NEEDS_REVISION")
state["fail"] = {"no_notify_all"}
out = deliver({"packager_output": json.dumps(p)}, {})
check("notify: if the connector refuses notify_all the comment is still posted once without it", out["delivery"] == "delivered" and len(state["comments"]) == 1 and state["comments"][0]["notify_all"] is None)
for st in ("INPUT_REQUIRED", "NEEDS_REVISION", "VALIDATION_UNAVAILABLE"):
    fresh()
    deliver({"packager_output": json.dumps(packaged(st))}, {})
    check(f"handoff: {st} goes back to the content owner, never to formal review, and names no reviewer",
          "Medical, Legal and Regulatory" not in state["comments"][0]["comment_text"] and "formal review" not in [c[1].get("status") for c in calls])
fresh()
deliver({"packager_output": json.dumps(packaged("READY_FOR_FORMAL_REVIEW"))}, {})
check("handoff: READY asks for a reviewer to be assigned because none is modeled, and does not name a person",
      "Assign this task to the appropriate Medical, Legal and Regulatory reviewer." in state["comments"][0]["comment_text"])

# --- source routing
fresh()
LAB = {"callback": "required", "request_id": "aaaaaaaa-1111-4111-8111-000000000001", "status": "NEEDS_REVISION", "summary": "s", "validation_status": "ok",
       "formal_review_required": True, "checked_at": "2026-10-09T00:00:00Z", "findings": [], "source": "direct"}
sdk.tools.call = lambda name, **kw: (calls.append((name, kw)) or {"response_type": "application/json", "response": {"status": "ok"}})
out = deliver({"packager_output": json.dumps(LAB)}, {})
check("routing: lab still goes to submit_readiness_result only", out["delivery"] == "delivered" and [c[0] for c in calls] == ["submit_readiness_result"])
calls.clear()
out = deliver({"packager_output": json.dumps({**LAB, "callback": "not_required", "request_id": ""})}, {})
check("routing: chat delivers nothing", out["delivery"] == "skipped" and not calls)


print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
