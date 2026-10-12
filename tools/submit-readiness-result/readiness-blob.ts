// Real Vercel Blob client for the shared readiness result store. Server only. Kept apart from readiness-result.ts
// so unit tests, which use an in-memory client, never import the SDK.
import { BlobPreconditionFailedError, del, get, list, put } from "@vercel/blob";
import { BlobConflict, type BlobClient } from "./readiness-result";

const isExists = (e: unknown) => e instanceof Error && /already exists/i.test(e.message);

export function vercelBlobClient(): BlobClient {
  return {
    async put(path, body, opts) {
      try {
        const r = await put(path, body, {
          access: "private",
          contentType: "application/json",
          addRandomSuffix: false,
          ...(opts.ifMatch ? { ifMatch: opts.ifMatch, allowOverwrite: true } : { allowOverwrite: !!opts.overwrite }),
        });
        return { etag: r.etag };
      } catch (e) {
        if (e instanceof BlobPreconditionFailedError) throw new BlobConflict("stale");
        if (isExists(e)) throw new BlobConflict("exists");
        throw e;
      }
    },
    async get(path) {
      const r = await get(path, { access: "private", useCache: false });
      if (!r || r.statusCode !== 200) return null;
      return { etag: r.blob.etag, text: await new Response(r.stream).text() };
    },
    async del(paths) {
      await del(paths);
    },
    async list(prefix, limit) {
      const r = await list({ prefix, limit });
      return r.blobs.map((b) => ({ pathname: b.pathname, uploadedAt: b.uploadedAt.getTime() }));
    },
  };
}
