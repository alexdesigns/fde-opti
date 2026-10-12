// The CMS-facing readiness result, the callback tool contract, and the temporary result store.
// Nothing here decides readiness. It validates and carries what the Optimizely AI workflow decided.
import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

export const STATES = ["INPUT_REQUIRED", "NEEDS_REVISION", "READY_FOR_FORMAL_REVIEW", "VALIDATION_UNAVAILABLE"] as const;
export type ReadinessState = (typeof STATES)[number];
const VALIDATION_STATUSES = ["ok", "not_called", "validation_unavailable", "invalid_request"] as const;
const SEVERITIES = ["blocking", "advisory"] as const;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

export const isRequestId = (v: unknown): v is string => typeof v === "string" && UUID.test(v);

export const RECOMMENDATION_BASES = ["approved_claim", "required_disclaimer", "contextual_rewrite"] as const;

// Advisory guidance on one blocking finding. It is never approval and never a state. approved_claim and
// required_disclaimer are exact governed text from the claim validator and must name their source;
// contextual_rewrite is a reviewer suggestion and is never presented as approved wording.
export interface Recommendation {
  suggested_revision: string;
  reason: string;
  recommendation_basis: (typeof RECOMMENDATION_BASES)[number];
  original_text?: string;
  source_reference?: string;
  human_review_required: true;
}

export interface Finding {
  type: string;
  severity: (typeof SEVERITIES)[number];
  quote: string;
  issue: string;
  suggestion: string;
  recommendation?: Recommendation;
}

export interface ReadinessResult {
  schema_version: "1";
  request_id: string;
  status: ReadinessState;
  checked_at: string;
  summary: string;
  validation_status: (typeof VALIDATION_STATUSES)[number];
  formal_review_required: true;
  findings: Finding[];
}

export type Checked<T> = { ok: true; value: T } | { ok: false; code: string; message: string };
const no = (code: string, message: string): { ok: false; code: string; message: string } => ({ ok: false, code, message });

const clip = (v: unknown, max: number) => (typeof v === "string" && v.length <= max ? v : null);

function checkRecommendation(raw: unknown): Checked<Recommendation> {
  let r: unknown = raw;
  if (typeof raw === "string") {
    try {
      r = JSON.parse(raw);
    } catch {
      return no("invalid_recommendation", "A recommendation was not valid JSON.");
    }
  }
  if (typeof r !== "object" || r === null || Array.isArray(r)) return no("invalid_recommendation", "A recommendation must be an object.");
  const o = r as Record<string, unknown>;
  const revised = clip(o.suggested_revision, 700);
  const reason = clip(o.reason, 400);
  const original = clip(o.original_text ?? "", 500);
  const source = clip(o.source_reference ?? "", 80);
  if (!revised || revised.trim() === "" || !reason || original === null || source === null) return no("invalid_recommendation", "A recommendation needs a suggested_revision and a reason, with optional original_text and source_reference within length limits.");
  if (typeof o.recommendation_basis !== "string" || !(RECOMMENDATION_BASES as readonly string[]).includes(o.recommendation_basis)) return no("invalid_recommendation", `recommendation_basis must be one of ${RECOMMENDATION_BASES.join(", ")}.`);
  const basis = o.recommendation_basis as Recommendation["recommendation_basis"];
  // Governed wording must say where it came from. Without a source it cannot be called governed.
  if (basis !== "contextual_rewrite" && source.trim() === "") return no("invalid_recommendation", "approved_claim and required_disclaimer recommendations must name their source_reference.");
  if (!(o.human_review_required === true || o.human_review_required === "true")) return no("invalid_recommendation", "human_review_required must be true. A recommendation is never approval.");
  const value: Recommendation = { suggested_revision: revised, reason, recommendation_basis: basis, human_review_required: true };
  if (original.trim() !== "") value.original_text = original;
  if (source.trim() !== "") value.source_reference = source;
  return { ok: true, value };
}

// Optimizely AI may send arrays as JSON text and booleans as strings. Accept both, nothing else.
function asArray(v: unknown): unknown[] | null {
  if (Array.isArray(v)) return v;
  if (typeof v === "string") {
    try {
      const p = JSON.parse(v);
      return Array.isArray(p) ? p : null;
    } catch {
      return null;
    }
  }
  return null;
}

// Validates what the workflow reports. Accepts the Optimizely AI parameters envelope.
export function parseSubmission(body: unknown): Checked<ReadinessResult> {
  const raw = typeof body === "object" && body !== null && "parameters" in body ? (body as { parameters: unknown }).parameters : body;
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return no("invalid_body", "Body must be a JSON object.");
  const b = raw as Record<string, unknown>;

  if (!isRequestId(b.request_id)) return no("invalid_request_id", "request_id must be a UUID issued by the gateway.");
  if (typeof b.status !== "string" || !(STATES as readonly string[]).includes(b.status)) return no("invalid_status", `status must be one of ${STATES.join(", ")}.`);
  const summary = clip(b.summary, 500);
  if (summary === null || summary.trim() === "") return no("invalid_summary", "summary is required, up to 500 characters.");
  if (typeof b.validation_status !== "string" || !(VALIDATION_STATUSES as readonly string[]).includes(b.validation_status)) return no("invalid_validation_status", `validation_status must be one of ${VALIDATION_STATUSES.join(", ")}.`);
  if (!(b.formal_review_required === true || b.formal_review_required === "true")) return no("invalid_formal_review_required", "formal_review_required must be true. Nothing here removes formal review.");
  if (typeof b.checked_at !== "string" || Number.isNaN(Date.parse(b.checked_at))) return no("invalid_checked_at", "checked_at must be an ISO 8601 time.");

  const list = asArray(b.findings ?? []);
  if (list === null) return no("invalid_findings", "findings must be an array.");
  if (list.length > 50) return no("invalid_findings", "At most 50 findings.");
  const findings: Finding[] = [];
  for (const item of list) {
    // Optimizely AI serializes array items as text, so an item may arrive as a JSON string. Valid JSON objects only.
    let f: unknown = item;
    if (typeof item === "string") {
      try {
        f = JSON.parse(item);
      } catch {
        return no("invalid_findings", "A finding was not valid JSON.");
      }
    }
    if (typeof f !== "object" || f === null || Array.isArray(f)) return no("invalid_findings", "Each finding must be an object.");
    const o = f as Record<string, unknown>;
    const type = clip(o.type, 40);
    const quote = clip(o.quote ?? "", 500);
    const issue = clip(o.issue, 700);
    const suggestion = clip(o.suggestion ?? "", 700);
    if (!type || quote === null || !issue || suggestion === null) return no("invalid_findings", "A finding needs type, issue, and optional quote and suggestion within length limits.");
    if (typeof o.severity !== "string" || !(SEVERITIES as readonly string[]).includes(o.severity)) return no("invalid_findings", "severity must be blocking or advisory.");
    const finding: Finding = { type, severity: o.severity as Finding["severity"], quote, issue, suggestion };
    if (o.recommendation !== undefined && o.recommendation !== null) {
      const r = checkRecommendation(o.recommendation);
      if (!r.ok) return r;
      if (finding.severity !== "blocking" || b.status !== "NEEDS_REVISION") return no("inconsistent_result", "A recommendation can only accompany a blocking finding of a NEEDS_REVISION result.");
      finding.recommendation = r.value;
    }
    findings.push(finding);
  }

  // The state and the findings must agree. A ready draft carries no blocking finding.
  if (b.status === "READY_FOR_FORMAL_REVIEW" && findings.some((f) => f.severity === "blocking")) return no("inconsistent_result", "READY_FOR_FORMAL_REVIEW cannot carry a blocking finding.");

  return {
    ok: true,
    value: {
      schema_version: "1",
      request_id: b.request_id,
      status: b.status as ReadinessState,
      checked_at: new Date(b.checked_at).toISOString(),
      summary,
      validation_status: b.validation_status as ReadinessResult["validation_status"],
      formal_review_required: true,
      findings,
    },
  };
}

// ---------------------------------------------------------------------------------------------
// Temporary result store. Keyed by request_id. Stores only the normalized result, never the draft.
// File-backed so it survives a dev-server restart. On a serverless host the filesystem is per
// instance and not durable, so a shared store must replace this behind the same interface.

export const RESULT_TTL_MS = 24 * 60 * 60 * 1000;

export type StoredRecord =
  | { request_id: string; state: "PROCESSING"; created_at: string; expires_at: string; idempotency_hash: string | null }
  | { request_id: string; state: "COMPLETE"; created_at: string; expires_at: string; idempotency_hash: string | null; result: ReadinessResult };

export interface ResultStore {
  // Resolves with the original request id when a concurrent identical request already holds the idempotency key.
  createPending(r: { request_id: string; idempotency_hash: string | null }, now?: number): Promise<void | { duplicate_of: string }>;
  get(request_id: string): Promise<StoredRecord | null>;
  findByIdempotency(hash: string): Promise<string | null>;
  complete(result: ReadinessResult, now?: number): Promise<"stored" | "duplicate" | "conflict" | "unknown" | "expired">;
  discard(request_id: string): Promise<void>;
}

export function idempotencyHash(key: string, draft: string, market: string, audience: string): string {
  // The draft is hashed, never stored, so the same revision with different content is a different request.
  return createHash("sha256").update(`${key}\n${market}\n${audience}\n${createHash("sha256").update(draft).digest("hex")}`).digest("hex");
}

// A re-run of the same workflow step stamps a new checked_at. Everything else must match, or it is a different result.
const sameResult = (a: ReadinessResult, b: ReadinessResult) => JSON.stringify({ ...a, checked_at: "" }) === JSON.stringify({ ...b, checked_at: "" });

export function fileStore(dir = process.env.READINESS_STORE_DIR || path.join(os.tmpdir(), "fde-readiness-results")): ResultStore {
  const rec = (id: string) => path.join(dir, `${id}.json`);
  const idx = (h: string) => path.join(dir, `idx-${h}.json`);
  const read = async (p: string) => {
    try {
      return JSON.parse(await fs.readFile(p, "utf8"));
    } catch (e) {
      if ((e as NodeJS.ErrnoException).code === "ENOENT") return null;
      throw e;
    }
  };
  const write = async (p: string, v: unknown) => {
    await fs.mkdir(dir, { recursive: true });
    const tmp = `${p}.${process.pid}.tmp`;
    await fs.writeFile(tmp, JSON.stringify(v), { mode: 0o600 });
    await fs.rename(tmp, p);
  };
  // Records are removed one TTL after they expire. Between expiry and removal a lookup says "expired".
  const purge = async (now: number) => {
    let names: string[] = [];
    try {
      names = await fs.readdir(dir);
    } catch {
      return;
    }
    for (const n of names) {
      if (!n.endsWith(".json") || n.startsWith("idx-")) continue;
      const r = (await read(path.join(dir, n))) as StoredRecord | null;
      if (r && Date.parse(r.expires_at) + RESULT_TTL_MS < now) {
        await fs.rm(path.join(dir, n), { force: true });
        if (r.idempotency_hash) await fs.rm(idx(r.idempotency_hash), { force: true });
      }
    }
  };
  return {
    async createPending({ request_id, idempotency_hash }, now = Date.now()) {
      await purge(now);
      const record: StoredRecord = { request_id, state: "PROCESSING", created_at: new Date(now).toISOString(), expires_at: new Date(now + RESULT_TTL_MS).toISOString(), idempotency_hash };
      await write(rec(request_id), record);
      if (idempotency_hash) await write(idx(idempotency_hash), { request_id });
    },
    async get(request_id) {
      return (await read(rec(request_id))) as StoredRecord | null;
    },
    async findByIdempotency(hash) {
      const i = (await read(idx(hash))) as { request_id: string } | null;
      if (!i) return null;
      const r = (await read(rec(i.request_id))) as StoredRecord | null;
      return r && Date.parse(r.expires_at) > Date.now() ? i.request_id : null;
    },
    async complete(result, now = Date.now()) {
      const cur = (await read(rec(result.request_id))) as StoredRecord | null;
      if (!cur) return "unknown";
      if (Date.parse(cur.expires_at) <= now) return "expired";
      // A retried delivery can repeat a write that already landed. The same result is success; a different one is never applied.
      if (cur.state === "COMPLETE") return sameResult(cur.result, result) ? "duplicate" : "conflict";
      await write(rec(result.request_id), { ...cur, state: "COMPLETE", result });
      return "stored";
    },
    async discard(request_id) {
      const cur = (await read(rec(request_id))) as StoredRecord | null;
      await fs.rm(rec(request_id), { force: true });
      if (cur?.idempotency_hash) await fs.rm(idx(cur.idempotency_hash), { force: true });
    },
  };
}

// ---------------------------------------------------------------------------------------------
// Shared store on Vercel Blob (private). The Blob client is injected so tests need no Vercel account.
// Atomicity comes from two Blob features: a put without allowOverwrite fails if the path exists
// (create-if-absent), and a put with ifMatch fails unless the ETag is unchanged (compare-and-swap).
// Not exactly-once processing: a caller can still send two different requests. What is guaranteed is that one
// request id is completed at most once and one idempotency key maps to one request id.

export interface BlobClient {
  // Rejects with { kind: "exists" } when the path exists and overwrite was not allowed.
  put(path: string, body: string, opts: { overwrite?: boolean; ifMatch?: string }): Promise<{ etag: string }>;
  // Always reads fresh from origin, never from a CDN cache.
  get(path: string): Promise<{ etag: string; text: string } | null>;
  del(paths: string[]): Promise<void>;
  list(prefix: string, limit: number): Promise<{ pathname: string; uploadedAt: number }[]>;
}

export class BlobConflict extends Error {
  constructor(readonly kind: "exists" | "stale") {
    super(kind);
  }
}

export function blobStore(client: BlobClient, prefix = "readiness"): ResultStore {
  const rec = (id: string) => `${prefix}/${id}.json`;
  const idx = (h: string) => `${prefix}/idx/${h}.json`;
  const parse = <T>(r: { text: string } | null) => (r ? (JSON.parse(r.text) as T) : null);

  // Records are removed one TTL after they expire. Best effort, never blocks a request.
  async function purge(now: number) {
    try {
      const old = (await client.list(`${prefix}/`, 200)).filter((b) => b.uploadedAt + 2 * RESULT_TTL_MS < now).map((b) => b.pathname);
      if (old.length) await client.del(old);
    } catch {
      /* cleanup only */
    }
  }

  const live = (r: StoredRecord | null, now: number) => (r && Date.parse(r.expires_at) > now ? r : null);

  return {
    async createPending({ request_id, idempotency_hash }, now = Date.now()) {
      await purge(now);
      const record: StoredRecord = { request_id, state: "PROCESSING", created_at: new Date(now).toISOString(), expires_at: new Date(now + RESULT_TTL_MS).toISOString(), idempotency_hash };
      if (idempotency_hash) {
        try {
          await client.put(idx(idempotency_hash), JSON.stringify({ request_id }), {});
        } catch (e) {
          if (!(e instanceof BlobConflict) || e.kind !== "exists") throw e;
          // Someone holds the key. If their request is still live this is a duplicate. If it has expired, take the key over.
          const held = await client.get(idx(idempotency_hash));
          const other = held ? parse<{ request_id: string }>(held)!.request_id : null;
          const otherRec = other ? live(parse<StoredRecord>(await client.get(rec(other))), now) : null;
          if (otherRec) return { duplicate_of: otherRec.request_id };
          try {
            await client.put(idx(idempotency_hash), JSON.stringify({ request_id }), { ifMatch: held?.etag });
          } catch (e2) {
            if (e2 instanceof BlobConflict) return { duplicate_of: other ?? request_id };
            throw e2;
          }
        }
      }
      try {
        await client.put(rec(request_id), JSON.stringify(record), {});
      } catch (e) {
        if (idempotency_hash) await client.del([idx(idempotency_hash)]).catch(() => undefined);
        throw e;
      }
    },
    async get(request_id) {
      return parse<StoredRecord>(await client.get(rec(request_id)));
    },
    async findByIdempotency(hash) {
      const held = parse<{ request_id: string }>(await client.get(idx(hash)));
      if (!held) return null;
      return live(parse<StoredRecord>(await client.get(rec(held.request_id))), Date.now())?.request_id ?? null;
    },
    async complete(result, now = Date.now()) {
      // Compare-and-swap: re-read and retry if another writer changed the record between our read and write.
      for (let attempt = 0; attempt < 4; attempt++) {
        const read = await client.get(rec(result.request_id));
        const cur = parse<StoredRecord>(read);
        if (!read || !cur) return "unknown";
        if (Date.parse(cur.expires_at) <= now) return "expired";
        if (cur.state === "COMPLETE") return sameResult(cur.result, result) ? "duplicate" : "conflict";
        try {
          await client.put(rec(result.request_id), JSON.stringify({ ...cur, state: "COMPLETE", result }), { overwrite: true, ifMatch: read.etag });
          return "stored";
        } catch (e) {
          if (!(e instanceof BlobConflict)) throw e;
        }
      }
      throw new Error("result_store_contended");
    },
    async discard(request_id) {
      const cur = parse<StoredRecord>(await client.get(rec(request_id)));
      await client.del([rec(request_id), ...(cur?.idempotency_hash ? [idx(cur.idempotency_hash)] : [])]);
    },
  };
}

// What GET /fde-opti/readiness/{id} says for a stored record. Pure, so it can be tested.
export function describeRecord(rec: StoredRecord | null, now = Date.now()): { http: number; body: Record<string, unknown> } {
  if (!rec) return { http: 404, body: { error: { code: "not_found", message: "No such request." } } };
  if (Date.parse(rec.expires_at) <= now) return { http: 410, body: { error: { code: "expired", message: "This result has expired. Submit the content again." } } };
  if (rec.state === "PROCESSING") return { http: 202, body: { state: "PROCESSING" } };
  return { http: 200, body: rec.result as unknown as Record<string, unknown> };
}

// ---------------------------------------------------------------------------------------------
// Callback tool manifest, registered in the same Optimizely AI registry as validate_approved_claim.
export const CALLBACK_ENDPOINT = "/fde-opti/tools/submit-readiness-result";

export const CALLBACK_DISCOVERY = {
  functions: [
    {
      name: "submit_readiness_result",
      description:
        "Reports one finished readiness result back to the readiness service so the requesting system can retrieve it. Call it exactly once, after the readiness decision, and only when a request_id was supplied. Pass every value exactly as given by the Result Packager step: do not edit, summarize or add to any field, and never include draft text. It stores the result and returns ok or an error. It does not decide readiness, approve content or publish anything.",
      parameters: [
        { name: "request_id", type: "string", description: "The request_id supplied with the request, exactly as given.", required: true },
        { name: "status", type: "string", description: "The readiness state exactly as given: INPUT_REQUIRED, NEEDS_REVISION, READY_FOR_FORMAL_REVIEW or VALIDATION_UNAVAILABLE.", required: true },
        { name: "summary", type: "string", description: "One-sentence summary exactly as given.", required: true },
        { name: "validation_status", type: "string", description: "ok, not_called, validation_unavailable or invalid_request, exactly as given.", required: true },
        { name: "formal_review_required", type: "boolean", description: "Always true.", required: true },
        { name: "checked_at", type: "string", description: "ISO 8601 time of the check, exactly as given.", required: true },
        { name: "findings", type: "array", description: "The findings exactly as given. Each is an object with type, severity (blocking or advisory), quote, issue and suggestion, and optionally a recommendation object (suggested_revision, reason, recommendation_basis, original_text, source_reference, human_review_required). Pass any recommendation unchanged.", required: true },
      ],
      endpoint: CALLBACK_ENDPOINT,
      http_method: "POST",
    },
  ],
};
