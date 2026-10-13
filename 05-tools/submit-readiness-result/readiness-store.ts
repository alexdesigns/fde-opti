// Chooses the result store. Production and preview use the private Vercel Blob store. Local runs without a Blob token
// use the file store. The path prefix includes the Vercel environment so local runs never touch production records.
import { blobStore, fileStore, type ResultStore } from "./readiness-result";
import { vercelBlobClient } from "./readiness-blob";

export function resultStore(): ResultStore {
  if (process.env.BLOB_READ_WRITE_TOKEN) return blobStore(vercelBlobClient(), `readiness-${process.env.VERCEL_ENV ?? "local"}`);
  return fileStore();
}
