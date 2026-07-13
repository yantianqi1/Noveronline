import assert from "node:assert/strict";
import { spawn, spawnSync } from "node:child_process";
import { rmSync } from "node:fs";
import { fileURLToPath } from "node:url";
import test from "node:test";
import { chromium } from "@playwright/test";

import { disposableLiveDatabaseConfig } from "../scripts/live-test-database.mjs";

const enabled = process.env.MIROFISH_ASSET_DETAIL_BROWSER_LIVE === "1";
const liveDatabase = enabled ? disposableLiveDatabaseConfig() : null;
const composeFile = fileURLToPath(new URL("../../../infra/docker-compose.yml", import.meta.url));
const tenantA = "a1000000-0000-4000-8000-000000000001";
const tenantB = "a1000000-0000-4000-8000-000000000002";
const projectA = "a2000000-0000-4000-8000-000000000001";
const projectB = "a2000000-0000-4000-8000-000000000002";
const owner = "a3000000-0000-4000-8000-000000000001";
const viewer = "a3000000-0000-4000-8000-000000000002";
const assetA = "a4000000-0000-4000-8000-000000000001";
const assetA2 = "a4000000-0000-4000-8000-000000000002";
const assetB = "a4000000-0000-4000-8000-000000000003";
const apiBase = "http://127.0.0.1:4188";

test("detail update version restore collection refresh viewer isolation and responsive privacy", { skip: !enabled, timeout: 120_000 }, async () => {
  seed();
  const processes = [];
  const apiBinary = `/tmp/mirofish-assetcatalog-testserver-${process.pid}`;
  let browser;
  try {
    const build = spawnSync("go", ["build", "-o", apiBinary, "./internal/assetcatalog/cmd/testserver"], { cwd: new URL("../../api", import.meta.url), encoding: "utf8" });
    if (build.status !== 0) throw new Error(build.stderr);
    processes.push(spawn(apiBinary, [], { env: { ...process.env, DATABASE_URL: liveDatabase.runtimeUrl, ASSET_CATALOG_TEST_OWNER_ID: owner }, stdio: "inherit", detached: true }));
    const ownerWeb = startWeb(4200, owner);
    processes.push(ownerWeb);
    await Promise.all([waitFor(`${apiBase}/health`, [401]), waitFor("http://127.0.0.1:4200", [200, 307])]);

    browser = await chromium.launch({ headless: true });
    const ownerContext = await browser.newContext({ viewport: { width: 1440, height: 960 } });
    await ownerContext.addCookies([{ name: "mirofish_session", value: "owner", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
    const desktop = await ownerContext.newPage();
    const ownerURL = `http://127.0.0.1:4200/${tenantA}/projects/${projectA}/assets/${assetA}`;
    await desktop.goto(ownerURL, { waitUntil: "domcontentloaded" });
    await desktop.getByTestId("asset-detail-workspace").waitFor();
    await desktop.waitForTimeout(800);
    assert.match(await desktop.getByTestId("private-content").inputValue(), /private body v1/);

    await desktop.getByRole("textbox", { name: "Title", exact: true }).first().fill("Rule v2");
    await desktop.getByTestId("private-content").fill("private body v2");
    await Promise.all([desktop.waitForURL(/status=/), desktop.getByRole("button", { name: "Save new version" }).click()]);
    await desktop.reload({ waitUntil: "domcontentloaded" });
    await desktop.getByTestId("asset-detail-workspace").waitFor();
    assert.equal(await desktop.getByRole("textbox", { name: "Title", exact: true }).first().inputValue(), "Rule v2");
    assert.match(await desktop.getByTestId("version-timeline").textContent(), /v1/);

    await desktop.goto(ownerURL, { waitUntil: "domcontentloaded" });
    await desktop.getByText("Restore", { exact: true }).first().click();
    await desktop.getByLabel(/Create a new current version/).check();
    await Promise.all([desktop.waitForURL(/status=/), desktop.getByRole("button", { name: "Confirm restore" }).click()]);
    await desktop.reload({ waitUntil: "domcontentloaded" });
    await desktop.getByTestId("asset-detail-workspace").waitFor();
    assert.equal(await desktop.getByRole("textbox", { name: "Title", exact: true }).first().inputValue(), "Rule v1");
    assert.match(await desktop.locator("body").textContent(), /Current version\s*3/);

    await desktop.goto(ownerURL, { waitUntil: "domcontentloaded" });
    await desktop.getByText("New collection", { exact: true }).click();
    const collectionForm = desktop.locator("details").filter({ hasText: "New collection" }).locator("form");
    await collectionForm.locator('input[name="title"]').fill("Browser Set");
    const createResponsePromise = desktop.waitForResponse((response) =>
      response.request().method() === "POST" && response.url().startsWith(ownerURL),
    );
    await collectionForm.getByRole("button", { name: "Create" }).click();
    const createResponse = await createResponsePromise;
    assert.ok(createResponse.ok() || [303, 307, 308].includes(createResponse.status()), `collection action returned HTTP ${createResponse.status()}`);
    const headers = { "X-Tenant-Id": tenantA, "X-User-Id": owner, "Content-Type": "application/json" };
    const list = await desktop.request.get(`${apiBase}/v1/projects/${projectA}/asset-catalog/collections`, { headers });
    const collection = (await list.json()).collections.find((item) => item.title === "Browser Set");
    await desktop.request.put(`${apiBase}/v1/projects/${projectA}/asset-catalog/collections/${collection.collection_id}/items/${assetA}`, { headers, data: {} });
    await desktop.request.put(`${apiBase}/v1/projects/${projectA}/asset-catalog/collections/${collection.collection_id}/items/${assetA2}`, { headers, data: {} });
    await desktop.request.put(`${apiBase}/v1/projects/${projectA}/asset-catalog/collections/${collection.collection_id}/order`, { headers, data: { asset_ids: [assetA2, assetA] } });
    await desktop.goto(ownerURL, { waitUntil: "domcontentloaded" });
    assert.match(await desktop.getByTestId("collection-memberships").textContent(), /Browser Set/);
    await desktop.request.delete(`${apiBase}/v1/projects/${projectA}/asset-catalog/collections/${collection.collection_id}/items/${assetA}`, { headers });
    await desktop.reload({ waitUntil: "domcontentloaded" });
    assert.doesNotMatch(await desktop.getByTestId("collection-memberships").textContent(), /Browser Set/);

    try { ownerWeb.kill("SIGKILL"); } catch {}
    await new Promise((resolve) => setTimeout(resolve, 1000));
    const viewerWeb = startWeb(4201, viewer);
    processes.push(viewerWeb);
    await waitFor("http://127.0.0.1:4201", [200, 307]);
    const viewerContext = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await viewerContext.addCookies([{ name: "mirofish_session", value: "viewer", domain: "127.0.0.1", path: "/", httpOnly: true, sameSite: "Lax" }]);
    const viewerPage = await viewerContext.newPage();
    await viewerPage.goto(`http://127.0.0.1:4201/${tenantA}/projects/${projectA}/assets/${assetA}`, { waitUntil: "domcontentloaded" });
    await viewerPage.getByTestId("asset-detail-workspace").waitFor();
    const viewerHTML = await viewerPage.locator("body").innerHTML();
    assert.doesNotMatch(viewerHTML, /private body|content_text|Save new version|Confirm restore/);
    const box = await viewerPage.getByTestId("asset-detail-workspace").boundingBox();
    assert.ok(box && box.width <= 390 && box.height > 300);

    const hidden = await viewerPage.goto(`http://127.0.0.1:4201/${tenantB}/projects/${projectB}/assets/${assetA}`, { waitUntil: "domcontentloaded" });
    assert.ok(hidden && [200, 404].includes(hidden.status()));
    const hiddenBody = await viewerPage.locator("body").textContent();
    assert.doesNotMatch(hiddenBody ?? "", /Rule v1|private body|content_text/);
    assert.match(hiddenBody ?? "", /404|not found|unavailable/i);
  } finally {
    await browser?.close();
    for (const child of processes) { try { child.kill("SIGKILL"); } catch {} }
    rmSync(apiBinary, { force: true });
    cleanup();
  }
});

function startWeb(port, actor) {
  return spawn(process.execPath, ["node_modules/next/dist/bin/next", "start", "-p", String(port)], { cwd: new URL("../", import.meta.url), env: { ...process.env, MIROFISH_API_BASE_URL: apiBase, MIROFISH_WEB_DEV_ACTOR_USER_ID: actor, MIROFISH_WEB_DEV_BYPASS_LOGIN: "1" }, stdio: "inherit", detached: true });
}
async function waitFor(url, statuses) { for (let i=0;i<90;i++){ try { const response=await fetch(url); if(statuses.includes(response.status)) return; } catch {} await new Promise((resolve)=>setTimeout(resolve,500)); } throw new Error(`server did not become ready: ${url}`); }
function psql(sql) {
  const guard = `DO $guard$ BEGIN
    IF current_database() !~ '^mirofish_test_[a-z0-9_]+$'
       OR COALESCE(current_setting('mirofish.live_test', true), '') <> 'on' THEN
      RAISE EXCEPTION 'refusing non-disposable live test database';
    END IF;
  END $guard$;\n`;
  const result = spawnSync("docker", [
    "compose", "-f", composeFile, "-p", liveDatabase.composeProject,
    "exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1",
    "-U", liveDatabase.adminUser, "-d", liveDatabase.database,
  ], { input: guard + sql, encoding: "utf8" });
  if (result.status !== 0) throw new Error(result.stderr);
}
function cleanup(){psql(`DELETE FROM tenants WHERE tenant_id IN ('${tenantA}','${tenantB}'); DELETE FROM users WHERE (user_id,email) IN (('${owner}','asset-browser-owner@example.invalid'),('${viewer}','asset-browser-viewer@example.invalid'));`)}
function seed(){cleanup();psql(`
INSERT INTO users(user_id,email,display_name) VALUES('${owner}','asset-browser-owner@example.invalid','Owner'),('${viewer}','asset-browser-viewer@example.invalid','Viewer');
INSERT INTO tenants(tenant_id,slug,name,tenant_type) VALUES('${tenantA}','asset-browser-a','A','organization'),('${tenantB}','asset-browser-b','B','organization');
INSERT INTO projects(tenant_id,project_id,title,created_by) VALUES('${tenantA}','${projectA}','A','${owner}'),('${tenantB}','${projectB}','B','${owner}');
INSERT INTO assets(tenant_id,asset_id,project_id,scope,asset_type,category,lifecycle,title,summary,content_text,payload_jsonb,tags_jsonb,source_kind,source_ref,created_by) VALUES
('${tenantA}','${assetA}','${projectA}','project','world_rule','world','canon','Rule v1','first','private body v1','{"secret":"payload"}','["v1"]','manual','browser-a','${owner}'),
('${tenantA}','${assetA2}','${projectA}','project','note','notes','material','Note','second','private note','{}','[]','manual','browser-a2','${owner}'),
('${tenantB}','${assetB}','${projectB}','project','note','notes','material','Foreign','foreign','foreign private','{}','[]','manual','browser-b','${owner}');`)}
