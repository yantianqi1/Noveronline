import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { afterEach, test } from "node:test";

import {
  addGraphSessionCookies,
  assertDisposableGraphProject,
  assertGraphDataScale,
  assertNoElementOverlap,
  graphApiContext,
  graphUrl,
  hasBrowserLiveGraphConfig,
  loadBrowserLiveGraphConfig,
  waitForBuiltGraph,
  waitForRunCandidate,
} from "./story-graph-live-harness.mjs";

const browserGraphTest = hasBrowserLiveGraphConfig() ? test : test.skip;
const previousApiBaseUrl = process.env.MIROFISH_API_BASE_URL;

afterEach(() => {
  if (previousApiBaseUrl === undefined) {
    delete process.env.MIROFISH_API_BASE_URL;
  } else {
    process.env.MIROFISH_API_BASE_URL = previousApiBaseUrl;
  }
});

browserGraphTest("Browser Story Graph builds, inspects, generates a candidate, and adopts it explicitly", async () => {
  const config = loadBrowserLiveGraphConfig();
  process.env.MIROFISH_API_BASE_URL = config.apiBaseUrl;
  const api = await import(`../lib/api.ts?storyGraphBrowserLive=${Date.now()}`);
  await assertDisposableGraphProject(api, config);
  const { chromium } = await import("@playwright/test").catch((error) => {
    assert.fail(`Playwright is required for browser Story Graph live check: ${error.message}`);
  });
  const browser = await chromium.launch({ headless: true });
  const timings = {};
  const screenshots = {
    desktop: path.join(config.screenshotDir, "story-graph-desktop.png"),
    mobile: path.join(config.screenshotDir, "story-graph-mobile.png"),
  };
  await mkdir(config.screenshotDir, { recursive: true });

  try {
    const context = await browser.newContext({ baseURL: config.appBaseUrl, viewport: { width: 1440, height: 1100 } });
    await addGraphSessionCookies(context, config);
    const page = await context.newPage();
    const runtimeErrors = [];
    page.on("pageerror", (error) => runtimeErrors.push(`pageerror: ${error.message}`));
    page.on("console", (message) => {
      if (message.type() === "error") {
        runtimeErrors.push(`console: ${message.text()}`);
      }
    });

    await page.goto(graphUrl(config, { mode: "build" }), { waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "Story Graph", exact: true }).waitFor();
    await page.getByRole("tab", { name: "Build", exact: true }).click();

    const buildPanel = page.getByRole("heading", { name: "Start build" }).locator("..");
    await buildPanel.locator("#graph-build-mode").selectOption("full");
    await buildPanel.locator("#graph-build-source").selectOption("seed_canon");
    const buildStarted = performance.now();
    await Promise.all([
      page.waitForURL((url) => (
        url.searchParams.get("buildStatus") === "success"
        && Boolean(url.searchParams.get("runId"))
        && url.searchParams.get("mode") === "build"
      ), {
        timeout: config.timeoutMs,
      }),
      buildPanel.getByRole("button", { name: "Build", exact: true }).click(),
    ]);
    const buildRunId = new URL(page.url()).searchParams.get("runId") ?? "";
    assert.notEqual(buildRunId, "", "browser build action did not expose its run id");
    const current = await waitForBuiltGraph(api, config, buildRunId);
    timings.build_ms = elapsedMs(buildStarted);
    const { view, evidence } = await assertGraphDataScale(api, config, current);

    const renderStarted = performance.now();
    await page.goto(graphUrl(config, { runId: buildRunId }), { waitUntil: "networkidle" });
    const canvas = page.getByLabel("Interactive story graph canvas");
    await canvas.waitFor();
    const canvasBox = await canvas.boundingBox();
    assert.ok(canvasBox && canvasBox.width >= 300 && canvasBox.height >= 180, "Story Graph canvas is blank or collapsed");
    const renderedClusterCount = await canvas.locator("[data-graph-cluster-id]").count();
    if (current.node_count > view.nodes.length) {
      assert.ok(renderedClusterCount > 0, "large Graph did not render cluster overview");
      assert.match(await canvas.getByRole("status").first().innerText(), /clusters represent/i);
    }
    await canvas.getByRole("button", { name: "Node view", exact: true }).click();
    const renderedNodes = canvas.locator("[data-graph-node-id]");
    assert.ok(await renderedNodes.count() >= config.minViewportNodes, "browser canvas did not render the DB-backed nodes");
    assert.equal(
      await canvas.locator("[data-graph-edge-id]").count(),
      view.edges.length,
      "browser canvas did not render every DB-backed edge in the current page",
    );
    await assertNoElementOverlap(renderedNodes, "Story Graph node");
    const stableNodeIds = await renderedNodes.evaluateAll((elements) => elements.map((element) => element.getAttribute("data-graph-node-id")));
    assert.ok(stableNodeIds.length >= config.minViewportNodes, "browser canvas node identities are incomplete");
    timings.desktop_render_ms = elapsedMs(renderStarted);
    assert.match(await page.getByRole("heading", { name: "Public evidence" }).locator("..").innerText(), new RegExp(`${evidence.items.length} public evidence`));
    const snapshotText = await page.getByRole("heading", { name: "Graph snapshot" }).locator("..").innerText();
    assert.match(snapshotText, new RegExp(`Version\\s+${current.version}`));
    assert.match(snapshotText, new RegExp(`Nodes\\s+${current.node_count}`));
    assert.match(snapshotText, new RegExp(`Edges\\s+${current.edge_count}`));
    await page.screenshot({ path: screenshots.desktop, fullPage: true });

    const graphBeforeCandidate = await api.getStoryGraphCurrent(graphApiContext(config));
    assert.equal(graphBeforeCandidate.ok, true);
    const composePanel = page.getByRole("heading", { name: "Generate bonds" }).locator("..");
    await composePanel.locator("#graph-bond-node-ids").selectOption(view.nodes.slice(0, 2).map((node) => node.node_id));
    await composePanel.locator("#graph-bond-focus").fill("Browser E2E relationship tension");
    const candidateStarted = performance.now();
    await Promise.all([
      page.waitForURL((url) => url.searchParams.get("bondStatus") === "success" && Boolean(url.searchParams.get("bondRunId")), {
        timeout: config.timeoutMs,
      }),
      composePanel.getByRole("button", { name: "Generate bonds", exact: true }).click(),
    ]);
    const bondRunId = new URL(page.url()).searchParams.get("bondRunId") ?? "";
    assert.notEqual(bondRunId, "", "browser bond action did not expose its run id");
    const candidate = await waitForRunCandidate(api, config, bondRunId);
    timings.candidate_ms = elapsedMs(candidateStarted);

    const graphWhileCandidate = await api.getStoryGraphCurrent(graphApiContext(config));
    assert.equal(graphWhileCandidate.ok, true);
    assert.equal(graphWhileCandidate.graph_id, graphBeforeCandidate.graph_id, "candidate generation replaced the canon graph");
    assert.equal(graphWhileCandidate.version, graphBeforeCandidate.version, "candidate generation advanced canon graph version");

    await page.goto(graphUrl(config, { runId: buildRunId, bondRunId }), { waitUntil: "networkidle" });
    const candidateRow = page.getByRole("row").filter({ hasText: candidate.source_ref });
    await candidateRow.waitFor();
    const targetKind = candidate.asset_type === "graph_bond" ? "relationship" : "plot_thread";
    const adoptionButtonName = targetKind === "relationship" ? "Adopt relationship" : "Adopt plot thread";
    const adoptionStarted = performance.now();
    await Promise.all([
      page.waitForURL((url) => (
        url.searchParams.get("storyGraphAdoptionStatus") === "success" &&
        url.searchParams.get("storyGraphAdoptionCode") === "STORY_GRAPH_CANDIDATE_ADOPTED" &&
        Boolean(url.searchParams.get("storyGraphAdoptionTargetId"))
      ), { timeout: config.timeoutMs }),
      candidateRow.getByRole("button", { name: adoptionButtonName, exact: true }).click(),
    ]);
    const adoptedTargetId = new URL(page.url()).searchParams.get("storyGraphAdoptionTargetId") ?? "";
    assert.notEqual(adoptedTargetId, "", "explicit Graph adoption did not return a canon target id");
    assert.match(await page.getByRole("heading", { name: "Graph candidates" }).locator("..").innerText(), /STORY_GRAPH_CANDIDATE_ADOPTED/);
    timings.adoption_ms = elapsedMs(adoptionStarted);

    const assetsAfterAdoption = await api.getProjectAssets(graphApiContext(config));
    assert.equal(assetsAfterAdoption.ok, true);
    const adoptedAsset = assetsAfterAdoption.items.find((item) => item.asset_id === candidate.asset_id);
    assert.ok(adoptedAsset, "adopted Graph candidate disappeared from the DB-backed asset read side");
    assert.equal(adoptedAsset.lifecycle, "canon", "explicit Graph adoption did not promote the selected candidate");

    const refreshStarted = performance.now();
    await page.reload({ waitUntil: "networkidle" });
    await page.getByRole("heading", { name: "Story Graph", exact: true }).waitFor();
    assert.match(await page.getByRole("heading", { name: "Graph candidates" }).locator("..").innerText(), /STORY_GRAPH_CANDIDATE_ADOPTED/);
    const refreshedCanvas = page.getByLabel("Interactive story graph canvas");
    await refreshedCanvas.getByRole("button", { name: "Node view", exact: true }).click();
    const refreshedNodeIds = await refreshedCanvas.locator("[data-graph-node-id]").evaluateAll((elements) => elements.map((element) => element.getAttribute("data-graph-node-id")));
    assert.deepEqual(refreshedNodeIds, stableNodeIds, "refresh changed stable Story Graph node identities or ordering");
    const refreshedAssets = await api.getProjectAssets(graphApiContext(config));
    assert.equal(refreshedAssets.items.find((item) => item.asset_id === candidate.asset_id)?.lifecycle, "canon");
    timings.refresh_ms = elapsedMs(refreshStarted);

    const mobileStarted = performance.now();
    await page.setViewportSize({ width: 390, height: 844 });
    const mobileCanvasBox = await refreshedCanvas.boundingBox();
    assert.ok(mobileCanvasBox && mobileCanvasBox.width >= 300 && mobileCanvasBox.height >= 180, "mobile Story Graph canvas is blank or collapsed");
    await assertNoElementOverlap(refreshedCanvas.locator("[data-graph-node-id]"), "mobile Story Graph node");
    await page.screenshot({ path: screenshots.mobile, fullPage: true });
    timings.mobile_render_ms = elapsedMs(mobileStarted);

    const invalidComposePanel = page.getByRole("heading", { name: "Generate bonds" }).locator("..");
    await invalidComposePanel.locator("#graph-bond-node-ids").selectOption(view.nodes[0].node_id);
    await Promise.all([
      page.waitForURL((url) => url.searchParams.get("bondStatus") === "error" && Boolean(url.searchParams.get("bondCode")), {
        timeout: config.timeoutMs,
      }),
      invalidComposePanel.getByRole("button", { name: "Generate bonds", exact: true }).click(),
    ]);
    const errorCode = new URL(page.url()).searchParams.get("bondCode") ?? "";
    assert.notEqual(errorCode, "", "invalid Graph Compose request did not expose a stable error code");
    const erroredComposePanel = page.getByRole("heading", { name: "Generate bonds" }).locator("..");
    await erroredComposePanel.locator(".error-box").filter({ hasText: errorCode }).waitFor();
    assert.deepEqual(runtimeErrors, [], `browser Story Graph emitted runtime errors:\n${runtimeErrors.join("\n")}`);

    const report = {
      node_count: current.node_count,
      edge_count: current.edge_count,
      viewport_node_count: view.nodes.length,
      viewport_edge_count: view.edges.length,
      public_evidence_sample_count: evidence.items.length,
      cluster_count: renderedClusterCount,
      timings,
      screenshots,
    };
    await writeFile(config.reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
    console.log("story graph browser live certification", report);
  } finally {
    await browser.close();
  }
});

function elapsedMs(started) {
  return Math.round((performance.now() - started) * 10) / 10;
}
