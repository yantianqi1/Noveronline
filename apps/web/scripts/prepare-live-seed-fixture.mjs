#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const FIXTURE_PREFIX = "MIROFISH_WEB_LIVE_SEED_FIXTURE_";
const API_PREFIX = "MIROFISH_WEB_LIVE_SEED_";
const BROWSER_PREFIX = "MIROFISH_WEB_BROWSER_LIVE_SEED_";
const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1", "[::1]"]);

const DEFAULTS = Object.freeze({
  userId: "00000000-0000-4000-8000-000000000501",
  tenantId: "00000000-0000-4000-8000-000000000502",
  projectId: "00000000-0000-4000-8000-000000000503",
  llmChannelId: "77777777-7777-7777-7777-777777777777",
  email: "web-live-seed-fixture@example.test",
  displayName: "Web Live Seed Fixture",
  tenantSlug: "web-live-seed-fixture",
  tenantName: "Web Live Seed Fixture Tenant",
  projectTitleBase: "Disposable Web Live Seed Fixture",
  apiBaseUrl: "http://127.0.0.1:3888",
  appBaseUrl: "http://localhost:3999",
});

const SEED_LLM_MODULES = Object.freeze([
  ["sequential_reading", "model-seed-sequential-live"],
  ["anchor_point_summary", "model-seed-global-aggregation-live"],
  ["story_ontology", "model-seed-ontology-live"],
  ["entity_resolution", "model-seed-entity-resolution-live"],
  ["character_agent_profile", "model-seed-profile-live"],
  ["narrative_archives", "model-seed-archive-live"],
]);

export function loadFixtureConfig(options = {}) {
  const env = options.env ?? process.env;
  const flags = parseArgs(options.argv ?? process.argv.slice(2));

  const config = {
    allowMutation: readBoolean(env, flags, "ALLOW_MUTATION", "allow-mutation"),
    throwawayProject: readBoolean(env, flags, "THROWAWAY_PROJECT", "throwaway-project"),
    disposableProjectMarker: readText(env, flags, "DISPOSABLE_PROJECT_MARKER", "marker"),
    apiBaseUrl: readText(env, flags, "API_BASE_URL", "api-base-url") || DEFAULTS.apiBaseUrl,
    appBaseUrl: readText(env, flags, "APP_BASE_URL", "app-base-url") || DEFAULTS.appBaseUrl,
    databaseUrl: readText(env, flags, "DATABASE_URL", "database-url"),
    userId: readText(env, flags, "USER_ID", "user-id") || DEFAULTS.userId,
    tenantId: readText(env, flags, "TENANT_ID", "tenant-id") || DEFAULTS.tenantId,
    projectId: readText(env, flags, "PROJECT_ID", "project-id") || DEFAULTS.projectId,
    email: readText(env, flags, "USER_EMAIL", "user-email") || DEFAULTS.email,
    displayName: readText(env, flags, "USER_DISPLAY_NAME", "user-display-name") || DEFAULTS.displayName,
    tenantSlug: readText(env, flags, "TENANT_SLUG", "tenant-slug") || DEFAULTS.tenantSlug,
    tenantName: readText(env, flags, "TENANT_NAME", "tenant-name") || DEFAULTS.tenantName,
    sessionCookie: readText(env, flags, "SESSION_COOKIE", "session-cookie"),
    createDevSession: readBoolean(env, flags, "CREATE_DEV_SESSION", "create-dev-session"),
    applySql: readBoolean(env, flags, "APPLY_SQL", "apply") || flags.has("apply"),
    printSql: readBoolean(env, flags, "PRINT_SQL", "print-sql") || flags.has("print-sql"),
    prepareLlmBindings: readBoolean(env, flags, "PREPARE_LLM_BINDINGS", "prepare-llm-bindings"),
    llmProviderBaseUrl: readText(env, flags, "LLM_PROVIDER_BASE_URL", "llm-provider-base-url"),
    llmEncryptedApiKey: readText(env, flags, "LLM_ENCRYPTED_API_KEY", "llm-encrypted-api-key"),
    llmChannelId: readText(env, flags, "LLM_CHANNEL_ID", "llm-channel-id") || DEFAULTS.llmChannelId,
  };

  config.projectTitle = projectTitle(config);
  assertStrictOptIn(config);
  assertLocalHttpUrl(config.apiBaseUrl, "MIROFISH_WEB_LIVE_SEED_FIXTURE_API_BASE_URL");
  assertLocalHttpUrl(config.appBaseUrl, "MIROFISH_WEB_LIVE_SEED_FIXTURE_APP_BASE_URL");
  return config;
}

export async function prepareLiveSeedFixture(options = {}) {
  const config = loadFixtureConfig(options);
  const sections = [];

  assertSessionPlan(config);
  assertLlmBindingPlan(config);
  if (config.applySql) {
    assertLocalPostgresUrl(config.databaseUrl, "MIROFISH_WEB_LIVE_SEED_FIXTURE_DATABASE_URL");
  }

  const sql = buildFixtureSql(config);
  if (config.printSql || !config.applySql) {
    sections.push(sql.trimEnd());
  }
  if (config.applySql) {
    applyFixtureSql(config, sql, options.runPsql);
  }

  let sessionCookie = config.sessionCookie;
  if (!sessionCookie && config.createDevSession) {
    sessionCookie = await createDevSession(config, options.fetchImpl ?? globalThis.fetch);
  }
  if (!sessionCookie) {
    throw new Error("live Seed fixture is missing env names: MIROFISH_WEB_LIVE_SEED_FIXTURE_SESSION_COOKIE or MIROFISH_WEB_LIVE_SEED_FIXTURE_CREATE_DEV_SESSION");
  }

  const finalConfig = { ...config, sessionCookie };
  sections.push(renderShellExports(finalConfig));
  return {
    config: finalConfig,
    sql,
    output: `${sections.join("\n\n")}\n`,
  };
}

export function buildFixtureSql(config) {
  const values = {
    userId: sqlLiteral(config.userId),
    tenantId: sqlLiteral(config.tenantId),
    projectId: sqlLiteral(config.projectId),
    email: sqlLiteral(config.email),
    displayName: sqlLiteral(config.displayName),
    tenantSlug: sqlLiteral(config.tenantSlug),
    tenantName: sqlLiteral(config.tenantName),
    projectTitle: sqlLiteral(config.projectTitle),
    llmChannelId: sqlLiteral(config.llmChannelId),
    llmProviderBaseUrl: sqlLiteral(config.llmProviderBaseUrl),
    llmEncryptedApiKey: sqlLiteral(config.llmEncryptedApiKey),
  };

  return `BEGIN;

INSERT INTO users (user_id, email, display_name, status)
VALUES (${values.userId}::uuid, ${values.email}, ${values.displayName}, 'active')
ON CONFLICT (user_id) DO UPDATE
SET email = EXCLUDED.email,
    display_name = EXCLUDED.display_name,
    status = 'active',
    updated_at = now();

INSERT INTO tenants (tenant_id, slug, name, tenant_type, status)
VALUES (${values.tenantId}::uuid, ${values.tenantSlug}, ${values.tenantName}, 'personal', 'active')
ON CONFLICT (tenant_id) DO UPDATE
SET slug = EXCLUDED.slug,
    name = EXCLUDED.name,
    tenant_type = EXCLUDED.tenant_type,
    status = 'active',
    updated_at = now();

INSERT INTO tenant_memberships (tenant_id, user_id, role, status, joined_at)
VALUES (${values.tenantId}::uuid, ${values.userId}::uuid, 'owner', 'active', now())
ON CONFLICT (tenant_id, user_id) DO UPDATE
SET role = EXCLUDED.role,
    status = 'active',
    joined_at = COALESCE(tenant_memberships.joined_at, EXCLUDED.joined_at),
    updated_at = now();

INSERT INTO projects (tenant_id, project_id, title, created_by, status)
VALUES (${values.tenantId}::uuid, ${values.projectId}::uuid, ${values.projectTitle}, ${values.userId}::uuid, 'active')
ON CONFLICT (project_id) DO UPDATE
SET tenant_id = EXCLUDED.tenant_id,
    title = EXCLUDED.title,
    created_by = EXCLUDED.created_by,
    status = 'active',
    updated_at = now();

INSERT INTO project_members (tenant_id, project_id, user_id, role, status)
VALUES (${values.tenantId}::uuid, ${values.projectId}::uuid, ${values.userId}::uuid, 'project_owner', 'active')
ON CONFLICT (tenant_id, project_id, user_id) DO UPDATE
SET role = EXCLUDED.role,
    status = 'active',
    updated_at = now();
${config.prepareLlmBindings ? buildLlmBindingSql(values) : ""}
COMMIT;
`;
}

export function renderShellExports(config) {
  const apiEntries = [
    ["API_BASE_URL", config.apiBaseUrl],
    ["TENANT_ID", config.tenantId],
    ["PROJECT_ID", config.projectId],
    ["SESSION_COOKIE", config.sessionCookie],
    ["ALLOW_MUTATION", "1"],
    ["THROWAWAY_PROJECT", "1"],
    ["DISPOSABLE_PROJECT_MARKER", config.disposableProjectMarker],
  ];
  const browserEntries = [
    ["APP_BASE_URL", config.appBaseUrl],
    ["API_BASE_URL", config.apiBaseUrl],
    ["TENANT_ID", config.tenantId],
    ["PROJECT_ID", config.projectId],
    ["SESSION_COOKIE", config.sessionCookie],
    ["ALLOW_MUTATION", "1"],
    ["THROWAWAY_PROJECT", "1"],
    ["DISPOSABLE_PROJECT_MARKER", config.disposableProjectMarker],
  ];

  return [
    ...apiEntries.map(([name, value]) => exportLine(`${API_PREFIX}${name}`, value)),
    ...browserEntries.map(([name, value]) => exportLine(`${BROWSER_PREFIX}${name}`, value)),
  ].join("\n");
}

export function extractSessionCookie(headers) {
  const cookieHeaders = [];
  if (typeof headers?.getSetCookie === "function") {
    cookieHeaders.push(...headers.getSetCookie());
  }
  if (typeof headers?.raw === "function") {
    const raw = headers.raw();
    if (Array.isArray(raw?.["set-cookie"])) {
      cookieHeaders.push(...raw["set-cookie"]);
    }
  }
  if (typeof headers?.get === "function") {
    const header = headers.get("set-cookie");
    if (header) {
      cookieHeaders.push(header);
    }
  }

  for (const header of cookieHeaders) {
    const match = String(header).match(/(?:^|[,\s])mirofish_session=([^;\s,]+)/);
    if (match?.[1]) {
      return match[1];
    }
  }
  return "";
}

export function assertLocalHttpUrl(value, envName) {
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

export function assertLocalPostgresUrl(value, envName) {
  const message = `${envName} must be a local postgres URL`;
  if (typeof value !== "string" || value.trim() === "") {
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
    !["postgres:", "postgresql:"].includes(parsed.protocol) ||
    !LOCAL_HOSTS.has(hostname)
  ) {
    throw new Error(message);
  }
  return parsed;
}

async function createDevSession(config, fetchImpl) {
  if (typeof fetchImpl !== "function") {
    throw new Error("dev session request failed");
  }
  const url = new URL("/v1/auth/dev-sessions", config.apiBaseUrl).toString();
  let response;
  try {
    response = await fetchImpl(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: config.userId }),
    });
  } catch {
    throw new Error("dev session request failed");
  }
  if (!response?.ok) {
    throw new Error(`dev session request failed with HTTP ${response?.status ?? "unknown"}`);
  }
  const sessionCookie = extractSessionCookie(response.headers);
  if (!sessionCookie) {
    throw new Error("dev session request failed to return mirofish_session cookie");
  }
  return sessionCookie;
}

function applyFixtureSql(config, sql, runPsql) {
  if (!config.databaseUrl) {
    throw new Error("live Seed fixture is missing env names: MIROFISH_WEB_LIVE_SEED_FIXTURE_DATABASE_URL");
  }
  const runner = runPsql ?? defaultRunPsql;
  const result = runner(config.databaseUrl, sql);
  if (!result?.ok) {
    throw new Error(`psql fixture apply failed${formatPsqlFailure(result)}`);
  }
}

function defaultRunPsql(databaseUrl, sql) {
  const result = spawnSync("psql", [databaseUrl, "-v", "ON_ERROR_STOP=1"], {
    input: sql,
    encoding: "utf8",
    stdio: ["pipe", "ignore", "ignore"],
  });
  return {
    ok: result.status === 0,
    status: result.status,
    signal: result.signal,
    errorCode: result.error?.code,
  };
}

function assertStrictOptIn(config) {
  const missing = [];
  if (!config.allowMutation) {
    missing.push(`${FIXTURE_PREFIX}ALLOW_MUTATION`);
  }
  if (!config.throwawayProject) {
    missing.push(`${FIXTURE_PREFIX}THROWAWAY_PROJECT`);
  }
  if (!config.disposableProjectMarker) {
    missing.push(`${FIXTURE_PREFIX}DISPOSABLE_PROJECT_MARKER`);
  }
  if (missing.length > 0) {
    throw new Error(`live Seed fixture mutation opt-in is incomplete; missing env/flag names: ${missing.join(", ")}`);
  }
}

function assertSessionPlan(config) {
  if (config.sessionCookie || config.createDevSession) {
    return;
  }
  throw new Error("live Seed fixture is missing env names: MIROFISH_WEB_LIVE_SEED_FIXTURE_SESSION_COOKIE or MIROFISH_WEB_LIVE_SEED_FIXTURE_CREATE_DEV_SESSION");
}

function assertLlmBindingPlan(config) {
  if (!config.prepareLlmBindings) {
    return;
  }
  if (!config.applySql || config.printSql) {
    throw new Error("MIROFISH_WEB_LIVE_SEED_FIXTURE_PREPARE_LLM_BINDINGS requires --apply without --print-sql");
  }
  assertLocalHttpUrl(config.llmProviderBaseUrl, "MIROFISH_WEB_LIVE_SEED_FIXTURE_LLM_PROVIDER_BASE_URL");
  if (!isEncryptedCredentialEnvelope(config.llmEncryptedApiKey)) {
    throw new Error("MIROFISH_WEB_LIVE_SEED_FIXTURE_LLM_ENCRYPTED_API_KEY must be an aes-256-gcm:v1 credential envelope");
  }
}

function formatPsqlFailure(result) {
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
    return "";
  }
  return ` (${details.join(", ")})`;
}

function projectTitle(config) {
  const marker = String(config.disposableProjectMarker ?? "").trim();
  if (!marker) {
    return DEFAULTS.projectTitleBase;
  }
  return `${DEFAULTS.projectTitleBase} - ${marker}`;
}

function parseArgs(argv) {
  const values = new Map();
  const booleans = new Set();
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (!arg.startsWith("--")) {
      continue;
    }
    const withoutPrefix = arg.slice(2);
    const equalsIndex = withoutPrefix.indexOf("=");
    if (equalsIndex >= 0) {
      values.set(withoutPrefix.slice(0, equalsIndex), withoutPrefix.slice(equalsIndex + 1));
      continue;
    }
    const next = argv[index + 1];
    if (next && !next.startsWith("--")) {
      values.set(withoutPrefix, next);
      index += 1;
      continue;
    }
    booleans.add(withoutPrefix);
  }
  return {
    get: (name) => values.get(name),
    has: (name) => booleans.has(name) || values.has(name),
    boolean: (name) => booleans.has(name) || values.get(name) === "1" || values.get(name) === "true",
  };
}

function readText(env, flags, envSuffix, flagName) {
  const flagged = flags.get(flagName);
  if (flagged !== undefined) {
    return String(flagged).trim();
  }
  return String(env[`${FIXTURE_PREFIX}${envSuffix}`] ?? "").trim();
}

function readBoolean(env, flags, envSuffix, flagName) {
  if (flags.has(flagName)) {
    return flags.boolean(flagName);
  }
  return String(env[`${FIXTURE_PREFIX}${envSuffix}`] ?? "").trim() === "1";
}

function buildLlmBindingSql(values) {
  const modelRows = SEED_LLM_MODULES.map(([, modelId]) =>
    `  (${values.tenantId}::uuid, ${values.llmChannelId}::uuid, ${sqlLiteral(modelId)}, 'live-provider', true, false)`,
  ).join(",\n");
  const bindingRows = SEED_LLM_MODULES.map(([moduleKey, modelId]) =>
    `  (${values.tenantId}::uuid, ${values.projectId}::uuid, ${sqlLiteral(moduleKey)}, ${values.llmChannelId}::uuid, ${sqlLiteral(modelId)}, '{"temperature":0}'::jsonb, ${values.userId}::uuid)`,
  ).join(",\n");

  return `
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM llm_channels
    WHERE channel_id = ${values.llmChannelId}::uuid
      AND tenant_id <> ${values.tenantId}::uuid
  ) THEN
    RAISE EXCEPTION 'LIVE_SEED_LLM_CHANNEL_TENANT_COLLISION'
      USING ERRCODE = 'check_violation';
  END IF;
END $$;

INSERT INTO llm_channels (
  tenant_id, channel_id, name, provider, base_url, encrypted_api_key, max_concurrency, enabled
)
VALUES (
  ${values.tenantId}::uuid,
  ${values.llmChannelId}::uuid,
  'Seed Semantic Live Provider',
  'openai-compatible',
  ${values.llmProviderBaseUrl},
  ${values.llmEncryptedApiKey},
  2,
  true
)
ON CONFLICT (channel_id) DO UPDATE
SET tenant_id = EXCLUDED.tenant_id,
    name = EXCLUDED.name,
    provider = EXCLUDED.provider,
    base_url = EXCLUDED.base_url,
    encrypted_api_key = EXCLUDED.encrypted_api_key,
    max_concurrency = EXCLUDED.max_concurrency,
    enabled = true,
    updated_at = now();

INSERT INTO llm_models (
  tenant_id, channel_id, model_id, owned_by, supports_json, supports_tools
)
VALUES
${modelRows}
ON CONFLICT (channel_id, model_id) DO UPDATE
SET tenant_id = EXCLUDED.tenant_id,
    owned_by = EXCLUDED.owned_by,
    supports_json = true,
    supports_tools = false,
    updated_at = now();

INSERT INTO llm_module_bindings (
  tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by
)
VALUES
${bindingRows}
ON CONFLICT (tenant_id, project_id, module_key) DO UPDATE
SET channel_id = EXCLUDED.channel_id,
    model_id = EXCLUDED.model_id,
    settings_jsonb = EXCLUDED.settings_jsonb,
    updated_by = EXCLUDED.updated_by,
    updated_at = now();
`;
}

function sqlLiteral(value) {
  return `'${String(value).replaceAll("'", "''")}'`;
}

function isEncryptedCredentialEnvelope(value) {
  const parts = String(value ?? "").split(":");
  if (parts.length !== 5 || parts[0] !== "aes-256-gcm" || parts[1] !== "v1") {
    return false;
  }
  const [iv, tag, ciphertext] = parts.slice(2);
  return base64ByteLength(iv) === 12 && base64ByteLength(tag) === 16 && base64ByteLength(ciphertext) > 0;
}

function base64ByteLength(value) {
  if (typeof value !== "string" || value.trim() === "" || /\s/.test(value)) {
    return -1;
  }
  let decoded;
  try {
    decoded = Buffer.from(value, "base64");
  } catch {
    return -1;
  }
  if (decoded.length === 0 || decoded.toString("base64") !== value) {
    return -1;
  }
  return decoded.length;
}

function exportLine(name, value) {
  return `export ${name}=${shellQuote(value)}`;
}

function shellQuote(value) {
  return `'${String(value).replaceAll("'", `'"'"'`)}'`;
}

async function main() {
  try {
    const result = await prepareLiveSeedFixture();
    process.stdout.write(result.output);
  } catch (error) {
    process.stderr.write(`${error instanceof Error ? error.message : "live Seed fixture failed"}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  await main();
}
