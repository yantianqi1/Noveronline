import assert from "node:assert/strict";
import { test } from "node:test";

import {
  assertNoPrivateGraphKeys,
  BROWSER_LIVE_GRAPH_PREFIX,
  graphUrl,
  loadBrowserLiveGraphConfig,
} from "./story-graph-live-harness.mjs";

test("Story Graph browser live harness stays disabled without explicit environment", () => {
  assert.deepEqual(loadBrowserLiveGraphConfig({}), {
    enabled: false,
    prefix: BROWSER_LIVE_GRAPH_PREFIX,
  });
});

test("Story Graph browser live harness requires a local disposable mutation target", () => {
  const base = validEnvironment();
  assert.throws(
    () => loadBrowserLiveGraphConfig({ ...base, [`${BROWSER_LIVE_GRAPH_PREFIX}ALLOW_MUTATION`]: "0" }),
    /ALLOW_MUTATION/,
  );
  assert.throws(
    () => loadBrowserLiveGraphConfig({ ...base, [`${BROWSER_LIVE_GRAPH_PREFIX}APP_BASE_URL`]: "https:\/\/example.com" }),
    /local http URL/,
  );
});

test("Story Graph browser live harness parses explicit scale and timeout controls", () => {
  const config = loadBrowserLiveGraphConfig({
    ...validEnvironment(),
    [`${BROWSER_LIVE_GRAPH_PREFIX}TIMEOUT_MS`]: "240000",
    [`${BROWSER_LIVE_GRAPH_PREFIX}MIN_NODES`]: "50",
    [`${BROWSER_LIVE_GRAPH_PREFIX}MIN_VIEWPORT_NODES`]: "20",
    [`${BROWSER_LIVE_GRAPH_PREFIX}MIN_EDGES`]: "60",
    [`${BROWSER_LIVE_GRAPH_PREFIX}MIN_EVIDENCE`]: "2",
    [`${BROWSER_LIVE_GRAPH_PREFIX}VIEW_LIMIT`]: "120",
    [`${BROWSER_LIVE_GRAPH_PREFIX}SCREENSHOT_DIR`]: "/tmp/graph-live-shots",
    [`${BROWSER_LIVE_GRAPH_PREFIX}REPORT_PATH`]: "/tmp/graph-live-report.json",
  });
  assert.equal(config.enabled, true);
  assert.equal(config.timeoutMs, 240000);
  assert.equal(config.minNodes, 50);
  assert.equal(config.minViewportNodes, 20);
  assert.equal(config.minEdges, 60);
  assert.equal(config.minEvidence, 2);
  assert.equal(config.viewLimit, 120);
  assert.equal(config.screenshotDir, "/tmp/graph-live-shots");
  assert.equal(config.reportPath, "/tmp/graph-live-report.json");
  assert.equal(
    graphUrl(config),
    "http://127.0.0.1:3999/tenant-live/projects/project-disposable/graph",
  );
});

test("Story Graph live evidence audit rejects private runtime fields recursively", () => {
  assert.doesNotThrow(() => assertNoPrivateGraphKeys({ items: [{ source_id: "entity-1", confidence: 0.8 }] }));
  assert.throws(
    () => assertNoPrivateGraphKeys({ items: [{ metadata: { snippet: "private source" } }] }),
    /private Story Graph field exposed at response\.items\[0\]\.metadata\.snippet/,
  );
});

function validEnvironment() {
  return {
    [`${BROWSER_LIVE_GRAPH_PREFIX}APP_BASE_URL`]: "http://127.0.0.1:3999",
    [`${BROWSER_LIVE_GRAPH_PREFIX}API_BASE_URL`]: "http://127.0.0.1:3888",
    [`${BROWSER_LIVE_GRAPH_PREFIX}TENANT_ID`]: "tenant-live",
    [`${BROWSER_LIVE_GRAPH_PREFIX}PROJECT_ID`]: "project-disposable",
    [`${BROWSER_LIVE_GRAPH_PREFIX}SESSION_COOKIE`]: "v2:test-session",
    [`${BROWSER_LIVE_GRAPH_PREFIX}DISPOSABLE_PROJECT_MARKER`]: "disposable",
    [`${BROWSER_LIVE_GRAPH_PREFIX}ALLOW_MUTATION`]: "1",
    [`${BROWSER_LIVE_GRAPH_PREFIX}THROWAWAY_PROJECT`]: "1",
  };
}
