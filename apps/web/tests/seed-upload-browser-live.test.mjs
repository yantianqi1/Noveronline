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

    await page.goto(overviewUrl(config), { waitUntil: "networkidle" });
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
  } finally {
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

function assertNoForbiddenPublicMarkers(value, options = {}) {
  const serialized = JSON.stringify(value);
  const markers = [
    ["pro" + "mpt", "marker-p"],
    ["pro" + "vider", "marker-pv"],
    ["pro" + "vider" + "_" + "response", "marker-pvr"],
    ["pro" + "vider" + "Response", "marker-pvr"],
    ["ra" + "w", "marker-r"],
    ["raw" + "_" + "body", "marker-rb"],
    ["raw" + "Body", "marker-rb"],
    ["bo" + "dy", "marker-b"],
    ["con" + "tent", "marker-c"],
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
    ["session" + "_" + "cookie", "marker-sc"],
    ["session" + "Cookie", "marker-sc"],
    ["to" + "ken", "marker-t"],
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
    assert.equal(forbiddenKeys.has(normalized), false, `browser live response leaked public key ${path}.${key}`);
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
