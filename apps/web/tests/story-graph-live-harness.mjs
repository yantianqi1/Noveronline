import assert from "node:assert/strict";

import {
  assertLocalHttpUrl,
  assertNoForbiddenPublicMarkers,
  publicFailure,
} from "./live-seed-harness.mjs";

export const BROWSER_LIVE_GRAPH_PREFIX = "MIROFISH_WEB_BROWSER_LIVE_GRAPH_";

const DEFAULT_TIMEOUT_MS = 180000;
const DEFAULT_SCREENSHOT_DIR = "/tmp/mirofish-story-graph-certification";
const PRIVATE_GRAPH_KEYS = new Set([
  "api_key",
  "candidate_body",
  "content_text",
  "credential_ref",
  "encrypted_api_key",
  "prompt",
  "provider_response",
  "raw_body",
  "raw_content",
  "response",
  "snippet",
  "source_text",
]);

export function hasBrowserLiveGraphConfig(env = process.env) {
  return Object.keys(env).some((name) => name.startsWith(BROWSER_LIVE_GRAPH_PREFIX));
}

export function loadBrowserLiveGraphConfig(env = process.env) {
  if (!hasBrowserLiveGraphConfig(env)) {
    return { enabled: false, prefix: BROWSER_LIVE_GRAPH_PREFIX };
  }

  const config = {
    enabled: true,
    prefix: BROWSER_LIVE_GRAPH_PREFIX,
    appBaseUrl: envText(env, "APP_BASE_URL"),
    apiBaseUrl: envText(env, "API_BASE_URL"),
    tenantId: envText(env, "TENANT_ID"),
    projectId: envText(env, "PROJECT_ID"),
    sessionCookie: envText(env, "SESSION_COOKIE"),
    disposableProjectMarker: envText(env, "DISPOSABLE_PROJECT_MARKER"),
    allowMutation: envText(env, "ALLOW_MUTATION") === "1",
    throwawayProject: envText(env, "THROWAWAY_PROJECT") === "1",
    timeoutMs: positiveInteger(envText(env, "TIMEOUT_MS"), DEFAULT_TIMEOUT_MS),
    minNodes: positiveInteger(envText(env, "MIN_NODES"), 1001),
    minViewportNodes: positiveInteger(envText(env, "MIN_VIEWPORT_NODES"), 250),
    minEdges: positiveInteger(envText(env, "MIN_EDGES"), 1000),
    minEvidence: positiveInteger(envText(env, "MIN_EVIDENCE"), 1),
    viewLimit: positiveInteger(envText(env, "VIEW_LIMIT"), 300),
    screenshotDir: envText(env, "SCREENSHOT_DIR") || DEFAULT_SCREENSHOT_DIR,
    reportPath: envText(env, "REPORT_PATH") || `${DEFAULT_SCREENSHOT_DIR}/report.json`,
  };
  assertBrowserLiveGraphConfig(config);
  return config;
}

export function assertBrowserLiveGraphConfig(config) {
  const missing = [];
  for (const [field, suffix] of [
    ["appBaseUrl", "APP_BASE_URL"],
    ["apiBaseUrl", "API_BASE_URL"],
    ["tenantId", "TENANT_ID"],
    ["projectId", "PROJECT_ID"],
    ["sessionCookie", "SESSION_COOKIE"],
    ["disposableProjectMarker", "DISPOSABLE_PROJECT_MARKER"],
  ]) {
    if (!config[field]) {
      missing.push(`${BROWSER_LIVE_GRAPH_PREFIX}${suffix}`);
    }
  }
  if (!config.allowMutation) {
    missing.push(`${BROWSER_LIVE_GRAPH_PREFIX}ALLOW_MUTATION`);
  }
  if (!config.throwawayProject) {
    missing.push(`${BROWSER_LIVE_GRAPH_PREFIX}THROWAWAY_PROJECT`);
  }
  if (missing.length > 0) {
    throw new Error(`live Story Graph config is incomplete; missing env names: ${missing.join(", ")}`);
  }
  assertLocalHttpUrl(config.appBaseUrl, "live Story Graph app base URL");
  assertLocalHttpUrl(config.apiBaseUrl, "live Story Graph API base URL");
  if (config.viewLimit < config.minViewportNodes) {
    throw new Error("live Story Graph VIEW_LIMIT must be at least MIN_VIEWPORT_NODES");
  }
  assertAbsoluteLocalPath(config.screenshotDir, "SCREENSHOT_DIR");
  assertAbsoluteLocalPath(config.reportPath, "REPORT_PATH");
}

export async function assertDisposableGraphProject(api, config) {
  const currentUser = await api.getCurrentUser({ sessionCookie: config.sessionCookie });
  assertNoForbiddenPublicMarkers(currentUser, { sessionCookie: config.sessionCookie });
  assert.equal(currentUser.ok, true, publicFailure(currentUser, { sessionCookie: config.sessionCookie }));
  const project = currentUser.active_projects.find(
    (item) => item.tenant_id === config.tenantId && item.project_id === config.projectId && item.status === "active",
  );
  assert.ok(project, "live Story Graph project must be active for the session user");
  const identity = `${project.project_id} ${project.name}`.toLowerCase();
  assert.equal(
    identity.includes(config.disposableProjectMarker.toLowerCase()),
    true,
    "live Story Graph target must contain the disposable project marker",
  );
}

export function graphUrl(config, query = {}) {
  const url = new URL(
    `/${encodeURIComponent(config.tenantId)}/projects/${encodeURIComponent(config.projectId)}/graph`,
    config.appBaseUrl,
  );
  for (const [key, value] of Object.entries(query)) {
    if (value) {
      url.searchParams.set(key, value);
    }
  }
  return url.toString();
}

export async function addGraphSessionCookies(context, config) {
  await context.addCookies([
    {
      name: "mirofish_session",
      value: config.sessionCookie,
      url: config.appBaseUrl,
      httpOnly: true,
      sameSite: "Lax",
    },
    {
      name: "mirofish_locale",
      value: "en",
      url: config.appBaseUrl,
      sameSite: "Lax",
    },
  ]);
}

export async function waitForWorkflowTerminal(api, config, runId, workflowType) {
  const deadline = Date.now() + config.timeoutMs;
  let latest;
  while (Date.now() <= deadline) {
    latest = await api.getWorkflowRunSummary({
      tenantId: config.tenantId,
      sessionCookie: config.sessionCookie,
      runId,
    });
    assertNoForbiddenPublicMarkers(latest, { sessionCookie: config.sessionCookie });
    assert.equal(latest.ok, true, publicFailure(latest, { sessionCookie: config.sessionCookie }));
    assert.equal(latest.project_id, config.projectId, "workflow run belongs to another project");
    assert.equal(latest.workflow_type, workflowType, "workflow type does not match the browser action");
    if (["completed", "failed", "cancelled"].includes(latest.status)) {
      assert.equal(
        latest.status,
        "completed",
        `${workflowType} did not complete: ${latest.error_code || latest.status}`,
      );
      return latest;
    }
    await delay(500);
  }
  assert.fail(`${workflowType} did not reach a terminal status before ${config.timeoutMs}ms`);
}

export async function waitForBuiltGraph(api, config, runId) {
  const deadline = Date.now() + config.timeoutMs;
  let latest;
  while (Date.now() <= deadline) {
    latest = await api.getStoryGraphCurrent(graphApiContext(config));
    assertNoForbiddenPublicMarkers(latest, { sessionCookie: config.sessionCookie });
    if (latest.ok && latest.status === "ready" && latest.build_run_id === runId) {
      return latest;
    }
    await delay(500);
  }
  assert.fail(`Story Graph current snapshot did not project build run ${runId}`);
}

export async function waitForRunCandidate(api, config, runId) {
  const sourcePrefix = `graph-bond:${runId}:`;
  const deadline = Date.now() + config.timeoutMs;
  let latest;
  while (Date.now() <= deadline) {
    latest = await api.getProjectAssets(graphApiContext(config));
    assertNoForbiddenPublicMarkers(latest, { sessionCookie: config.sessionCookie });
    assert.equal(latest.ok, true, publicFailure(latest, { sessionCookie: config.sessionCookie }));
    const candidate = latest.items.find(
      (item) => item.source_kind === "graph_bond_generation" && item.source_ref.startsWith(sourcePrefix),
    );
    if (candidate) {
      assert.equal(candidate.lifecycle, "candidate", "generated Graph candidate became canon without adoption");
      assert.ok(
        candidate.asset_type === "graph_bond" || candidate.asset_type === "plot_thread",
        `unsupported generated Graph candidate type: ${candidate.asset_type}`,
      );
      return candidate;
    }
    const run = await api.getWorkflowRunSummary({
      tenantId: config.tenantId,
      sessionCookie: config.sessionCookie,
      runId,
    });
    assertNoForbiddenPublicMarkers(run, { sessionCookie: config.sessionCookie });
    if (run.ok && ["failed", "cancelled"].includes(run.status)) {
      assert.fail(`Story Graph bond workflow did not complete: ${run.error_code || run.status}`);
    }
    await delay(500);
  }
  assert.fail(`Story Graph bond run ${runId} did not persist a candidate asset`);
}

export async function assertGraphDataScale(api, config, current) {
  assert.ok(current.node_count >= config.minNodes, `expected at least ${config.minNodes} graph nodes`);
  assert.ok(current.edge_count >= config.minEdges, `expected at least ${config.minEdges} graph edges`);
  const view = await api.getStoryGraphView({
    ...graphApiContext(config),
    viewId: "world",
    limit: config.viewLimit,
    includeEdges: true,
  });
  assertNoForbiddenPublicMarkers(view, { sessionCookie: config.sessionCookie });
  assert.equal(view.ok, true, publicFailure(view, { sessionCookie: config.sessionCookie }));
  assert.equal(view.graph_id, current.graph_id);
  assert.ok(view.nodes.length >= config.minViewportNodes, "DB-backed world view is missing built nodes");
  assert.ok(view.edges.length > 0, "DB-backed world view is missing paged graph edges");

  const evidence = await api.getStoryGraphEvidence({
    ...graphApiContext(config),
    ownerType: "node",
    ownerId: view.nodes[0].node_id,
    limit: 25,
  });
  assertNoForbiddenPublicMarkers(evidence, { sessionCookie: config.sessionCookie });
  assert.equal(evidence.ok, true, publicFailure(evidence, { sessionCookie: config.sessionCookie }));
  assert.equal(evidence.graph_id, current.graph_id);
  assert.ok(evidence.items.length >= config.minEvidence, `expected at least ${config.minEvidence} evidence records`);
  const rawEvidence = await fetchGraphPublicJson(
    config,
    `/v1/projects/${encodeURIComponent(config.projectId)}/story-graph/nodes/${encodeURIComponent(view.nodes[0].node_id)}/evidence?limit=25`,
  );
  assertNoPrivateGraphKeys(rawEvidence);
  return { view, evidence };
}

export async function fetchGraphPublicJson(config, path) {
  assert.equal(path.startsWith("/"), true, "Story Graph public fetch path must be absolute");
  assert.equal(path.startsWith("//"), false, "Story Graph public fetch path must stay on API base");
  const base = assertLocalHttpUrl(config.apiBaseUrl, "live Story Graph API base URL");
  const url = new URL(path, base);
  assert.equal(url.origin, base.origin, "Story Graph public fetch URL must stay on API base");
  const response = await fetch(url, {
    headers: {
      "X-Tenant-Id": config.tenantId,
      Cookie: `mirofish_session=${config.sessionCookie}`,
    },
  });
  const raw = await response.text();
  let payload;
  try {
    payload = JSON.parse(raw);
  } catch {
    assert.fail(`Story Graph public API returned non-JSON HTTP ${response.status}`);
  }
  assert.equal(response.ok, true, `Story Graph public API failed with HTTP ${response.status}`);
  return payload;
}

export function assertNoPrivateGraphKeys(value, path = "response") {
  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoPrivateGraphKeys(item, `${path}[${index}]`));
    return;
  }
  if (!value || typeof value !== "object") {
    return;
  }
  for (const [key, item] of Object.entries(value)) {
    const normalized = key.trim().toLowerCase().replaceAll("-", "_");
    assert.equal(PRIVATE_GRAPH_KEYS.has(normalized), false, `private Story Graph field exposed at ${path}.${key}`);
    assertNoPrivateGraphKeys(item, `${path}.${key}`);
  }
}

export async function assertNoElementOverlap(locator, label) {
  const boxes = (await locator.evaluateAll((elements) => elements.map((element) => {
    const rect = element.getBoundingClientRect();
    return {
      left: rect.left,
      right: rect.right,
      top: rect.top,
      bottom: rect.bottom,
      width: rect.width,
      height: rect.height,
    };
  }))).filter((box) => box.width > 0 && box.height > 0);
  assert.ok(boxes.length > 0, `${label} did not render any visible elements`);
  for (let leftIndex = 0; leftIndex < boxes.length; leftIndex += 1) {
    for (let rightIndex = leftIndex + 1; rightIndex < boxes.length; rightIndex += 1) {
      const left = boxes[leftIndex];
      const right = boxes[rightIndex];
      const overlapWidth = Math.min(left.right, right.right) - Math.max(left.left, right.left);
      const overlapHeight = Math.min(left.bottom, right.bottom) - Math.max(left.top, right.top);
      assert.equal(
        overlapWidth > 1 && overlapHeight > 1,
        false,
        `${label} elements ${leftIndex} and ${rightIndex} overlap`,
      );
    }
  }
}

export function graphApiContext(config) {
  return {
    tenantId: config.tenantId,
    projectId: config.projectId,
    sessionCookie: config.sessionCookie,
  };
}

function envText(env, suffix) {
  const value = env[`${BROWSER_LIVE_GRAPH_PREFIX}${suffix}`];
  return typeof value === "string" ? value.trim() : "";
}

function positiveInteger(raw, fallback) {
  if (!raw) {
    return fallback;
  }
  const parsed = Number(raw);
  if (!Number.isSafeInteger(parsed) || parsed <= 0) {
    throw new Error(`live Story Graph numeric config must be a positive integer: ${raw}`);
  }
  return parsed;
}

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function assertAbsoluteLocalPath(value, suffix) {
  if (typeof value !== "string" || !value.startsWith("/") || value.includes("\0")) {
    throw new Error(`live Story Graph ${suffix} must be an absolute local path`);
  }
}
