import assert from "node:assert/strict";
import path from "node:path";

export const JOURNEY_PREFIX = "MIROFISH_WEB_WORLDLINE_CHARACTER_";
const LOCAL_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);
const PRIVATE_PATTERN = /(?:mirofish_session|csrf[_-]?token|api[_-]?key|credential[_-]?ref|encrypted[_-]?api[_-]?key|provider[_-]?response|raw[_-]?(?:body|content)|prompt|complete manuscript|full manuscript)/i;

export function hasJourneyConfig(env = process.env) {
  return Object.keys(env).some((key) => key.startsWith(JOURNEY_PREFIX));
}

export function loadJourneyConfig(env = process.env) {
  const config = {
    appBaseUrl: value(env, "APP_BASE_URL") || "http://localhost:3999",
    apiBaseUrl: value(env, "API_BASE_URL") || "http://127.0.0.1:3888",
    email: value(env, "EMAIL"),
    password: value(env, "PASSWORD"),
    sessionCookie: value(env, "SESSION_COOKIE"),
    tenantId: value(env, "TENANT_ID"),
    projectId: value(env, "PROJECT_ID"),
    disposableMarker: value(env, "DISPOSABLE_PROJECT_MARKER"),
    allowMutation: value(env, "ALLOW_MUTATION") === "1",
    localProvider: value(env, "LOCAL_PROVIDER") === "1",
    externalProvider: value(env, "EXTERNAL_PROVIDER") === "1",
    screenshotDir: value(env, "SCREENSHOT_DIR") || "/tmp/mirofish-worldline-character-certification",
    timeoutMs: positive(value(env, "TIMEOUT_MS"), 180000),
  };
  const missing = [];
  for (const [field, suffix] of [["tenantId", "TENANT_ID"], ["projectId", "PROJECT_ID"], ["disposableMarker", "DISPOSABLE_PROJECT_MARKER"]]) {
    if (!config[field]) missing.push(`${JOURNEY_PREFIX}${suffix}`);
  }
  if (!config.sessionCookie) {
    if (!config.email) missing.push(`${JOURNEY_PREFIX}EMAIL`);
    if (!config.password) missing.push(`${JOURNEY_PREFIX}PASSWORD`);
  }
  if (!config.allowMutation) missing.push(`${JOURNEY_PREFIX}ALLOW_MUTATION=1`);
  if (!config.localProvider && !config.externalProvider) missing.push(`${JOURNEY_PREFIX}LOCAL_PROVIDER=1 or ${JOURNEY_PREFIX}EXTERNAL_PROVIDER=1`);
  if (config.externalProvider && value(env, "EXTERNAL_HTTPS_OPT_IN") !== "1") missing.push(`${JOURNEY_PREFIX}EXTERNAL_HTTPS_OPT_IN=1`);
  if (missing.length) throw new Error(`Worldline/Character journey config is incomplete: ${missing.join(", ")}`);
  assertLocalUrl(config.appBaseUrl, "app URL");
  assertLocalUrl(config.apiBaseUrl, "API URL");
  assert.equal(path.isAbsolute(config.screenshotDir), true, "journey screenshot directory must be absolute");
  return config;
}

export async function authenticateJourney(api, config) {
  const session = config.sessionCookie
    ? await api.getCurrentUser({ sessionCookie: config.sessionCookie })
    : await api.loginWithPassword({ email: config.email, password: config.password });
  assert.equal(session.ok, true, publicFailure(session));
  const project = session.active_projects.find((item) => item.tenant_id === config.tenantId && item.project_id === config.projectId && item.status === "active");
  assert.ok(project, "password login does not grant the requested active project");
  assert.match(`${project.project_id} ${project.name}`, new RegExp(escapeRegExp(config.disposableMarker), "i"), "journey target is not marked disposable");
  const sessionCookie = config.sessionCookie || session.session_cookie.value;
  const csrf = await api.getSessionCSRFToken({ sessionCookie });
  assert.equal(csrf.ok, true, publicFailure(csrf));
  return { sessionCookie, csrfToken: csrf.csrf_token };
}

export function apiContext(config, auth) {
  return { tenantId: config.tenantId, projectId: config.projectId, sessionCookie: auth.sessionCookie, csrfToken: auth.csrfToken };
}

export async function addJourneySession(context, config, auth) {
  await context.addCookies([
    { name: "mirofish_session", value: auth.sessionCookie, url: config.appBaseUrl, httpOnly: true, sameSite: "Lax" },
    { name: "mirofish_locale", value: "en", url: config.appBaseUrl, sameSite: "Lax" },
  ]);
}

export function projectUrl(config, surface, query = {}) {
  const url = new URL(`/${encodeURIComponent(config.tenantId)}/projects/${encodeURIComponent(config.projectId)}/${surface}`, config.appBaseUrl);
  for (const [key, val] of Object.entries(query)) if (val) url.searchParams.set(key, String(val));
  return url.toString();
}

export async function waitUntil(read, accept, config, label) {
  const deadline = Date.now() + config.timeoutMs;
  let latest;
  while (Date.now() <= deadline) {
    latest = await read();
    assertPublic(latest);
    if (accept(latest)) return latest;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  assert.fail(`${label} did not reach the required persisted state; latest=${publicFailure(latest)}`);
}

export async function assertResponsiveSurface(page, width, height, screenshotPath) {
  await page.setViewportSize({ width, height });
  await page.locator("main, .workbench-grid").first().waitFor();
  const metrics = await page.evaluate(() => ({
    bodyWidth: document.body.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
    textLength: document.body.innerText.trim().length,
    overlaps: Array.from(document.querySelectorAll("button, input, select, textarea")).flatMap((element, index, elements) => {
      const a = element.getBoundingClientRect();
      if (a.width === 0 || a.height === 0) return [];
      return elements.slice(index + 1).flatMap((other) => {
        const b = other.getBoundingClientRect();
        const overlap = a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
        return overlap ? [`${element.tagName}:${other.tagName}`] : [];
      });
    }),
  }));
  assert.ok(metrics.textLength > 80, `${width}px journey surface is empty`);
  assert.ok(metrics.bodyWidth <= metrics.viewportWidth + 1, `${width}px journey surface overflows horizontally`);
  assert.deepEqual(metrics.overlaps, [], `${width}px interactive controls overlap`);
  await page.screenshot({ path: screenshotPath, fullPage: true });
}

export function attachPrivacyScanner(page, findings) {
  page.on("console", (message) => scanText(message.text(), "console", findings));
  page.on("pageerror", (error) => findings.push(`pageerror:${sanitize(error.message)}`));
  page.on("response", async (response) => {
    if (response.status() >= 400) findings.push(`network:${response.status()}:${new URL(response.url()).pathname}`);
    const contentType = response.headers()["content-type"] || "";
    if (/text|json|rsc/i.test(contentType)) scanText(await response.text().catch(() => ""), "network-body", findings);
  });
}

export async function scanPage(page, findings) {
  scanText(await page.locator("body").innerText(), "dom", findings);
  scanText(await page.content(), "html", findings);
}

export function assertPrivacyClean(findings) {
  assert.deepEqual(findings, [], `journey privacy/runtime scan failed:\n${findings.join("\n")}`);
}

export function publicFailure(value) {
  if (!value || typeof value !== "object") return "request failed";
  return `${typeof value.code === "string" ? value.code : "REQUEST_FAILED"}: ${typeof value.message === "string" ? sanitize(value.message) : "request failed"}`;
}

function assertPublic(value) {
  const serialized = JSON.stringify(value ?? {});
  assert.equal(PRIVATE_PATTERN.test(serialized), false, "public journey payload contains private fields");
}

function scanText(text, source, findings) {
  if (text && PRIVATE_PATTERN.test(text)) findings.push(`${source}:private-marker`);
}

function sanitize(text) {
  return String(text || "").replace(/mirofish_session=[^;\s]+/gi, "mirofish_session=[redacted]").slice(0, 240);
}

function assertLocalUrl(raw, label) {
  const url = new URL(raw);
  assert.equal(["http:", "https:"].includes(url.protocol), true, `${label} must use HTTP(S)`);
  assert.equal(LOCAL_HOSTS.has(url.hostname), true, `${label} must be local`);
}

function value(env, suffix) { return String(env[`${JOURNEY_PREFIX}${suffix}`] || "").trim(); }
function positive(raw, fallback) { const parsed = Number.parseInt(raw, 10); return parsed > 0 ? parsed : fallback; }
function escapeRegExp(value) { return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
