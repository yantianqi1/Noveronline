import assert from "node:assert/strict";
import test from "node:test";

import { loadAssetBrowserConfig } from "./asset-library-live-harness.mjs";

function baseEnv(overrides = {}) {
  return {
    MIROFISH_WEB_BROWSER_LIVE_ASSETS_APP_BASE_URL: "http://127.0.0.1:3000",
    MIROFISH_WEB_BROWSER_LIVE_ASSETS_API_BASE_URL: "http://127.0.0.1:8080",
    MIROFISH_WEB_BROWSER_LIVE_ASSETS_PROVIDER_BASE_URL: "http://127.0.0.1:18080/v1",
    MIROFISH_WEB_BROWSER_LIVE_ASSETS_PROVIDER_MODE: "local",
    MIROFISH_WEB_BROWSER_LIVE_ASSETS_TENANT_ID: "tenant-1",
    MIROFISH_WEB_BROWSER_LIVE_ASSETS_PROJECT_ID: "project-1",
    MIROFISH_WEB_BROWSER_LIVE_ASSETS_SESSION_COOKIE: "session-secret",
    MIROFISH_WEB_BROWSER_LIVE_ASSETS_QUERY: "Moon rule",
    ...overrides,
  };
}

test("asset browser harness accepts an explicit local provider certification", () => {
  const config = loadAssetBrowserConfig(baseEnv());
  assert.equal(config.providerMode, "local");
  assert.equal(config.runReindex, false);
});

test("asset browser harness never labels a local provider as external", () => {
  assert.throws(
    () => loadAssetBrowserConfig(baseEnv({
      MIROFISH_WEB_BROWSER_LIVE_ASSETS_PROVIDER_MODE: "external",
      MIROFISH_WEB_BROWSER_LIVE_ASSETS_ALLOW_EXTERNAL_PROVIDER: "1",
    })),
    /external provider certification requires HTTPS|local provider cannot be certified as external/,
  );
});

test("external provider harness requires a non-local HTTPS endpoint and explicit opt-in", () => {
  assert.throws(
    () => loadAssetBrowserConfig(baseEnv({
      MIROFISH_WEB_BROWSER_LIVE_ASSETS_PROVIDER_MODE: "external",
      MIROFISH_WEB_BROWSER_LIVE_ASSETS_PROVIDER_BASE_URL: "https://provider.example/v1",
    })),
    /ALLOW_EXTERNAL_PROVIDER=1/,
  );
  const config = loadAssetBrowserConfig(baseEnv({
    MIROFISH_WEB_BROWSER_LIVE_ASSETS_PROVIDER_MODE: "external",
    MIROFISH_WEB_BROWSER_LIVE_ASSETS_PROVIDER_BASE_URL: "https://provider.example/v1",
    MIROFISH_WEB_BROWSER_LIVE_ASSETS_ALLOW_EXTERNAL_PROVIDER: "1",
  }));
  assert.equal(config.providerMode, "external");
  assert.equal(config.allowExternalProvider, true);
});

test("mutating reindex browser run requires explicit mutation opt-in", () => {
  assert.throws(
    () => loadAssetBrowserConfig(baseEnv({ MIROFISH_WEB_BROWSER_LIVE_ASSETS_RUN_REINDEX: "1" })),
    /ALLOW_MUTATION=1/,
  );
});
