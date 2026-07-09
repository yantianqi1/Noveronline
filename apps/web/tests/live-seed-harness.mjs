import assert from "node:assert/strict";

export const LIVE_SEED_PREFIX = "MIROFISH_WEB_LIVE_SEED_";
export const BROWSER_LIVE_SEED_PREFIX = "MIROFISH_WEB_BROWSER_LIVE_SEED_";

const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);
const JWT_LIKE_PATTERN = /\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{6,}\b/g;
const BEARER_PATTERN = /Bearer\s+[A-Za-z0-9._~+/-]+=*/gi;
const SESSION_TOKEN_PATTERN = /\bv[12]:[A-Za-z0-9:_-]+\b/g;
const SESSION_COOKIE_PATTERN = /mirofish_session=([^;\s"'`,)]+)/gi;
const FORBIDDEN_PUBLIC_MARKER_SOURCE =
  String.raw`prompt|provider[_\s-]?response|raw[_\s-]?content|raw[_\s-]?body|content[_\s-]?text|source[_\s-]?text|private[_\s-]?content|api[_\s-]?key|encrypted[_\s-]?(?:api[_\s-]?key|credential)|credential[_\s-]?ref|object[_\s-]?key|draft|manuscript`;
const FORBIDDEN_PUBLIC_VALUE_MARKER_SOURCE =
  String.raw`prompt|provider[_\s-]?response|raw[_\s-]?content|raw[_\s-]?body|content[_\s-]?text|source[_\s-]?text|private[_\s-]?content|api[_\s-]?key|encrypted[_\s-]?(?:api[_\s-]?key|credential)|credential[_\s-]?ref|object[_\s-]?key`;
const FORBIDDEN_PUBLIC_STRUCTURED_KEY_SOURCE =
  String.raw`(?:[A-Za-z0-9_-]*(?:prompt|provider[_-]?response|raw[_-]?(?:body|content)|content[_-]?text|source[_-]?text|private[_-]?content|api[_-]?key|encrypted[_-]?(?:api[_-]?key|credential)|credential[_-]?ref|object[_-]?key|draft|manuscript|session[_-]?cookie)[A-Za-z0-9_-]*|token|(?:access|refresh|csrf|session|auth|bearer)[_-]?token)`;
const FORBIDDEN_PUBLIC_MARKER_PATTERN =
  new RegExp(String.raw`(?:^|["'{\s,;])(?:${FORBIDDEN_PUBLIC_VALUE_MARKER_SOURCE})(?:$|["'}\s:=,;])`, "i");
const FORBIDDEN_PUBLIC_ASSIGNMENT_PATTERN = new RegExp(
  String.raw`("?(?:${FORBIDDEN_PUBLIC_MARKER_SOURCE})"?\s*[:=]\s*)("[^"]*"|'[^']*'|[^,;}\]\s]+)`,
  "gi",
);
const FORBIDDEN_PUBLIC_STRUCTURED_KEY_PATTERN = new RegExp(
  String.raw`(?:^|[{,]\s*)["'](?:${FORBIDDEN_PUBLIC_STRUCTURED_KEY_SOURCE})["']\s*:`,
  "i",
);
const FORBIDDEN_PUBLIC_TOKEN_ASSIGNMENT_PATTERN =
  /\b(?:access|refresh|csrf|session|auth|bearer)[_-]?token\b"?\s*[:=]\s*("[^"]*"|'[^']*'|[^,;}\]\s]+)/gi;
const EXACT_TOKEN_ASSIGNMENT_PATTERN =
  /\btoken\b"?\s*[:=]\s*("[^"]*"|'[^']*'|[^,;}\]\s]+)/gi;
const FORBIDDEN_PUBLIC_KEYS = new Set([
  "prompt",
  "providerresponse",
  "rawcontent",
  "rawbody",
  "contenttext",
  "sourcetext",
  "privatecontent",
  "apikey",
  "encryptedapikey",
  "encryptedcredential",
  "credentialref",
  "objectkey",
  "sessioncookie",
  "token",
  "draft",
  "manuscript",
]);

export function loadLiveSeedConfig(options = {}) {
  const env = options.env ?? process.env;
  const prefix = options.prefix ?? LIVE_SEED_PREFIX;
  const browser = options.browser === true;
  if (!hasPrefixedEnv(env, prefix)) {
    return { enabled: false, prefix };
  }

  const config = {
    enabled: true,
    prefix,
    browser,
    apiBaseUrl: envText(env, `${prefix}API_BASE_URL`),
    tenantId: envText(env, `${prefix}TENANT_ID`),
    projectId: envText(env, `${prefix}PROJECT_ID`),
    sessionCookie: envText(env, `${prefix}SESSION_COOKIE`),
    allowMutation: envText(env, `${prefix}ALLOW_MUTATION`) === "1",
    throwawayProject: envText(env, `${prefix}THROWAWAY_PROJECT`) === "1",
    disposableProjectMarker: envText(env, `${prefix}DISPOSABLE_PROJECT_MARKER`),
  };
  if (browser) {
    config.appBaseUrl = envText(env, `${prefix}APP_BASE_URL`);
    config.retryRunId = envText(env, `${prefix}RETRY_RUN_ID`);
    config.consumeRetryRun = envText(env, `${prefix}CONSUME_RETRY_RUN`) === "1";
  }

  assertDisposableLiveSeedConfig(config);
  return config;
}

export function assertDisposableLiveSeedConfig(config) {
  const prefix = config.prefix ?? LIVE_SEED_PREFIX;
  const missing = [];
  if (config.browser && !config.appBaseUrl) {
    missing.push(`${prefix}APP_BASE_URL`);
  }
  if (!config.apiBaseUrl) {
    missing.push(`${prefix}API_BASE_URL`);
  }
  if (!config.tenantId) {
    missing.push(`${prefix}TENANT_ID`);
  }
  if (!config.projectId) {
    missing.push(`${prefix}PROJECT_ID`);
  }
  if (!config.sessionCookie) {
    missing.push(`${prefix}SESSION_COOKIE`);
  }
  if (!config.allowMutation) {
    missing.push(`${prefix}ALLOW_MUTATION`);
  }
  if (!config.throwawayProject) {
    missing.push(`${prefix}THROWAWAY_PROJECT`);
  }
  if (!config.disposableProjectMarker) {
    missing.push(`${prefix}DISPOSABLE_PROJECT_MARKER`);
  }
  if (config.consumeRetryRun && !config.retryRunId) {
    missing.push(`${prefix}RETRY_RUN_ID`);
  }
  if (missing.length > 0) {
    throw new Error(`live Seed config is incomplete; missing env names: ${missing.join(", ")}`);
  }

  if (config.browser) {
    assertLocalHttpUrl(config.appBaseUrl, "live Seed app base URL");
  }
  assertLocalHttpUrl(config.apiBaseUrl, "live Seed API base URL");
}

export function assertLocalHttpUrl(value, label = "URL") {
  const message = `${label} must be a local http URL`;
  if (typeof value !== "string" || value.trim() === "" || value.trim().startsWith("//")) {
    throw new Error(message);
  }

  let parsed;
  try {
    parsed = new URL(value.trim());
  } catch {
    throw new Error(message);
  }

  const hostname = parsed.hostname.toLowerCase();
  if (
    parsed.protocol !== "http:" ||
    parsed.username !== "" ||
    parsed.password !== "" ||
    !LOCAL_HOSTS.has(hostname)
  ) {
    throw new Error(message);
  }
  return parsed;
}

export async function liveAuthContext(api, config) {
  const csrf = await api.getSessionCSRFToken({ sessionCookie: config.sessionCookie });
  assert.equal(csrf.ok, true, publicFailure(csrf, { sessionCookie: config.sessionCookie }));
  return {
    tenantId: config.tenantId,
    sessionCookie: config.sessionCookie,
    csrfToken: csrf.csrf_token,
  };
}

export async function assertDisposableProject(api, config, options = {}) {
  const currentUser = await api.getCurrentUser({ sessionCookie: config.sessionCookie });
  assertNoForbiddenPublicMarkers(currentUser, {
    sourceText: options.sourceText,
    sessionCookie: config.sessionCookie,
  });
  assert.equal(currentUser.ok, true, publicFailure(currentUser, { sessionCookie: config.sessionCookie }));
  const project = currentUser.active_projects.find(
    (candidate) =>
      candidate.tenant_id === config.tenantId &&
      candidate.project_id === config.projectId &&
      candidate.status === "active",
  );
  assert.ok(project, "live Seed target project must be active for the session user");
  const marker = config.disposableProjectMarker.toLowerCase();
  const projectIdentity = `${project.project_id} ${project.name}`.toLowerCase();
  assert.equal(
    projectIdentity.includes(marker),
    true,
    "live Seed target project must contain the disposable project marker",
  );
}

export function overviewUrl(config) {
  const url = new URL(
    `/${encodeURIComponent(config.tenantId)}/projects/${encodeURIComponent(config.projectId)}/overview`,
    config.appBaseUrl,
  );
  return url.toString();
}

export async function addLiveSeedSessionCookie(context, config) {
  assertLocalHttpUrl(config.appBaseUrl, "live Seed app base URL");
  await context.addCookies([
    {
      name: "mirofish_session",
      value: config.sessionCookie,
      url: config.appBaseUrl,
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
}

export async function fetchLiveSeedPublicJsonWithRawScan(config, path, options = {}) {
  assertLocalHttpUrl(config.apiBaseUrl, "live Seed API base URL");
  assert.equal(path.startsWith("/"), true, "live Seed public fetch path must be absolute");
  assert.equal(path.startsWith("//"), false, "live Seed public fetch path must stay on API base");
  const url = new URL(path, config.apiBaseUrl);
  const apiBase = new URL(config.apiBaseUrl);
  assert.equal(url.origin, apiBase.origin, "live Seed public fetch URL must stay on API base");
  const response = await fetch(url, {
    headers: {
      "X-Tenant-Id": config.tenantId,
      Cookie: `mirofish_session=${config.sessionCookie}`,
    },
  });
  const rawText = await response.text();
  assertNoForbiddenPublicMarkers(rawText, {
    sourceText: options.sourceText,
    sessionCookie: config.sessionCookie,
  });

  let payload;
  try {
    payload = JSON.parse(rawText);
  } catch {
    assert.fail(`live Seed public fetch returned invalid JSON: ${publicPathLabel(url)}`);
  }
  assert.equal(response.ok, true, `live Seed public fetch failed: ${publicPathLabel(url)}`);
  return payload;
}

export function installAppResponsePrivacyScan(page, config, options = {}) {
  const pending = [];
  const appOrigin = new URL(config.appBaseUrl).origin;
  const optionValues = typeof options === "function" ? options : () => options;
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
          ...optionValues(),
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

export async function flushResponseScans(pending) {
  const queue = Array.isArray(pending) ? pending : pending.pending;
  while (queue.length > 0) {
    await Promise.all(queue.splice(0));
  }
}

export async function waitForSeedRunTerminalStatus(api, config, runId, options = {}) {
  const timeoutMs = options.timeoutMs ?? 60000;
  const deadline = Date.now() + timeoutMs;
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
    assert.equal(latest.ok, true, publicFailure(latest, { sessionCookie: config.sessionCookie }));
    if (latest.status === "completed" || latest.status === "failed" || latest.status === "cancelled") {
      return latest;
    }
    await delay(options.pollMs ?? 500);
  }
  assert.fail("live Seed run did not reach a terminal status before the timeout");
}

export function assertNoForbiddenPublicMarkers(value, options = {}) {
  const serialized = safeSerialize(value);
  const checks = [
    options.sourceText,
    options.sessionCookie,
    SESSION_COOKIE_PATTERN,
    BEARER_PATTERN,
    SESSION_TOKEN_PATTERN,
    JWT_LIKE_PATTERN,
    FORBIDDEN_PUBLIC_MARKER_PATTERN,
    FORBIDDEN_PUBLIC_STRUCTURED_KEY_PATTERN,
  ];
  for (const check of checks) {
    if (!check) {
      continue;
    }
    if (typeof check === "string" && check !== "" && sourceTextLeakVariants(check).some((item) => serialized.includes(item))) {
      failForbiddenPublicMaterial();
    }
    if (check instanceof RegExp && check.test(serialized)) {
      check.lastIndex = 0;
      failForbiddenPublicMaterial();
    }
  }
  assertNoForbiddenPublicKeys(value);
}

export function assertNoForbiddenPublicKeys(value) {
  if (Array.isArray(value)) {
    value.forEach((item) => assertNoForbiddenPublicKeys(item));
    return;
  }
  if (!value || typeof value !== "object") {
    return;
  }
  for (const [key, item] of Object.entries(value)) {
    const normalized = key.toLowerCase().replace(/[^a-z0-9]/g, "");
    if (
      FORBIDDEN_PUBLIC_KEYS.has(normalized) ||
      isCredentialTokenKey(normalized) ||
      normalized.includes("prompt") ||
      normalized.includes("providerresponse") ||
      normalized.includes("rawbody") ||
      normalized.includes("rawcontent") ||
      normalized.includes("contenttext") ||
      normalized.includes("sourcetext") ||
      normalized.includes("apikey") ||
      normalized.includes("encryptedcredential") ||
      normalized.includes("credentialref") ||
      normalized.includes("objectkey") ||
      normalized.includes("draft") ||
      normalized.includes("manuscript")
    ) {
      failForbiddenPublicMaterial();
    }
    assertNoForbiddenPublicKeys(item);
  }
}

export function publicFailure(result, options = {}) {
  if (result?.ok !== false) {
    return "";
  }
  return sanitizePublicMessage(`${result.code}: ${result.message ?? ""}`, options);
}

export function redactSensitiveText(value, options = {}) {
  let text = typeof value === "string" ? value : safeSerialize(value);
  for (const secret of [options.sessionCookie, options.sourceText]) {
    if (secret) {
      text = text.replaceAll(secret, "[redacted]");
    }
  }
  return text
    .replace(FORBIDDEN_PUBLIC_ASSIGNMENT_PATTERN, "[redacted]")
    .replace(FORBIDDEN_PUBLIC_TOKEN_ASSIGNMENT_PATTERN, "[redacted]")
    .replace(EXACT_TOKEN_ASSIGNMENT_PATTERN, "[redacted]")
    .replace(SESSION_COOKIE_PATTERN, "mirofish_session=[redacted]")
    .replace(BEARER_PATTERN, "Bearer [redacted]")
    .replace(SESSION_TOKEN_PATTERN, "[redacted-session-token]")
    .replace(JWT_LIKE_PATTERN, "[redacted-token]")
    .replace(/\b(?:api[_\s-]?key|credential[_\s-]?ref|object[_\s-]?key|draft|manuscript|prompt|provider[_\s-]?response|raw[_\s-]?content|raw[_\s-]?body|content[_\s-]?text|source[_\s-]?text)\b[^\n\r,;}]*/gi, "[redacted]")
    .replace(/\bsk-[A-Za-z0-9_-]{8,}\b/g, "[redacted-api-key]");
}

export function publicPathLabel(url) {
  return `${url.pathname}${url.search ? "?..." : ""}`;
}

export function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function hasPrefixedEnv(env, prefix) {
  return Object.keys(env).some((name) => name.startsWith(prefix));
}

function envText(env, name) {
  return String(env[name] ?? "").trim();
}

function sanitizePublicMessage(value, options = {}) {
  return redactSensitiveText(value, options).replace(
    new RegExp(String.raw`\b(?:${FORBIDDEN_PUBLIC_MARKER_SOURCE})\b`, "gi"),
    "[redacted]",
  );
}

function isCredentialTokenKey(normalized) {
  if (!normalized.includes("token")) {
    return false;
  }
  return (
    normalized === "token" ||
    normalized.includes("accesstoken") ||
    normalized.includes("refreshtoken") ||
    normalized.includes("csrftoken") ||
    normalized.includes("sessiontoken") ||
    normalized.includes("authtoken") ||
    normalized.includes("bearertoken")
  );
}

function failForbiddenPublicMaterial() {
  assert.fail("live Seed public payload contained forbidden material");
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

function safeSerialize(value) {
  if (typeof value === "string") {
    return value;
  }
  const seen = new WeakSet();
  try {
    return JSON.stringify(value, (_key, item) => {
      if (typeof item === "bigint") {
        return item.toString();
      }
      if (item && typeof item === "object") {
        if (seen.has(item)) {
          return "[Circular]";
        }
        seen.add(item);
      }
      return item;
    }) ?? "";
  } catch {
    return String(value);
  }
}

function htmlEscapedVariants(value) {
  return [
    value
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;"),
    value
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&#34;")
      .replaceAll("'", "&#x27;"),
  ];
}

function sourceTextLeakVariants(value) {
  const normalizedWhitespace = value.replace(/\s+/g, " ");
  const variants = new Set([value, normalizedWhitespace, JSON.stringify(value).slice(1, -1)]);
  for (const escaped of [value, normalizedWhitespace, ...htmlEscapedVariants(value), ...htmlEscapedVariants(normalizedWhitespace)]) {
    variants.add(escaped);
    variants.add(JSON.stringify(escaped).slice(1, -1));
  }
  for (const item of [...variants]) {
    variants.add(JSON.stringify(item).slice(1, -1));
  }
  return [...variants].filter(Boolean);
}
