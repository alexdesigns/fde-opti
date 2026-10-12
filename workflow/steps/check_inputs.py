import hashlib
import json
import re
from datetime import date

# IN1. Checks the request before review. A ClickUp-started run arrives as the raw Call webhook body: this step parses it
# with code, reads the task and the draft Doc through the ClickUp connector, and hands on exact values. No model picks the
# task ID or rewrites the draft. Every other source (Chat, Lab) behaves as before.
TASK_ID = re.compile(r"[A-Za-z0-9]{4,20}")
DRAFT_DOC_SUFFIX = ": Draft Copy"


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


def parse_clickup(raw):
    # ClickUp's Call webhook body: {date, auto_id, payload: {id, name, status: {status}, ...}}. Anything else is not ClickUp.
    body = as_obj(raw)
    if not body or "auto_id" not in body or not isinstance(body.get("payload"), dict):
        return None
    task = body["payload"]
    status = task.get("status")
    return {"task_id": task.get("id"), "task_name": task.get("name"), "fired": str(body.get("date") or ""),
            "status": status.get("status") if isinstance(status, dict) else status}


def connector(tools, name, **kwargs):
    # A tool failure comes back as a value, not an exception. None means the call did not succeed.
    try:
        reply = tools.call(name, **kwargs)
    except Exception:
        return None
    if not isinstance(reply, dict) or reply.get("response_type") == "error":
        return None
    body = reply.get("response")
    if isinstance(body, dict) and body.get("success") is False:
        return None
    if isinstance(body, dict) and "result" in body:
        body = body["result"]
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return None
    return body


def field_value(task, name):
    for f in task.get("custom_fields") or []:
        if f.get("name") != name:
            continue
        value = f.get("value")
        if f.get("type") == "drop_down":
            if isinstance(value, int) and not isinstance(value, bool):
                for o in (f.get("type_config") or {}).get("options") or []:
                    if o.get("orderindex") == value:
                        return o.get("name") or ""
            return ""
        if f.get("type") == "tasks" and isinstance(value, list):
            return ", ".join(str(v.get("name")) for v in value if isinstance(v, dict))
        return value if isinstance(value, str) else ""
    return ""


def find_draft_doc(tools, task_name, list_id):
    # The Doc is found by its name, "<task name>: Draft Copy", inside the task's own list. Exactly one match or nothing.
    wanted, matches, cursor = f"{task_name}{DRAFT_DOC_SUFFIX}", [], None
    for _ in range(3):
        args = {"keywords": wanted, "filters": {"asset_types": ["doc"]}, "count": 10}
        if cursor:
            args["cursor"] = cursor
        found = connector(tools, "clickup_search", **args)
        if not isinstance(found, dict):
            return None, "unavailable"
        for r in found.get("results") or []:
            sub = ((r.get("hierarchy") or {}).get("subcategory") or {}).get("id")
            if r.get("type") == "doc" and r.get("name") == wanted and str(sub) == str(list_id):
                matches.append(r)
        cursor = found.get("next_cursor")
        if not cursor:
            break
    if len(matches) != 1:
        return None, "not_found" if not matches else "ambiguous"
    return matches[0], "ok"


def seal(out, info, tools):
    # The delivery key ties one readiness result to one ClickUp event (task, the time the Automation fired) and one draft.
    # A retried webhook repeats the same event and draft, so it repeats the key. A new move to Internal Review does not.
    out["delivery_key"] = hashlib.sha256(f"{out['task_id']}|{info.get('fired')}|{out['draft_sha256']}".encode()).hexdigest()[:16]
    comments = connector(tools, "clickup_get_task_comments", task_id=out["task_id"])
    out["duplicate"] = comments is not None and out["delivery_key"] in json.dumps(comments)
    return out


def resolve_clickup(info, tools):
    task_id = info["task_id"]
    out = {"source": "clickup", "task_id": task_id, "missing": [], "duplicate": False, "draft_content": "", "market": "", "audience": "",
           "delivery_key": "", "draft_sha256": "", "doc_id": "", "doc_updated": "", "list_id": "", "task_name": "", "product": "", "campaign": ""}
    task = connector(tools, "clickup_get_task", task_id=task_id, include=["custom_fields"])
    if not isinstance(task, dict) or task.get("id") != task_id:
        raise RuntimeError("ClickUp task could not be read through the connector, so nothing was checked.")
    if info.get("task_name") and task.get("name") != info["task_name"]:
        raise RuntimeError("The task read through the connector does not match the webhook payload, so nothing was checked.")
    out.update(task_name=task.get("name") or "", list_id=str((task.get("list") or {}).get("id") or ""),
               market=field_value(task, "Market"), audience=field_value(task, "Audience"),
               product=field_value(task, "Product / Offering"), campaign=field_value(task, "Campaign / Initiative"))
    doc, why = find_draft_doc(tools, out["task_name"], out["list_id"])
    if why == "unavailable":
        raise RuntimeError("ClickUp Docs could not be searched through the connector, so nothing was checked.")
    if doc is None:
        out["missing"].append("draft")
        return seal(out, info, tools)
    out.update(doc_id=doc.get("id") or "", doc_updated=str(doc.get("dateUpdated") or ""))
    page = connector(tools, "clickup_get_document_pages", document_id=doc.get("id"), page_ids=[doc.get("pageId")], content_format="text/plain")
    pages = page.get("pages") if isinstance(page, dict) else None
    if not pages or not isinstance(pages[0].get("content"), str):
        raise RuntimeError("The draft Doc could not be read through the connector, so nothing was checked.")
    draft = pages[0]["content"]
    out["draft_content"] = draft
    out["draft_sha256"] = hashlib.sha256(draft.encode("utf-8")).hexdigest()
    return seal(out, info, tools)


def handler(input, ctx):
    draft = (input.get("draft_content") or "").strip()
    market = (input.get("market") or "").strip().upper()
    audience = (input.get("audience") or "").strip().lower()
    as_of = (input.get("as_of_date") or "").strip()
    resolved = {"source": "direct", "task_id": "", "delivery_key": "", "duplicate": False, "draft_content": "", "doc_id": "", "doc_updated": "",
                "draft_sha256": "", "task_name": "", "product": "", "campaign": ""}
    missing = []

    info = parse_clickup(input.get("webhook_payload"))
    if info is not None:
        if not isinstance(info["task_id"], str) or not TASK_ID.fullmatch(info["task_id"]):
            missing.append("clickup_task_id")
            resolved.update(source="clickup")
        else:
            from opal_tms_sdk import tools
            resolved = resolve_clickup(info, tools)
            missing += resolved["missing"]
            draft, market, audience = resolved["draft_content"].strip(), resolved["market"].strip().upper(), resolved["audience"].strip().lower()
    if not draft and "draft" not in missing and "clickup_task_id" not in missing:
        missing.append("draft_content")
    if not re.fullmatch(r"[A-Z]{2}", market):
        missing.append("market")
    if audience not in ("hcp", "patient"):
        missing.append("audience")
    if as_of:
        try:
            date.fromisoformat(as_of)
        except ValueError:
            missing.append("as_of_date")
    full_draft = resolved["draft_content"] if resolved["source"] == "clickup" else draft
    ids = sorted(set(re.findall(r"\[(CLM-\d{3})\]", full_draft)))
    gate = "INPUT_REQUIRED" if missing else ("DUPLICATE_DELIVERED" if resolved["duplicate"] else "INPUTS_OK")
    # Every value echoed here is pattern-checked, so the Condition's text match cannot be spoofed by draft content.
    return {
        "gate": gate,
        "missing": missing,
        "market": market if "market" not in missing else "",
        "audience": audience if "audience" not in missing else "",
        "as_of_date": as_of if "as_of_date" not in missing else "",
        "cited_claim_ids": ",".join(ids),
        "source": resolved["source"],
        "task_id": resolved["task_id"],
        "task_name": resolved["task_name"],
        "delivery_key": resolved["delivery_key"],
        "duplicate": resolved["duplicate"],
        "doc_id": resolved["doc_id"],
        "doc_updated": resolved["doc_updated"],
        "draft_sha256": resolved["draft_sha256"],
        "draft_content": full_draft if resolved["source"] == "clickup" else "",
        "summary": f"{gate}: {', '.join(missing) or 'all inputs present'}; cited IDs: {', '.join(ids) or 'none'}",
    }
