// Guards the published examples: every result example must pass the submit_readiness_result contract unchanged.
// Run: npm test (from tools/)
import * as assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as path from "node:path";
import { test } from "node:test";
import { parseSubmission } from "../submit-readiness-result/readiness-result";

const dir = path.join(process.cwd(), "..", "examples");
const load = (name: string) => JSON.parse(readFileSync(path.join(dir, name), "utf8"));

for (const [name, state] of [["needs-revision-result.json", "NEEDS_REVISION"], ["ready-for-formal-review-result.json", "READY_FOR_FORMAL_REVIEW"]] as const) {
  test(`${name} is a valid readiness result`, () => {
    const example = load(name);
    const parsed = parseSubmission(example);
    assert.ok(parsed.ok, parsed.ok ? "" : parsed.message);
    if (parsed.ok) {
      assert.equal(parsed.value.status, state);
      assert.deepEqual(parsed.value, example);
    }
  });
}
