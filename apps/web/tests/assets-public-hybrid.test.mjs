import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");

test("asset browser keeps ranking diagnostics out of the author UI while preserving server-driven search", async () => {
  const shell = await readFile(path.join(root, "components/asset-library-shell.tsx"), "utf8");
  const page = await readFile(path.join(root, "app/(app)/[tenantSlug]/projects/[projectId]/assets/page.tsx"), "utf8");
  const provider = await readFile(path.join(root, "scripts/assets-live-embedding-provider.mjs"), "utf8");
  const fixture = await readFile(path.join(root, "scripts/prepare-live-assets-fixture.mjs"), "utf8");

  assert.match(shell, /name="mode"/);
  assert.match(shell, /value="keyword"/);
  assert.match(shell, /value="vector"/);
  assert.match(shell, /value="hybrid"/);
  assert.doesNotMatch(shell, /ranking\.(?:final_score|keyword_score|vector_score|embedding_model|keyword_contribution|vector_contribution|recency_boost|lifecycle_boost|pinned_boost|explanation)/);
  assert.doesNotMatch(shell, /formatScore|raw relevance|keyword contribution|vector contribution|boosts/);
  for (const filter of ["assetType", "category", "lifecycle", "source", "tag", "pinned"]) {
    assert.match(shell, new RegExp(`name=["']${filter}["']`));
    assert.match(page, new RegExp(`setOptionalQuery\\(nextQuery, ["']${filter}["']`));
  }
  assert.match(page, /compactSearchFilters\(searchFilters\)/);
  assert.match(page, /baseAssetQuery\(searchState\)/);
  assert.match(page, /reindexRunId/);
  assert.match(shell, /getWorkflowRunSummary|ReindexRunStatus/);
  const reindexForm = shell.slice(shell.indexOf("function ReindexAssetsForm"), shell.indexOf("function ReindexRunStatus"));
  assert.doesNotMatch(reindexForm, /<option value="tenant">/);
  assert.match(reindexForm, /<option[^>]*value="vector"/);
  assert.match(reindexForm, /SearchModeSelect/);
  assert.match(reindexForm, /disabled=\{!vectorEnabled\}/);

  for (const forbidden of [
    /name="(?:queryEmbedding|embedding|vector)"/i,
    /name="(?:modelId|channelId|credential|apiKey)"/i,
  ]) {
    assert.doesNotMatch(shell, forbidden);
  }
  assert.match(provider, /MIROFISH_ASSETS_LOCAL_PROVIDER_KEY is required/);
  assert.match(fixture, /required\("PROVIDER_KEY"\)/);
  assert.doesNotMatch(`${provider}\n${fixture}`, /asset-local-provider-key|sk-[A-Za-z0-9_-]{8,}/);
});
