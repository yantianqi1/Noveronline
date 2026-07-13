#!/usr/bin/env node

import { createCipheriv, createHash, randomBytes } from "node:crypto";
import { spawnSync } from "node:child_process";

const prefix = "MIROFISH_WEB_PLATFORM_FIXTURE_";
const action = process.argv[2] || "prepare";
const ids = Object.freeze({
  owner: "a3000000-0000-4000-8000-000000000001",
  invitee: "a3000000-0000-4000-8000-000000000003",
  tenant: "b3000000-0000-4000-8000-000000000001",
  project: "c3000000-0000-4000-8000-000000000001",
  invitation: "f3000000-0000-4000-8000-000000000001",
  reset: "f3000000-0000-4000-8000-000000000002",
  channel: "f3000000-0000-4000-8000-000000000003",
});
const databaseURL = required("DATABASE_URL");
assertLocalDatabase(databaseURL);

if (action === "cleanup") {
  psql(cleanupSQL());
  process.stdout.write("Platform browser fixture cleaned\n");
} else if (action === "prepare") {
  const ownerPassword = required("OWNER_PASSWORD");
  const inviteePassword = required("INVITEE_PASSWORD");
  const recoveryToken = required("RECOVERY_TOKEN");
  const invitationToken = required("INVITATION_TOKEN");
  const providerBaseURL = required("PROVIDER_BASE_URL");
  assertLocalProvider(providerBaseURL);
  const key = decodeKey(required("LLM_CREDENTIAL_ENCRYPTION_KEY"));
  psql(fixtureSQL({ ownerPassword, inviteePassword, recoveryToken, invitationToken, providerBaseURL, encryptedKey: encrypt("platform-browser-local-key", key) }));
  process.stdout.write("Platform browser fixture ready\n");
} else {
  throw new Error("Platform browser fixture action must be prepare or cleanup");
}

function fixtureSQL(input) {
  return `
BEGIN;
${cleanupSQL()}
UPDATE user_password_credentials
SET password_hash=crypt('${sql(input.ownerPassword)}', gen_salt('bf', 8)), status='active', updated_at=now()
WHERE user_id='${ids.owner}';
INSERT INTO project_members(tenant_id,project_id,user_id,role,status)
VALUES('${ids.tenant}','${ids.project}','${ids.owner}','project_owner','active')
ON CONFLICT (tenant_id,project_id,user_id) DO UPDATE SET role='project_owner',status='active',updated_at=now();
INSERT INTO users(user_id,email,display_name,status)
VALUES('${ids.invitee}','platform-invitee@example.test','Platform Invitee','active');
INSERT INTO user_password_credentials(user_id,password_hash,status)
VALUES('${ids.invitee}',crypt('${sql(input.inviteePassword)}',gen_salt('bf',8)),'active');
INSERT INTO password_reset_tokens(reset_token_id,user_id,token_hash,status,delivery_status,request_id,expires_at)
VALUES('${ids.reset}','${ids.owner}','${hash(input.recoveryToken)}','pending','pending','platform-browser-reset',now()+interval '30 minutes');
INSERT INTO collaboration_invitations(
  tenant_id,invitation_id,project_id,email_normalized,project_role,token_hash,status,delivery_status,invited_by,request_id,expires_at
) VALUES(
  '${ids.tenant}','${ids.invitation}','${ids.project}','platform-invitee@example.test','viewer','${hash(input.invitationToken)}',
  'pending','pending','${ids.owner}','platform-browser-invite',now()+interval '30 minutes'
);
INSERT INTO llm_channels(tenant_id,channel_id,name,provider,base_url,encrypted_api_key,max_concurrency,enabled)
VALUES('${ids.tenant}','${ids.channel}','Platform Browser Local','openai-compatible','${sql(input.providerBaseURL)}','${sql(input.encryptedKey)}',2,true);
INSERT INTO llm_models(tenant_id,channel_id,model_id,owned_by,supports_tools,supports_json,input_cost,output_cost)
VALUES('${ids.tenant}','${ids.channel}','writer-live-composer','local-provider',false,true,1,2);
INSERT INTO llm_module_bindings(tenant_id,project_id,module_key,channel_id,model_id,settings_jsonb,updated_by)
VALUES('${ids.tenant}','${ids.project}','writer_composer','${ids.channel}','writer-live-composer','{"temperature":0,"max_tokens":64}','${ids.owner}');
COMMIT;
`;
}

function cleanupSQL() {
  return `
DELETE FROM auth_abuse_rate_limits WHERE scope_key_hash='${abuseHash("password_reset_request_email", "compose-auth@example.test")}';
DELETE FROM password_reset_tokens WHERE user_id='${ids.owner}';
DELETE FROM collaboration_invitations WHERE tenant_id='${ids.tenant}' AND email_normalized='platform-invitee@example.test';
DELETE FROM llm_quota_reservations WHERE tenant_id='${ids.tenant}' AND channel_id='${ids.channel}';
DELETE FROM llm_quota_policies WHERE tenant_id='${ids.tenant}' AND project_id='${ids.project}';
DELETE FROM llm_module_bindings WHERE tenant_id='${ids.tenant}' AND channel_id='${ids.channel}';
DELETE FROM llm_channels WHERE tenant_id='${ids.tenant}' AND channel_id='${ids.channel}';
DELETE FROM project_members WHERE tenant_id='${ids.tenant}' AND user_id='${ids.invitee}';
DELETE FROM tenant_memberships WHERE tenant_id='${ids.tenant}' AND user_id='${ids.invitee}';
DELETE FROM audit_logs WHERE tenant_id='${ids.tenant}' AND actor_user_id='${ids.invitee}' AND resource_type='collaboration_invitation' AND resource_id='${ids.invitation}';
DELETE FROM users WHERE user_id='${ids.invitee}';`;
}

function encrypt(value, key) {
  const iv = randomBytes(12);
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const ciphertext = Buffer.concat([cipher.update(value, "utf8"), cipher.final()]);
  return `aes-256-gcm:v1:${iv.toString("base64")}:${cipher.getAuthTag().toString("base64")}:${ciphertext.toString("base64")}`;
}

function decodeKey(raw) {
  if (/^[0-9a-fA-F]{64}$/.test(raw)) return Buffer.from(raw, "hex");
  const decoded = Buffer.from(raw, "base64");
  if (decoded.length !== 32 || decoded.toString("base64") !== raw) throw new Error("platform fixture encryption key must be canonical 32-byte hex or standard Base64");
  return decoded;
}

function hash(value) { return createHash("sha256").update(value).digest("hex"); }
function abuseHash(action, scopeKey) { return hash(`${action.trim()}\0${scopeKey.trim()}`); }
function sql(value) { return String(value).replaceAll("'", "''"); }
function required(suffix) { const value = String(process.env[`${prefix}${suffix}`] || "").trim(); if (!value) throw new Error(`missing ${prefix}${suffix}`); return value; }
function assertLocalDatabase(value) { const url = new URL(value); if (!["postgres:", "postgresql:"].includes(url.protocol) || !["127.0.0.1", "localhost", "::1"].includes(url.hostname)) throw new Error("platform fixture database must be local"); }
function assertLocalProvider(value) { const url = new URL(value); if (url.protocol !== "http:" || !["127.0.0.1", "localhost", "host.docker.internal"].includes(url.hostname) || url.username || url.password) throw new Error("platform fixture provider must be local credential-free HTTP"); }
function psql(statement) {
  const result = spawnSync("psql", [databaseURL, "-v", "ON_ERROR_STOP=1", "-q"], { input: statement, encoding: "utf8" });
  if (result.status !== 0) {
    if (result.stderr) process.stderr.write(result.stderr);
    throw new Error("Platform disposable fixture SQL failed");
  }
}
