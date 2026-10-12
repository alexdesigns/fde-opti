// Deterministic tests for the result contract, the callback validation and the temporary store.
// Run: npm test (from tools/)
import { test } from "node:test";
import * as assert from "node:assert/strict";
import * as os from "node:os";
import * as path from "node:path";
import { promises as fs } from "node:fs";
import { BlobConflict, CALLBACK_DISCOVERY, RESULT_TTL_MS, blobStore, describeRecord, fileStore, idempotencyHash, isRequestId, parseSubmission, type BlobClient, type ReadinessResult } from "./readiness-result";

const ID = "5a92e7b8-c5ba-44f5-887f-235fd818f676";
const good = {
  request_id: ID,
  status: "NEEDS_REVISION",
  summary: "2 items to resolve before formal review.",
  validation_status: "ok",
  formal_review_required: true,
  checked_at: "2026-10-09T22:30:00Z",
  findings: [{ type: "claim_wording", severity: "blocking", quote: "convenient once-daily", issue: "Not approved for this audience.", suggestion: "Remove it." }],
};

test("accepts a normalized result and the Opal parameters envelope", () => {
  assert.equal(parseSubmission(good).ok, true);
  const wrapped = parseSubmission({ parameters: good });
  assert.equal(wrapped.ok, true);
  if (wrapped.ok) assert.equal(wrapped.value.schema_version, "1");
});

test("tolerates findings as JSON text and the boolean as text, as Opal may send them", () => {
  const r = parseSubmission({ ...good, findings: JSON.stringify(good.findings), formal_review_required: "true" });
  assert.equal(r.ok, true);
});

test("tolerates each finding arriving as JSON text, but only valid JSON objects", () => {
  const asText = good.findings.map((f) => JSON.stringify(f));
  assert.equal(parseSubmission({ ...good, findings: asText }).ok, true);
  assert.equal(parseSubmission({ ...good, findings: ["not json"] }).ok, false);
  assert.equal(parseSubmission({ ...good, findings: ["[1,2]"] }).ok, false);
  assert.equal(parseSubmission({ ...good, findings: ["\"just a string\""] }).ok, false);
});

test("only the four readiness states are accepted; approved words never are", () => {
  for (const s of ["APPROVED", "COMPLIANT", "REGULATORY_APPROVED", "ready", "", undefined, 7]) {
    const r = parseSubmission({ ...good, status: s });
    assert.equal(r.ok === false && r.code, "invalid_status");
  }
  for (const s of ["INPUT_REQUIRED", "NEEDS_REVISION", "READY_FOR_FORMAL_REVIEW", "VALIDATION_UNAVAILABLE"]) {
    assert.equal(parseSubmission({ ...good, status: s, findings: [] }).ok, true);
  }
});

const rec = (over: Record<string, unknown> = {}) => ({ suggested_revision: "OptiThera is indicated for adults with moderate to severe plaque psoriasis.", reason: "Wording differs from the approved claim.", recommendation_basis: "approved_claim", source_reference: "CLM-001", original_text: "adults with plaque psoriasis", human_review_required: true, ...over });
const withRec = (r: unknown, status = "NEEDS_REVISION", severity = "blocking") => ({ ...good, status, findings: [{ ...good.findings[0], severity, recommendation: r }] });

test("R8 a governed recommendation is kept with its basis and source", () => {
  const r = parseSubmission(withRec(rec()));
  assert.equal(r.ok, true);
  if (r.ok) assert.deepEqual(r.value.findings[0].recommendation, rec());
});

test("R1 a contextual rewrite needs no source and keeps its basis", () => {
  const r = parseSubmission(withRec(rec({ recommendation_basis: "contextual_rewrite", source_reference: undefined })));
  assert.equal(r.ok, true);
  if (r.ok) assert.equal(r.value.findings[0].recommendation?.recommendation_basis, "contextual_rewrite");
});

test("R9 governed wording without a source is refused, so an AI rewrite cannot pass as approved", () => {
  for (const basis of ["approved_claim", "required_disclaimer"]) assert.equal(parseSubmission(withRec(rec({ recommendation_basis: basis, source_reference: "" }))).ok, false);
});

test("a recommendation is never approval: human review must be true and the basis must be known", () => {
  assert.equal(parseSubmission(withRec(rec({ human_review_required: false }))).ok, false);
  assert.equal(parseSubmission(withRec(rec({ recommendation_basis: "approved" }))).ok, false);
  assert.equal(parseSubmission(withRec(rec({ suggested_revision: "  " }))).ok, false);
  assert.equal(parseSubmission(withRec(rec({ suggested_revision: "x".repeat(701) }))).ok, false);
});

test("R5 R6 R7 recommendations only ride on blocking findings of a NEEDS_REVISION result", () => {
  assert.equal(parseSubmission(withRec(rec(), "READY_FOR_FORMAL_REVIEW", "advisory")).ok, false);
  assert.equal(parseSubmission(withRec(rec(), "INPUT_REQUIRED")).ok, false);
  assert.equal(parseSubmission(withRec(rec(), "VALIDATION_UNAVAILABLE")).ok, false);
  assert.equal(parseSubmission(withRec(rec(), "NEEDS_REVISION", "advisory")).ok, false);
});

test("R4 a finding with no safe suggestion carries no recommendation and still validates; the four states are unchanged", () => {
  const r = parseSubmission(good);
  assert.equal(r.ok, true);
  if (r.ok) assert.equal(r.value.findings[0].recommendation, undefined);
  assert.equal(parseSubmission({ ...good, status: "APPROVED" }).ok, false);
});

test("a recommendation may arrive as JSON text, as Opal may send nested objects", () => {
  assert.equal(parseSubmission(withRec(JSON.stringify(rec()))).ok, true);
});

test("request_id must be a UUID; formal review can never be waived", () => {
  assert.equal(isRequestId(ID), true);
  assert.equal(isRequestId("../etc/passwd"), false);
  assert.equal(parseSubmission({ ...good, request_id: "42" }).ok, false);
  assert.equal(parseSubmission({ ...good, formal_review_required: false }).ok, false);
});

test("a ready result cannot carry a blocking finding", () => {
  const r = parseSubmission({ ...good, status: "READY_FOR_FORMAL_REVIEW" });
  assert.equal(r.ok === false && r.code, "inconsistent_result");
  const advisory = parseSubmission({ ...good, status: "READY_FOR_FORMAL_REVIEW", findings: [{ ...good.findings[0], severity: "advisory" }] });
  assert.equal(advisory.ok, true);
});

test("bounds: oversized fields and too many findings are rejected", () => {
  assert.equal(parseSubmission({ ...good, summary: "x".repeat(501) }).ok, false);
  assert.equal(parseSubmission({ ...good, findings: [{ ...good.findings[0], quote: "x".repeat(501) }] }).ok, false);
  assert.equal(parseSubmission({ ...good, findings: Array(51).fill(good.findings[0]) }).ok, false);
  assert.equal(parseSubmission({ ...good, checked_at: "yesterday" }).ok, false);
  assert.equal(parseSubmission({ ...good, findings: [{ ...good.findings[0], severity: "fatal" }] }).ok, false);
});

test("unexpected extra fields, such as draft text, are dropped, not stored", () => {
  const r = parseSubmission({ ...good, draft_content: "the whole draft", market: "US" });
  assert.equal(r.ok, true);
  if (r.ok) assert.equal("draft_content" in r.value || "market" in r.value, false);
});

async function tmp() {
  return fileStore(await fs.mkdtemp(path.join(os.tmpdir(), "fde-store-test-")));
}
const result = (over: Partial<ReadinessResult> = {}): ReadinessResult => {
  const p = parseSubmission({ ...good, ...over });
  if (!p.ok) throw new Error("setup");
  return p.value;
};

test("store: pending, then complete, then read back; an identical retry is a duplicate and a different result is a conflict", async () => {
  const s = await tmp();
  await s.createPending({ request_id: ID, idempotency_hash: null });
  assert.equal((await s.get(ID))?.state, "PROCESSING");
  assert.equal(await s.complete(result()), "stored");
  const done = await s.get(ID);
  assert.equal(done?.state, "COMPLETE");
  assert.equal(await s.complete(result({ status: "INPUT_REQUIRED" })), "conflict");
  assert.equal(await s.complete(result()), "duplicate");
  // A retried run restamps checked_at. Same content is still a duplicate; any other difference is a conflict.
  assert.equal(await s.complete(result({ checked_at: "2026-10-09T23:59:59.000Z" })), "duplicate");
  assert.equal(await s.complete(result({ summary: "Different wording." })), "conflict");
  assert.equal(await s.complete(result({ findings: [] })), "conflict");
  assert.equal((await s.get(ID) as { result: ReadinessResult }).result.status, "NEEDS_REVISION");
});

test("store: a result for a request nobody started is refused; nothing is invented", async () => {
  const s = await tmp();
  assert.equal(await s.complete(result()), "unknown");
  assert.equal(await s.get(ID), null);
});

test("store: expiry and cleanup", async () => {
  const s = await tmp();
  const t0 = Date.parse("2026-10-09T00:00:00Z");
  await s.createPending({ request_id: ID, idempotency_hash: null }, t0);
  assert.equal(await s.complete(result(), t0 + RESULT_TTL_MS + 1), "expired");
  const other = "6896a230-6dbe-458b-8973-3bf5f18833d8";
  await s.createPending({ request_id: other, idempotency_hash: null }, t0 + 3 * RESULT_TTL_MS); // purges the stale one
  assert.equal(await s.get(ID), null);
  assert.equal((await s.get(other))?.state, "PROCESSING");
});

test("store: idempotency maps the same revision and content to the same request; discard frees it", async () => {
  const s = await tmp();
  const h = idempotencyHash("rev:wordpress:42:7", "draft text", "US", "patient");
  assert.notEqual(h, idempotencyHash("rev:wordpress:42:7", "draft text changed", "US", "patient"));
  assert.notEqual(h, idempotencyHash("rev:wordpress:42:7", "draft text", "US", "hcp"));
  await s.createPending({ request_id: ID, idempotency_hash: h });
  assert.equal(await s.findByIdempotency(h), ID);
  await s.discard(ID);
  assert.equal(await s.findByIdempotency(h), null);
});

test("store never writes the draft: only ids, times and the normalized result", async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), "fde-store-test-"));
  const s = fileStore(dir);
  await s.createPending({ request_id: ID, idempotency_hash: idempotencyHash("k", "SECRET DRAFT BODY", "US", "patient") });
  await s.complete(result());
  const all = (await Promise.all((await fs.readdir(dir)).map((n) => fs.readFile(path.join(dir, n), "utf8")))).join("");
  assert.equal(all.includes("SECRET DRAFT BODY"), false);
});

test("callback manifest: one POST function with the minimal parameters", () => {
  const [f] = CALLBACK_DISCOVERY.functions;
  assert.equal(f.name, "submit_readiness_result");
  assert.equal(f.http_method, "POST");
  assert.deepEqual(f.parameters.map((p) => p.name), ["request_id", "status", "summary", "validation_status", "formal_review_required", "checked_at", "findings"]);
  const documented = new Set(["string", "number", "boolean", "array", "object"]);
  assert.ok(f.parameters.every((p) => documented.has(p.type) && p.required));
});

test("status endpoint: unknown, processing, complete and expired each answer plainly", () => {
  const t0 = Date.parse("2026-10-09T12:00:00Z");
  const base = { request_id: ID, created_at: new Date(t0).toISOString(), expires_at: new Date(t0 + RESULT_TTL_MS).toISOString(), idempotency_hash: null };
  assert.equal(describeRecord(null, t0).http, 404);
  const pending = describeRecord({ ...base, state: "PROCESSING" }, t0 + 1000);
  assert.deepEqual([pending.http, pending.body], [202, { state: "PROCESSING" }]);
  const done = describeRecord({ ...base, state: "COMPLETE", result: result() }, t0 + 1000);
  assert.equal(done.http, 200);
  assert.equal((done.body as { status: string }).status, "NEEDS_REVISION");
  assert.equal(describeRecord({ ...base, state: "COMPLETE", result: result() }, t0 + RESULT_TTL_MS + 1).http, 410);
  assert.equal(describeRecord({ ...base, state: "PROCESSING" }, t0 + RESULT_TTL_MS + 1).http, 410);
});

// ---------------------------------------------------------------------------------------------
// Shared (Blob) store, against an in-memory client that models create-if-absent and ETag preconditions.
function fakeBlob() {
  const files = new Map<string, { text: string; etag: number; uploadedAt: number }>();
  let etag = 0;
  let beforeNextConditionalPut: (() => void) | null = null;
  let clock = Date.now();
  const client: BlobClient = {
    async put(path, body, opts) {
      const cur = files.get(path);
      if (opts.ifMatch !== undefined || opts.overwrite) {
        const hook = beforeNextConditionalPut;
        beforeNextConditionalPut = null;
        hook?.();
        const now = files.get(path);
        if (opts.ifMatch !== undefined && (!now || String(now.etag) !== opts.ifMatch)) throw new BlobConflict("stale");
      } else if (cur) throw new BlobConflict("exists");
      etag += 1;
      files.set(path, { text: body, etag, uploadedAt: clock });
      return { etag: String(etag) };
    },
    async get(path) {
      const f = files.get(path);
      return f ? { etag: String(f.etag), text: f.text } : null;
    },
    async del(paths) {
      for (const x of paths) files.delete(x);
    },
    async list(prefix, limit) {
      return [...files].filter(([k]) => k.startsWith(prefix)).slice(0, limit).map(([k, v]) => ({ pathname: k, uploadedAt: v.uploadedAt }));
    },
  };
  return { client, files, race: (fn: () => void) => (beforeNextConditionalPut = fn), setClock: (t: number) => (clock = t) };
}
const ID2 = "6b03f8c9-d6cb-45a5-998e-346e92909787";

test("blob store: pending, complete, read back, identical retry is a duplicate, different result is a conflict", async () => {
  const { client } = fakeBlob();
  const s = blobStore(client);
  await s.createPending({ request_id: ID, idempotency_hash: null });
  assert.equal((await s.get(ID))?.state, "PROCESSING");
  assert.equal(await s.complete(result()), "stored");
  assert.equal((await s.get(ID))?.state, "COMPLETE");
  assert.equal(await s.complete(result()), "duplicate");
  assert.equal(await s.complete(result({ checked_at: "2026-10-10T01:00:00Z" })), "duplicate");
  assert.equal(await s.complete(result({ status: "INPUT_REQUIRED" })), "conflict");
  assert.equal(((await s.get(ID)) as { result: ReadinessResult }).result.status, "NEEDS_REVISION");
});

test("blob store: unknown and expired requests are refused", async () => {
  const { client } = fakeBlob();
  const s = blobStore(client);
  assert.equal(await s.complete(result()), "unknown");
  const t0 = Date.now();
  await s.createPending({ request_id: ID, idempotency_hash: null }, t0);
  assert.equal(await s.complete(result(), t0 + RESULT_TTL_MS + 1), "expired");
  assert.equal(describeRecord(await s.get(ID), t0 + RESULT_TTL_MS + 1).http, 410);
});

test("blob store: a concurrent writer between read and write is detected and the retry sees the winner", async () => {
  const { client, race } = fakeBlob();
  const s = blobStore(client);
  await s.createPending({ request_id: ID, idempotency_hash: null });
  // Another callback lands with a different result after we read, before we write.
  race(() => void client.put(`readiness/${ID}.json`, JSON.stringify({ request_id: ID, state: "COMPLETE", created_at: "x", expires_at: new Date(Date.now() + 1e6).toISOString(), idempotency_hash: null, result: result({ status: "INPUT_REQUIRED" }) }), { overwrite: true }));
  assert.equal(await s.complete(result()), "conflict");
  assert.equal(((await s.get(ID)) as { result: ReadinessResult }).result.status, "INPUT_REQUIRED");
});

test("blob store: the same idempotency key maps to one request; a concurrent identical request is reported as a duplicate", async () => {
  const { client } = fakeBlob();
  const s = blobStore(client);
  const h = idempotencyHash("rev:wordpress:42:7", "draft", "US", "patient");
  assert.equal(await s.createPending({ request_id: ID, idempotency_hash: h }), undefined);
  assert.equal(await s.findByIdempotency(h), ID);
  assert.deepEqual(await s.createPending({ request_id: ID2, idempotency_hash: h }), { duplicate_of: ID });
  assert.equal(await s.get(ID2), null);
});

test("blob store: an expired idempotency key can be taken over by a new request", async () => {
  const { client } = fakeBlob();
  const s = blobStore(client);
  const h = idempotencyHash("rev:wordpress:42:7", "draft", "US", "patient");
  const t0 = Date.now() - RESULT_TTL_MS - 1000;
  await s.createPending({ request_id: ID, idempotency_hash: h }, t0);
  assert.equal(await s.createPending({ request_id: ID2, idempotency_hash: h }), undefined);
  assert.equal(await s.findByIdempotency(h), ID2);
});

test("blob store: discard frees the key so a retry after a failed start is accepted", async () => {
  const { client } = fakeBlob();
  const s = blobStore(client);
  const h = idempotencyHash("k", "draft", "US", "hcp");
  await s.createPending({ request_id: ID, idempotency_hash: h });
  await s.discard(ID);
  assert.equal(await s.get(ID), null);
  assert.equal(await s.createPending({ request_id: ID2, idempotency_hash: h }), undefined);
});

test("blob store: records past two lifetimes are removed on the next request", async () => {
  const { client, files, setClock } = fakeBlob();
  const s = blobStore(client);
  setClock(Date.now() - 3 * RESULT_TTL_MS);
  await s.createPending({ request_id: ID, idempotency_hash: null });
  setClock(Date.now());
  await s.createPending({ request_id: ID2, idempotency_hash: null });
  assert.equal(files.has(`readiness/${ID}.json`), false);
  assert.equal(files.has(`readiness/${ID2}.json`), true);
});

test("blob store: only ids, times, the idempotency hash and the normalized result are persisted, never the draft", async () => {
  const { client, files } = fakeBlob();
  const s = blobStore(client);
  await s.createPending({ request_id: ID, idempotency_hash: idempotencyHash("k", "SECRET DRAFT TEXT", "US", "hcp") });
  await s.complete(result());
  for (const f of files.values()) assert.equal(/SECRET DRAFT TEXT/.test(f.text), false);
  const stored = JSON.parse(files.get(`readiness/${ID}.json`)!.text);
  assert.deepEqual(Object.keys(stored).sort(), ["created_at", "expires_at", "idempotency_hash", "request_id", "result", "state"]);
});
