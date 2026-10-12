# Local test of the Deliver Result step with a stubbed opal_tms_sdk. Run: python3 -I test_delivery.py .
import json, sys, types
sys.path.insert(0, sys.argv[1])

calls = []
mode = {"reply": {"response_type": "application/json", "response": {"status": "ok"}}, "raise": None}


class OpalTmsSdkError(Exception):
    pass


class ToolInvocationError(OpalTmsSdkError):
    pass


class FakeTools:
    def call(self, name, **kwargs):
        calls.append((name, kwargs))
        if mode["raise"]:
            raise mode["raise"]
        return mode["reply"]


sdk = types.ModuleType("opal_tms_sdk")
sdk.tools, sdk.OpalTmsSdkError = FakeTools(), OpalTmsSdkError
sys.modules["opal_tms_sdk"] = sdk
from deliver_result import handler as deliver, FIELDS

RID = "aaaaaaaa-1111-4111-8111-000000000001"
PKG = {"callback": "required", "request_id": RID, "status": "NEEDS_REVISION", "summary": "1 item to resolve before formal review.",
       "validation_status": "ok", "formal_review_required": True, "checked_at": "2026-10-09T00:00:00Z",
       "findings": [{"type": "claim_wording", "severity": "blocking", "quote": "q", "issue": "i", "suggestion": "s"}],
       "extra_field_that_must_not_travel": "draft text"}
results = []


def check(name, ok):
    results.append(ok)
    print("PASS" if ok else "FAIL", name)


def raises(fn):
    try:
        fn()
    except RuntimeError as e:
        return str(e)
    return None


def reset(reply=None, error=None):
    calls.clear()
    mode["reply"] = reply or {"response_type": "application/json", "response": {"status": "ok"}}
    mode["raise"] = error


reset()
out = deliver({"packager_output": json.dumps(PKG)}, {})
check("delivered: success reply returns delivered", out["delivery"] == "delivered" and out["request_id"] == RID)
check("delivered: one call, to the registered tool", len(calls) == 1 and calls[0][0] == "submit_readiness_result")
check("delivered: only the seven contract fields travel, unchanged", set(calls[0][1]) == set(FIELDS) and all(calls[0][1][k] == PKG[k] for k in FIELDS))

reset()
out = deliver({"packager_output": "Result:\n" + json.dumps(PKG) + "\nDone."}, {})
check("delivered: JSON wrapped in prose is still read", out["delivery"] == "delivered")

for rid in ("", None):
    reset()
    out = deliver({"packager_output": json.dumps({**PKG, "callback": "not_required", "request_id": rid})}, {})
    check(f"skipped: no request_id ({rid!r}) makes no call", out["delivery"] == "skipped" and not calls)

reset()
msg = raises(lambda: deliver({"packager_output": json.dumps({**PKG, "callback": "invalid", "request_id": ""})}, {}))
check("fail closed: a malformed request_id raises, no call", msg is not None and "not a valid identifier" in msg and not calls)

reset()
check("fail closed: unreadable packager output raises, no call", raises(lambda: deliver({"packager_output": "nope"}, {})) is not None and not calls)
check("fail closed: missing packager output raises", raises(lambda: deliver({}, {})) is not None)

reset({"response_type": "error", "response": {"message": "Tool invocation failed with status 404.", "status_code": 404}})
msg = raises(lambda: deliver({"packager_output": json.dumps(PKG)}, {}))
check("fail closed: an error reply value raises and names the status", msg is not None and "404" in msg)

reset({"response_type": "error", "response": {"message": "x", "status_code": 409}})
check("fail closed: a 409 conflict raises", raises(lambda: deliver({"packager_output": json.dumps(PKG)}, {})) is not None)

reset({"response_type": "application/json", "response": {"status": "weird"}})
check("fail closed: an unexpected success body raises", raises(lambda: deliver({"packager_output": json.dumps(PKG)}, {})) is not None)

reset({"unexpected": True})
check("fail closed: a reply without the expected shape raises", raises(lambda: deliver({"packager_output": json.dumps(PKG)}, {})) is not None)

reset(error=ToolInvocationError("boom with draft text"))
msg = raises(lambda: deliver({"packager_output": json.dumps(PKG)}, {}))
check("fail closed: an SDK exception raises with the class name only", msg is not None and "ToolInvocationError" in msg and "draft text" not in msg)


from deliver_result import STATUS_AFTER
check("no automated readiness state maps to an approved, scheduled, live or complete task status",
      set(STATUS_AFTER) == {"INPUT_REQUIRED", "NEEDS_REVISION", "VALIDATION_UNAVAILABLE", "READY_FOR_FORMAL_REVIEW"}
      and set(STATUS_AFTER.values()) == {"changes needed", "formal review"})
check("an unknown state such as APPROVED cannot be delivered to ClickUp",
      raises(lambda: deliver({"packager_output": json.dumps({"source": "clickup", "task_id": "86a0test1", "delivery_key": "0123456789abcdef", "status": "APPROVED", "duplicate": False})}, {})) is not None)

print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
