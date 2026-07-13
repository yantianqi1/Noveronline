#!/usr/bin/env node

import { createCipheriv } from "node:crypto";
import { spawnSync } from "node:child_process";

const IDS = Object.freeze({
  user: "91000000-0000-4000-8000-000000000001",
  tenant: "91000000-0000-4000-8000-000000000002",
  project: "91000000-0000-4000-8000-000000000003",
  channel: "91000000-0000-4000-8000-000000000004",
  moon: "91000000-0000-4000-8000-000000000005",
  fire: "91000000-0000-4000-8000-000000000006",
  foreignTenant: "91000000-0000-4000-8000-000000000007",
  foreignProject: "91000000-0000-4000-8000-000000000008",
  foreignAsset: "91000000-0000-4000-8000-000000000009",
});
const KEY_MATERIAL = "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f";
const PREFIX = "MIROFISH_WEB_ASSETS_FIXTURE_";
const action = process.argv[2] || "prepare";
const databaseUrl = required("DATABASE_URL");
assertLocalUrl(databaseUrl, ["postgres:", "postgresql:"], "DATABASE_URL");

if (action === "cleanup") {
  runPsql(cleanupSql());
  process.stdout.write("Asset Library disposable fixture cleaned\n");
} else if (action === "prepare") {
  const apiBaseUrl = required("API_BASE_URL");
  const providerBaseUrl = required("PROVIDER_BASE_URL");
  const providerKey = required("PROVIDER_KEY");
  assertLocalUrl(apiBaseUrl, ["http:"], "API_BASE_URL");
  assertLocalProviderUrl(providerBaseUrl);
  runPsql(fixtureSql(providerBaseUrl, providerKey));
  const sessionCookie = await createSession(apiBaseUrl);
  process.stdout.write(`${JSON.stringify({
    tenantId: IDS.tenant,
    projectId: IDS.project,
    userId: IDS.user,
    sessionCookie,
    keyMaterial: KEY_MATERIAL,
    query: "Moon rule",
    foreignMarker: "ASSET-FOREIGN-TENANT-MARKER",
  })}\n`);
} else {
  throw new Error("Asset Library fixture action must be prepare or cleanup");
}

function fixtureSql(providerBaseUrl, providerKey) {
  const encryptedApiKey = encrypt(providerKey);
  return `${cleanupSql()}
INSERT INTO users (user_id, email, display_name)
VALUES ('${IDS.user}', 'assets-browser-disposable@example.test', 'Assets Browser Disposable');
INSERT INTO tenants (tenant_id, slug, name, tenant_type)
VALUES
  ('${IDS.tenant}', 'assets-browser-disposable', 'Assets Browser Disposable', 'personal'),
  ('${IDS.foreignTenant}', 'assets-browser-foreign', 'Assets Browser Foreign', 'personal');
INSERT INTO tenant_memberships (tenant_id, user_id, role)
VALUES ('${IDS.tenant}', '${IDS.user}', 'owner');
INSERT INTO projects (tenant_id, project_id, title, created_by)
VALUES
  ('${IDS.tenant}', '${IDS.project}', 'Assets Browser Disposable', '${IDS.user}'),
  ('${IDS.foreignTenant}', '${IDS.foreignProject}', 'Assets Browser Foreign', '${IDS.user}');
INSERT INTO project_members (tenant_id, project_id, user_id, role)
VALUES ('${IDS.tenant}', '${IDS.project}', '${IDS.user}', 'project_owner');
INSERT INTO assets (
  tenant_id, asset_id, project_id, scope, asset_type, category, lifecycle, title, summary,
  content_text, tags_jsonb, source_kind, source_ref, enabled, pinned, created_by
) VALUES
  ('${IDS.tenant}', '${IDS.moon}', '${IDS.project}', 'project', 'world_rule', 'world', 'canon',
   'Moon rule', 'Moon rule governs the night archive.', 'Moon rule private fixture content.', '["moon","rule"]', 'manual', 'moon', true, true, '${IDS.user}'),
  ('${IDS.tenant}', '${IDS.fire}', '${IDS.project}', 'project', 'world_rule', 'world', 'material',
   'Fire rule', 'Fire rule governs the forge archive.', 'Fire rule private fixture content.', '["fire","rule"]', 'manual', 'fire', true, false, '${IDS.user}'),
  ('${IDS.foreignTenant}', '${IDS.foreignAsset}', '${IDS.foreignProject}', 'project', 'note', 'private', 'canon',
   'ASSET-FOREIGN-TENANT-MARKER', 'Foreign tenant marker.', 'Foreign private fixture content.', '[]', 'manual', 'foreign', true, false, '${IDS.user}');
INSERT INTO llm_channels (
  tenant_id, channel_id, name, provider, base_url, encrypted_api_key, max_concurrency, enabled
) VALUES (
  '${IDS.tenant}', '${IDS.channel}', 'Assets Browser Local Provider', 'openai-compatible',
  '${sqlText(providerBaseUrl)}', '${sqlText(encryptedApiKey)}', 2, true
);
INSERT INTO llm_models (tenant_id, channel_id, model_id, owned_by, supports_json, supports_tools)
VALUES ('${IDS.tenant}', '${IDS.channel}', 'assets-browser-embedding-3', 'local-provider', false, false);
INSERT INTO llm_module_bindings (
  tenant_id, project_id, module_key, channel_id, model_id, settings_jsonb, updated_by
) VALUES
  ('${IDS.tenant}', '${IDS.project}', 'asset_reindex', '${IDS.channel}', 'assets-browser-embedding-3', '{"embedding_dimensions":3}', '${IDS.user}'),
  ('${IDS.tenant}', '${IDS.project}', 'asset_search_embedding', '${IDS.channel}', 'assets-browser-embedding-3', '{"embedding_dimensions":3}', '${IDS.user}');
`;
}

function cleanupSql() {
  return `DELETE FROM tenants WHERE tenant_id IN ('${IDS.tenant}', '${IDS.foreignTenant}');
DELETE FROM users WHERE user_id = '${IDS.user}';`;
}

async function createSession(apiBaseUrl) {
  const response = await fetch(new URL("/v1/auth/dev-sessions", apiBaseUrl), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: IDS.user }),
  });
  if (!response.ok) throw new Error(`Asset Library dev session failed with HTTP ${response.status}`);
  const cookie = response.headers.getSetCookie?.().find((value) => value.startsWith("mirofish_session="))
    ?? response.headers.get("set-cookie");
  const match = cookie?.match(/(?:^|;)\s*mirofish_session=([^;]+)/);
  if (!match) throw new Error("Asset Library dev session did not return a session cookie");
  return match[1];
}

function encrypt(value) {
  const key = Buffer.from(KEY_MATERIAL, "hex");
  const iv = Buffer.from("102132435465768798a9bacb", "hex");
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
  if (result.status !== 0) throw new Error("Asset Library disposable fixture SQL failed");
}

function required(suffix) {
  const value = String(process.env[`${PREFIX}${suffix}`] ?? "").trim();
  if (!value) throw new Error(`missing ${PREFIX}${suffix}`);
  return value;
}

function assertLocalUrl(value, protocols, suffix) {
  const url = new URL(value);
  if (!protocols.includes(url.protocol) || !["127.0.0.1", "localhost", "::1"].includes(url.hostname)) {
    throw new Error(`${PREFIX}${suffix} must be local`);
  }
}

function assertLocalProviderUrl(value) {
  const url = new URL(value);
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost", "::1", "host.docker.internal"].includes(url.hostname)) {
    throw new Error(`${PREFIX}PROVIDER_BASE_URL must be local`);
  }
}

function sqlText(value) {
  return String(value).replaceAll("'", "''");
}
