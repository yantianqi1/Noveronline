import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const root = new URL("../", import.meta.url);
const file = (path) => readFile(new URL(path, root), "utf8");

test("asset detail uses an isolated client and route surface", async () => {
  const [page, client] = await Promise.all([file("app/(app)/[tenantSlug]/projects/[projectId]/assets/[assetId]/page.tsx"), file("lib/asset-detail-api.ts")]);
  assert.match(page, /asset-detail-api/);
  assert.doesNotMatch(page, /lib\/api/);
  assert.match(client, /asset-catalog\$\{path\}/);
  assert.match(client, /expected_version/);
  assert.match(client, /csrf-token/);
});

test("viewer DOM omits mutation and private content controls by capability", async () => {
  const shell = await file("components/asset-detail-shell.tsx");
  assert.match(shell, /asset\.capabilities\.mutate/);
  assert.match(shell, /asset\.capabilities\.read_private/);
  assert.match(shell, /asset\.capabilities\.manage_collections/);
  assert.match(shell, /Confirm restore/);
  assert.match(shell, /Move asset up/);
});

test("asset detail has stable responsive dimensions", async () => {
  const css = await file("components/asset-detail-shell.module.css");
  assert.match(css, /grid-template-columns:minmax\(0,1\.55fr\)/);
  assert.match(css, /@media\(max-width:850px\)/);
  assert.match(css, /@media\(max-width:430px\)/);
});
