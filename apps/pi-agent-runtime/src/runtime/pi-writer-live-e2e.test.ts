import { createCipheriv, randomBytes } from "node:crypto";
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { once } from "node:events";
import { URL } from "node:url";

import pg from "pg";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { createWorkerActivityBundle, type WorkerActivityBundle } from "../worker.js";
import { createPgPoolQueryExecutor } from "./postgres-pi-writer-deps.js";
import { createPostgresQuotaStore } from "../llm/quota/postgres-quota-store.js";

const adminURL = process.env.MIROFISH_PI_WRITER_LIVE_DATABASE_URL?.trim();
const externalBaseURL = process.env.MIROFISH_PI_WRITER_EXTERNAL_BASE_URL?.trim();
const externalModelID = process.env.MIROFISH_PI_WRITER_EXTERNAL_MODEL_ID?.trim();
const externalAPIKey = process.env.MIROFISH_PI_WRITER_EXTERNAL_API_KEY?.trim();
const describeLive = adminURL ? describe : describe.skip;
const localProviderRequests: Array<{
  providerCallID: string;
  tenantID: string;
  projectID: string;
  runID: string;
  moduleKey: string;
}> = [];
const ids = {
  tenant: "a1111111-1111-4111-8111-111111111111",
  project: "a2222222-2222-4222-8222-222222222222",
  user: "a3333333-3333-4333-8333-333333333333",
  run: "a4444444-4444-4444-8444-444444444444",
  orchestratorChannel: "a5555555-5555-4555-8555-555555555555",
  composerChannel: "a6666666-6666-4666-8666-666666666666",
  interaction: "a7777777-7777-4777-8777-777777777777",
  turn: "a8888888-8888-4888-8888-888888888888",
  chapter: "a9999999-9999-4999-8999-999999999999",
  scene: "aa111111-1111-4111-8111-111111111111"
  ,asset: "aa222222-2222-4222-8222-222222222222"
  ,graph: "aa333333-3333-4333-8333-333333333333"
  ,graphNode: "aa444444-4444-4444-8444-444444444444"
  ,graphNeighbor: "aa555555-5555-4555-8555-555555555555"
  ,graphEdge: "aa666666-6666-4666-8666-666666666666"
  ,worldlineRun: "aa777777-7777-4777-8777-777777777777"
  ,worldlineSession: "aa888888-8888-4888-8888-888888888888"
  ,worldlinePath: "aa999999-9999-4999-8999-999999999999"
  ,segment: "ab111111-1111-4111-8111-111111111111"
  ,worldRule: "ab222222-2222-4222-8222-222222222222"
  ,entity: "ab333333-3333-4333-8333-333333333333"
  ,entityAlias: "ab444444-4444-4444-8444-444444444444"
  ,foreignTenant: "ab555555-5555-4555-8555-555555555555"
  ,foreignProject: "ab666666-6666-4666-8666-666666666666"
  ,foreignRun: "ab777777-7777-4777-8777-777777777777"
  ,foreignSegment: "ab888888-8888-4888-8888-888888888888"
  ,foreignWorldRule: "ab999999-9999-4999-8999-999999999999"
  ,foreignEntity: "ac111111-1111-4111-8111-111111111111"
  ,foreignEntityAlias: "ac222222-2222-4222-8222-222222222222"
  ,otherProject: "ac333333-3333-4333-8333-333333333333"
  ,otherRun: "ac444444-4444-4444-8444-444444444444"
  ,otherSegment: "ac555555-5555-4555-8555-555555555555"
  ,otherWorldRule: "ac666666-6666-4666-8666-666666666666"
  ,otherEntity: "ac777777-7777-4777-8777-777777777777"
  ,otherEntityAlias: "ac888888-8888-4888-8888-888888888888"
};

describeLive(`Pi writer Postgres + ${externalBaseURL ? "external-provider" : "local-provider"} live E2E`, () => {
  let admin: pg.Pool;
  let provider: ReturnType<typeof createServer>;
  let bundle: WorkerActivityBundle;
  let key: Buffer;
  let providerURL: string;

  beforeAll(async () => {
    localProviderRequests.length = 0;
    admin = new pg.Pool({ connectionString: adminURL });
    const identity = await admin.query<{ current_database: string; live_test_marker: string }>(
      "SELECT current_database(), COALESCE(current_setting('mirofish.live_test', true), '') AS live_test_marker"
    );
    const databaseName = identity.rows[0]?.current_database ?? "";
    if (!/^mirofish_test_[a-z0-9_]+$/.test(databaseName) || identity.rows[0]?.live_test_marker !== "on") {
      throw new Error(`refusing non-disposable Pi writer live test database ${JSON.stringify(databaseName)}`);
    }
    if (externalBaseURL) {
      if (!externalModelID) throw new Error("external writer certification requires MIROFISH_PI_WRITER_EXTERNAL_MODEL_ID");
      if (!externalAPIKey) throw new Error("external writer certification requires MIROFISH_PI_WRITER_EXTERNAL_API_KEY");
      const parsed = new URL(externalBaseURL);
      if (parsed.protocol !== "https:" || parsed.username || parsed.password || ["localhost", "127.0.0.1", "::1"].includes(parsed.hostname)) {
        throw new Error("external writer certification requires a remote HTTPS provider URL");
      }
      providerURL = externalBaseURL;
    } else {
      provider = createServer(localProviderHandler);
      provider.listen(0, "127.0.0.1");
      await once(provider, "listening");
      const address = provider.address();
      if (!address || typeof address === "string") throw new Error("local provider did not bind");
      providerURL = `http://127.0.0.1:${address.port}/v1`;
    }
    const configuredKey = process.env.MIROFISH_PI_WRITER_LIVE_ENCRYPTION_KEY?.trim();
    key = configuredKey ? Buffer.from(configuredKey, "base64") : randomBytes(32);
    if (key.length !== 32) throw new Error("MIROFISH_PI_WRITER_LIVE_ENCRYPTION_KEY must decode to 32 bytes");
    await prepareFixture(admin, providerURL, key, externalModelID, externalAPIKey || "local-key");
    bundle = await createWorkerActivityBundle({
      env: {
        DATABASE_URL: appRoleURL(adminURL!),
        LLM_CREDENTIAL_ENCRYPTION_KEY: key.toString("base64")
      }
    });
  }, 20_000);

  afterAll(async () => {
    await bundle?.close();
    if (admin) {
      if (process.env.MIROFISH_PI_WRITER_LIVE_PRESERVE_FIXTURE !== "1") {
        await admin.query("DELETE FROM tenants WHERE tenant_id = $1", [ids.tenant]).catch(() => undefined);
        await admin.query("DELETE FROM tenants WHERE tenant_id = $1", [ids.foreignTenant]).catch(() => undefined);
      }
      await admin.end();
    }
    if (provider) await new Promise<void>((resolve) => provider.close(() => resolve()));
  });

  it("persists two bound LLM calls, real tool trace, replayable tokens, and one candidate draft", async () => {
    const payload = {
      tenant_id: ids.tenant, project_id: ids.project, run_id: ids.run, trace_id: `trace-${ids.run}`,
      requested_by: ids.user, mode: "draft", instruction: "Rewrite the saved interaction as restrained chapter prose.",
      selected_asset_ids: [ids.asset], graph_node_ids: [ids.graphNode], worldline_path_ids: [ids.worldlinePath], options: {
        module_key: "writer_composer", target_words: 80,
        source: "character_console", character_interaction_id: ids.interaction,
        target_chapter_id: ids.chapter, target_scene_id: ids.scene
      }
    };
    const canonStateBefore = await canonWriteState(admin);
    const result = await bundle.activities.runPiWriterRunActivity(payload);

    const diagnosticEvents = await admin.query("SELECT event_type, payload_jsonb FROM workflow_events WHERE tenant_id = $1 AND run_id = $2 ORDER BY sequence", [ids.tenant, ids.run]);
    const diagnosticActivity = await admin.query("SELECT module_key,status,error_jsonb FROM llm_activity WHERE tenant_id=$1 AND run_id=$2", [ids.tenant, ids.run]);
    const diagnosticQuota = await admin.query("SELECT module_key,status,actual_prompt_tokens,actual_completion_tokens,actual_cost_micros FROM llm_quota_reservations WHERE tenant_id=$1 AND run_id=$2", [ids.tenant, ids.run]);
    const diagnosticUsage = await admin.query("SELECT module_key,usage_type,quantity FROM usage_events WHERE tenant_id=$1 AND run_id=$2", [ids.tenant, ids.run]);
    const diagnosticLocks = await admin.query("SELECT resource_type,resource_id,lock_mode FROM resource_locks WHERE tenant_id=$1", [ids.tenant]);
    expect(result.status, JSON.stringify({
      result,
      events: diagnosticEvents.rows,
      activity: diagnosticActivity.rows,
      quota: diagnosticQuota.rows,
      usage: diagnosticUsage.rows,
      locks: diagnosticLocks.rows
    })).toBe("completed");
    const drafts = await admin.query("SELECT draft_id, status, content_text, chapter_id::text, scene_id::text FROM writer_drafts WHERE tenant_id = $1 AND run_id = $2", [ids.tenant, ids.run]);
    expect(drafts.rows).toHaveLength(1);
    expect(drafts.rows[0]?.status).toBe("candidate");
    expect(String(drafts.rows[0]?.content_text).trim().length).toBeGreaterThan(0);
    expect(drafts.rows[0]?.chapter_id).toBe(ids.chapter);
    expect(drafts.rows[0]?.scene_id).toBe(ids.scene);
    if (!externalBaseURL) expect(drafts.rows[0]?.content_text).toBe("Live writer prose from the bound composer.");
    const modules = await admin.query("SELECT module_key, status, prompt_tokens, completion_tokens, error_jsonb FROM llm_activity WHERE tenant_id = $1 AND run_id = $2 ORDER BY created_at", [ids.tenant, ids.run]);
    expect(modules.rows).toEqual([
      expect.objectContaining({ module_key: "writer_orchestrator", status: "completed" }),
      expect.objectContaining({ module_key: "writer_composer", status: "completed" })
    ]);
    const events = await admin.query("SELECT event_type, payload_jsonb FROM workflow_events WHERE tenant_id = $1 AND run_id = $2 ORDER BY sequence", [ids.tenant, ids.run]);
    const toolStarts = events.rows.filter((row) => row.event_type === "writer.tool.started");
    const toolCompletions = events.rows.filter((row) => row.event_type === "writer.tool.completed");
    expect(toolStarts.length).toBeGreaterThan(0);
    expect(toolCompletions).toHaveLength(toolStarts.length);
    for (const toolName of [
      "query_assets",
      "query_world_rules",
      "query_character_profile",
      "query_graph_neighbors",
      "query_worldline_paths"
    ]) {
      expect(toolStarts.some((row) => row.payload_jsonb?.tool_name === toolName)).toBe(true);
      const completion = toolCompletions.find((row) => row.payload_jsonb?.tool_name === toolName);
      expect(completion?.payload_jsonb?.result).toBeTruthy();
      expect(JSON.stringify(completion?.payload_jsonb)).not.toContain("content_text");
    }
    const worldRuleEvent = toolCompletions.find((row) => row.payload_jsonb?.tool_name === "query_world_rules");
    expect(worldRuleEvent?.payload_jsonb?.result).toEqual({
      items: [{ rule_evidence_id: ids.worldRule, category: "magic", confidence: 0.95, source: "seed_evidence" }]
    });
    const characterEvent = toolCompletions.find((row) => row.payload_jsonb?.tool_name === "query_character_profile");
    expect(characterEvent?.payload_jsonb?.result).toEqual({
      items: [
        {
          entity_id: ids.entity,
          canonical_name: "Mara Venn",
          entity_type: "character",
          importance: "primary",
          source: "entity",
          state_summary: "Negotiating at the rain gate."
        },
        {
          entity_id: ids.asset,
          canonical_name: "Mara Venn",
          entity_type: "character",
          category: null,
          importance: null,
          lifecycle: "canon",
          source: "canon_asset",
          state_summary: "Negotiator with a strict promise."
        }
      ]
    });
    const publicToolEvents = JSON.stringify([worldRuleEvent?.payload_jsonb, characterEvent?.payload_jsonb]);
    for (const privateValue of [
      "Magic requires a private sacrifice.",
      "Private rule evidence excerpt.",
      "The Rain Captain",
      ids.foreignWorldRule,
      ids.foreignEntity,
      "Foreign private world rule.",
      "Foreign Private Alias",
      ids.otherWorldRule,
      ids.otherEntity,
      "Other project private world rule.",
      "Other Project Private Alias",
      "metadata_jsonb"
    ]) {
      expect(publicToolEvents).not.toContain(privateValue);
    }
    const savedEvent = events.rows.find((row) => row.event_type === "writer.draft.saved");
    expect(savedEvent?.payload_jsonb?.source_metadata).toEqual({
      asset_ids: [ids.asset], graph_node_ids: [ids.graphNode], worldline_path_ids: [ids.worldlinePath],
      reference_counts: { assets: 1, graph_nodes: 1, worldline_paths: 1 }
    });
    expect(events.rows.filter((row) => row.event_type === "writer.token").length).toBeGreaterThan(0);
    expect(events.rows.filter((row) => row.event_type === "writer.run.completed")).toHaveLength(1);
    const reservations = await admin.query(`SELECT provider_call_id, module_key, model_id, status,
      reserved_tokens, actual_prompt_tokens, actual_completion_tokens, actual_cost_micros
      FROM llm_quota_reservations WHERE tenant_id = $1 AND run_id = $2 ORDER BY module_key`, [ids.tenant, ids.run]);
    expect(reservations.rows).toHaveLength(2);
    expect(reservations.rows.map((row) => row.status)).toEqual(["finalized", "finalized"]);
    expect(new Set(reservations.rows.map((row) => row.provider_call_id))).toHaveLength(2);
    for (const reservation of reservations.rows) {
      expect(Number(reservation.actual_prompt_tokens)).toBeGreaterThanOrEqual(0);
      expect(Number(reservation.actual_completion_tokens)).toBeGreaterThanOrEqual(0);
      expect(Number(reservation.actual_prompt_tokens) + Number(reservation.actual_completion_tokens)).toBeLessThanOrEqual(Number(reservation.reserved_tokens));
      expect(Number(reservation.actual_cost_micros)).toBeGreaterThanOrEqual(0);
      const activity = modules.rows.find((row) => row.module_key === reservation.module_key);
      expect(activity?.error_jsonb?.provider_call_id).toBe(reservation.provider_call_id);
    }
    const usage = await admin.query("SELECT module_key, usage_type, quantity, metadata_jsonb FROM usage_events WHERE tenant_id = $1 AND run_id = $2 ORDER BY created_at", [ids.tenant, ids.run]);
    const tokenUsage = usage.rows.filter((row) => row.usage_type === "llm_tokens");
    const costUsage = usage.rows.filter((row) => row.usage_type === "llm_cost_micros");
    expect(tokenUsage).toHaveLength(2);
    expect(costUsage).toHaveLength(2);
    expect(tokenUsage.map((row) => row.module_key)).toEqual(["writer_orchestrator", "writer_composer"]);
    for (const usageRow of tokenUsage) {
      const activityRow = modules.rows.find((row) => row.module_key === usageRow.module_key);
      expect(Number(usageRow.quantity)).toBe(
        Number(activityRow?.prompt_tokens ?? 0) + Number(activityRow?.completion_tokens ?? 0)
      );
      expect(usageRow.metadata_jsonb?.provider_call_id).toBe(activityRow?.error_jsonb?.provider_call_id);
    }
    const traces = await admin.query("SELECT event_type, redaction_level FROM agent_trace_events WHERE tenant_id = $1 AND trace_id = $2 ORDER BY event_order", [ids.tenant, `trace-${ids.run}`]);
    expect(traces.rows).toEqual(expect.arrayContaining([
      { event_type: "tool_call", redaction_level: "full" },
      { event_type: "tool_result", redaction_level: "full" },
      { event_type: "assistant_message", redaction_level: "full" },
      { event_type: "artifact_written", redaction_level: "summary" }
    ]));
    const privateToolTraces = await admin.query(
      "SELECT payload_jsonb FROM agent_trace_events WHERE tenant_id = $1 AND trace_id = $2 AND event_type = 'tool_result' ORDER BY event_order",
      [ids.tenant, `trace-${ids.run}`]
    );
    const privateToolPayload = JSON.stringify(privateToolTraces.rows);
    expect(privateToolPayload).toContain("Magic requires a private sacrifice.");
    expect(privateToolPayload).toContain("The Rain Captain");
    expect(privateToolPayload).not.toContain("Foreign private world rule.");
    expect(privateToolPayload).not.toContain("Foreign Private Alias");
    expect(privateToolPayload).not.toContain("Other project private world rule.");
    expect(privateToolPayload).not.toContain("Other Project Private Alias");
    const manuscript = await admin.query("SELECT COUNT(*)::int AS count FROM manuscript_blocks WHERE tenant_id = $1 AND project_id = $2", [ids.tenant, ids.project]);
    expect(manuscript.rows[0]?.count).toBe(0);
    expect(await canonWriteState(admin)).toEqual(canonStateBefore);
    const activeLocks = await admin.query("SELECT COUNT(*)::int AS count FROM resource_locks WHERE tenant_id = $1", [ids.tenant]);
    expect(activeLocks.rows[0]?.count).toBe(0);
    if (!externalBaseURL) {
      expect(new Set(localProviderRequests.map((request) => request.providerCallID))).toHaveLength(3);
      for (const request of localProviderRequests) {
        expect(request).toMatchObject({ tenantID: ids.tenant, projectID: ids.project, runID: ids.run });
        expect(["writer_orchestrator", "writer_composer"]).toContain(request.moduleKey);
      }
    }

    const providerHitsBeforeReplay = localProviderRequests.length;
    const replayedActivity = await bundle.activities.runPiWriterRunActivity(payload);
    expect(replayedActivity).toMatchObject({ status: "completed", draft_id: result.draft_id });
    const persistedCounts = await admin.query(`SELECT
      (SELECT COUNT(*)::int FROM writer_drafts WHERE tenant_id = $1 AND run_id = $2) AS drafts,
      (SELECT COUNT(*)::int FROM workflow_events WHERE tenant_id = $1 AND run_id = $2 AND event_type = 'writer.run.completed') AS terminals,
      (SELECT COUNT(*)::int FROM llm_activity WHERE tenant_id = $1 AND run_id = $2) AS activities,
      (SELECT COUNT(*)::int FROM usage_events WHERE tenant_id = $1 AND run_id = $2) AS usage_events,
      (SELECT COUNT(*)::int FROM llm_quota_reservations WHERE tenant_id = $1 AND run_id = $2) AS reservations`, [ids.tenant, ids.run]);
    expect(persistedCounts.rows[0]).toEqual({ drafts: 1, terminals: 1, activities: 2, usage_events: 4, reservations: 2 });
    if (!externalBaseURL) expect(localProviderRequests).toHaveLength(providerHitsBeforeReplay);
  }, externalBaseURL ? 180_000 : 60_000);

  it("atomically rejects concurrent reservations in the same module scope", async () => {
    const db = createPgPoolQueryExecutor(appRoleURL(adminURL!));
    const quota = createPostgresQuotaStore(db);
    const base = {
      tenant_id: ids.tenant,
      project_id: ids.project,
      run_id: ids.run,
      module_key: "writer_composer",
      channel_id: ids.composerChannel,
      model_id: externalModelID || "writer_composer-model",
      reserved_tokens: 64,
      reserved_cost_micros: 128,
      pricing_status: "billing_ready" as const,
      ttl_seconds: 60
    };
    try {
      const outcomes = await Promise.allSettled([
        quota.reserve({ ...base, provider_call_id: `pi-writer:concurrency:${Date.now()}:a` }),
        quota.reserve({ ...base, provider_call_id: `pi-writer:concurrency:${Date.now()}:b` })
      ]);
      expect(outcomes.filter((outcome) => outcome.status === "fulfilled")).toHaveLength(1);
      const rejected = outcomes.find((outcome): outcome is PromiseRejectedResult => outcome.status === "rejected");
      expect(String(rejected?.reason)).toContain("LLM_QUOTA_CONCURRENCY_EXCEEDED");
      const reserved = outcomes.find((outcome): outcome is PromiseFulfilledResult<Awaited<ReturnType<typeof quota.reserve>>> => outcome.status === "fulfilled")!.value;
      await quota.release({
        tenant_id: ids.tenant,
        project_id: ids.project,
        reservation_id: reserved.reservation_id,
        provider_call_id: reserved.provider_call_id
      });
    } finally {
      await db.close();
    }
  }, 60_000);
});

async function prepareFixture(
  db: pg.Pool,
  baseURL: string,
  key: Buffer,
  modelID?: string,
  apiKey = "local-key"
): Promise<void> {
  await db.query("DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mirofish_pi_writer_live_app') THEN CREATE ROLE mirofish_pi_writer_live_app LOGIN PASSWORD 'mirofish_pi_writer_live_password' IN ROLE mirofish_app; ELSE ALTER ROLE mirofish_pi_writer_live_app WITH LOGIN PASSWORD 'mirofish_pi_writer_live_password'; END IF; END $$; GRANT mirofish_app TO mirofish_pi_writer_live_app;");
  await db.query("DELETE FROM tenants WHERE tenant_id = $1", [ids.tenant]);
  await db.query("DELETE FROM tenants WHERE tenant_id = $1", [ids.foreignTenant]);
  await db.query("INSERT INTO users (user_id,email,display_name) VALUES ($1,'pi-writer-live@example.test','Pi Writer Live') ON CONFLICT (user_id) DO NOTHING", [ids.user]);
  await db.query("INSERT INTO tenants (tenant_id,slug,name,tenant_type) VALUES ($1,'pi-writer-live','Pi Writer Live','personal')", [ids.tenant]);
  await db.query("INSERT INTO projects (tenant_id,project_id,title,description,genre,language,created_by) VALUES ($1,$2,'Pi Writer Live Project','Live context','fiction','en',$3)", [ids.tenant, ids.project, ids.user]);
  await db.query("INSERT INTO projects (tenant_id,project_id,title,description,genre,language,created_by) VALUES ($1,$2,'Pi Writer Other Project','Same-tenant negative context','fiction','en',$3)", [ids.tenant, ids.otherProject, ids.user]);
  await db.query("INSERT INTO tenants (tenant_id,slug,name,tenant_type) VALUES ($1,'pi-writer-live-foreign','Pi Writer Live Foreign','organization')", [ids.foreignTenant]);
  await db.query("INSERT INTO projects (tenant_id,project_id,title,description,genre,language,created_by) VALUES ($1,$2,'Foreign Project','Foreign context','fiction','en',$3)", [ids.foreignTenant, ids.foreignProject, ids.user]);
  await db.query(`INSERT INTO llm_quota_policies (
    tenant_id, scope_type, token_limit, cost_limit_micros, concurrency_limit, period_seconds, updated_by
  ) VALUES ($1, 'tenant', 1000000, 1000000, 2, 3600, $2)`, [ids.tenant, ids.user]);
  await db.query(`INSERT INTO llm_quota_policies (
    tenant_id, scope_type, project_id, token_limit, cost_limit_micros, concurrency_limit, period_seconds, updated_by
  ) VALUES ($1, 'project', $2, 1000000, 1000000, 2, 3600, $3)`, [ids.tenant, ids.project, ids.user]);
  await db.query("INSERT INTO workflow_runs (tenant_id,run_id,workflow_type,project_id,status,started_by) VALUES ($1,$2,'writer_run',$3,'queued',$4)", [ids.tenant, ids.run, ids.project, ids.user]);
  await db.query("INSERT INTO workflow_runs (tenant_id,run_id,workflow_type,project_id,status,started_by) VALUES ($1,$2,'worldline_step',$3,'completed',$4)", [ids.tenant, ids.worldlineRun, ids.project, ids.user]);
  await db.query("INSERT INTO workflow_runs (tenant_id,run_id,workflow_type,project_id,status,started_by) VALUES ($1,$2,'seed',$3,'completed',$4)", [ids.tenant, ids.otherRun, ids.otherProject, ids.user]);
  await db.query("INSERT INTO workflow_runs (tenant_id,run_id,workflow_type,project_id,status,started_by) VALUES ($1,$2,'seed',$3,'completed',$4)", [ids.foreignTenant, ids.foreignRun, ids.foreignProject, ids.user]);
  await db.query("INSERT INTO text_segments (tenant_id,segment_id,project_id,run_id,segment_order,summary) VALUES ($1,$2,$3,$4,0,'Local segment summary')", [ids.tenant, ids.segment, ids.project, ids.run]);
  await db.query("INSERT INTO text_segments (tenant_id,segment_id,project_id,run_id,segment_order,summary) VALUES ($1,$2,$3,$4,0,'Foreign segment summary')", [ids.foreignTenant, ids.foreignSegment, ids.foreignProject, ids.foreignRun]);
  await db.query("INSERT INTO text_segments (tenant_id,segment_id,project_id,run_id,segment_order,summary) VALUES ($1,$2,$3,$4,0,'Other project segment summary')", [ids.tenant, ids.otherSegment, ids.otherProject, ids.otherRun]);
  await db.query("INSERT INTO world_rule_evidence (tenant_id,rule_evidence_id,project_id,run_id,segment_id,rule_text,evidence_text,category,confidence) VALUES ($1,$2,$3,$4,$5,'Magic requires a private sacrifice.','Private rule evidence excerpt.','magic',0.95)", [ids.tenant, ids.worldRule, ids.project, ids.run, ids.segment]);
  await db.query("INSERT INTO world_rule_evidence (tenant_id,rule_evidence_id,project_id,run_id,segment_id,rule_text,evidence_text,category,confidence) VALUES ($1,$2,$3,$4,$5,'Foreign private world rule.','Foreign evidence excerpt.','foreign',0.5)", [ids.foreignTenant, ids.foreignWorldRule, ids.foreignProject, ids.foreignRun, ids.foreignSegment]);
  await db.query("INSERT INTO world_rule_evidence (tenant_id,rule_evidence_id,project_id,run_id,segment_id,rule_text,evidence_text,category,confidence) VALUES ($1,$2,$3,$4,$5,'Other project private world rule.','Other project evidence excerpt.','other',0.7)", [ids.tenant, ids.otherWorldRule, ids.otherProject, ids.otherRun, ids.otherSegment]);
  await db.query("INSERT INTO entities (tenant_id,entity_id,project_id,source_run_id,canonical_name,entity_type,importance,state_summary) VALUES ($1,$2,$3,$4,'Mara Venn','character','primary','Negotiating at the rain gate.')", [ids.tenant, ids.entity, ids.project, ids.run]);
  await db.query("INSERT INTO entity_aliases (tenant_id,alias_id,project_id,entity_id,alias) VALUES ($1,$2,$3,$4,'The Rain Captain')", [ids.tenant, ids.entityAlias, ids.project, ids.entity]);
  await db.query("INSERT INTO entities (tenant_id,entity_id,project_id,source_run_id,canonical_name,entity_type,importance,state_summary) VALUES ($1,$2,$3,$4,'Foreign Character','character','primary','Foreign private state.')", [ids.foreignTenant, ids.foreignEntity, ids.foreignProject, ids.foreignRun]);
  await db.query("INSERT INTO entity_aliases (tenant_id,alias_id,project_id,entity_id,alias) VALUES ($1,$2,$3,$4,'Foreign Private Alias')", [ids.foreignTenant, ids.foreignEntityAlias, ids.foreignProject, ids.foreignEntity]);
  await db.query("INSERT INTO entities (tenant_id,entity_id,project_id,source_run_id,canonical_name,entity_type,importance,state_summary) VALUES ($1,$2,$3,$4,'Other Project Character','character','primary','Other project private state.')", [ids.tenant, ids.otherEntity, ids.otherProject, ids.otherRun]);
  await db.query("INSERT INTO entity_aliases (tenant_id,alias_id,project_id,entity_id,alias) VALUES ($1,$2,$3,$4,'Other Project Private Alias')", [ids.tenant, ids.otherEntityAlias, ids.otherProject, ids.otherEntity]);
  await db.query("INSERT INTO assets (tenant_id,asset_id,project_id,asset_type,lifecycle,title,summary,content_text,source_kind,source_ref,created_by) VALUES ($1,$2,$3,'character','canon','Mara Venn','Negotiator with a strict promise.','Private asset writing context.','writer_live','asset-ref',$4)", [ids.tenant, ids.asset, ids.project, ids.user]);
  await db.query("INSERT INTO story_graph_snapshots (tenant_id,graph_id,project_id,version,status,node_count,edge_count) VALUES ($1,$2,$3,1,'ready',2,1)", [ids.tenant, ids.graph, ids.project]);
  await db.query("INSERT INTO story_graph_nodes (tenant_id,node_id,project_id,graph_id,node_type,title,summary,lifecycle,importance) VALUES ($1,$2,$3,$4,'character','Mara Venn','Lead negotiator','canon',10),($1,$5,$3,$4,'location','Rain Gate','Closed checkpoint','canon',8)", [ids.tenant, ids.graphNode, ids.project, ids.graph, ids.graphNeighbor]);
  await db.query("INSERT INTO story_graph_edges (tenant_id,edge_id,project_id,graph_id,source_node_id,target_node_id,edge_type,label,lifecycle) VALUES ($1,$2,$3,$4,$5,$6,'located_in','waits at','canon')", [ids.tenant, ids.graphEdge, ids.project, ids.graph, ids.graphNode, ids.graphNeighbor]);
  await db.query("INSERT INTO worldline_sessions (tenant_id,session_id,project_id,run_id,status,lifecycle,goal_summary,created_by) VALUES ($1,$2,$3,$4,'completed','saved','Reach the rain gate',$5)", [ids.tenant, ids.worldlineSession, ids.project, ids.worldlineRun, ids.user]);
  await db.query("INSERT INTO worldline_saved_paths (tenant_id,path_id,session_id,project_id,title,summary,lifecycle,writer_instruction,created_by) VALUES ($1,$2,$3,$4,'Gate bargain','Mara trades certainty for passage.','saved','Keep this path reference-only.',$5)", [ids.tenant, ids.worldlinePath, ids.worldlineSession, ids.project, ids.user]);
  await db.query(`INSERT INTO character_interaction_sessions (
    tenant_id, interaction_id, project_id, mode, status, title, summary, created_by
  ) VALUES ($1, $2, $3, 'first_person', 'saved', 'Live conversion source', 'Saved interaction metadata', $4)`,
    [ids.tenant, ids.interaction, ids.project, ids.user]);
  await db.query(`INSERT INTO character_interaction_turns (
    tenant_id, turn_id, interaction_id, project_id, turn_order, actor_type, turn_kind, summary
  ) VALUES ($1, $2, $3, $4, 1, 'user', 'dialogue', 'Saved public turn summary')`,
    [ids.tenant, ids.turn, ids.interaction, ids.project]);
  await db.query(`INSERT INTO writer_runs (
    tenant_id,run_id,workflow_run_id,project_id,mode,status,module_key,instruction,options_jsonb,created_by
  ) VALUES ($1,$2,$2,$3,'draft','queued','writer_composer','live writer',
    jsonb_build_object('source','character_console','character_interaction_id',$5::text,'target_chapter_id',$6::text,'target_scene_id',$7::text,'asset_ids',jsonb_build_array($8::text),'graph_node_ids',jsonb_build_array($9::text),'worldline_path_ids',jsonb_build_array($10::text)),$4)`,
    [ids.tenant, ids.run, ids.project, ids.user, ids.interaction, ids.chapter, ids.scene, ids.asset, ids.graphNode, ids.worldlinePath]);
  await db.query("INSERT INTO workflow_events (tenant_id,run_id,workflow_type,project_id,event_type,sequence,payload_jsonb) VALUES ($1,$2,'writer_run',$3,'workflow.queued',1,'{}')", [ids.tenant, ids.run, ids.project]);
  for (const [moduleKey, channelID, supportsTools] of [
    ["writer_orchestrator", ids.orchestratorChannel, true], ["writer_composer", ids.composerChannel, false]
  ] as const) {
    const resolvedModelID = modelID || `${moduleKey}-model`;
    await db.query("INSERT INTO llm_channels (tenant_id,channel_id,name,provider,base_url,encrypted_api_key,max_concurrency) VALUES ($1,$2,$3,'openai-compatible',$4,$5,2)", [ids.tenant, channelID, moduleKey, baseURL, encrypt(apiKey, key)]);
    await db.query("INSERT INTO llm_models (tenant_id,channel_id,model_id,supports_tools,supports_json) VALUES ($1,$2,$3,$4,true)", [ids.tenant, channelID, resolvedModelID, supportsTools]);
    await db.query("INSERT INTO llm_module_bindings (tenant_id,project_id,module_key,channel_id,model_id,settings_jsonb,updated_by) VALUES ($1,$2,$3,$4,$5,$6,$7)", [ids.tenant, ids.project, moduleKey, channelID, resolvedModelID, JSON.stringify({ max_tokens: 240, quota_reserved_tokens: 512, input_cost: 1, output_cost: 2, temperature: 0 }), ids.user]);
    await db.query(`INSERT INTO llm_quota_policies (
      tenant_id, scope_type, project_id, module_key, token_limit, cost_limit_micros,
      concurrency_limit, period_seconds, updated_by
    ) VALUES ($1, 'module', $2, $3, 1000000, 1000000, 1, 3600, $4)`,
      [ids.tenant, ids.project, moduleKey, ids.user]);
  }
}

async function canonWriteState(db: pg.Pool): Promise<Record<string, number>> {
  const result = await db.query(`SELECT
    (SELECT COUNT(*)::int FROM manuscript_blocks WHERE tenant_id = $1 AND project_id = $2) AS manuscript_blocks,
    (SELECT COUNT(*)::int FROM worldline_event_adoptions WHERE tenant_id = $1 AND project_id = $2) AS worldline_adoptions,
    (SELECT COUNT(*)::int FROM assets WHERE tenant_id = $1 AND project_id = $2 AND lifecycle = 'canon') AS canon_assets,
    (SELECT COUNT(*)::int FROM writer_drafts WHERE tenant_id = $1 AND project_id = $2 AND status <> 'candidate') AS adopted_drafts`,
  [ids.tenant, ids.project]);
  return result.rows[0] as Record<string, number>;
}

async function localProviderHandler(request: IncomingMessage, response: ServerResponse): Promise<void> {
  localProviderRequests.push({
    providerCallID: String(request.headers["idempotency-key"] ?? ""),
    tenantID: String(request.headers["x-mirofish-tenant-id"] ?? ""),
    projectID: String(request.headers["x-mirofish-project-id"] ?? ""),
    runID: String(request.headers["x-mirofish-run-id"] ?? ""),
    moduleKey: String(request.headers["x-mirofish-module-key"] ?? "")
  });
  const chunks: Buffer[] = [];
  for await (const chunkValue of request) chunks.push(Buffer.from(chunkValue));
  const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  const lastRole = body.messages.at(-1)?.role;
  start(response);
  if (Array.isArray(body.tools) && lastRole !== "tool") {
    send(response, eventChunk({ role: "assistant", tool_calls: [
      { index: 0, id: "call-assets", type: "function", function: { name: "query_assets", arguments: "{}" } },
      { index: 1, id: "call-world-rules", type: "function", function: { name: "query_world_rules", arguments: "{}" } },
      { index: 2, id: "call-character-profile", type: "function", function: { name: "query_character_profile", arguments: "{}" } },
      { index: 3, id: "call-graph", type: "function", function: { name: "query_graph_neighbors", arguments: "{}" } },
      { index: 4, id: "call-worldline", type: "function", function: { name: "query_worldline_paths", arguments: "{}" } }
    ] }, null));
    send(response, eventChunk({}, "tool_calls"));
  } else {
    const text = Array.isArray(body.tools) ? "Live authoritative writing brief." : "Live writer prose from the bound composer.";
    send(response, eventChunk({ role: "assistant" }, null));
    send(response, eventChunk({ content: text.slice(0, 20) }, null));
    send(response, eventChunk({ content: text.slice(20) }, null));
    send(response, eventChunk({}, "stop", { prompt_tokens: 5, completion_tokens: 7, total_tokens: 12 }));
  }
  response.end("data: [DONE]\n\n");
}

function start(response: ServerResponse): void { response.writeHead(200, { "Content-Type": "text/event-stream" }); }
function send(response: ServerResponse, value: unknown): void { response.write(`data: ${JSON.stringify(value)}\n\n`); }
function eventChunk(delta: Record<string, unknown>, finish_reason: string | null, usage?: Record<string, number>): Record<string, unknown> {
  return { id: "live", object: "chat.completion.chunk", created: 1, model: "live", choices: [{ index: 0, delta, finish_reason }], ...(usage ? { usage } : {}) };
}
function encrypt(text: string, key: Buffer): string {
  const iv = randomBytes(12); const cipher = createCipheriv("aes-256-gcm", key, iv);
  const ciphertext = Buffer.concat([cipher.update(text, "utf8"), cipher.final()]);
  return ["aes-256-gcm", "v1", iv.toString("base64"), cipher.getAuthTag().toString("base64"), ciphertext.toString("base64")].join(":");
}
function appRoleURL(value: string): string {
  const parsed = new URL(value); parsed.username = "mirofish_pi_writer_live_app"; parsed.password = "mirofish_pi_writer_live_password"; return parsed.toString();
}
