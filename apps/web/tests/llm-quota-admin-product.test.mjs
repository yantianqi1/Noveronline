import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

const root = path.resolve(import.meta.dirname, "..");
const read = (file) => readFile(path.join(root, file), "utf8");

test("LLM quota admin uses a standalone client and route", async () => {
  const [client, page] = await Promise.all([
    read("lib/llm-admin-api.ts"),
    read("app/(app)/[tenantSlug]/projects/[projectId]/llm-facility/quotas/page.tsx"),
  ]);
  assert.doesNotMatch(client, /from ["']\.\/api["']/);
  for (const endpoint of ["policies", "resolution", "reservations", "reconciliation", "provider-health"]) {
    assert.match(client, new RegExp(`/v1/llm-admin/${endpoint}`));
  }
  assert.match(client, /expected_version/);
  assert.match(client, /pricing_status/);
  assert.match(page, /createQuotaPolicy/);
  assert.match(page, /updateQuotaPolicy/);
  assert.match(page, /deleteQuotaPolicy/);
  assert.match(page, /checkProviderHealth/);
});

test("LLM quota admin renders resolution, all reservation states, reconciliation, and explicit unavailable pricing", async () => {
  const shell = await read("components/llm-quota-admin-shell.tsx");
  assert.match(shell, /Module → Project → Workspace/);
  for (const status of ["reserved", "finalized", "released", "expired"]) {
    assert.match(shell, new RegExp(`value=\\"${status}\\"`));
  }
  assert.match(shell, /actual_cost_micros \?\?/);
  assert.match(shell, /unavailable/);
  assert.match(shell, /billing_status/);
  assert.match(shell, /provider_call_id/);
  assert.match(shell, /expectedVersion/);
});

test("LLM admin public surface never accepts or renders credentials and provider request content", async () => {
  const files = await Promise.all([
    read("lib/llm-admin-api.ts"),
    read("components/llm-quota-admin-shell.tsx"),
    read("app/(app)/[tenantSlug]/projects/[projectId]/llm-facility/quotas/page.tsx"),
  ]);
  const source = files.join("\n").toLowerCase();
  for (const forbidden of ["api" + "_key", "encrypted" + "_api", "request" + "_body", "response" + "_body", "prompt_text"]) {
    assert.doesNotMatch(source, new RegExp(forbidden));
  }
  assert.doesNotMatch(source, /console\.(log|error|warn)/);
  assert.match(source, /channel_id/);
  assert.match(source, /model_id/);
  assert.match(source, /latency_ms/);
  assert.match(source, /supports_tools/);
  assert.match(source, /supports_json/);
});
