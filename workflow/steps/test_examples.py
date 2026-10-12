# Checks that IN1 accepts the published request example. Run: python3 -I test_examples.py .
import json, os, sys, tempfile
sys.path.insert(0, sys.argv[1])
from check_inputs import handler as check
here = os.path.dirname(os.path.abspath(__file__))
request = json.load(open(os.path.join(here, "..", "..", "examples", "request-example.json")))
out = check({k: v for k, v in request.items() if k != "request_id"}, {"output_dir": tempfile.mkdtemp(), "input_dir": "/nonexistent"})
ok = out["gate"] == "INPUTS_OK" and out["market"] == request["market"] and out["audience"] == request["audience"]
print(("PASS" if ok else "FAIL"), "request-example.json passes IN1:", out["gate"], out["cited_claim_ids"])
sys.exit(0 if ok else 1)
