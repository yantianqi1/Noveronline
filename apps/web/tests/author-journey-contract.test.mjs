import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");
const source = (name) => readFile(path.join(root, name), "utf8");

test("author journey live harness and browser test cover full handoff contract", async () => {
  const [harness, live, migration] = await Promise.all([
    source("tests/author-journey-live-harness.mjs"),
    source("tests/author-journey-browser-live.test.mjs"),
    readFile(path.join(root, "../../infra/postgres/migrations/0017_llm_quota_tenant_backfill.sql"), "utf8"),
  ]);
  assert.match(harness, /submitServerAction/);
  assert.match(harness, /COMPLETE_JOURNEY/);
  assert.match(live, /Enter Character Console/);
  assert.match(live, /View in Writer/);
  assert.match(live, /Adopt draft into manuscript/);
  assert.match(live, /Generate TXT artifact/);
  assert.match(live, /prepare_id/);
  assert.doesNotMatch(live, /page\.goto\(projectUrl\(config, auth, "writer"\)/);
  assert.match(migration, /INSERT INTO llm_quota_policies/);
  assert.match(migration, /scope_type = 'tenant'/);
});

test("writer workbench shell no longer exposes manual saved path id entry", async () => {
  const shell = await source("components/writer-workbench-shell.tsx");
  assert.match(shell, /name="worldlinePathIds" type="checkbox"/);
  assert.doesNotMatch(shell, /Manual saved path IDs/);
  assert.doesNotMatch(shell, /worldline-path-ids/);
  assert.doesNotMatch(shell, /path_1, path_2/);
});