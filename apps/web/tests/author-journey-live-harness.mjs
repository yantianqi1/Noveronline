import assert from "node:assert/strict";

export const AUTHOR_JOURNEY_PREFIX = "MIROFISH_WEB_BROWSER_LIVE_AUTHOR_";
const LOCAL_HOSTS = new Set(["127.0.0.1", "localhost", "::1", "[::1]"]);
const PRIVATE_PATTERN = /(?:mirofish_session|csrf[_-]?token|api[_-]?key|credential[_-]?ref|encrypted[_-]?api[_-]?key|provider[_-]?response|raw[_-]?(?:body|content)|prompt|complete manuscript|full manuscript)/i;

export function hasAuthorJourneyConfig(env = process.env) {
  return Object.keys(env).some((key) => key.startsWith(AUTHOR_JOURNEY_PREFIX));
}

export function loadAuthorJourneyConfig(env = process.env) {
  const config = {
    appBaseUrl: value(env, "APP_BASE_URL") || "http://127.0.0.1:3999",
    apiBaseUrl: value(env, "API_BASE_URL") || "http://127.0.0.1:3888",
    email: value(env, "EMAIL"),
    password: value(env, "PASSWORD"),
    displayName: value(env, "DISPLAY_NAME") || "Author Journey",
    projectTitle: value(env, "PROJECT_TITLE") || "Author Journey Novel",
    sessionCookie: value(env, "SESSION_COOKIE"),
    tenantId: value(env, "TENANT_ID"),
    projectId: value(env, "PROJECT_ID"),
    disposableMarker: value(env, "DISPOSABLE_PROJECT_MARKER"),
    allowMutation: value(env, "ALLOW_MUTATION") === "1",
    freshSignup: value(env, "FRESH_SIGNUP") === "1",
    localProvider: value(env, "LOCAL_PROVIDER") === "1",
    externalProvider: value(env, "EXTERNAL_PROVIDER") === "1",
    expectCompletedSeed: value(env, "EXPECT_COMPLETED_SEED") === "1",
    completeJourney: value(env, "COMPLETE_JOURNEY") === "1",
    screenshotDir: value(env, "SCREENSHOT_DIR") || "/tmp/mirofish-author-journey-certification",
    timeoutMs: positive(value(env, "TIMEOUT_MS"), 240000),
  };
  const missing = [];
  if (!config.allowMutation) missing.push(`${AUTHOR_JOURNEY_PREFIX}ALLOW_MUTATION=1`);
  if (!config.localProvider && !config.externalProvider) {
    missing.push(`${AUTHOR_JOURNEY_PREFIX}LOCAL_PROVIDER=1 or ${AUTHOR_JOURNEY_PREFIX}EXTERNAL_PROVIDER=1`);
  }
  if (config.externalProvider && value(env, "EXTERNAL_HTTPS_OPT_IN") !== "1") {
    missing.push(`${AUTHOR_JOURNEY_PREFIX}EXTERNAL_HTTPS_OPT_IN=1`);
  }
  if (config.freshSignup) {
    if (!config.email) missing.push(`${AUTHOR_JOURNEY_PREFIX}EMAIL`);
    if (!config.password) missing.push(`${AUTHOR_JOURNEY_PREFIX}PASSWORD`);
  } else {
    if (!config.tenantId) missing.push(`${AUTHOR_JOURNEY_PREFIX}TENANT_ID`);
    if (!config.projectId) missing.push(`${AUTHOR_JOURNEY_PREFIX}PROJECT_ID`);
    if (!config.disposableMarker) missing.push(`${AUTHOR_JOURNEY_PREFIX}DISPOSABLE_PROJECT_MARKER`);
    if (!config.sessionCookie) {
      if (!config.email) missing.push(`${AUTHOR_JOURNEY_PREFIX}EMAIL`);
      if (!config.password) missing.push(`${AUTHOR_JOURNEY_PREFIX}PASSWORD`);
    }
  }
  if (missing.length) {
    throw new Error(`Author journey live config is incomplete: ${missing.join(", ")}`);
  }
  assertLocalUrl(config.appBaseUrl, "app URL");
  assertLocalUrl(config.apiBaseUrl, "API URL");
  return config;
}

export async function authenticateAuthorJourney(api, config) {
  if (config.freshSignup) {
    const { registerAccount } = await import(`../lib/registration-api.ts?authorJourneySignup=${Date.now()}`);
    const registration = await registerAccount({
      displayName: config.displayName,
      email: config.email,
      password: config.password,
      projectTitle: config.projectTitle,
    });
    assert.equal(registration.ok, true, publicFailure(registration));
    const project = registration.active_projects[0];
    assert.ok(project, "fresh signup did not create a first project");
    const csrf = await api.getSessionCSRFToken({ sessionCookie: registration.session_cookie.value });
    assert.equal(csrf.ok, true, publicFailure(csrf));
    return {
      sessionCookie: registration.session_cookie.value,
      csrfToken: csrf.csrf_token,
      tenantId: project.tenant_id,
      projectId: project.project_id,
      disposableMarker: config.projectTitle,
    };
  }

  const session = config.sessionCookie
    ? await api.getCurrentUser({ sessionCookie: config.sessionCookie })
    : await api.loginWithPassword({ email: config.email, password: config.password });
  assert.equal(session.ok, true, publicFailure(session));
  const project = session.active_projects.find(
    (item) => item.tenant_id === config.tenantId && item.project_id === config.projectId && item.status === "active",
  );
  assert.ok(project, "author journey session does not grant the requested active project");
  assert.match(`${project.project_id} ${project.name}`, new RegExp(escapeRegExp(config.disposableMarker), "i"), "author journey target is not marked disposable");
  const sessionCookie = config.sessionCookie || session.session_cookie.value;
  const csrf = await api.getSessionCSRFToken({ sessionCookie });
  assert.equal(csrf.ok, true, publicFailure(csrf));
  return {
    sessionCookie,
    csrfToken: csrf.csrf_token,
    tenantId: config.tenantId,
    projectId: config.projectId,
    disposableMarker: config.disposableMarker,
  };
}

export function apiContext(config, auth) {
  return {
    tenantId: auth.tenantId,
    projectId: auth.projectId,
    sessionCookie: auth.sessionCookie,
    csrfToken: auth.csrfToken,
  };
}

export async function addAuthorJourneySession(context, config, auth) {
  await context.addCookies([
    { name: "mirofish_session", value: auth.sessionCookie, url: config.appBaseUrl, httpOnly: true, sameSite: "Lax" },
    { name: "mirofish_locale", value: "en", url: config.appBaseUrl, sameSite: "Lax" },
  ]);
}

export function projectUrl(config, auth, surface, query = {}) {
  const url = new URL(`/${encodeURIComponent(auth.tenantId)}/projects/${encodeURIComponent(auth.projectId)}/${surface}`, config.appBaseUrl);
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
  assert.deepEqual(findings, [], `author journey privacy/runtime scan failed:\n${findings.join("\n")}`);
}

export async function submitServerAction(page, button, key, accept, timeoutMs) {
  const responsePromise = page.waitForResponse(
    (response) => response.request().method() === "POST" && response.status() >= 300 && response.status() < 400,
    { timeout: timeoutMs },
  );
  const clickPromise = button.click({ noWaitAfter: true });
  const response = await responsePromise;
  await clickPromise;
  const redirectHeader = response.headers().location ?? response.headers()["x-action-redirect"];
  assert.ok(redirectHeader, `${key} server action response is missing a redirect location`);
  const location = redirectHeader.replace(/;(?:push|replace)$/, "");
  const target = new URL(location, page.url());
  assert.equal(accept(target.searchParams.get(key)), true, `${key} redirect did not reach the required value`);
  const reachedTarget = () => accept(new URL(page.url()).searchParams.get(key));
  if (!reachedTarget()) {
    try {
      await page.waitForURL((url) => accept(url.searchParams.get(key)), {
        timeout: Math.min(timeoutMs, 5_000),
        waitUntil: "domcontentloaded",
      });
    } catch (error) {
      if (error?.name !== "TimeoutError") throw error;
      await page.goto(target.href, { waitUntil: "domcontentloaded" });
      await page.waitForLoadState("domcontentloaded");
    }
  }
  assert.equal(reachedTarget(), true, `${key} page navigation did not reach the redirect target`);
}

export function publicFailure(value) {
  if (!value || typeof value !== "object") return "request failed";
  return `${typeof value.code === "string" ? value.code : "REQUEST_FAILED"}: ${typeof value.message === "string" ? sanitize(value.message) : "request failed"}`;
}

function assertPublic(value) {
  const serialized = JSON.stringify(value ?? {});
  assert.equal(PRIVATE_PATTERN.test(serialized), false, "public author journey payload contains private fields");
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

function value(env, suffix) {
  return String(env[`${AUTHOR_JOURNEY_PREFIX}${suffix}`] || "").trim();
}

function positive(raw, fallback) {
  const parsed = Number.parseInt(raw, 10);
  return parsed > 0 ? parsed : fallback;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}