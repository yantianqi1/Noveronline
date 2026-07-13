import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import { chromium } from "playwright";

const prefix = "MIROFISH_WEB_BROWSER_LIVE_WRITER_";
const configured = Object.keys(process.env).some((name) => name.startsWith(prefix));
const browserTest = configured ? test : test.skip;

browserTest("Writer start, recovery, refresh, explicit adoption, and TXT download", { timeout: 240_000 }, async () => {
  const config = loadConfig();
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ locale: "en-US" });
  const sessionResponse = await context.request.post(`${config.apiBaseURL}/v1/auth/dev-sessions`, {
    data: { user_id: config.userId },
  });
  assert.equal(sessionResponse.status(), 201, "writer browser fixture could not create an authenticated session");
  await context.addCookies([{ name: "mirofish_locale", value: "en", url: config.appBaseURL, sameSite: "Lax" }]);
  const page = await context.newPage();
  const consoleMessages = [];
  const rscBodies = [];
  page.on("console", (message) => consoleMessages.push(message.text()));
  page.on("response", async (response) => {
    const contentType = response.headers()["content-type"] || "";
    if (contentType.includes("text/x-component")) {
      rscBodies.push(await response.text().catch(() => ""));
    }
  });

  try {
    await page.goto(writerURL(config), { waitUntil: "networkidle" });
    if (!config.resumeRunId) {
      assert.equal(await page.getByRole("link", { name: "Download completed TXT", exact: true }).count(), 0);
      const emptyArtifact = await context.request.get(`${config.appBaseURL}/api/manuscript-export/${config.tenantId}/${config.projectId}?exportId=missing-export`);
      assert.notEqual(emptyArtifact.status(), 200, "writer download must fail closed before an artifact exists");

      await page.getByLabel("Instruction").fill("CANCEL_BOUNDARY keep this run active until the user cancels it.");
      await Promise.all([
        page.waitForURL(/\?[^#]*runId=/, { timeout: config.timeoutMs }),
        page.getByRole("button", { name: "Start writer run", exact: true }).click(),
      ]);
      await waitForButton(page, "Cancel writer run", config.timeoutMs);
      await submitServerAction(page, page.getByRole("button", { name: "Cancel writer run", exact: true }), config.timeoutMs);
      await waitForRunStatus(page, "cancelled", config.timeoutMs);
      const cancelledRunId = new URL(page.url()).searchParams.get("runId");
      assert.ok(cancelledRunId, "cancelled writer run lost its run id");
      assert.match(await page.locator("body").innerText(), /cancelled/i);
      assert.equal(await page.getByRole("button", { name: "Adopt draft into manuscript", exact: true }).count(), 0);
      await page.waitForTimeout(5_500);

      await page.getByLabel("Instruction").fill("Draft a restrained negotiation in the rain.");
      await page.getByLabel(/Mara Venn/).first().check();
      await page.getByLabel(/Mara Venn/).nth(1).check();
      const savedPathCheckbox = page.locator(`input[name="worldlinePathIds"][value="${config.worldlinePathId}"]`);
      if (await savedPathCheckbox.count()) {
        await savedPathCheckbox.check();
      } else {
        await page.locator('input[name="worldlinePathIds"]').first().check();
      }
      await Promise.all([
        page.waitForURL((url) => {
          const nextRunId = url.searchParams.get("runId");
          return Boolean(nextRunId && nextRunId !== cancelledRunId);
        }, { timeout: config.timeoutMs }),
        page.getByRole("button", { name: "Start writer run", exact: true }).click(),
      ]);
    }
    const runId = new URL(page.url()).searchParams.get("runId");
    assert.ok(runId, "writer start did not return a run id");
    assert.doesNotMatch(await page.locator("body").innerText(), /DRAFT_ADOPTED/);

    const eventRows = await waitForTerminal(page, config.timeoutMs);
    assert.equal(eventRows.filter((row) => row.type === "writer.run.completed").length, 1);
    assert.ok(eventRows.some((row) => row.type === "writer.token"), "writer stream did not expose token events");
    assert.ok(eventRows.some((row) => row.type === "writer.tool.completed"), "writer stream did not expose tool completion");
    const fullReplayURL = new URL(page.url());
    fullReplayURL.searchParams.delete("after_event_id");
    await page.goto(fullReplayURL.toString(), { waitUntil: "networkidle" });
    const bodyAfterRun = await page.locator("body").innerText();
    for (const toolName of ["query_assets", "query_graph_neighbors", "query_worldline_paths"]) {
      assert.match(bodyAfterRun, new RegExp(toolName), `${toolName} result card was not visible`);
    }

    if (!config.resumeRunId) {
      const cursor = eventRows.findLast((row) => row.type === "writer.token");
      assert.ok(cursor?.id, "writer stream did not expose a reconnect cursor");
      const reconnectURL = new URL(page.url());
      reconnectURL.searchParams.set("after_event_id", cursor.id);
      await page.goto(reconnectURL.toString(), { waitUntil: "networkidle" });
      const replayRows = await writerEventRows(page);
      assert.ok(replayRows.length > 0, "reconnect returned no events after the selected cursor");
      assert.ok(replayRows.every((row) => row.sequence > cursor.sequence), "reconnect repeated an event at or before the cursor");
      assert.equal(replayRows.filter((row) => row.type === "writer.run.completed").length, 1);
      await page.reload({ waitUntil: "networkidle" });
      await waitForRecoveredRows(page, replayRows, config.timeoutMs);
    } else {
      await page.reload({ waitUntil: "networkidle" });
      assert.equal((await writerEventRows(page)).filter((row) => row.type === "writer.run.completed").length, 1);
    }
    assert.match(await page.locator("body").innerText(), /candidate/i);
    await openWriterTab(page, "Review");
    if (!(await page.getByText("pov_drift", { exact: false }).count())) {
      await submitServerAction(page, page.getByRole("button", { name: "Start reviewer", exact: true }), config.timeoutMs);
    }
    await waitForReviewerIssue(page, config.timeoutMs);
    await openWriterTab(page, "Review");
    assert.match(await page.locator("body").innerText(), /pov_drift/);
    assert.doesNotMatch(await page.locator("body").innerText(), /DRAFT_ADOPTED/);
    const acceptButton = page.getByRole("button", { name: "Accepted", exact: true });
    if (await acceptButton.count()) {
      await submitServerAction(page, acceptButton, config.timeoutMs);
      await openWriterTab(page, "Review");
      await waitForButtonGone(page, "Accepted", config.timeoutMs);
    }
    assert.match(await page.locator("body").innerText(), /accepted/i);
    const adoptButton = page.getByRole("button", { name: "Adopt draft into manuscript", exact: true });
    if (await adoptButton.count()) {
      await submitServerAction(page, adoptButton, config.timeoutMs);
      await waitForBody(page, /Blocks\s+1/i, config.timeoutMs);
    }
    assert.match(await page.locator("body").innerText(), /DRAFT_ADOPTED|Adopted/i);
    assert.match(await page.locator("body").innerText(), /Blocks\s+1/);

    await openWriterTab(page, "Studio");
    await submitServerAction(page, page.getByRole("button", { name: "Generate candidate plan", exact: true }), config.timeoutMs);
    const bookPlanningRunId = await waitForPlanningRunSelection(page, config.timeoutMs);
    const bookPlanningRun = await waitForPlanningRun(context, config, bookPlanningRunId);
    assert.equal(bookPlanningRun.workflow_type, "writer_book_plan_generation");
    await page.reload({ waitUntil: "networkidle" });
    await openWriterTab(page, "Studio");
    assert.match(await page.locator("body").innerText(), /Rain Gate Plan[\s\S]*Draft[\s\S]*Completed/i);

    await openWriterTab(page, "Manuscript");
    const adoptedBlockButton = page.locator('form[action$="/writer"] button').filter({ hasText: /^#\d+$/ }).first();
    assert.equal(await adoptedBlockButton.count(), 1, "adopted manuscript block was not selectable");
    await adoptedBlockButton.click();
    await page.waitForLoadState("networkidle");
    assert.ok(new URL(page.url()).searchParams.get("blockId"), "selected adopted block was not retained in the URL");
    await openWriterTab(page, "Studio");
    await submitServerAction(page, page.getByRole("button", { name: "Extract candidate patterns", exact: true }), config.timeoutMs);
    const dedupPlanningRunId = await waitForPlanningRunSelection(page, config.timeoutMs, bookPlanningRunId);
    const dedupPlanningRun = await waitForPlanningRun(context, config, dedupPlanningRunId);
    assert.equal(dedupPlanningRun.workflow_type, "writer_dedup_extraction");
    await page.reload({ waitUntil: "networkidle" });
    await openWriterTab(page, "Studio");
    assert.match(await page.locator("body").innerText(), /Repeated threshold gesture/);
    assert.match(await page.locator("body").innerText(), /Candidate/i);

    const bookPlansResponse = await context.request.get(`${config.apiBaseURL}/v1/projects/${config.projectId}/book-plans`, { headers: { "X-Tenant-Id": config.tenantId } });
    assert.equal(bookPlansResponse.status(), 200);
    const bookPlansPayload = await bookPlansResponse.json();
    const generatedPlan = bookPlansPayload.data.find((item) => item.book_plan_id === config.bookPlanId);
    assert.equal(generatedPlan.status, "draft", "book planning activated a draft without explicit user action");
    assert.equal(generatedPlan.last_run_status, "completed");
    assert.equal(generatedPlan.optimistic_version, 2);
    const dedupResponse = await context.request.get(`${config.apiBaseURL}/v1/projects/${config.projectId}/manuscript-workspace/dedup-patterns?lifecycle=candidate`, { headers: { "X-Tenant-Id": config.tenantId } });
    assert.equal(dedupResponse.status(), 200);
    const dedupPayload = await dedupResponse.json();
    const extractedPattern = dedupPayload.patterns.find((item) => item.pattern_text === "Repeated threshold gesture");
    assert.ok(extractedPattern, "dedup extraction did not persist a visible candidate");
    assert.equal(extractedPattern.lifecycle, "candidate");
    assert.equal(extractedPattern.enabled, false, "dedup extraction enabled a candidate without explicit acceptance");

    await page.reload({ waitUntil: "networkidle" });
    await openWriterTab(page, "Studio");
    assert.equal(new URL(page.url()).searchParams.get("planningRunId"), dedupPlanningRunId, "refresh lost the planning run recovery id");
    assert.match(await page.locator("body").innerText(), /Dedup extraction[\s\S]*Completed/i);

    await submitServerAction(page, page.getByRole("button", { name: "Generate TXT artifact", exact: true }), config.timeoutMs);
    await waitForLink(page, "Download completed TXT", config.timeoutMs);
    const downloadLink = page.getByRole("link", { name: "Download completed TXT", exact: true });
    const downloadURL = new URL(await downloadLink.getAttribute("href"), page.url()).toString();
    const artifactResponse = await context.request.get(downloadURL);
    assert.equal(artifactResponse.status(), 200);
    const artifactBytes = await artifactResponse.body();
    const downloadPromise = page.waitForEvent("download");
    await downloadLink.click();
    const download = await downloadPromise;
    const contentDisposition = artifactResponse.headers()["content-disposition"] || "";
    const expectedHash = artifactResponse.headers()["x-content-sha256"] || "";
    assert.match(contentDisposition, /^attachment; filename="[A-Za-z0-9_-]+\.txt"$/);
    assert.match(expectedHash, /^[0-9a-f]{64}$/);
    const downloadPath = await download.path();
    assert.ok(downloadPath, "Playwright download did not produce a local artifact");
    const content = await readFile(downloadPath);
    assert.ok(content.length > 0, "downloaded manuscript is empty");
    assert.deepEqual(content, artifactBytes, "UI download differs from the same-origin artifact response");
    assert.equal(createHash("sha256").update(content).digest("hex"), expectedHash);
    assert.doesNotMatch(content.toString("utf8", 0, Math.min(content.length, 80)), /^\s*[\[{]/, "download returned metadata instead of TXT prose");

    assertPublicSurface(await page.locator("body").innerText(), "DOM");
    assertPublicSurface(consoleMessages.join("\n"), "console");
    assertPublicSurface(rscBodies.join("\n"), "RSC");
    for (const privateSentinel of ["Private Writer reference body.", "writer-browser-local-key"]) {
      assert.doesNotMatch(await page.locator("body").innerText(), new RegExp(privateSentinel.replaceAll(".", "\\.")), "DOM exposed a private sentinel");
      assert.doesNotMatch(rscBodies.join("\n"), new RegExp(privateSentinel.replaceAll(".", "\\.")), "RSC exposed a private sentinel");
    }
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true, "desktop writer workspace overflowed horizontally");
    await mkdir(config.screenshotDir, { recursive: true });
    await openWriterTab(page, "Manuscript");
    await page.screenshot({ path: path.join(config.screenshotDir, "writer-planning-desktop.png"), fullPage: true });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.reload({ waitUntil: "networkidle" });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth), true, "mobile writer workspace overflowed horizontally");
    await openWriterTab(page, "Structure");
    assert.equal(await page.getByRole("heading", { name: "Chapters and scenes" }).count(), 1);
    await openWriterTab(page, "Studio");
    assert.match(await page.locator("body").innerText(), /Repeated threshold gesture/);
    await page.screenshot({ path: path.join(config.screenshotDir, "writer-planning-mobile.png"), fullPage: true });
  } finally {
    await context.close();
    await browser.close();
  }
});

async function waitForReviewerIssue(page, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await page.getByText("pov_drift", { exact: false }).count()) return;
    await page.waitForTimeout(500);
    await page.reload({ waitUntil: "networkidle" });
  }
  assert.fail("writer reviewer did not return an issue before timeout");
}

async function openWriterTab(page, name) {
  const tab = page.getByRole("tab", { name, exact: true });
  assert.equal(await tab.count(), 1, `writer artifact tab ${name} was not available`);
  await tab.click();
}

async function waitForPlanningRunSelection(page, timeoutMs, previousRunId = "") {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const runId = new URL(page.url()).searchParams.get("planningRunId") || "";
    if (runId && runId !== previousRunId) return runId;
    await page.waitForTimeout(250);
  }
  const url = new URL(page.url());
  const status = url.searchParams.get("workspaceStatus") || "missing";
  const code = url.searchParams.get("workspaceCode") || "missing";
  assert.fail(`writer planning action did not retain a new run id (workspaceStatus=${status}, workspaceCode=${code})`);
}

async function waitForPlanningRun(context, config, runId) {
  const deadline = Date.now() + config.timeoutMs;
  while (Date.now() < deadline) {
    const response = await context.request.get(`${config.apiBaseURL}/v1/workflow-runs/${runId}`, { headers: { "X-Tenant-Id": config.tenantId } });
    assert.equal(response.status(), 200, `planning workflow query returned HTTP ${response.status()}`);
    const payload = await response.json();
    if (payload.status === "completed") return payload;
    assert.notEqual(payload.status, "failed", `planning workflow failed with ${payload.error_code || "unknown"}`);
    assert.notEqual(payload.status, "cancelled", "planning workflow was unexpectedly cancelled");
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  assert.fail(`planning workflow ${runId} did not complete before timeout`);
}

async function submitServerAction(page, button, timeoutMs) {
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
    assert.equal(redirectURL.origin, new URL(page.url()).origin, "writer server action redirected outside the application origin");
    await page.goto(redirectURL.toString(), { waitUntil: "networkidle" });
  }
}

async function waitForButton(page, name, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await page.getByRole("button", { name, exact: true }).count()) return;
    await page.waitForTimeout(250);
    await page.reload({ waitUntil: "networkidle" });
  }
  assert.fail(`${name} did not become available before timeout`);
}

async function waitForLink(page, name, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await page.getByRole("link", { name, exact: true }).count()) return;
    await page.waitForTimeout(250);
    await page.reload({ waitUntil: "networkidle" });
  }
  assert.fail(`${name} did not become available before timeout`);
}

async function waitForButtonGone(page, name, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (!(await page.getByRole("button", { name, exact: true }).count())) return;
    await page.waitForTimeout(500);
    await page.reload({ waitUntil: "networkidle" });
  }
  assert.fail(`${name} remained available after timeout`);
}

async function waitForBody(page, pattern, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (pattern.test(await page.locator("body").innerText())) return;
    await page.waitForTimeout(500);
    await page.reload({ waitUntil: "networkidle" });
  }
  assert.fail(`${pattern} did not become visible before timeout`);
}

async function waitForRunStatus(page, status, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const body = await page.locator("body").innerText();
    if (new RegExp(`Status:\\s*${status}`, "i").test(body)) return;
    await page.waitForTimeout(500);
    await page.reload({ waitUntil: "networkidle" });
  }
  assert.fail(`writer run did not reach ${status} before timeout`);
}

async function waitForRecoveredRows(page, expected, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const actual = await writerEventRows(page);
    if (JSON.stringify(actual) === JSON.stringify(expected)) return;
    await page.waitForTimeout(500);
    await page.goto(page.url(), { waitUntil: "networkidle" });
  }
  assert.deepEqual(await writerEventRows(page), expected, "refresh changed the recovered event window");
}

async function waitForTerminal(page, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  const recovered = new Map();
  let highestSequence = 0;
  while (Date.now() < deadline) {
    const body = await page.locator("body").innerText();
    assert.doesNotMatch(body, /writer\.run\.failed/);
    const window = await writerEventRows(page);
    for (const row of window) {
      const existing = recovered.get(row.id);
      assert.equal(existing, undefined, `reconnect repeated event ${row.id}`);
      assert.ok(row.sequence > highestSequence, "reconnect event sequence did not advance monotonically");
      recovered.set(row.id, row);
      highestSequence = row.sequence;
    }
    if (window.some((row) => row.type === "writer.run.completed")) return [...recovered.values()];
    const reconnect = page.getByRole("button", { name: "Reconnect after latest event", exact: true });
    if (await reconnect.count()) {
      await reconnect.click();
      await page.waitForLoadState("networkidle");
    } else {
      await page.waitForTimeout(1000);
      await page.reload({ waitUntil: "networkidle" });
    }
  }
  assert.fail("writer run did not reach completed before the browser timeout");
}

async function writerEventRows(page) {
  return page.locator("#workflow-events-heading + .compact-action-list ~ form + .trace-list .trace-event").evaluateAll((rows) =>
    rows.map((row) => {
      const header = row.querySelector(".trace-event-header");
      const meta = row.querySelector(".trace-meta")?.textContent || "";
      return {
        type: header?.querySelector("strong")?.textContent?.trim() || "",
        sequence: Number((header?.querySelector(".trace-redaction")?.textContent || "").replace("#", "")),
        id: meta.split("/")[0]?.trim() || "",
      };
    }),
  );
}

function writerURL(config) {
  const url = new URL(`/${config.tenantId}/projects/${config.projectId}/writer`, config.appBaseURL);
  if (config.resumeRunId) url.searchParams.set("runId", config.resumeRunId);
  return url.toString();
}

function loadConfig() {
  const value = (suffix) => process.env[`${prefix}${suffix}`]?.trim() || "";
  const config = {
    appBaseURL: value("APP_BASE_URL"),
    apiBaseURL: value("API_BASE_URL"),
    tenantId: value("TENANT_ID"),
    projectId: value("PROJECT_ID"),
    userId: value("USER_ID"),
    worldlinePathId: value("WORLDLINE_PATH_ID"),
    bookPlanId: value("BOOK_PLAN_ID"),
    resumeRunId: value("RESUME_RUN_ID"),
    timeoutMs: Number(value("TIMEOUT_MS") || 180_000),
    screenshotDir: path.resolve(value("SCREENSHOT_DIR") || "test-results/writer-browser-live"),
  };
  for (const [name, field] of [["APP_BASE_URL", "appBaseURL"], ["API_BASE_URL", "apiBaseURL"], ["TENANT_ID", "tenantId"], ["PROJECT_ID", "projectId"], ["USER_ID", "userId"], ["WORLDLINE_PATH_ID", "worldlinePathId"], ["BOOK_PLAN_ID", "bookPlanId"]]) {
    if (!config[field]) throw new Error(`writer browser live config is missing ${prefix}${name}`);
  }
  const appURL = new URL(config.appBaseURL);
  const apiURL = new URL(config.apiBaseURL);
  if ([appURL, apiURL].some((url) => url.protocol !== "http:" || !["127.0.0.1", "localhost"].includes(url.hostname))) {
    throw new Error("writer browser live app and API URLs must be local HTTP");
  }
  if (!Number.isSafeInteger(config.timeoutMs) || config.timeoutMs <= 0) throw new Error("writer browser live timeout must be a positive integer");
  return config;
}

function assertPublicSurface(text, surface) {
  assert.doesNotMatch(text, /(?:sk-[A-Za-z0-9_-]{8,}|bearer\s+[A-Za-z0-9._-]+|mirofish_session=|encrypted_api_key|credential_ref|provider_response|content_text)/i, `${surface} exposed a sensitive marker`);
}
