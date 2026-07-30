import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

/**
 * Module display-metadata contract.
 *
 * The settings surface translates and grades every LLM module on the frontend
 * (lib/api/llm-module-meta.ts) because the Go registry ships English labels and
 * has no capability tiers. The risk that quietly breaks the page is coverage:
 * the registry adds a module upstream, the table isn't updated, and that module
 * renders as its raw key in the middle "standard" tier. These assertions read
 * both sources and cross-check them so a missing translation fails loudly.
 *
 * Follows the same read-source-and-assert shape as design-tokens.test.mjs — no
 * new dependencies, run with `node --test`.
 */

const root = path.resolve(import.meta.dirname, "..");
const repoRoot = path.resolve(root, "../..");

async function source(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

/** ModuleKeys the Go registry emits, in registry order. */
async function registryModuleKeys() {
  const go = await readFile(path.join(repoRoot, "apps/api/internal/llm/registry.go"), "utf8");
  const keys = [...go.matchAll(/ModuleKey:\s*"([a-z0-9_]+)"/g)].map((m) => m[1]);
  return [...new Set(keys)];
}

test("every registry module has a Chinese translation + a valid tier", async () => {
  const meta = await source("lib/api/llm-module-meta.ts");
  const keys = await registryModuleKeys();
  assert.ok(keys.length > 0, "registry.go should declare at least one module");

  for (const key of keys) {
    // The entry exists with a Chinese label, a Chinese description and a tier.
    const entry = new RegExp(
      `${key}:\\s*\\{\\s*tier:\\s*"(heavy|high|standard|light)",\\s*labelZh:\\s*"([^"]+)",\\s*descZh:\\s*"([^"]+)"`,
    );
    const m = meta.match(entry);
    assert.ok(m, `module "${key}" is missing a MODULE_META entry (translate + grade it)`);
    assert.match(m[2], /[一-鿿]/, `module "${key}" labelZh should be Chinese, got "${m[2]}"`);
    assert.match(m[3], /[一-鿿]/, `module "${key}" descZh should be Chinese, got "${m[3]}"`);
  }
});

test("TIER_ORDER declares exactly the four tiers, heaviest workload first", async () => {
  const meta = await source("lib/api/llm-module-meta.ts");
  const block = meta.match(/TIER_ORDER[^=]*=\s*\[([\s\S]*?)\];/);
  assert.ok(block, "TIER_ORDER should be exported from llm-module-meta.ts");
  const tiers = [...block[1].matchAll(/key:\s*"(heavy|high|standard|light)"/g)].map((m) => m[1]);
  assert.deepEqual(tiers, ["heavy", "high", "standard", "light"]);
});

test("llm.ts exposes both grouping dimensions and tags tier groups", async () => {
  const llm = await source("lib/api/llm.ts");
  assert.match(llm, /export function groupModules\(/, "groupModules (by family) should remain");
  assert.match(llm, /export function groupModulesByTier\(/, "groupModulesByTier should exist");
  assert.match(llm, /tier\?:\s*CapabilityTier/, "ModuleGroup should carry an optional tier");
});

test("the settings workspace wires the view-mode toggle to the grouping", async () => {
  const ws = await source("app/projects/[projectId]/settings/settings-workspace.tsx");
  assert.match(ws, /ViewModeToggle/, "settings workspace should render the view-mode toggle");
  assert.match(ws, /groupModulesByTier/, "settings workspace should group by tier in tier mode");
  assert.match(ws, /handleViewModeChange/, "switching views should reset the active group");
});
