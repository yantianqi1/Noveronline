/**
 * Full author journey browser live test.
 *
 * Run:
 *   infra/scripts/run-live-test-stack.sh --app -- node apps/web/tests/author-journey-browser-live.test.mjs
 *
 * Requires MIROFISH_WEB_BROWSER_LIVE_AUTHOR_* env (see author-journey-live-harness.mjs).
 * Set MIROFISH_WEB_BROWSER_LIVE_AUTHOR_COMPLETE_JOURNEY=1 to require adoption and TXT export.
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { Buffer } from "node:buffer";
import { randomUUID } from "node:crypto";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import {
  addAuthorJourneySession,
  apiContext,
  assertPrivacyClean,
  attachPrivacyScanner,
  authenticateAuthorJourney,
  hasAuthorJourneyConfig,
  loadAuthorJourneyConfig,
  projectUrl,
  scanPage,
  submitServerAction,
  waitUntil,
} from "./author-journey-live-harness.mjs";

const journeyTest = hasAuthorJourneyConfig() ? test : test.skip;

journeyTest("Author journey covers signup, upload, handoffs, adoption and TXT export", { timeout: 420_000 }, async () => {
  const config = loadAuthorJourneyConfig();
  process.env.MIROFISH_API_BASE_URL = config.apiBaseUrl;
  const api = await import(`../lib/api.ts?authorJourneyLive=${Date.now()}`);
  const auth = await authenticateAuthorJourney(api, config);
  const contextInput = apiContext(config, auth);
  const findings = [];

  const { chromium } = await import("@playwright/test");
  const browser = await chromium.launch({ headless: true });
  const screenshotDir = path.join(config.screenshotDir, randomUUID());
  await mkdir(screenshotDir, { recursive: true });

  try {
    const browserContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await addAuthorJourneySession(browserContext, config, auth);
    const page = await browserContext.newPage();
    page.setDefaultNavigationTimeout(config.timeoutMs);
    page.setDefaultTimeout(config.timeoutMs);
    attachPrivacyScanner(page, findings);

    await page.goto(projectUrl(config, auth, "overview"), { waitUntil: "domcontentloaded" });
    const overviewBody = await page.locator("body").innerText();
    if (/Quota policy: missing|配额策略：未配置/.test(overviewBody)) {
      await page.goto(projectUrl(config, auth, "llm-facility/quotas"), { waitUntil: "domcontentloaded" });
      await page.getByRole("heading", { name: "Quota & Billing" }).waitFor();
      const policy = page.locator('section[aria-labelledby="policy-heading"]');
      if (await policy.getByRole("button", { name: "Create policy" }).count()) {
        await policy.locator('input[name="tokenLimit"]').first().fill("100000");
        await policy.locator('input[name="costLimitMicros"]').first().fill("100000");
        await policy.locator('input[name="concurrencyLimit"]').first().fill("2");
        await policy.getByRole("button", { name: "Create policy" }).click();
        await page.waitForTimeout(1000);
      }
    }
    journeyStage("llm readiness checked");

    const sourceText = `第一章 旅程 ${randomUUID()}\n雨声压住脚步。\n\n第二章 破晓\n光落在窗沿。\n`;
    await page.goto(projectUrl(config, auth, "overview"), { waitUntil: "domcontentloaded" });
    await page.locator("#source-file").setInputFiles({
      name: `author-journey-${randomUUID()}.txt`,
      mimeType: "text/plain",
      buffer: Buffer.from(sourceText, "utf8"),
    });
    await page.locator("#seed-mode").selectOption("full");
    const runsBefore = await api.getProjectSeedRuns(contextInput);
    assert.equal(runsBefore.ok, true);
    const existingRunIds = new Set(runsBefore.items.map((run) => run.run_id));
    await page.getByRole("button", { name: /Upload and start analysis/i }).click();
    const uploadedRun = await waitUntil(
      () => api.getProjectSeedRuns(contextInput),
      (result) => result.ok && result.items.some((run) => !existingRunIds.has(run.run_id)),
      config,
      "seed upload run",
    ).then((result) => result.items.find((run) => !existingRunIds.has(run.run_id)));
    assert.ok(uploadedRun);
    if (config.expectCompletedSeed) {
      await waitUntil(
        () => api.getSeedRunSummary({ ...contextInput, runId: uploadedRun.run_id }),
        (result) => result.ok && ["completed", "failed", "cancelled"].includes(result.status),
        config,
        "seed terminal status",
      );
      assert.equal((await api.getSeedRunSummary({ ...contextInput, runId: uploadedRun.run_id })).status, "completed");
    }
    journeyStage("seed uploaded");

    await page.goto(projectUrl(config, auth, "assets"), { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Asset Library", exact: true }).waitFor();
    journeyStage("assets opened");

    await page.goto(projectUrl(config, auth, "story-graph"), { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Story Graph", exact: true }).waitFor();
    journeyStage("graph opened");

    await page.goto(projectUrl(config, auth, "worldline"), { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Worldline", exact: true }).waitFor();
    const sessionPanel = page.getByRole("heading", { name: "Start session" }).locator("..");
    if (await sessionPanel.getByRole("button", { name: "Start session" }).isEnabled()) {
      await sessionPanel.getByLabel("Goal").fill(`Author journey world ${Date.now()}`);
      await sessionPanel.getByRole("button", { name: "Start session" }).click();
      await page.waitForTimeout(1500);
    }
    const sessions = await api.getWorldlineSessions(contextInput);
    assert.equal(sessions.ok, true);
    const sessionId = sessions.items.find((item) => item.lifecycle === "active")?.session_id;
    assert.ok(sessionId, "worldline session was not available for the author journey");

    const preparePanel = page.getByRole("heading", { name: "Prepare agents" }).locator("..");
    await preparePanel.getByLabel("Goal").fill("Prepare the selected character for a browser author journey");
    const agentRefs = preparePanel.locator('input[name="agentRefs"]');
    if (await agentRefs.count()) await agentRefs.first().check();
    await preparePanel.getByRole("button", { name: "Prepare agents" }).click();
    await page.waitForURL(/(?:prepare_id|worldlinePreparationPrepareId)=/, { timeout: config.timeoutMs });
    const prepareId = new URL(page.url()).searchParams.get("prepare_id")
      || new URL(page.url()).searchParams.get("worldlinePreparationPrepareId");
    assert.ok(prepareId);
    const preparation = await waitUntil(
      () => api.getWorldlinePreparation({ ...contextInput, prepareId }),
      (result) => result.ok && ["completed", "failed", "cancelled"].includes(result.status),
      config,
      "worldline preparation",
    );
    assert.equal(preparation.status, "completed");
    journeyStage("worldline preparation completed");

    await page.getByRole("link", { name: "Enter Characters" }).click();
    await page.waitForURL(/\/character-console/, { waitUntil: "domcontentloaded" });
    journeyStage("character console opened from worldline");

    const create = page.getByRole("heading", { name: "Create interaction" }).locator("..");
    await create.getByLabel("Worldline session").selectOption(sessionId);
    const typedAnchor = create.getByLabel("Typed anchor");
    if (await typedAnchor.locator("option").count() > 1) {
      await typedAnchor.selectOption({ index: 1 });
    }
    const povAgent = create.getByLabel("POV agent");
    if (await povAgent.locator("option").count() > 1) {
      await povAgent.selectOption({ index: 1 });
    }
    await create.getByLabel("Title").fill(`Author journey interaction ${Date.now()}`);
    await submitServerAction(page, create.getByRole("button", { name: "Create interaction" }), "interaction_id", Boolean, config.timeoutMs);
    const interactionId = new URL(page.url()).searchParams.get("interaction_id");
    assert.ok(interactionId);

    const turn = page.getByRole("heading", { name: "Record turn" }).locator("..");
    await turn.getByLabel("Interaction").selectOption(interactionId);
    await turn.getByLabel("Turn summary").fill("What do you remember about the rain-night pact?");
    await submitServerAction(page, turn.getByRole("button", { name: "Record turn" }), "turn_id", Boolean, config.timeoutMs);
    journeyStage("character interaction recorded");

    const convert = page.getByRole("heading", { name: "Convert to chapter draft" }).locator("..");
    await convert.getByLabel("Interaction").selectOption(interactionId);
    await submitServerAction(page, convert.getByRole("button", { name: "Request chapter draft" }), "runtime_run_id", Boolean, config.timeoutMs);
    await page.getByRole("link", { name: "View in Writer" }).click();
    await page.waitForURL(/\/writer\?.*runId=/, { waitUntil: "domcontentloaded" });
    const writerRunId = new URL(page.url()).searchParams.get("runId");
    assert.ok(writerRunId);
    journeyStage("writer opened from character handoff");

    if (config.completeJourney) {
      const writerRun = await waitUntil(
        () => api.getWriterRunSummary({ ...contextInput, runId: writerRunId }),
        (result) => result.ok && ["completed", "failed", "cancelled"].includes(result.status),
        config,
        "writer candidate run",
      );
      assert.equal(writerRun.status, "completed", `writer handoff failed with ${writerRun.status}`);
      await page.reload({ waitUntil: "domcontentloaded" });
      const adoptButton = page.getByRole("button", { name: "Adopt draft into manuscript", exact: true });
      if (await adoptButton.count()) {
        await submitWriterAction(page, adoptButton, config.timeoutMs);
      }
      assert.match(await page.locator("body").innerText(), /DRAFT_ADOPTED|Adopted|Blocks\s+1/i);
      await page.getByRole("button", { name: "Generate TXT artifact", exact: true }).click();
      await waitForDownloadLink(page, "Download completed TXT", config.timeoutMs);
      const downloadLink = page.getByRole("link", { name: "Download completed TXT", exact: true });
      const downloadURL = new URL(await downloadLink.getAttribute("href"), page.url()).toString();
      const artifactResponse = await browserContext.request.get(downloadURL);
      assert.equal(artifactResponse.status(), 200);
      const artifactBytes = await artifactResponse.body();
      const downloadPromise = page.waitForEvent("download");
      await downloadLink.click();
      const download = await downloadPromise;
      const downloadPath = await download.path();
      assert.ok(downloadPath, "author journey download did not produce a local artifact");
      const content = await readFile(downloadPath);
      assert.ok(content.length > 0, "downloaded manuscript is empty");
      assert.deepEqual(content, artifactBytes);
      const expectedHash = artifactResponse.headers()["x-content-sha256"] || "";
      if (expectedHash) {
        assert.equal(createHash("sha256").update(content).digest("hex"), expectedHash);
      }
      journeyStage("manuscript exported");
    }

    await scanPage(page, findings);
    await page.screenshot({ path: path.join(screenshotDir, "author-journey-writer.png"), fullPage: true });
    assertPrivacyClean(findings);
  } finally {
    await browser.close();
  }
});

async function submitWriterAction(page, button, timeoutMs) {
  const actionResponse = page.waitForResponse((response) => {
    const request = response.request();
    return request.method() === "POST" && new URL(response.url()).pathname.endsWith("/writer");
  }, { timeout: timeoutMs });
  await button.click({ noWaitAfter: true });
  const response = await actionResponse;
  assert.ok(response.status() < 400, `writer server action returned HTTP ${response.status()}`);
  const actionRedirect = (response.headers()["x-action-redirect"] || "").split(";")[0].trim();
  if (actionRedirect) {
    const redirectURL = new URL(actionRedirect, page.url());
    await page.goto(redirectURL.toString(), { waitUntil: "domcontentloaded" });
  }
}

async function waitForDownloadLink(page, label, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await page.getByRole("link", { name: label, exact: true }).count()) return;
    await page.waitForTimeout(500);
    await page.reload({ waitUntil: "domcontentloaded" });
  }
  assert.fail(`${label} did not appear before timeout`);
}

function journeyStage(stage) {
  process.stdout.write(`Author journey: ${stage}\n`);
}