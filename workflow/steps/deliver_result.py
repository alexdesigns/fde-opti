import json

# Hands the packaged readiness result to the requesting system through the registered Lab tool.
# Delivery is plumbing. It decides nothing and changes nothing: every field is passed exactly as the
# Result Packager produced it. Chat runs carry no request_id, so nothing is delivered for them.
FIELDS = ("request_id", "status", "summary", "validation_status", "formal_review_required", "checked_at", "findings")


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


STATUS_AFTER = {"NEEDS_REVISION": "changes needed", "READY_FOR_FORMAL_REVIEW": "formal review",
                "INPUT_REQUIRED": "changes needed", "VALIDATION_UNAVAILABLE": "changes needed"}
# The ClickUp "Content Readiness" dropdown label for each state. Readiness is separate from the task status above.
READINESS_LABEL = {"INPUT_REQUIRED": "Input Required", "NEEDS_REVISION": "Needs Revision",
                   "VALIDATION_UNAVAILABLE": "Validation Unavailable", "READY_FOR_FORMAL_REVIEW": "Ready for Formal Review"}
READINESS_FIELD, CHECKED_FIELD = "Content Readiness", "Last Checked"
MISSING_LABEL = {"market": "Market", "audience": "Audience",
                 "draft": "The draft copy Doc (named \"<task name>: Draft Copy\" in this list)",
                 "draft_content": "The draft copy (the Doc is empty)", "as_of_date": "The check date"}


def connector(tools, name, **kwargs):
    # A tool failure comes back as a value, not an exception. None means the call did not succeed.
    reply = tools.call(name, **kwargs)
    if not isinstance(reply, dict) or reply.get("response_type") == "error":
        return None
    body = reply.get("response")
    if isinstance(body, dict) and body.get("success") is False:
        return None
    if isinstance(body, dict) and "result" in body:
        body = body["result"]
    if isinstance(body, str):
        try:
            return json.loads(body)
        except ValueError:
            return {}
    return body if body is not None else {}


def bullets(items):
    return "\n".join(f"- {i}" for i in items)


def finding_line(f):
    quote = f' ("{f.get("quote")}")' if f.get("quote") else ""
    return f"{f.get('issue')}{quote}"


# What a reader sees for each recommendation basis. AI-written rewrites never read like approved wording.
SUGGEST_HEAD = {"approved_claim": "Suggested revision (approved wording)", "required_disclaimer": "Suggested revision (required disclaimer)",
                "contextual_rewrite": "Suggested rewrite (not approved copy)"}
BASIS_LINE = {"approved_claim": "approved claim", "required_disclaimer": "required disclaimer from the approved claim", "contextual_rewrite": "reviewer suggestion, not approved copy"}


def recommendation_lines(f):
    # Compact guidance for the content owner. Nothing here edits the Doc and nothing here is approval.
    rec = f.get("recommendation")
    if not isinstance(rec, dict) or not rec.get("suggested_revision") or rec.get("recommendation_basis") not in SUGGEST_HEAD:
        return ""
    basis = rec["recommendation_basis"]
    lines = [f"{SUGGEST_HEAD[basis]}: {rec['suggested_revision']}"]
    if rec.get("reason"):
        lines.append(f"Why: {rec['reason']}")
    lines.append(f"Basis: {BASIS_LINE[basis]}" + (f", {rec['source_reference']}" if rec.get("source_reference") else ""))
    return "\n" + "\n".join(lines)


def comment_text(package):
    # Built from the packaged result only. No raw JSON, tool payloads or step names.
    state, key = package.get("status"), package.get("delivery_key")
    ref = package.get("draft_ref") or ""
    findings = package.get("findings") or []
    blocking = [finding_line(f) + recommendation_lines(f) for f in findings if f.get("severity") == "blocking"][:8]
    advisories = [finding_line(f) for f in findings if f.get("severity") == "advisory"][:5]
    parts = ["CONTENT READINESS", READINESS_LABEL[state]]
    if state == "INPUT_REQUIRED":
        names = [MISSING_LABEL.get(m, m) for m in package.get("missing") or []] or ["Required input"]
        parts += ["Missing:\n" + bullets(names), "Next step:\nAdd the missing context and move the brief back into Internal Review."]
    elif state == "NEEDS_REVISION":
        parts.append("Blocking findings:\n" + ("\n\n".join(f"Finding {n}: {t}" for n, t in enumerate(blocking, 1)) if blocking else "- See the readiness report."))
        if advisories:
            parts.append("Advisories:\n" + bullets(advisories))
        parts.append("Next step:\nUpdate the draft and move the task to Internal Review when ready to check again. Suggestions are guidance, not approval.")
    elif state == "VALIDATION_UNAVAILABLE":
        parts += ["The governed validation step could not complete.", "Next step:\nRetry the readiness check or escalate the integration issue."]
    else:
        parts.append("Automated readiness is complete.")
        if advisories:
            parts.append("Advisories:\n" + bullets(advisories))
        # No Medical, Legal and Regulatory reviewer is modeled in this ClickUp workspace, so the comment asks for one rather than naming a person.
        parts += ["Human approval is still required.", "Next step:\nSend the content to formal Medical, Legal and Regulatory review. Assign this task to the appropriate Medical, Legal and Regulatory reviewer."]
    parts.append(f"Readiness ref: {key}\nDraft ref: {ref or 'none (no draft was read)'}")
    return "\n\n".join(parts)


def checked_stamp(package):
    # The packaged result already carries the completed-result time (UTC). No second clock is read.
    value = package.get("checked_at")
    return f"{value[:10]} {value[11:16]}" if isinstance(value, str) and len(value) >= 16 else None


def write_fields(tools, task_id, task, package):
    # Cosmetic metadata. A failure here is reported, never raised, and never changes the readiness result or the comment.
    fields = {f.get("name"): f for f in task.get("custom_fields") or [] if isinstance(f, dict)}
    wanted, label = [], READINESS_LABEL[package["status"]]
    ready_field = fields.get(READINESS_FIELD)
    option = next((o for o in (ready_field or {}).get("type_config", {}).get("options") or [] if o.get("name") == label), None)
    if ready_field and option and ready_field.get("id") and option.get("id"):
        wanted.append({"id": ready_field["id"], "value": option["id"]})
    stamp, checked_field = checked_stamp(package), fields.get(CHECKED_FIELD)
    if checked_field and checked_field.get("id") and stamp:
        wanted.append({"id": checked_field["id"], "value": stamp})
    if len(wanted) < 2:
        return "skipped: field or option not found"
    return "written" if connector(tools, "clickup_update_task", task_id=task_id, custom_fields=wanted) is not None else "failed"


def deliver_clickup(package):
    task_id, key = package["task_id"], package["delivery_key"]
    if package.get("duplicate"):
        return {"delivery": "skipped", "reason": "this readiness event was already delivered", "summary": f"Duplicate for task {task_id}: nothing posted."}
    target = STATUS_AFTER.get(package.get("status"))
    if target is None or package.get("status") not in READINESS_LABEL:
        raise RuntimeError("Delivery failed: the readiness state is not one this step can deliver.")
    from opal_tms_sdk import tools, OpalTmsSdkError

    try:
        task = connector(tools, "clickup_get_task", task_id=task_id, include=["custom_fields"])
        if not isinstance(task, dict) or task.get("id") != task_id:
            raise RuntimeError("Delivery failed: the ClickUp task could not be read, so nothing was written.")
        comments = connector(tools, "clickup_get_task_comments", task_id=task_id)
        if comments is None:
            raise RuntimeError("Delivery failed: existing comments could not be read, so nothing was written.")
        posted = key in json.dumps(comments)
        # Order: readiness fields, comment, then task status. The fields come first because they are repeatable and harmless.
        # The status comes last so a task is never moved on before its comment exists. A fields failure does not stop the rest.
        fields = write_fields(tools, task_id, task, package)
        if not posted:
            text = comment_text(package)
            # notify_all makes ClickUp notify the task's own assignees, so the next person hears about it through the existing
            # assignee mechanism. No person is named or hardcoded. If the connector refuses the option, post without it.
            made = connector(tools, "clickup_create_comment", entity_id=task_id, entity_type="task", comment_text=text, notify_all=True)
            if made is None:
                made = connector(tools, "clickup_create_comment", entity_id=task_id, entity_type="task", comment_text=text)
            if made is None:
                raise RuntimeError("Delivery failed: ClickUp did not accept the comment.")
        # Setting a status is repeatable, so a retry after a half-finished delivery finishes the job without a second comment.
        moved = connector(tools, "clickup_update_task", task_id=task_id, status=target)
        if moved is None:
            raise RuntimeError("Delivery failed: ClickUp did not accept the status change.")
    except OpalTmsSdkError as error:
        raise RuntimeError(f"Delivery failed: {type(error).__name__}.") from None
    return {"delivery": "delivered", "target": "clickup", "task_id": task_id, "status": package.get("status"), "task_status": target,
            "readiness_fields": fields, "comment": "already present" if posted else "posted",
            "notified": "task assignees" if task.get("assignees") else "nobody: the task has no assignee",
            "summary": f"Delivered {package.get('status')} to ClickUp task {task_id} (fields {fields.split(':')[0]})."}


def handler(input, ctx):
    package = as_obj(input.get("packager_output"))
    if package is None:
        raise RuntimeError("Delivery failed: the Result Packager output could not be read, so nothing was delivered.")
    if package.get("source") == "clickup":
        return deliver_clickup(package)
    if package.get("callback") == "invalid":
        raise RuntimeError("Delivery failed: a request_id was supplied but is not a valid identifier, so the result was not delivered.")
    if package.get("callback") != "required":
        return {"delivery": "skipped", "reason": "no request_id supplied", "summary": "Delivery skipped: no request_id, as in Chat."}

    from opal_tms_sdk import tools, OpalTmsSdkError

    try:
        reply = tools.call("submit_readiness_result", **{k: package.get(k) for k in FIELDS})
    except OpalTmsSdkError as error:
        # Opal retries a failed step. The Lab accepts an identical resubmission, so a retry is safe.
        raise RuntimeError(f"Delivery failed: {type(error).__name__}.") from None

    # A tool failure comes back as a value, not an exception, so success is checked explicitly.
    body = reply.get("response") if isinstance(reply, dict) else None
    if not (isinstance(reply, dict) and reply.get("response_type") != "error" and isinstance(body, dict) and body.get("status") == "ok"):
        code = body.get("status_code") if isinstance(body, dict) else None
        raise RuntimeError(f"Delivery failed: the Lab did not accept the result (status {code}).")
    return {"delivery": "delivered", "request_id": package["request_id"], "status": package.get("status"),
            "summary": f"Delivered {package.get('status')} for request {package['request_id']}."}
