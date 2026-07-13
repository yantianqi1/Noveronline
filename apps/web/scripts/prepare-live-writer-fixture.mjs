#!/usr/bin/env node

import { createCipheriv } from "node:crypto";
import { spawnSync } from "node:child_process";
import { pathToFileURL } from "node:url";

const ids = Object.freeze({
  user: "c1000000-0000-4000-8000-000000000001",
  tenant: "c1000000-0000-4000-8000-000000000002",
  project: "c1000000-0000-4000-8000-000000000003",
  asset: "c1000000-0000-4000-8000-000000000004",
  graph: "c1000000-0000-4000-8000-000000000005",
  node: "c1000000-0000-4000-8000-000000000006",
  neighbor: "c1000000-0000-4000-8000-000000000007",
  edge: "c1000000-0000-4000-8000-000000000008",
  worldlineRun: "c1000000-0000-4000-8000-000000000009",
  worldlineSession: "c1000000-0000-4000-8000-000000000010",
  worldlinePath: "c1000000-0000-4000-8000-000000000011",
  orchestratorChannel: "c1000000-0000-4000-8000-000000000012",
  composerChannel: "c1000000-0000-4000-8000-000000000013",
  reviewerChannel: "c1000000-0000-4000-8000-000000000014",
  dedupChannel: "c1000000-0000-4000-8000-000000000015",
  bookPlannerChannel: "c1000000-0000-4000-8000-000000000016",
  bookPlan: "c1000000-0000-4000-8000-000000000017",
});
const role = "mirofish_writer_browser_app";
const rolePassword = "mirofish_writer_browser_password";
const prefix = "MIROFISH_WEB_WRITER_FIXTURE_";
let databaseURL = "";

function main() {
  const action = process.argv[2] || "prepare";
  databaseURL = required("DATABASE_URL");
  assertLocalDatabase(databaseURL);

  if (action === "cleanup") {
    psql(cleanupSQL(true));
    process.stdout.write("Writer disposable fixture cleaned\n");
  } else if (action === "prepare") {
    const encryptionKey = decodeWriterCredentialEncryptionKey(required("LLM_CREDENTIAL_ENCRYPTION_KEY"));
    const providerBaseURL = required("PROVIDER_BASE_URL");
    const provider = new URL(providerBaseURL);
    if (provider.protocol !== "http:" || provider.username || provider.password) {
      throw new Error("writer fixture provider must be credential-free HTTP");
    }
    psql(fixtureSQL(providerBaseURL, encryptionKey));
    const appDatabaseURL = new URL(databaseURL);
    appDatabaseURL.username = role;
    appDatabaseURL.password = rolePassword;
    process.stdout.write(`${JSON.stringify({
      tenantId: ids.tenant,
      projectId: ids.project,
      userId: ids.user,
      assetId: ids.asset,
      graphNodeId: ids.node,
      worldlinePathId: ids.worldlinePath,
      bookPlanId: ids.bookPlan,
      appDatabaseURL: appDatabaseURL.toString(),
    })}\n`);
  } else {
    throw new Error("Writer fixture action must be prepare or cleanup");
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main();
}

function fixtureSQL(providerBaseURL, encryptionKey) {
  const encrypted = encrypt("writer-browser-local-key", encryptionKey);
  return `
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${role}') THEN
    CREATE ROLE ${role} LOGIN PASSWORD '${rolePassword}' IN ROLE mirofish_app;
  ELSE
    ALTER ROLE ${role} WITH LOGIN PASSWORD '${rolePassword}';
  END IF;
  GRANT mirofish_app TO ${role};
END $$;
${cleanupSQL(false)}
INSERT INTO users (user_id,email,display_name) VALUES ('${ids.user}','writer-browser@example.test','Writer Browser');
INSERT INTO tenants (tenant_id,slug,name,tenant_type) VALUES ('${ids.tenant}','writer-browser','Writer Browser','personal');
INSERT INTO tenant_memberships (tenant_id,user_id,role) VALUES ('${ids.tenant}','${ids.user}','owner');
INSERT INTO projects (tenant_id,project_id,title,description,genre,language,created_by)
VALUES ('${ids.tenant}','${ids.project}','Writer Browser Project','Negotiation at a rain gate','fiction','en','${ids.user}');
INSERT INTO project_members (tenant_id,project_id,user_id,role) VALUES ('${ids.tenant}','${ids.project}','${ids.user}','project_owner');
INSERT INTO assets (tenant_id,asset_id,project_id,asset_type,category,lifecycle,title,summary,content_text,source_kind,source_ref,enabled,pinned,created_by)
VALUES ('${ids.tenant}','${ids.asset}','${ids.project}','character','cast','canon','Mara Venn','Negotiator bound by a promise.','Private Writer reference body.','writer_browser','mara',true,true,'${ids.user}');
INSERT INTO story_graph_snapshots (tenant_id,graph_id,project_id,version,status,node_count,edge_count)
VALUES ('${ids.tenant}','${ids.graph}','${ids.project}',1,'ready',2,1);
INSERT INTO story_graph_nodes (tenant_id,node_id,project_id,graph_id,node_type,title,summary,lifecycle,importance)
VALUES ('${ids.tenant}','${ids.node}','${ids.project}','${ids.graph}','character','Mara Venn','Lead negotiator','canon',10),
       ('${ids.tenant}','${ids.neighbor}','${ids.project}','${ids.graph}','location','Rain Gate','Closed checkpoint','canon',8);
INSERT INTO story_graph_edges (tenant_id,edge_id,project_id,graph_id,source_node_id,target_node_id,edge_type,label,lifecycle)
VALUES ('${ids.tenant}','${ids.edge}','${ids.project}','${ids.graph}','${ids.node}','${ids.neighbor}','located_in','waits at','canon');
INSERT INTO workflow_runs (tenant_id,run_id,workflow_type,project_id,status,progress,started_by)
VALUES ('${ids.tenant}','${ids.worldlineRun}','worldline_step','${ids.project}','completed',100,'${ids.user}');
INSERT INTO worldline_sessions (tenant_id,session_id,project_id,run_id,status,lifecycle,goal_summary,created_by)
VALUES ('${ids.tenant}','${ids.worldlineSession}','${ids.project}','${ids.worldlineRun}','completed','saved','Reach the gate','${ids.user}');
INSERT INTO worldline_saved_paths (tenant_id,path_id,session_id,project_id,title,summary,lifecycle,selected_event_ids_jsonb,writer_instruction,created_by)
VALUES ('${ids.tenant}','${ids.worldlinePath}','${ids.worldlineSession}','${ids.project}','Gate bargain','Mara trades certainty for passage.','saved','[]','Keep this path reference-only.','${ids.user}');
INSERT INTO book_plans (tenant_id,project_id,book_plan_id,title,status,premise,target_chapter_count,planning_jsonb,created_by,updated_by)
VALUES ('${ids.tenant}','${ids.project}','${ids.bookPlan}','Rain Gate Plan','draft','A private planning premise.',6,'{}','${ids.user}','${ids.user}');
INSERT INTO llm_channels (tenant_id,channel_id,name,provider,base_url,encrypted_api_key,max_concurrency,enabled)
VALUES ('${ids.tenant}','${ids.orchestratorChannel}','Writer Orchestrator Local','openai-compatible','${sql(providerBaseURL)}','${sql(encrypted)}',2,true),
       ('${ids.tenant}','${ids.composerChannel}','Writer Composer Local','openai-compatible','${sql(providerBaseURL)}','${sql(encrypted)}',2,true),
       ('${ids.tenant}','${ids.reviewerChannel}','Writer Reviewer Local','openai-compatible','${sql(providerBaseURL)}','${sql(encrypted)}',1,true),
       ('${ids.tenant}','${ids.dedupChannel}','Writer Dedup Local','openai-compatible','${sql(providerBaseURL)}','${sql(encrypted)}',1,true),
       ('${ids.tenant}','${ids.bookPlannerChannel}','Writer Book Planner Local','openai-compatible','${sql(providerBaseURL)}','${sql(encrypted)}',1,true);
INSERT INTO llm_models (tenant_id,channel_id,model_id,owned_by,supports_tools,supports_json,input_cost,output_cost)
VALUES ('${ids.tenant}','${ids.orchestratorChannel}','writer-live-orchestrator','local-provider',true,true,1,2),
       ('${ids.tenant}','${ids.composerChannel}','writer-live-composer','local-provider',false,true,1,2),
       ('${ids.tenant}','${ids.reviewerChannel}','writer-live-reviewer','local-provider',false,true,1,2),
       ('${ids.tenant}','${ids.dedupChannel}','writer-live-dedup','local-provider',false,true,1,2),
       ('${ids.tenant}','${ids.bookPlannerChannel}','writer-live-book-planner','local-provider',false,true,1,2);
INSERT INTO llm_module_bindings (tenant_id,project_id,module_key,channel_id,model_id,settings_jsonb,updated_by)
VALUES ('${ids.tenant}','${ids.project}','writer_orchestrator','${ids.orchestratorChannel}','writer-live-orchestrator','{"temperature":0,"max_tokens":256,"quota_reserved_tokens":512,"input_cost":1,"output_cost":2}','${ids.user}'),
       ('${ids.tenant}','${ids.project}','writer_composer','${ids.composerChannel}','writer-live-composer','{"temperature":0,"max_tokens":256,"quota_reserved_tokens":512,"input_cost":1,"output_cost":2}','${ids.user}'),
       ('${ids.tenant}','${ids.project}','writer_reviewer','${ids.reviewerChannel}','writer-live-reviewer','{"temperature":0,"max_tokens":256,"quota_reserved_tokens":512,"input_cost":1,"output_cost":2}','${ids.user}'),
       ('${ids.tenant}','${ids.project}','writer_dedup_extractor','${ids.dedupChannel}','writer-live-dedup','{"temperature":0,"max_tokens":256,"quota_reserved_tokens":512,"input_cost":1,"output_cost":2}','${ids.user}'),
       ('${ids.tenant}','${ids.project}','writer_book_planner','${ids.bookPlannerChannel}','writer-live-book-planner','{"temperature":0,"max_tokens":256,"quota_reserved_tokens":512,"input_cost":1,"output_cost":2}','${ids.user}');
INSERT INTO llm_quota_policies
  (tenant_id,scope_type,token_limit,cost_limit_micros,concurrency_limit,period_seconds,updated_by)
VALUES ('${ids.tenant}','tenant',1000000,1000000,2,3600,'${ids.user}');
INSERT INTO llm_quota_policies
  (tenant_id,scope_type,project_id,token_limit,cost_limit_micros,concurrency_limit,period_seconds,updated_by)
VALUES ('${ids.tenant}','project','${ids.project}',1000000,1000000,2,3600,'${ids.user}');
INSERT INTO llm_quota_policies
  (tenant_id,scope_type,project_id,module_key,token_limit,cost_limit_micros,concurrency_limit,period_seconds,updated_by)
VALUES ('${ids.tenant}','module','${ids.project}','writer_orchestrator',1000000,1000000,1,3600,'${ids.user}'),
       ('${ids.tenant}','module','${ids.project}','writer_composer',1000000,1000000,1,3600,'${ids.user}'),
       ('${ids.tenant}','module','${ids.project}','writer_reviewer',1000000,1000000,1,3600,'${ids.user}'),
       ('${ids.tenant}','module','${ids.project}','writer_dedup_extractor',1000000,1000000,1,3600,'${ids.user}'),
       ('${ids.tenant}','module','${ids.project}','writer_book_planner',1000000,1000000,1,3600,'${ids.user}');
`;
}

function cleanupSQL(dropRole) {
  return `DELETE FROM tenants WHERE tenant_id='${ids.tenant}';
DELETE FROM users WHERE user_id='${ids.user}';
${dropRole ? `DROP ROLE IF EXISTS ${role};` : ""}`;
}

function encrypt(value, key) {
  const iv = Buffer.from("112233445566778899aabbcc", "hex");
  const cipher = createCipheriv("aes-256-gcm", key, iv);
  const ciphertext = Buffer.concat([cipher.update(value, "utf8"), cipher.final()]);
  return `aes-256-gcm:v1:${iv.toString("base64")}:${cipher.getAuthTag().toString("base64")}:${ciphertext.toString("base64")}`;
}

export function decodeWriterCredentialEncryptionKey(rawValue) {
  const value = String(rawValue || "").trim();
  let decoded;
  if (/^[0-9a-fA-F]{64}$/.test(value)) {
    decoded = Buffer.from(value, "hex");
  } else if (/^[A-Za-z0-9+/]+={0,2}$/.test(value) && value.length % 4 === 0) {
    decoded = Buffer.from(value, "base64");
    if (decoded.toString("base64") !== value) {
      decoded = undefined;
    }
  }
  if (!decoded || decoded.length !== 32) {
    throw new Error(`${prefix}LLM_CREDENTIAL_ENCRYPTION_KEY must be 32-byte hex or standard base64`);
  }
  return decoded;
}

function psql(statement) {
  const result = spawnSync("psql", [databaseURL, "-v", "ON_ERROR_STOP=1", "-q"], { input: statement, encoding: "utf8" });
  if (result.status !== 0) throw new Error("Writer disposable fixture SQL failed");
}

function required(name) {
  const value = String(process.env[`${prefix}${name}`] || "").trim();
  if (!value) throw new Error(`missing ${prefix}${name}`);
  return value;
}

function assertLocalDatabase(value) {
  const parsed = new URL(value);
  if (!["postgres:", "postgresql:"].includes(parsed.protocol) || !["127.0.0.1", "localhost", "::1"].includes(parsed.hostname)) {
    throw new Error("writer fixture database must be local");
  }
}

function sql(value) {
  return String(value).replaceAll("'", "''");
}
