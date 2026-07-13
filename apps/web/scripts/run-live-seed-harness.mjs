#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { prepareLiveSeedFixture } from "./prepare-live-seed-fixture.mjs";

const API_PREFIX = "MIROFISH_WEB_LIVE_SEED_";
const BROWSER_PREFIX = "MIROFISH_WEB_BROWSER_LIVE_SEED_";
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);
const VALID_MODES = new Set(["api", "browser", "both"]);
const SAFE_CHILD_ENV_NAMES = [
  "CI",
  "FORCE_COLOR",
  "HOME",
  "LANG",
  "LC_ALL",
  "NO_COLOR",
  "PATH",
  "PLAYWRIGHT_BROWSERS_PATH",
  "TERM",
  "TMP",
  "TMPDIR",
  "TEMP",
  "XDG_CACHE_HOME",
];
const LIVE_CHILD_ENV_SUFFIXES = new Set([
  "ALLOW_MUTATION",
  "APP_DEV_BYPASS",
  "API_BASE_URL",
  "APP_BASE_URL",
  "CONSUME_RETRY_RUN",
  "DISPOSABLE_PROJECT_MARKER",
  "EXPECT_COMPLETED",
  "PROJECT_ID",
  "REQUIRE_WORKER_RETRY",
  "RETRY_RUN_ID",
  "SESSION_COOKIE",
  "TENANT_ID",
  "THROWAWAY_PROJECT",
  "WORKER_RETRY_TIMEOUT_MS",
]);
const REDACTED = "[redacted]";
const MAX_CHILD_DIAGNOSTIC_CHARS = 1600;

export function loadRunnerConfig(options = {}) {
  const env = { ...(options.env ?? process.env) };
  const flags = parseArgs(options.argv ?? process.argv.slice(2));
  const mode = flags.get("mode") || "both";
  if (!VALID_MODES.has(mode)) {
    throw new Error("live Seed runner mode must be one of: api, browser, both");
  }

  const config = {
    mode,
    prepareFixture: flags.has("prepare-fixture"),
    api: mode === "api" || mode === "both" ? readLiveConfig(env, API_PREFIX, { browser: false }) : null,
    browser: mode === "browser" || mode === "both" ? readLiveConfig(env, BROWSER_PREFIX, { browser: true }) : null,
  };
  assertRunnerConfig(config);
  return config;
}

export async function runLiveSeedHarness(options = {}) {
  let env = { ...(options.env ?? process.env) };
  const flags = parseArgs(options.argv ?? process.argv.slice(2));
  const output = [];

  if (flags.has("prepare-fixture")) {
    const prepare = options.prepareFixture ?? prepareLiveSeedFixture;
    const fixture = await prepare({
      env,
      argv: fixtureArgvFromRunnerFlags(flags),
      fetchImpl: options.fetchImpl ?? globalThis.fetch,
      runPsql: options.runPsql,
    });
    env = mergeFixtureEnv(env, fixture.config);
    output.push("fixture env prepared");
  }

  const config = loadRunnerConfig({ env, argv: options.argv ?? process.argv.slice(2) });
  await preflightLiveSeedServices(config, options.fetchImpl ?? globalThis.fetch);
  output.push("live Seed service preflight passed");

  const result = runLiveSeedTests(config, env, options.runCommand ?? defaultRunCommand);
  if (!result?.ok) {
    throw new Error(`live Seed harness tests failed${formatCommandFailure(result, env)}`);
  }
  output.push("live Seed harness tests passed");
  return { config: redactedRunnerConfig(config), output: `${output.join("\n")}\n` };
}

export function mergeFixtureEnv(env, fixtureConfig) {
  const next = { ...env };
  const apiEntries = {
    API_BASE_URL: fixtureConfig.apiBaseUrl,
    TENANT_ID: fixtureConfig.tenantId,
    PROJECT_ID: fixtureConfig.projectId,
    SESSION_COOKIE: fixtureConfig.sessionCookie,
    ALLOW_MUTATION: "1",
    THROWAWAY_PROJECT: "1",
    DISPOSABLE_PROJECT_MARKER: fixtureConfig.disposableProjectMarker,
  };
  const browserEntries = {
    APP_BASE_URL: fixtureConfig.appBaseUrl,
    ...apiEntries,
  };
  for (const [name, value] of Object.entries(apiEntries)) {
    next[`${API_PREFIX}${name}`] = String(value ?? "");
  }
  for (const [name, value] of Object.entries(browserEntries)) {
    next[`${BROWSER_PREFIX}${name}`] = String(value ?? "");
  }
  return next;
}

async function preflightLiveSeedServices(config, fetchImpl) {
  if (typeof fetchImpl !== "function") {
    throw new Error("live Seed service preflight failed");
  }
  for (const apiBaseUrl of distinctApiBaseUrls(config)) {
    await assertServiceReachable({
      fetchImpl,
      url: new URL("/healthz", apiBaseUrl).toString(),
      label: "Go API health",
      acceptStatus: (response) => response.ok,
    });
  }
  if (config.browser) {
    await assertServiceReachable({
      fetchImpl,
      url: new URL("/", config.browser.appBaseUrl).toString(),
      label: "Next app",
      acceptStatus: (response) => Number(response.status) < 500,
      requestInit: { redirect: "manual" },
    });
  }
}

async function assertServiceReachable({ fetchImpl, url, label, acceptStatus, requestInit = {} }) {
  let response;
  try {
    response = await fetchImpl(url, { method: "GET", ...requestInit });
  } catch {
    throw new Error(`${label} preflight failed`);
  }
  if (!response || !acceptStatus(response)) {
    throw new Error(`${label} preflight failed: HTTP ${response?.status ?? "unknown"}`);
  }
}

function runLiveSeedTests(config, env, runCommand) {
  const tests = [];
  if (config.api) {
    tests.push("tests/seed-upload-live.test.mjs");
  }
  if (config.browser) {
    tests.push("tests/seed-upload-browser-live.test.mjs");
  }
  return runCommand(process.execPath, ["--test", ...tests], {
    cwd: process.cwd(),
    env: buildChildEnv(env),
  });
}

function defaultRunCommand(command, args, options) {
  const result = spawnSync(command, args, {
    cwd: options.cwd,
    env: options.env,
    encoding: "utf8",
    stdio: "pipe",
  });
  return {
    ok: result.status === 0,
    status: result.status,
    signal: result.signal,
    errorCode: result.error?.code,
    stdout: result.stdout,
    stderr: result.stderr,
  };
}

function distinctApiBaseUrls(config) {
  const urls = [];
  for (const candidate of [config.api?.apiBaseUrl, config.browser?.apiBaseUrl]) {
    if (!candidate || urls.includes(candidate)) {
      continue;
    }
    urls.push(candidate);
  }
  return urls;
}

function buildChildEnv(env) {
  const childEnv = { NODE_ENV: "test" };
  for (const name of SAFE_CHILD_ENV_NAMES) {
    if (process.env[name] !== undefined) {
      childEnv[name] = process.env[name];
    }
  }
  for (const [name, value] of Object.entries(env)) {
    if (isLiveChildEnvName(name)) {
      childEnv[name] = String(value ?? "");
    }
  }
  return childEnv;
}

function isLiveChildEnvName(name) {
  if (name.startsWith(API_PREFIX)) {
    return LIVE_CHILD_ENV_SUFFIXES.has(name.slice(API_PREFIX.length));
  }
  if (name.startsWith(BROWSER_PREFIX)) {
    return LIVE_CHILD_ENV_SUFFIXES.has(name.slice(BROWSER_PREFIX.length));
  }
  return false;
}

function redactedRunnerConfig(config) {
  return {
    mode: config.mode,
    prepareFixture: config.prepareFixture,
    api: config.api ? redactedLiveConfig(config.api, { browser: false }) : null,
    browser: config.browser ? redactedLiveConfig(config.browser, { browser: true }) : null,
  };
}

function redactedLiveConfig(config, options) {
  const redacted = {
    apiBaseUrl: config.apiBaseUrl,
    tenantId: REDACTED,
    projectId: REDACTED,
    sessionCookie: REDACTED,
    allowMutation: config.allowMutation,
    throwawayProject: config.throwawayProject,
    disposableProjectMarker: REDACTED,
    retryRunId: config.retryRunId ? REDACTED : "",
    consumeRetryRun: config.consumeRetryRun,
    requireWorkerRetry: config.requireWorkerRetry,
    expectCompleted: config.expectCompleted,
    workerRetryTimeoutMs: config.workerRetryTimeoutMs,
  };
  if (options.browser) {
    redacted.appBaseUrl = config.appBaseUrl;
  }
  return redacted;
}

function assertRunnerConfig(config) {
  if (config.api) {
    assertLiveConfig(config.api, API_PREFIX, { browser: false });
  }
  if (config.browser) {
    assertLiveConfig(config.browser, BROWSER_PREFIX, { browser: true });
  }
}

function assertLiveConfig(config, prefix, options) {
  const missing = [];
  if (options.browser && !config.appBaseUrl) {
    missing.push(`${prefix}APP_BASE_URL`);
  }
  for (const [suffix, value] of [
    ["API_BASE_URL", config.apiBaseUrl],
    ["TENANT_ID", config.tenantId],
    ["PROJECT_ID", config.projectId],
    ["SESSION_COOKIE", config.sessionCookie],
    ["DISPOSABLE_PROJECT_MARKER", config.disposableProjectMarker],
  ]) {
    if (!value) {
      missing.push(`${prefix}${suffix}`);
    }
  }
  if (!config.allowMutation) {
    missing.push(`${prefix}ALLOW_MUTATION=1`);
  }
  if (!config.throwawayProject) {
    missing.push(`${prefix}THROWAWAY_PROJECT=1`);
  }
  if (config.consumeRetryRun && !config.retryRunId) {
    missing.push(`${prefix}RETRY_RUN_ID`);
  }
  if (options.browser && config.requireWorkerRetry && (config.consumeRetryRun || config.retryRunId)) {
    throw new Error("worker retry mode must retry the browser-uploaded run");
  }
  if (options.browser && config.expectCompleted && (config.requireWorkerRetry || config.consumeRetryRun || config.retryRunId)) {
    throw new Error("completed mode cannot enable retry-run options");
  }
  if (missing.length > 0) {
    throw new Error(`live Seed runner config is incomplete; missing env names: ${missing.join(", ")}`);
  }
  assertLocalHttpUrl(config.apiBaseUrl, `${prefix}API_BASE_URL`);
  if (options.browser) {
    assertLocalHttpUrl(config.appBaseUrl, `${prefix}APP_BASE_URL`);
  }
}

function readLiveConfig(env, prefix, options) {
  const config = {
    apiBaseUrl: envText(env, `${prefix}API_BASE_URL`),
    tenantId: envText(env, `${prefix}TENANT_ID`),
    projectId: envText(env, `${prefix}PROJECT_ID`),
    sessionCookie: envText(env, `${prefix}SESSION_COOKIE`),
    allowMutation: envText(env, `${prefix}ALLOW_MUTATION`) === "1",
    throwawayProject: envText(env, `${prefix}THROWAWAY_PROJECT`) === "1",
    disposableProjectMarker: envText(env, `${prefix}DISPOSABLE_PROJECT_MARKER`),
    retryRunId: envText(env, `${prefix}RETRY_RUN_ID`),
    consumeRetryRun: envText(env, `${prefix}CONSUME_RETRY_RUN`) === "1",
  };
  if (options.browser) {
    config.appBaseUrl = envText(env, `${prefix}APP_BASE_URL`);
    config.requireWorkerRetry = envText(env, `${prefix}REQUIRE_WORKER_RETRY`) === "1";
    config.workerRetryTimeoutMs = envPositiveInt(env, `${prefix}WORKER_RETRY_TIMEOUT_MS`, 120000);
    config.appDevBypass = envText(env, `${prefix}APP_DEV_BYPASS`) === "1";
    config.expectCompleted = envText(env, `${prefix}EXPECT_COMPLETED`) === "1";
  }
  return config;
}

function assertLocalHttpUrl(value, envName) {
  const message = `${envName} must be a local http URL`;
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

function fixtureArgvFromRunnerFlags(flags) {
  const argv = [];
  for (const name of ["apply", "print-sql"]) {
    if (flags.has(name)) {
      argv.push(`--${name}`);
    }
  }
  return argv;
}

function parseArgs(argv) {
  const values = new Map();
  const booleans = new Set();
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) {
      continue;
    }
    const name = arg.slice(2);
    const equalsIndex = name.indexOf("=");
    if (equalsIndex >= 0) {
      values.set(name.slice(0, equalsIndex), name.slice(equalsIndex + 1));
      continue;
    }
    const next = argv[index + 1];
    if (next && !next.startsWith("--")) {
      values.set(name, next);
      index += 1;
      continue;
    }
    booleans.add(name);
  }
  return {
    get: (name) => values.get(name),
    has: (name) => booleans.has(name) || values.has(name),
  };
}

function envText(env, name) {
  return String(env[name] ?? "").trim();
}

function envPositiveInt(env, name, defaultValue) {
  const value = envText(env, name);
  if (!value) {
    return defaultValue;
  }
  if (!/^[1-9][0-9]*$/.test(value)) {
    throw new Error("live Seed worker retry timeout must be a positive integer");
  }
  const parsed = Number(value);
  if (!Number.isSafeInteger(parsed)) {
    throw new Error("live Seed worker retry timeout must be a positive integer");
  }
  return parsed;
}

function formatCommandFailure(result, env = {}) {
  const details = [];
  if (Number.isInteger(result?.status)) {
    details.push(`status ${result.status}`);
  }
  if (typeof result?.signal === "string" && result.signal) {
    details.push(`signal ${result.signal}`);
  }
  if (typeof result?.errorCode === "string" && result.errorCode) {
    details.push(`error ${result.errorCode}`);
  }
  if (details.length === 0) {
    return formatChildDiagnostics(result, env);
  }
  return ` (${details.join(", ")})${formatChildDiagnostics(result, env)}`;
}

function formatChildDiagnostics(result, env) {
  const chunks = [];
  if (typeof result?.stdout === "string" && result.stdout.trim() !== "") {
    chunks.push(`stdout:\n${result.stdout}`);
  }
  if (typeof result?.stderr === "string" && result.stderr.trim() !== "") {
    chunks.push(`stderr:\n${result.stderr}`);
  }
  if (chunks.length === 0) {
    return "";
  }
  const redacted = redactDiagnosticText(chunks.join("\n"), sensitiveEnvValues(env));
  const tail = redacted.slice(-MAX_CHILD_DIAGNOSTIC_CHARS).trim();
  if (!tail) {
    return "";
  }
  return `\nchild diagnostics:\n${tail}`;
}

function sensitiveEnvValues(env) {
  const values = new Set();
  for (const [name, value] of Object.entries(env)) {
    if (!isSensitiveEnvName(name)) {
      continue;
    }
    const text = String(value ?? "").trim();
    if (text.length >= 4) {
      values.add(text);
    }
  }
  return values;
}

function isSensitiveEnvName(name) {
  return (
    name.includes("SESSION_COOKIE") ||
    name.includes("TENANT_ID") ||
    name.includes("PROJECT_ID") ||
    name.includes("DISPOSABLE_PROJECT_MARKER") ||
    name.includes("RETRY_RUN_ID") ||
    name.includes("DATABASE_URL") ||
    name.includes("API_KEY") ||
    name.includes("CREDENTIAL") ||
    name.includes("TOKEN") ||
    name.includes("SECRET")
  );
}

function redactDiagnosticText(value, exactValues) {
  let text = String(value ?? "");
  for (const exact of exactValues) {
    text = text.split(exact).join(REDACTED);
  }
  text = text.replace(/(mirofish_session\s*=\s*)[^\s;]+/gi, `$1${REDACTED}`);
  text = text.replace(/(bearer\s+)[a-z0-9._~+/=-]+/gi, `$1${REDACTED}`);
  text = text.replace(/\b(v[12]:[a-z0-9_-]+:[a-z0-9:_-]+)\b/gi, REDACTED);
  text = text.replace(/([a-z0-9_-]*(?:api[_-]?key|credential[_-]?ref|encrypted[_-]?credential|token|secret)[a-z0-9_-]*\s*[:=]\s*)[^\s,;]+/gi, `$1${REDACTED}`);
  text = text.replace(/([a-z0-9_-]*(?:prompt|provider(?:[_-]?response)?|raw[_-]?body|raw[_-]?content|content|object[_-]?key)[a-z0-9_-]*\s*[:=]\s*)[^\n]+/gi, `$1${REDACTED}`);
  return text
    .split("\n")
    .map((line) => (/\b(draft|manuscript)\b/i.test(line) ? REDACTED : line))
    .join("\n");
}

async function main() {
  try {
    const result = await runLiveSeedHarness();
    process.stdout.write(result.output);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : "live Seed runner failed"}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  await main();
}
