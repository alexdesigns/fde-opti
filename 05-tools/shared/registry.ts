// The Regulated Content registry: one Optimizely AI tool registry, one bearer token, two tools.
// Each tool still enforces its own input, state and write boundaries; the token only authenticates the caller.
import { CALLBACK_DISCOVERY } from "../submit-readiness-result/readiness-result";
import { tokenMatches } from "./token";
import { DISCOVERY as VALIDATOR_DISCOVERY } from "../validate-approved-claim/validate";

export const REGISTRY_DISCOVERY = {
  functions: [...VALIDATOR_DISCOVERY.functions, ...CALLBACK_DISCOVERY.functions],
};

export type RegistryAuth = "ok" | "not_configured" | "unauthorized";

// Fails closed: a missing token never means open.
export function registryAuth(authorization: string | null, env: Record<string, string | undefined> = process.env): RegistryAuth {
  const expected = env.OPTITHERA_REGULATED_REGISTRY_TOKEN;
  if (!expected) return "not_configured";
  return tokenMatches(authorization, expected) ? "ok" : "unauthorized";
}
