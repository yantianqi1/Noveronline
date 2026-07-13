import assert from "node:assert/strict";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

import {
  assertPublicAssetSurface,
  assetPageUrl,
  hasAssetBrowserConfig,
  loadAssetBrowserConfig,
  publicFailure,
  waitForAssetReindex,
} from "./asset-library-live-harness.mjs";

const liveTest = hasAssetBrowserConfig() ? test : test.skip;

liveTest("Asset Library authenticates, reindexes, hybrid-searches, restores, and renders desktop/mobile", { timeout: 300_000 }, async () => {
  const config = loadAssetBrowserConfig();
  const previousBaseUrl = process.env.MIROFISH_API_BASE_URL;
  process.env.MIROFISH_API_BASE_URL = config.apiBaseUrl;
  const api = await import(`../lib/api.ts?assetBrowserLive=${Date.now()}`);
  const currentUser = await api.getCurrentUser({ sessionCookie: config.sessionCookie });
  assertPublicAssetSurface(currentUser, config);
  assert.equal(currentUser.ok, true, publicFailure(currentUser));
  assert.ok(currentUser.active_projects.some((project) => project.tenant_id === config.tenantId && project.project_id === config.projectId));
  const csrf = await api.getSessionCSRFToken({ sessionCookie: config.sessionCookie });
  assertPublicAssetSurface(csrf, config);
  assert.equal(csrf.ok, true, publicFailure(csrf));
  assert.notEqual(csrf.csrf_token, "", "authenticated session returned an empty CSRF token");

  const { chromium } = await import("@playwright/test");
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 }, locale: "en-US" });
  await context.addCookies([
    { name: "mirofish_session", value: config.sessionCookie, url: config.appBaseUrl, httpOnly: true, sameSite: "Lax" },
    { name: "mirofish_locale", value: "en", url: config.appBaseUrl, sameSite: "Lax" },
  ]);
  const page = await context.newPage();
  const browserErrors = [];
  page.on("pageerror", (error) => browserErrors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  await mkdir(config.screenshotDir, { recursive: true });

  try {
    await page.goto(assetPageUrl(config), { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "Asset Library", exact: true }).waitFor();

    if (config.runReindex) {
      await page.getByRole("button", { name: "Open asset operations", exact: true }).click();
      const panel = page.getByRole("dialog", { name: "Create asset" });
      await panel.getByRole("button", { name: "Reindex assets", exact: true }).click();
      await panel.locator("#reindex-mode").selectOption("hybrid");
      await Promise.all([
        page.waitForURL((url) => ["success", "error"].includes(url.searchParams.get("reindexStatus") || ""), { timeout: config.timeoutMs }),
        panel.getByRole("button", { name: "Refresh search", exact: true }).click(),
      ]);
      const reindexUrl = new URL(page.url());
      assert.equal(
        reindexUrl.searchParams.get("reindexStatus"),
        "success",
        `browser reindex admission failed: ${reindexUrl.searchParams.get("reindexCode") || "UNKNOWN"}`,
      );
      const runId = reindexUrl.searchParams.get("reindexRunId") || "";
      assert.notEqual(runId, "");
      await waitForAssetReindex(api, config, runId);
    }

    await page.goto(assetPageUrl(config), { waitUntil: "networkidle" });
    const searchPanel = page.getByRole("heading", { name: "Browse assets", exact: true }).locator("..");
    const resultRows = searchPanel.locator("article.trace-event");
    assert.ok(await resultRows.count() > 0, "hybrid browser search returned no DB-backed results");
    assert.match(await searchPanel.innerText(), /Best match/i);
    assert.doesNotMatch(await searchPanel.innerText(), /keyword contribution|vector contribution|raw relevance|embedding|boosts/i);
    const stableResults = await resultRows.allTextContents();
    assertPublicAssetSurface(await page.locator("body").innerText(), config);
    await page.screenshot({ path: path.join(config.screenshotDir, `assets-${config.providerMode}-desktop.png`), fullPage: true });

    await page.reload({ waitUntil: "networkidle" });
    assert.deepEqual(
      await page.locator(".asset-search-panel article.trace-event").allTextContents(),
      stableResults,
      "refresh did not restore the same ranked search result set",
    );
    const restored = new URL(page.url());
    assert.equal(restored.searchParams.get("query"), config.query);
    assert.equal(restored.searchParams.get("mode"), "hybrid");

    await page.setViewportSize({ width: 375, height: 812 });
    await page.reload({ waitUntil: "networkidle" });
    const bodyMetrics = await page.locator("body").evaluate((body) => ({ text: body.innerText.trim(), width: body.scrollWidth }));
    assert.ok(bodyMetrics.text.length > 100, "mobile Asset Library rendered blank content");
    assert.ok(bodyMetrics.width <= 375, `mobile Asset Library overflows horizontally: ${bodyMetrics.width}px`);
    assert.ok(await page.locator(".asset-search-panel article.trace-event").count() > 0, "mobile Asset Library lost search results");
    await page.screenshot({ path: path.join(config.screenshotDir, `assets-${config.providerMode}-mobile.png`), fullPage: true });
    assert.deepEqual(browserErrors, [], `browser emitted runtime errors: ${browserErrors.join(" | ")}`);
  } finally {
    await context.close();
    await browser.close();
    if (previousBaseUrl === undefined) delete process.env.MIROFISH_API_BASE_URL;
    else process.env.MIROFISH_API_BASE_URL = previousBaseUrl;
  }
});
