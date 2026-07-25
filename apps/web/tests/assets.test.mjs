import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");

async function source(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

test("asset library workbench is routed and wired to real backend routes", async () => {
  const sectionPage = await source("app/projects/[projectId]/[section]/page.tsx");
  assert.match(sectionPage, /AssetWorkspace/);
  assert.match(sectionPage, /section === "assets"/);

  const workspace = await source("app/projects/[projectId]/assets/asset-workspace.tsx");
  // Reads the unified asset model + catalog through the real client.
  assert.match(workspace, /fetchAssets/);
  assert.match(workspace, /fetchCatalogAsset/);
  assert.match(workspace, /adoptAsset/);
  assert.match(workspace, /restoreAssetVersion/);

  const client = await source("lib/api/asset-client.ts");
  // BFF paths the Go API actually serves (see internal/httpapi + assetcatalog).
  assert.match(client, /\/assets\/facets/);
  assert.match(client, /\/assets\/search-capabilities/);
  assert.match(client, /asset-catalog\/assets\//);
  assert.match(client, /asset-catalog\/collections/);
  assert.match(client, /\/adoptions/);
  // Optimistic-lock + idempotency discipline for catalog mutations.
  assert.match(client, /expected_version/);
  assert.match(client, /X-Request-Id/);
  // The list endpoint paginates; fetchAssets walks offset pages until done.
  assert.match(client, /ASSET_PAGE_SIZE/);
  assert.match(client, /offset=\$\{offset\}/);
  assert.match(client, /has_more/);
  assert.match(client, /next_offset/);
});

test("asset library BFF proxy allowlists only the real asset routes", async () => {
  const route = await source("app/api/projects/[projectId]/[...path]/route.ts");
  // Project-prefixed reads/writes.
  assert.match(route, /asset-catalog\\\/assets/);
  assert.match(route, /asset-catalog\\\/collections/);
  assert.match(route, /assets\\\/facets/);
  assert.match(route, /assets\\\/search-capabilities/);
  // Top-level translation for asset detail/adoption + cross-entity search.
  assert.match(route, /\/v1\/assets\/search/);
  assert.match(route, /project_id: projectId/);
});

test("asset library fabricates no domain data", async () => {
  const files = [
    "app/projects/[projectId]/assets/asset-workspace.tsx",
    "app/projects/[projectId]/assets/asset-list.tsx",
    "app/projects/[projectId]/assets/asset-inspector.tsx",
    "app/projects/[projectId]/assets/asset-filter-bar.tsx",
    "app/projects/[projectId]/assets/asset-collections-rail.tsx",
  ];
  for (const file of files) {
    const text = await source(file);
    // No hard-coded story entities, mock fixtures, or lorem placeholders.
    assert.doesNotMatch(text, /mock|fixture|lorem|苍兰诀|示例角色|占位资产/i, `${file} must not fabricate data`);
  }
});
