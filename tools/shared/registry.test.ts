import * as assert from "node:assert/strict";
import { test } from "node:test";
import { REGISTRY_DISCOVERY, registryAuth } from "./registry";

const T = "reg-token-for-tests";

test("one registry lists exactly the two regulated content tools", () => {
  assert.deepEqual(REGISTRY_DISCOVERY.functions.map((f) => f.name), ["validate_approved_claim", "submit_readiness_result"]);
  assert.ok(REGISTRY_DISCOVERY.functions.every((f) => f.http_method === "POST" && f.endpoint.startsWith("/fde-opti/tools/")));
});

test("registry auth fails closed when no token is configured", () => {
  assert.equal(registryAuth(`Bearer ${T}`, {}), "not_configured");
  assert.equal(registryAuth(null, {}), "not_configured");
});

test("registry auth accepts only the exact bearer token", () => {
  const env = { OPTITHERA_REGULATED_REGISTRY_TOKEN: T };
  assert.equal(registryAuth(`Bearer ${T}`, env), "ok");
  for (const bad of [null, "", T, `Bearer ${T}x`, `Bearer ${T.slice(1)}`, "Bearer wrong", `Basic ${T}`]) {
    assert.equal(registryAuth(bad, env), "unauthorized", String(bad));
  }
});

test("other credentials do not open the registry", () => {
  const env = { OPTITHERA_REGULATED_REGISTRY_TOKEN: T, OTHER_SERVICE_TOKEN: "other-token", SECOND_SERVICE_TOKEN: "second-token" };
  for (const other of ["other-token", "second-token"]) assert.equal(registryAuth(`Bearer ${other}`, env), "unauthorized");
});
