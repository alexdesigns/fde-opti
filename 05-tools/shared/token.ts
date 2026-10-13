// Bearer token check shared by both tools.

// Constant-time comparison without a Node-only dependency.
export function tokenMatches(presented: string | null, expected: string | undefined): boolean {
  if (!expected || !presented) return false;
  const m = /^Bearer (.+)$/.exec(presented);
  if (!m) return false;
  const a = new TextEncoder().encode(m[1]);
  const e = new TextEncoder().encode(expected);
  let diff = a.length ^ e.length;
  for (let i = 0; i < Math.max(a.length, e.length); i++) diff |= (a[i] ?? 0) ^ (e[i] ?? 0);
  return diff === 0;
}
