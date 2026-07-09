import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { randomUUID } from "node:crypto";
import { afterEach, test } from "node:test";

import { waitForSeedWorkerStageEvents } from "./live-seed-harness.mjs";

const browserSeedUploadTest = hasAnyBrowserLiveConfig() ? test : test.skip;
const previousApiBaseUrl = process.env.MIROFISH_API_BASE_URL;

afterEach(() => {
  if (previousApiBaseUrl === undefined) {
    delete process.env.MIROFISH_API_BASE_URL;
    return;
  }
  process.env.MIROFISH_API_BASE_URL = previousApiBaseUrl;
});

browserSeedUploadTest("Browser Overview upload form can upload, complete, and start a live Seed run", async () => {
  const config = browserLiveConfig();
  assertBrowserLiveConfigComplete(config);
  assertSafeLocalUrl(config.appBaseUrl, "Next app");
  assertSafeLocalUrl(config.apiBaseUrl, "Go API");
  process.env.MIROFISH_API_BASE_URL = config.apiBaseUrl;
  const api = await import(`../lib/api.ts?seedUploadBrowserLive=${Date.now()}`);
  await assertDisposableProject(api, config);
  const { chromium } = await import("@playwright/test").catch((error) => {
    assert.fail(`Playwright is required for browser Seed upload live check: ${error.message}`);
  });
  const sourceText = `MiroFish browser seed upload ${randomUUID()}`;
  const sourceBytes = Buffer.from(sourceText, "utf8");
  const browser = await chromium.launch({ headless: true });
  let appResponseScans;

  try {
    const context = await browser.newContext({ baseURL: config.appBaseUrl });
    await context.addCookies([
      {
        name: "mirofish_session",
        value: config.sessionCookie,
        url: config.appBaseUrl,
        httpOnly: true,
        sameSite: "Lax",
      },
    ]);
    const page = await context.newPage();
    appResponseScans = installAppResponsePrivacyScan(page, config, () => ({ sourceText }));

    await page.goto(overviewUrl(config), { waitUntil: "networkidle" });
    await flushResponseScans(appResponseScans);
    assertNoForbiddenPublicMarkers(await page.textContent("body"), { sessionCookie: config.sessionCookie });

    await page.locator("#source-file").setInputFiles({
      name: `browser-seed-${randomUUID()}.txt`,
      mimeType: "text/plain",
      buffer: sourceBytes,
    });
    await page.locator("#seed-mode").selectOption("full");
    await Promise.all([
      page.waitForURL((url) => {
        return (
          url.searchParams.get("sourceStatus") === "success" &&
          url.searchParams.get("seedStatus") === "success" &&
          Boolean(url.searchParams.get("runId"))
        );
      }, { timeout: 60000 }),
      page.getByRole("button", { name: /Upload and start Seed/i }).click(),
    ]);
    await page.waitForLoadState("networkidle");
    await flushResponseScans(appResponseScans);

    const pageUrl = new URL(page.url());
    const runId = pageUrl.searchParams.get("runId") ?? "";
    assert.notEqual(runId, "", "browser Seed upload did not return a run id");
    assertNoForbiddenPublicMarkers(pageUrl.toString(), {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assertNoForbiddenPublicMarkers(await page.textContent("body"), {
      sourceText,
      sessionCookie: config.sessionCookie,
    });

    const initialEvents = await api.getSeedRunEvents({
      tenantId: config.tenantId,
      sessionCookie: config.sessionCookie,
      runId,
    });
    assertNoForbiddenPublicMarkers(initialEvents, {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assert.equal(initialEvents.ok, true, publicFailure(initialEvents));
    assert.equal(initialEvents.run_id, runId);
    const queuedEvent = initialEvents.items.find((event) => event.event_type === "workflow.queued");
    assert.ok(queuedEvent, "browser Seed upload did not expose persisted queued progress event");
    assert.equal(queuedEvent.sequence, 1);
    assert.equal(queuedEvent.project_id, config.projectId);
    assert.equal(queuedEvent.payload.status, "queued");
    assert.equal(queuedEvent.payload.workflow_type, "seed_pipeline");
    assert.equal(typeof queuedEvent.payload.upload_id, "string");
    assert.notEqual(queuedEvent.payload.upload_id, "");
    assert.equal(typeof queuedEvent.payload.source_file_id, "string");
    assert.notEqual(queuedEvent.payload.source_file_id, "");

    if (config.requireWorkerRetry) {
      await waitForSeedWorkerStageEvents(api, config, runId, {
        sourceText,
        afterSequence: queuedEvent.sequence,
        timeoutMs: config.workerRetryTimeoutMs,
      });
    }

    let retryControlRunId = runId;
    const earlySelectedRunPanel = page.getByRole("heading", { name: "Selected Seed run" }).locator("..");
    const earlyControlSeedPanel = page.getByRole("heading", { name: "Control Seed run" }).locator("..");
    const earlyCancelButton = earlyControlSeedPanel.getByRole("button", { name: /^Cancel Seed run$/ });
    const earlyRetryButton = earlyControlSeedPanel.getByRole("button", { name: /^Retry Seed run$/ });
    await earlySelectedRunPanel.getByText(runId).waitFor();
    await earlyCancelButton.waitFor();
    await earlyRetryButton.waitFor();
    const earlyRunStatus = await assertSeedRunBrowserControlsReflectStatus(page, earlySelectedRunPanel, "fresh selected run");
    if (earlyRunStatus === "queued" || earlyRunStatus === "running") {
      const freshRunBeforeCancel = await api.getSeedRunSummary({
        tenantId: config.tenantId,
        sessionCookie: config.sessionCookie,
        runId,
      });
      assertNoForbiddenPublicMarkers(freshRunBeforeCancel, {
        sourceText,
        sessionCookie: config.sessionCookie,
      });
      assert.equal(freshRunBeforeCancel.ok, true, publicFailure(freshRunBeforeCancel));
      if (freshRunBeforeCancel.status === "queued" || freshRunBeforeCancel.status === "running") {
        assert.equal(await earlyCancelButton.isEnabled(), true, "fresh browser Seed run must be cancellable for retry-control live coverage");
        assert.equal(await earlyRetryButton.isDisabled(), true, "fresh browser Seed run must not expose retry before a retryable terminal status");
        const beforeCancelUrl = page.url();
        try {
          await Promise.all([
            page.waitForURL((url) => (
              url.toString() !== beforeCancelUrl &&
              url.searchParams.get("runId") === runId &&
              Boolean(url.searchParams.get("seedStatus")) &&
              Boolean(url.searchParams.get("seedCode"))
            ), { timeout: 60000 }),
            earlyCancelButton.click(),
          ]);
        } catch (error) {
          const afterCancelRace = await api.getSeedRunSummary({
            tenantId: config.tenantId,
            sessionCookie: config.sessionCookie,
            runId,
          });
          assertNoForbiddenPublicMarkers(afterCancelRace, {
            sourceText,
            sessionCookie: config.sessionCookie,
          });
          assert.equal(afterCancelRace.ok, true, publicFailure(afterCancelRace));
          if (afterCancelRace.status === "queued" || afterCancelRace.status === "running") {
            throw error;
          }
        }
        await page.waitForLoadState("networkidle");
        await flushResponseScans(appResponseScans);
        assertNoForbiddenPublicMarkers(await page.textContent("body"), {
          sourceText,
          sessionCookie: config.sessionCookie,
        });
      }
    }

    const preparedRetryRun = await waitForSeedRunTerminalStatus(api, config, runId, {
      sourceText,
      timeoutMs: 60000,
    });
    if (preparedRetryRun.status === "completed" && config.requireWorkerRetry) {
      assert.fail("browser Seed worker-retry mode requires the browser-uploaded run to be retryable after worker evidence");
    } else if (preparedRetryRun.status === "completed" && config.consumeRetryRun) {
      await assertConsumableRetryableSeedRun(api, config, config.retryRunId);
      retryControlRunId = config.retryRunId;
    } else if (preparedRetryRun.status === "completed") {
      assert.fail("browser Seed retry live coverage requires MIROFISH_WEB_BROWSER_LIVE_SEED_CONSUME_RETRY_RUN=1 and MIROFISH_WEB_BROWSER_LIVE_SEED_RETRY_RUN_ID when the uploaded run completes before cancellation");
    } else if (preparedRetryRun.status === "failed" || preparedRetryRun.status === "cancelled") {
      retryControlRunId = runId;
    } else {
      assert.fail("browser Seed retry live coverage could not prepare a retryable terminal run");
    }

    const preparedRetrySummary = await api.getSeedRunSummary({
      tenantId: config.tenantId,
      sessionCookie: config.sessionCookie,
      runId,
    });
    assertNoForbiddenPublicMarkers(preparedRetrySummary, {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assert.equal(preparedRetrySummary.ok, true, publicFailure(preparedRetrySummary));

    const rawRun = await fetchBrowserLivePublicJsonWithRawScan(
      config,
      `/v1/seed-runs/${runId}`,
      { sourceText },
    );
    assertNoForbiddenPublicMarkers(rawRun, {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assert.equal(rawRun.project_id, config.projectId);
    assert.equal(rawRun.workflow_type, "seed_pipeline");

    const run = await api.getSeedRunSummary({
      tenantId: config.tenantId,
      sessionCookie: config.sessionCookie,
      runId,
    });
    assertNoForbiddenPublicMarkers(run, {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assert.equal(run.ok, true, publicFailure(run));
    assert.equal(run.project_id, config.projectId);
    assert.equal(run.workflow_type, "seed_pipeline");

    const rawEvents = await fetchBrowserLivePublicJsonWithRawScan(
      config,
      `/v1/seed-runs/${runId}/events`,
      { sourceText },
    );
    assertNoForbiddenPublicMarkers(rawEvents, {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assert.equal(Array.isArray(rawEvents.items), true);
    assert.equal(rawEvents.items.every((event) => event.run_id === runId), true);

    const events = await api.getSeedRunEvents({
      tenantId: config.tenantId,
      sessionCookie: config.sessionCookie,
      runId,
    });
    assertNoForbiddenPublicMarkers(events, {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assert.equal(events.ok, true, publicFailure(events));
    assert.equal(events.run_id, runId);
    assert.ok(
      events.items.some((event) => event.event_id === queuedEvent.event_id && event.sequence === queuedEvent.sequence),
      "browser Seed upload replay did not preserve the queued event",
    );

    const rawReplayAfterQueued = await fetchBrowserLivePublicJsonWithRawScan(
      config,
      `/v1/seed-runs/${runId}/events?after_event_id=${encodeURIComponent(queuedEvent.event_id)}`,
      { sourceText },
    );
    assertNoForbiddenPublicMarkers(rawReplayAfterQueued, {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assert.equal(Array.isArray(rawReplayAfterQueued.items), true);
    assert.equal(
      rawReplayAfterQueued.items.every((event) => event.event_id !== queuedEvent.event_id && event.sequence > queuedEvent.sequence),
      true,
    );

    const replayAfterQueued = await api.getSeedRunEvents({
      tenantId: config.tenantId,
      sessionCookie: config.sessionCookie,
      runId,
      afterEventId: queuedEvent.event_id,
    });
    assertNoForbiddenPublicMarkers(replayAfterQueued, {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assert.equal(replayAfterQueued.ok, true, publicFailure(replayAfterQueued));
    assert.equal(replayAfterQueued.after_event_id, queuedEvent.event_id);
    assert.equal(
      replayAfterQueued.items.every((event) => event.event_id !== queuedEvent.event_id && event.sequence > queuedEvent.sequence),
      true,
      "Seed event cursor replay returned the queued event again",
    );

    await page.reload({ waitUntil: "networkidle" });
    await flushResponseScans(appResponseScans);
    const selectedRunPanel = page.getByRole("heading", { name: "Selected Seed run" }).locator("..");
    const seedEventsPanel = page.getByRole("heading", { name: "Seed events" }).locator("..");
    await selectedRunPanel.getByText(runId).waitFor();
    await selectedRunPanel.getByText("Progress").waitFor();
    const progressValue = selectedRunPanel.locator("dt", { hasText: /^Progress$/ }).locator("xpath=following-sibling::dd[1]");
    await progressValue.waitFor();
    assert.equal((await progressValue.textContent())?.trim(), String(run.progress));
    await seedEventsPanel.getByText("workflow.queued").waitFor();
    await seedEventsPanel.getByText("seq 1").waitFor();
    assertNoForbiddenPublicMarkers(await page.textContent("body"), {
      sourceText,
      sessionCookie: config.sessionCookie,
    });

    const retryOverviewUrl = new URL(overviewUrl(config));
    retryOverviewUrl.searchParams.set("runId", retryControlRunId);
    await page.goto(retryOverviewUrl.toString(), { waitUntil: "networkidle" });
    await flushResponseScans(appResponseScans);
    const retrySelectedRunPanel = page.getByRole("heading", { name: "Selected Seed run" }).locator("..");
    const retrySeedEventsPanel = page.getByRole("heading", { name: "Seed events" }).locator("..");
    await retrySelectedRunPanel.getByText(retryControlRunId).waitFor();
    await assertSeedRunBrowserControlsReflectStatus(page, retrySelectedRunPanel, "retryable selected run");

    const controlSeedPanel = page.getByRole("heading", { name: "Control Seed run" }).locator("..");
    const cancelButton = controlSeedPanel.getByRole("button", { name: /^Cancel Seed run$/ });
    const retryButton = controlSeedPanel.getByRole("button", { name: /^Retry Seed run$/ });
    await cancelButton.waitFor();
    await retryButton.waitFor();

    const retryableRun = await api.getSeedRunSummary({
      tenantId: config.tenantId,
      sessionCookie: config.sessionCookie,
      runId: retryControlRunId,
    });
    assertNoForbiddenPublicMarkers(retryableRun, {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assert.equal(retryableRun.ok, true, publicFailure(retryableRun));
    assert.equal(
      retryableRun.status === "cancelled" || retryableRun.status === "failed",
      true,
      "browser Seed run did not reach a retryable terminal status for retry-control live coverage",
    );
    assert.equal(await cancelButton.isDisabled(), true, "retryable terminal browser Seed run must not expose cancel");
    assert.equal(await retryButton.isEnabled(), true, "retryable terminal browser Seed run must expose retry");

    const retryableEvents = await api.getSeedRunEvents({
      tenantId: config.tenantId,
      sessionCookie: config.sessionCookie,
      runId: retryControlRunId,
    });
    assertNoForbiddenPublicMarkers(retryableEvents, {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assert.equal(retryableEvents.ok, true, publicFailure(retryableEvents));
    const maxRetryableSequence = maxEventSequence(retryableEvents.items);
    const retryCursorEvent = retryableEvents.items.find(
      (event) => event.event_type === "workflow.queued" && event.sequence < maxRetryableSequence,
    ) ?? retryableEvents.items.find((event) => event.sequence < maxRetryableSequence);
    assert.ok(retryCursorEvent, "browser Seed retryable run must expose a cursor event with later events");
    assert.ok(maxRetryableSequence > retryCursorEvent.sequence, "browser Seed retryable run did not preserve visible progress events after the cursor");
    const retryReplayAfterCursor = await api.getSeedRunEvents({
      tenantId: config.tenantId,
      sessionCookie: config.sessionCookie,
      runId: retryControlRunId,
      afterEventId: retryCursorEvent.event_id,
    });
    assertNoForbiddenPublicMarkers(retryReplayAfterCursor, {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assert.equal(retryReplayAfterCursor.ok, true, publicFailure(retryReplayAfterCursor));
    assert.equal(retryReplayAfterCursor.after_event_id, retryCursorEvent.event_id);
    assert.ok(retryReplayAfterCursor.items.length > 0, "browser Seed retryable run did not expose post-cursor events");
    assert.equal(
      retryReplayAfterCursor.items.every((event) => event.event_id !== retryCursorEvent.event_id && event.sequence > retryCursorEvent.sequence),
      true,
      "browser Seed retryable replay returned the cursor event again",
    );
    const expectedPostCursorEvent = retryReplayAfterCursor.items[0];

    const cursorUrl = new URL(overviewUrl(config));
    cursorUrl.searchParams.set("runId", retryControlRunId);
    cursorUrl.searchParams.set("after_event_id", retryCursorEvent.event_id);
    await page.goto(cursorUrl.toString(), { waitUntil: "networkidle" });
    await flushResponseScans(appResponseScans);
    await page.getByText(`Event cursor: ${retryCursorEvent.event_id}`).first().waitFor();
    const cursoredEventsText = await retrySeedEventsPanel.textContent();
    assert.match(cursoredEventsText ?? "", new RegExp(escapeRegExp(expectedPostCursorEvent.event_type)));
    assert.match(cursoredEventsText ?? "", new RegExp(`seq ${expectedPostCursorEvent.sequence}\\b`));
    assert.doesNotMatch(cursoredEventsText ?? "", new RegExp(`seq ${retryCursorEvent.sequence}\\b`));
    assertNoForbiddenPublicMarkers(await page.textContent("body"), {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assert.equal(await retryButton.isEnabled(), true, "retryable browser Seed run lost retry enablement with an event cursor");

    await Promise.all([
      page.waitForURL((url) => (
        url.searchParams.get("seedStatus") === "success" &&
        url.searchParams.get("seedCode") === "retry_requested" &&
        url.searchParams.get("runId") === retryControlRunId &&
        !url.searchParams.has("after_event_id")
      ), { timeout: 60000 }),
      retryButton.click(),
    ]);
    await page.waitForLoadState("networkidle");
    await flushResponseScans(appResponseScans);
    assertNoForbiddenPublicMarkers(page.url(), {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assertNoForbiddenPublicMarkers(await page.textContent("body"), {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    await retrySeedEventsPanel.getByText("Event cursor: beginning").waitFor();
    await retrySeedEventsPanel.getByText("workflow.queued").waitFor();
    await retrySeedEventsPanel.getByText("workflow.retry_requested").waitFor();

    const retriedEvents = await api.getSeedRunEvents({
      tenantId: config.tenantId,
      sessionCookie: config.sessionCookie,
      runId: retryControlRunId,
    });
    assertNoForbiddenPublicMarkers(retriedEvents, {
      sourceText,
      sessionCookie: config.sessionCookie,
    });
    assert.equal(retriedEvents.ok, true, publicFailure(retriedEvents));
    const retryRequestedEvent = retriedEvents.items.find((event) => event.event_type === "workflow.retry_requested");
    assert.ok(
      retryRequestedEvent,
      "browser Seed retry control did not expose the accepted retry event",
    );
    if (config.requireWorkerRetry) {
      await waitForSeedWorkerStageEvents(api, config, retryControlRunId, {
        sourceText,
        afterSequence: retryRequestedEvent.sequence,
        timeoutMs: config.workerRetryTimeoutMs,
      });
    }
    assert.ok(
      retriedEvents.items.some((event) => event.sequence > maxRetryableSequence),
      "browser Seed retry control did not make post-terminal events visible after clearing the cursor",
    );
  } finally {
    if (appResponseScans) {
      appResponseScans.stop();
      await flushResponseScans(appResponseScans);
    }
    await browser.close();
  }
});

function hasAnyBrowserLiveConfig() {
  return Object.keys(process.env).some((name) => name.startsWith("MIROFISH_WEB_BROWSER_LIVE_SEED_"));
}

function browserLiveConfig() {
  return {
    appBaseUrl: env("MIROFISH_WEB_BROWSER_LIVE_SEED_APP_BASE_URL"),
    apiBaseUrl: env("MIROFISH_WEB_BROWSER_LIVE_SEED_API_BASE_URL"),
    tenantId: env("MIROFISH_WEB_BROWSER_LIVE_SEED_TENANT_ID"),
    projectId: env("MIROFISH_WEB_BROWSER_LIVE_SEED_PROJECT_ID"),
    sessionCookie: env("MIROFISH_WEB_BROWSER_LIVE_SEED_SESSION_COOKIE"),
    retryRunId: env("MIROFISH_WEB_BROWSER_LIVE_SEED_RETRY_RUN_ID"),
    consumeRetryRun: env("MIROFISH_WEB_BROWSER_LIVE_SEED_CONSUME_RETRY_RUN") === "1",
    requireWorkerRetry: env("MIROFISH_WEB_BROWSER_LIVE_SEED_REQUIRE_WORKER_RETRY") === "1",
    workerRetryTimeoutMs: envPositiveInt("MIROFISH_WEB_BROWSER_LIVE_SEED_WORKER_RETRY_TIMEOUT_MS", 120000),
    allowMutation: env("MIROFISH_WEB_BROWSER_LIVE_SEED_ALLOW_MUTATION") === "1",
    throwawayProject: env("MIROFISH_WEB_BROWSER_LIVE_SEED_THROWAWAY_PROJECT") === "1",
    disposableProjectMarker: env("MIROFISH_WEB_BROWSER_LIVE_SEED_DISPOSABLE_PROJECT_MARKER"),
  };
}

async function assertDisposableProject(api, config) {
  const rawCurrentUser = await fetchBrowserLivePublicJsonWithRawScan(config, "/v1/me");
  assertNoForbiddenPublicMarkers(rawCurrentUser, { sessionCookie: config.sessionCookie });
  assert.equal(typeof rawCurrentUser.user?.user_id, "string");
  assert.equal(Array.isArray(rawCurrentUser.active_projects), true);
  const currentUser = await api.getCurrentUser({ sessionCookie: config.sessionCookie });
  assertNoForbiddenPublicMarkers(currentUser, { sessionCookie: config.sessionCookie });
  assert.equal(currentUser.ok, true, publicFailure(currentUser));
  const project = currentUser.active_projects.find(
    (candidate) =>
      candidate.tenant_id === config.tenantId &&
      candidate.project_id === config.projectId &&
      candidate.status === "active",
  );
  assert.ok(project, "browser Seed upload target project must be active for the session user");
  const marker = config.disposableProjectMarker.toLowerCase();
  const projectIdentity = `${project.project_id} ${project.name}`.toLowerCase();
  assert.equal(
    projectIdentity.includes(marker),
    true,
    "browser Seed upload target project must contain the disposable project marker",
  );
}

function assertBrowserLiveConfigComplete(config) {
  const missing = [];
  const requiredText = [
    ["MIROFISH_WEB_BROWSER_LIVE_SEED_APP_BASE_URL", config.appBaseUrl],
    ["MIROFISH_WEB_BROWSER_LIVE_SEED_API_BASE_URL", config.apiBaseUrl],
    ["MIROFISH_WEB_BROWSER_LIVE_SEED_TENANT_ID", config.tenantId],
    ["MIROFISH_WEB_BROWSER_LIVE_SEED_PROJECT_ID", config.projectId],
    ["MIROFISH_WEB_BROWSER_LIVE_SEED_SESSION_COOKIE", config.sessionCookie],
    ["MIROFISH_WEB_BROWSER_LIVE_SEED_DISPOSABLE_PROJECT_MARKER", config.disposableProjectMarker],
  ];
  for (const [name, value] of requiredText) {
    if (!value) {
      missing.push(name);
    }
  }
  if (!config.allowMutation) {
    missing.push("MIROFISH_WEB_BROWSER_LIVE_SEED_ALLOW_MUTATION=1");
  }
  if (!config.throwawayProject) {
    missing.push("MIROFISH_WEB_BROWSER_LIVE_SEED_THROWAWAY_PROJECT=1");
  }
  if (config.consumeRetryRun && !config.retryRunId) {
    missing.push("MIROFISH_WEB_BROWSER_LIVE_SEED_RETRY_RUN_ID");
  }
  if (config.requireWorkerRetry && (config.consumeRetryRun || config.retryRunId)) {
    assert.fail("browser Seed worker-retry mode cannot consume an external retry run");
  }
  assert.equal(
    missing.length,
    0,
    `browser Seed upload live config is incomplete: ${missing.join(", ")}`,
  );
}

function assertSafeLocalUrl(value, label) {
  const parsed = new URL(value);
  const hostname = parsed.hostname.toLowerCase();
  assert.equal(
    parsed.protocol === "http:" &&
      (hostname === "127.0.0.1" || hostname === "localhost" || hostname === "::1" || hostname === "[::1]"),
    true,
    `${label} live Seed upload harness URL must be local http`,
  );
}

function overviewUrl(config) {
  const url = new URL(`/${config.tenantId}/projects/${config.projectId}/overview`, config.appBaseUrl);
  return url.toString();
}

async function assertSeedRunBrowserControlsReflectStatus(page, selectedRunPanel, label) {
  const controlSeedPanel = page.getByRole("heading", { name: "Control Seed run" }).locator("..");
  const statusValue = selectedRunPanel.locator("dt", { hasText: /^Status$/ }).locator("xpath=following-sibling::dd[1]");
  await statusValue.waitFor();
  const status = ((await statusValue.textContent()) ?? "").trim().toLowerCase();
  assert.notEqual(status, "", `${label} did not render a status`);
  assert.equal(
    await controlSeedPanel.getByRole("button", { name: /^Cancel Seed run$/ }).isEnabled(),
    status === "queued" || status === "running",
    `${label} cancel control did not match status`,
  );
  assert.equal(
    await controlSeedPanel.getByRole("button", { name: /^Retry Seed run$/ }).isEnabled(),
    status === "failed" || status === "cancelled",
    `${label} retry control did not match status`,
  );
  return status;
}

async function assertConsumableRetryableSeedRun(api, config, runId) {
  const rawRun = await fetchBrowserLivePublicJsonWithRawScan(config, `/v1/seed-runs/${runId}`);
  assertNoForbiddenPublicMarkers(rawRun, { sessionCookie: config.sessionCookie });
  assert.equal(rawRun.project_id, config.projectId);
  assert.equal(rawRun.workflow_type, "seed_pipeline");
  assert.equal(
    rawRun.status === "failed" || rawRun.status === "cancelled",
    true,
    "browser Seed consumable retry run must be failed or cancelled",
  );

  const run = await api.getSeedRunSummary({
    tenantId: config.tenantId,
    sessionCookie: config.sessionCookie,
    runId,
  });
  assertNoForbiddenPublicMarkers(run, { sessionCookie: config.sessionCookie });
  assert.equal(run.ok, true, publicFailure(run));
  assert.equal(run.project_id, config.projectId);
  assert.equal(run.workflow_type, "seed_pipeline");
  assert.equal(
    run.status === "failed" || run.status === "cancelled",
    true,
    "browser Seed consumable retry summary must be failed or cancelled",
  );
}

async function waitForSeedRunTerminalStatus(api, config, runId, options) {
  const deadline = Date.now() + options.timeoutMs;
  let latest;
  while (Date.now() <= deadline) {
    latest = await api.getSeedRunSummary({
      tenantId: config.tenantId,
      sessionCookie: config.sessionCookie,
      runId,
    });
    assertNoForbiddenPublicMarkers(latest, {
      sourceText: options.sourceText,
      sessionCookie: config.sessionCookie,
    });
    assert.equal(latest.ok, true, publicFailure(latest));
    if (latest.status === "completed" || latest.status === "failed" || latest.status === "cancelled") {
      return latest;
    }
    await delay(500);
  }
  assert.fail(`browser Seed run did not reach a terminal status after cancel request: ${latest?.status ?? "unknown"}`);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function maxEventSequence(events) {
  return events.reduce((maxSequence, event) => Math.max(maxSequence, event.sequence), 0);
}

async function fetchBrowserLivePublicJsonWithRawScan(config, path, options = {}) {
  assertSafeLocalUrl(config.apiBaseUrl, "Go API");
  assert.equal(path.startsWith("/"), true, "browser live public fetch path must be absolute");
  assert.equal(path.startsWith("//"), false, "browser live public fetch path must stay on API base");
  const url = new URL(path, config.apiBaseUrl);
  const apiBase = new URL(config.apiBaseUrl);
  assert.equal(url.origin, apiBase.origin, "browser live public fetch URL must stay on API base");
  const response = await fetch(url, {
    headers: {
      "X-Tenant-Id": config.tenantId,
      Cookie: `mirofish_session=${config.sessionCookie}`,
    },
  });
  const rawText = await response.text();
  const sourceText = options.sourceText;
  assertNoForbiddenPublicMarkers(rawText, {
    sourceText,
    sessionCookie: config.sessionCookie,
  });
  let payload;
  try {
    payload = JSON.parse(rawText);
  } catch {
    assert.fail(`browser live public fetch returned invalid JSON: ${publicPathLabel(url)}`);
  }
  assert.equal(response.ok, true, `browser live public fetch failed: ${publicPathLabel(url)}`);
  return payload;
}

function publicPathLabel(url) {
  return `${url.pathname}${url.search ? "?..." : ""}`;
}

function installAppResponsePrivacyScan(page, config, options) {
  const pending = [];
  const appOrigin = new URL(config.appBaseUrl).origin;
  const onResponse = (response) => {
    const url = new URL(response.url());
    if (url.origin !== appOrigin || !isScannableAppResponse(response, url)) {
      return;
    }
    pending.push(
      response.text().catch((error) => {
        if (isUnavailableResponseBodyError(error)) {
          return "";
        }
        throw error;
      }).then((text) => {
        if (!text) {
          return;
        }
        assertNoForbiddenPublicMarkers(text, {
          ...options(),
          sessionCookie: config.sessionCookie,
        });
      }),
    );
  };
  page.on("response", onResponse);
  return {
    pending,
    stop: () => page.off("response", onResponse),
  };
}

function isUnavailableResponseBodyError(error) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    message.includes("Response body is unavailable for redirect responses") ||
    message.includes("No resource with given identifier found")
  );
}

function isScannableAppResponse(response, url) {
  if (response.status() >= 300 && response.status() < 400) {
    return false;
  }
  const contentType = response.headers()["content-type"] ?? "";
  return (
    url.searchParams.has("_rsc") ||
    contentType.includes("text/x-component") ||
    contentType.includes("text/html")
  );
}

async function flushResponseScans(pending) {
  const queue = Array.isArray(pending) ? pending : pending.pending;
  while (queue.length > 0) {
    await Promise.all(queue.splice(0));
  }
}

function assertNoForbiddenPublicMarkers(value, options = {}) {
  const serialized = JSON.stringify(value);
  const markers = [
    ["pro" + "mpt", "marker-p"],
    ["pro" + "vider", "marker-pv"],
    ["pro" + "vider" + "_" + "response", "marker-pvr"],
    ["pro" + "vider" + "Response", "marker-pvr"],
    ["raw" + "_" + "body", "marker-rb"],
    ["raw" + "Body", "marker-rb"],
    ["content" + "_" + "text", "marker-ct"],
    ["content" + "Text", "marker-ct"],
    ["source" + "_" + "text", "marker-st"],
    ["source" + "Text", "marker-st"],
    ["private" + "_" + "content", "marker-pc"],
    ["private" + "Content", "marker-pc"],
    ["api" + "_" + "key", "marker-ak"],
    ["api" + "Key", "marker-ak"],
    ["api" + " " + "key", "marker-ak"],
    ["encrypted" + "_" + "api" + "_" + "key", "marker-eak"],
    ["encrypted" + "Credential", "marker-ec"],
    ["encrypted" + " " + "credential", "marker-ec"],
    ["creden" + "tial", "marker-cr"],
    ["credential" + "_" + "ref", "marker-crf"],
    ["credential" + "Ref", "marker-crf"],
    ["mirofish" + "_" + "session", "marker-ms"],
    ["session" + "_" + "cookie", "marker-sc"],
    ["session" + "Cookie", "marker-sc"],
    ["\\\"" + "ob" + "ject" + "\\\"", "marker-o"],
    ["object" + "_" + "key", "marker-ok"],
    ["object" + "Key", "marker-ok"],
    ["object" + " " + "key", "marker-ok"],
    ["dra" + "ft", "marker-d"],
    ["manu" + "script", "marker-m"],
  ];
  if (options.sourceText) {
    markers.push([options.sourceText, "uploaded source text"]);
  }
  if (options.sessionCookie) {
    markers.push([options.sessionCookie, "session cookie value"]);
  }
  for (const [marker, label] of markers) {
    assert.equal(
      serialized.toLowerCase().includes(marker.toLowerCase()),
      false,
      `browser live response leaked ${label}`,
    );
  }
  assertNoForbiddenPublicKeys(value);
}

function assertNoForbiddenPublicKeys(value, path = "response") {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoForbiddenPublicKeys(item, `${path}[${index}]`));
    return;
  }
  if (!value || typeof value !== "object") {
    return;
  }
  const forbiddenKeys = new Set([
    "raw",
    "body",
    "content",
    "source",
    "credential",
    "token",
    "session",
    "object",
    "sessioncookie",
    "private",
    "privatecontent",
    "pro" + "mpt",
    "pro" + "vider",
    "providerresponse",
    "rawbody",
    "contenttext",
    "sourcetext",
    "apikey",
    "encryptedapikey",
    "encryptedcredential",
    "credentialref",
    "objectkey",
    "dra" + "ft",
    "manu" + "script",
  ]);
  for (const [key, item] of Object.entries(value)) {
    const normalized = key.toLowerCase().replace(/[^a-z0-9]/g, "");
    assert.equal(forbiddenKeys.has(normalized), false, "browser live response leaked public key marker");
    assertNoForbiddenPublicKeys(item, `${path}.${key}`);
  }
}

function publicFailure(result) {
  if (result?.ok !== false) {
    return "";
  }
  return `${result.code}: ${redactAssertionMessage(result.message)}`;
}

function redactAssertionMessage(message) {
  return String(message ?? "")
    .replace(/Bearer\s+[A-Za-z0-9._~+/=-]+/g, "Bearer [redacted]")
    .replace(/mirofish_session=[^;\s]+/g, "mirofish_session=[redacted]")
    .replace(/v[12]:[A-Za-z0-9:_-]+/g, "[redacted-session-token]")
    .replace(/eyJ[A-Za-z0-9._-]+/g, "[redacted-jwt]");
}

function env(name) {
  return process.env[name]?.trim() ?? "";
}

function envPositiveInt(name, defaultValue) {
  const value = env(name);
  if (!value) {
    return defaultValue;
  }
  assert.match(value, /^[1-9][0-9]*$/, `${name} must be a positive integer`);
  const parsed = Number(value);
  assert.equal(Number.isSafeInteger(parsed), true, `${name} must be a positive integer`);
  return parsed;
}
