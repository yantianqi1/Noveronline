import assert from "node:assert/strict";

export const ASSET_BROWSER_PREFIX = "MIROFISH_WEB_BROWSER_LIVE_ASSETS_";

export function hasAssetBrowserConfig(env = process.env) {
  return Object.keys(env).some((key) => key.startsWith(ASSET_BROWSER_PREFIX));
}

export function loadAssetBrowserConfig(env = process.env) {
  const value = (suffix) => env[`${ASSET_BROWSER_PREFIX}${suffix}`]?.trim() || "";
  const config = {
    appBaseUrl: value("APP_BASE_URL"),
    apiBaseUrl: value("API_BASE_URL"),
    providerBaseUrl: value("PROVIDER_BASE_URL"),
    providerMode: value("PROVIDER_MODE") || "local",
    allowExternalProvider: value("ALLOW_EXTERNAL_PROVIDER") === "1",
    tenantId: value("TENANT_ID"),
    projectId: value("PROJECT_ID"),
    sessionCookie: value("SESSION_COOKIE"),
    query: value("QUERY"),
    assetType: value("ASSET_TYPE"),
    category: value("CATEGORY"),
    lifecycle: value("LIFECYCLE"),
    source: value("SOURCE"),
    tag: value("TAG"),
    pinned: value("PINNED"),
    foreignMarker: value("FOREIGN_MARKER"),
    runReindex: value("RUN_REINDEX") === "1",
    allowMutation: value("ALLOW_MUTATION") === "1",
    timeoutMs: positiveInteger(value("TIMEOUT_MS"), 180_000),
    screenshotDir: value("SCREENSHOT_DIR") || "/tmp/mirofish-assets-certification",
  };
  validateAssetBrowserConfig(config);
  return config;
}

export function validateAssetBrowserConfig(config) {
  for (const field of ["appBaseUrl", "apiBaseUrl", "providerBaseUrl", "tenantId", "projectId", "sessionCookie", "query"]) {
    assert.notEqual(config[field], "", `asset browser live config is missing ${field}`);
  }
  assertLocalHttp(config.appBaseUrl, "appBaseUrl");
  assertLocalHttp(config.apiBaseUrl, "apiBaseUrl");
  const provider = new URL(config.providerBaseUrl);
  if (config.providerMode === "external") {
    assert.equal(config.allowExternalProvider, true, "external provider certification requires ALLOW_EXTERNAL_PROVIDER=1");
    assert.equal(provider.protocol, "https:", "external provider certification requires HTTPS");
    assert.equal(isLocalHost(provider.hostname), false, "a local provider cannot be certified as external");
  } else {
    assert.equal(config.providerMode, "local", "PROVIDER_MODE must be local or external");
    assert.equal(provider.protocol, "http:", "local provider certification requires local HTTP");
    assert.equal(isLocalHost(provider.hostname), true, "local provider certification requires localhost or 127.0.0.1");
  }
  if (config.runReindex) {
    assert.equal(config.allowMutation, true, "reindex certification requires ALLOW_MUTATION=1");
  }
  if (config.pinned) {
    assert.ok(["true", "false"].includes(config.pinned), "PINNED must be true or false");
  }
  assert.ok(config.screenshotDir.startsWith("/"), "SCREENSHOT_DIR must be absolute");
}

export function assetPageUrl(config) {
  const url = new URL(`/${encodeURIComponent(config.tenantId)}/projects/${encodeURIComponent(config.projectId)}/assets`, config.appBaseUrl);
  url.searchParams.set("query", config.query);
  url.searchParams.set("mode", "hybrid");
  for (const [key, value] of [
    ["assetType", config.assetType],
    ["category", config.category],
    ["lifecycle", config.lifecycle],
    ["source", config.source],
    ["tag", config.tag],
    ["pinned", config.pinned],
  ]) {
    if (value) url.searchParams.set(key, value);
  }
  return url.toString();
}

export async function waitForAssetReindex(api, config, runId) {
  const deadline = Date.now() + config.timeoutMs;
  while (Date.now() < deadline) {
    const run = await api.getWorkflowRunSummary({
      tenantId: config.tenantId,
      projectId: config.projectId,
      sessionCookie: config.sessionCookie,
      runId,
    });
    assertPublicAssetSurface(run, config);
    assert.equal(run.ok, true, publicFailure(run));
    assert.equal(run.project_id, config.projectId);
    assert.equal(run.workflow_type, "asset_reindex");
    if (["completed", "failed", "cancelled"].includes(run.status)) {
      assert.equal(run.status, "completed", `asset reindex failed with ${run.error_code || run.status}`);
      return run;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  assert.fail(`asset reindex did not finish within ${config.timeoutMs}ms`);
}

export function assertPublicAssetSurface(value, config) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  assert.doesNotMatch(text, /(?:sk-[A-Za-z0-9_-]{8,}|bearer\s+[A-Za-z0-9._-]+|mirofish_session=|encrypted_api_key|credential_ref|provider_response|content_text|query_embedding)/i);
  assert.equal(text.includes(config.sessionCookie), false, "public surface exposed the session cookie");
  if (config.foreignMarker) {
    assert.equal(text.includes(config.foreignMarker), false, "public surface exposed a foreign-tenant marker");
  }
}

export function publicFailure(result) {
  return result?.ok ? "unexpected success" : `${result?.code || "UNKNOWN"}: ${result?.message || "request failed"}`;
}

function assertLocalHttp(value, label) {
  const url = new URL(value);
  assert.equal(url.protocol, "http:", `${label} must use HTTP for local certification`);
  assert.equal(isLocalHost(url.hostname), true, `${label} must use localhost or 127.0.0.1`);
}

function isLocalHost(hostname) {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "::1";
}

function positiveInteger(value, fallback) {
  const number = value ? Number(value) : fallback;
  assert.ok(Number.isSafeInteger(number) && number > 0, "TIMEOUT_MS must be a positive integer");
  return number;
}
