import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { randomUUID } from "node:crypto";
import { afterEach, test } from "node:test";

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
    const queuedEvent = events.items.find((event) => event.event_type === "workflow.queued");
    assert.ok(queuedEvent, "browser Seed upload did not expose persisted queued progress event");
    assert.equal(queuedEvent.sequence, 1);
    assert.equal(queuedEvent.project_id, config.projectId);
    assert.equal(queuedEvent.payload.status, "queued");
    assert.equal(queuedEvent.payload.workflow_type, "seed_pipeline");
    assert.equal(typeof queuedEvent.payload.upload_id, "string");
    assert.notEqual(queuedEvent.payload.upload_id, "");
    assert.equal(typeof queuedEvent.payload.source_file_id, "string");
    assert.notEqual(queuedEvent.payload.source_file_id, "");

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
