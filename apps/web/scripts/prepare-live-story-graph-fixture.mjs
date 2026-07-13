#!/usr/bin/env node

import { createCipheriv } from "node:crypto";
import { spawnSync } from "node:child_process";

const IDS = Object.freeze({
  user: "81000000-0000-4000-8000-000000000001",
  tenant: "81000000-0000-4000-8000-000000000002",
  project: "81000000-0000-4000-8000-000000000003",
  seedRun: "81000000-0000-4000-8000-000000000004",
  channel: "81000000-0000-4000-8000-000000000005",
});
const APP_ROLE = "mirofish_graph_browser_app";
const APP_PASSWORD = "mirofish_graph_browser_password";
const KEY_MATERIAL = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f";
const PREFIX = "MIROFISH_WEB_GRAPH_FIXTURE_";

const action = process.argv[2] || "prepare";
const databaseUrl = required("DATABASE_URL");
assertLocalUrl(databaseUrl, ["postgres:", "postgresql:"], "DATABASE_URL");

if (action === "cleanup") {
  runPsql(cleanupSql({ dropRole: true }));
  process.stdout.write("Story Graph disposable fixture cleaned\n");
} else if (action === "prepare") {
  const apiBaseUrl = required("API_BASE_URL");
  const providerBaseUrl = required("PROVIDER_BASE_URL");
  assertLocalUrl(apiBaseUrl, ["http:"], "API_BASE_URL");
  assertLocalUrl(providerBaseUrl, ["http:"], "PROVIDER_BASE_URL");
  runPsql(fixtureSql(providerBaseUrl));
  const sessionCookie = await createSession(apiBaseUrl);
  const appDatabaseUrl = databaseUrlForRole(databaseUrl);
  const output = {
    tenantId: IDS.tenant,
    projectId: IDS.project,
    userId: IDS.user,
    sessionCookie,
    appDatabaseUrl,
    keyMaterial: KEY_MATERIAL,
    disposableProjectMarker: "graph browser disposable",
  };
  process.stdout.write(`${JSON.stringify(output)}\n`);
} else {
  throw new Error("Story Graph fixture action must be prepare or cleanup");
}

function fixtureSql(providerBaseUrl) {
  const encryptedApiKey = encrypt("sk-local-graph-browser");
  return `
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${APP_ROLE}') THEN
    CREATE ROLE ${APP_ROLE} LOGIN PASSWORD '${APP_PASSWORD}' IN ROLE mirofish_app;
  ELSE
    ALTER ROLE ${APP_ROLE} WITH LOGIN PASSWORD '${APP_PASSWORD}';
  END IF;
  GRANT mirofish_app TO ${APP_ROLE};
END $$;
${cleanupSql()}
INSERT INTO users (user_id, email, display_name)
VALUES ('${IDS.user}', 'graph-browser-disposable@example.test', 'Graph Browser Disposable');
INSERT INTO tenants (tenant_id, slug, name, tenant_type)
VALUES ('${IDS.tenant}', 'graph-browser-disposable', 'Graph Browser Disposable', 'personal');
INSERT INTO tenant_memberships (tenant_id, user_id, role)
VALUES ('${IDS.tenant}', '${IDS.user}', 'owner');
INSERT INTO projects (tenant_id, project_id, title, created_by)
VALUES ('${IDS.tenant}', '${IDS.project}', 'Graph Browser Disposable', '${IDS.user}');
INSERT INTO project_members (tenant_id, project_id, user_id, role)
VALUES ('${IDS.tenant}', '${IDS.project}', '${IDS.user}', 'project_owner');
INSERT INTO workflow_runs (tenant_id, run_id, workflow_type, project_id, status, progress, started_by)
VALUES ('${IDS.tenant}', '${IDS.seedRun}', 'seed_pipeline', '${IDS.project}', 'completed', 100, '${IDS.user}');
INSERT INTO entities (
  tenant_id, entity_id, project_id, source_run_id, canonical_name, entity_type, importance, state_summary
)
SELECT '${IDS.tenant}',
       ('82000000-0000-4000-8000-' || lpad(series::text, 12, '0'))::uuid,
       '${IDS.project}', '${IDS.seedRun}',
       CASE WHEN series = 2 THEN 'Alias Character' ELSE 'Character ' || lpad(series::text, 4, '0') END,
       CASE WHEN series < 3 OR series % 3 <> 0 THEN 'character' ELSE 'organization' END,
       CASE WHEN series <= 20 THEN 'high' ELSE 'medium' END,
       'Public graph browser summary ' || series
FROM generate_series(1, 1005) AS series;
INSERT INTO entity_aliases (tenant_id, project_id, entity_id, alias)
VALUES ('${IDS.tenant}', '${IDS.project}', '82000000-0000-4000-8000-000000000002', 'Character 0001');
INSERT INTO relationships (
  tenant_id, project_id, source_entity_name, target_entity_name, relationship_type, summary, source_run_id
)
SELECT '${IDS.tenant}', '${IDS.project}',
       CASE WHEN series = 2 THEN 'Alias Character' ELSE 'Character ' || lpad(series::text, 4, '0') END,
       CASE WHEN series + 1 = 2 THEN 'Alias Character' ELSE 'Character ' || lpad((series + 1)::text, 4, '0') END,
       CASE WHEN series % 5 = 0 THEN 'opposes' ELSE 'relationship' END,
       'Public relationship summary ' || series, '${IDS.seedRun}'
FROM generate_series(1, 1004) AS series;
INSERT INTO plot_threads (tenant_id, project_id, source_run_id, title, status, summary)
SELECT '${IDS.tenant}', '${IDS.project}', '${IDS.seedRun}', 'Plot thread ' || series, 'open', 'Public plot summary ' || series
FROM generate_series(1, 4) AS series;
INSERT INTO assets (
  tenant_id, project_id, scope, asset_type, category, lifecycle, title, summary,
  source_kind, source_ref, enabled, pinned, created_by
)
SELECT '${IDS.tenant}', '${IDS.project}', 'project', 'artifact', 'world', 'canon',
       'Artifact ' || series, 'Public artifact summary ' || series, 'manual',
       'graph-browser:' || series, true, false, '${IDS.user}'
FROM generate_series(1, 2) AS series;
INSERT INTO llm_channels (
  tenant_id, channel_id, name, provider, base_url, encrypted_api_key, max_concurrency, enabled
)
VALUES (
  '${IDS.tenant}', '${IDS.channel}', 'Graph Browser Local Provider', 'openai-compatible',
  '${sqlText(providerBaseUrl)}', '${sqlText(encryptedApiKey)}', 1, true
);
INSERT INTO llm_models (tenant_id, channel_id, model_id, owned_by, supports_json, supports_tools)
VALUES ('${IDS.tenant}', '${IDS.channel}', 'model-graph-browser-live', 'local-provider', true, false);
INSERT INTO llm_module_bindings (
  tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by
)
VALUES (
  '${IDS.tenant}', '${IDS.project}', 'graph_bond_generator', '${IDS.channel}',
  'model-graph-browser-live', '{"temperature":0}'::jsonb, '${IDS.user}'
);
`;
}

function cleanupSql({ dropRole = false } = {}) {
  return `DELETE FROM tenants WHERE tenant_id = '${IDS.tenant}';
DELETE FROM users WHERE user_id = '${IDS.user}';
${dropRole ? `DROP ROLE IF EXISTS ${APP_ROLE};` : ""}`;
}

async function createSession(apiBaseUrl) {
  const response = await fetch(new URL("/v1/auth/dev-sessions", apiBaseUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: IDS.user }),
  });
  if (!response.ok) {
    throw new Error(`Story Graph dev session failed with HTTP ${response.status}`);
  }
  const cookie = response.headers.getSetCookie?.().find((value) => value.startsWith("mirofish_session="))
    ?? response.headers.get("set-cookie");
  const match = cookie?.match(/(?:^|;)\s*mirofish_session=([^;]+)/);
  if (!match) {
    throw new Error("Story Graph dev session did not return a session cookie");
  }
  return match[1];
}

function encrypt(value) {
  const key = Buffer.from(KEY_MATERIAL, "hex");
  const iv = Buffer.from("00112233445566778899aabb", "hex");
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const ciphertext = Buffer.concat([cipher.update(value, "utf8"), cipher.final()]);
  return `aes-256-gcm:v1:${iv.toString("base64")}:${cipher.getAuthTag().toString("base64")}:${ciphertext.toString("base64")}`;
}

function runPsql(sql) {
  const result = spawnSync("psql", [databaseUrl, "-v", "ON_ERROR_STOP=1", "-q"], {
    input: sql,
    encoding: "utf8",
    stdio: ["pipe", "pipe", "pipe"],
  });
  if (result.status !== 0) {
    throw new Error("Story Graph disposable fixture SQL failed");
  }
}

function databaseUrlForRole(value) {
  const url = new URL(value);
  url.username = APP_ROLE;
  url.password = APP_PASSWORD;
  return url.toString();
}

function required(suffix) {
  const value = String(process.env[`${PREFIX}${suffix}`] ?? "").trim();
  if (!value) {
    throw new Error(`missing ${PREFIX}${suffix}`);
  }
  return value;
}

function assertLocalUrl(value, protocols, suffix) {
  const url = new URL(value);
  if (!protocols.includes(url.protocol) || !["127.0.0.1", "localhost", "::1"].includes(url.hostname)) {
    throw new Error(`${PREFIX}${suffix} must be local`);
  }
}

function sqlText(value) {
  return String(value).replaceAll("'", "''");
}
