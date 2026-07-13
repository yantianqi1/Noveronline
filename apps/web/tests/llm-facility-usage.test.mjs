import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

const root = path.resolve(import.meta.dirname, "..");

test("LLM Facility exposes auditable usage scope without inventing quota data", async () => {
  const shell = await readFile(path.join(root, "components/llm-facility-shell.tsx"), "utf8");

  assert.match(shell, /tenantSlug=\{tenantSlug\}/);
  assert.match(shell, /projectId=\{projectId\}/);
  assert.match(shell, /item\.module_key \|\| "-"/);
  assert.match(shell, /item\.run_id \|\| "-"/);
  assert.match(shell, /data-usage-status=\{telemetryStatus\}/);
  assert.match(shell, /data-quota-status=\{quotaStatus\}/);
  assert.match(shell, /zero_truth/);
  assert.match(shell, /Actual token usage is unavailable/);
  assert.match(shell, /Quota.*unavailable/s);
  assert.doesNotMatch(shell, /cost_estimate.*UsageTable|estimated cost|estimated usage/i);
});

test("LLM Facility keeps usage permission and activity errors on stable public codes", async () => {
  const shell = await readFile(path.join(root, "components/llm-facility-shell.tsx"), "utf8");

  assert.match(shell, /AUTH_ACCESS_DENIED/);
  assert.match(shell, /UNAUTHENTICATED/);
  assert.match(shell, /LLM_QUOTA_EXCEEDED/);
  assert.match(shell, /LLM_CONCURRENCY_LEASE_EXPIRED/);
  assert.match(shell, /safeActivityErrorCode\(item\.error\)/);
  assert.match(shell, /SAFE_ACTIVITY_ERROR_CODES\.has\(code\)/);
  assert.doesNotMatch(shell, /JSON\.stringify\(item\.error\)|usage\.message|activity\.message/);
});

test("LLM Facility manages persistent quota policies and external provider opt-in", async () => {
  const shell = await readFile(path.join(root, "components/llm-facility-shell.tsx"), "utf8");
  const page = await readFile(path.join(root, "app/(app)/[tenantSlug]/projects/[projectId]/llm-facility/page.tsx"), "utf8");

  for (const field of ["scopeType", "tokenLimit", "costLimitMicros", "concurrencyLimit", "periodSeconds"]) {
    assert.match(shell, new RegExp(`name=\\"${field}\\"`));
  }
  assert.match(shell, /tenant.*project.*module/s);
  assert.match(shell, /externalProviderOptIn/);
  assert.match(shell, /external_provider_opt_in/);
  assert.match(shell, /billing_ready/);
  assert.match(shell, /pricing_unavailable/);
  assert.match(page, /\/llm\/quota-policies/);
  assert.match(page, /\/llm\/billing-usage/);
  assert.match(page, /external_provider_opt_in/);
  assert.match(shell, /role=\{status === "error" \? "alert" : "status"\}/);
  assert.doesNotMatch(page, /api_key.*console|prompt.*console|response.*console/i);
});
