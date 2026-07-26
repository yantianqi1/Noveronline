import { createDecipheriv } from "node:crypto";

import pg from "pg";

import type {
  ComposeDraftRequest,
  ComposeDraftResult,
  CompletedWriterRunReplay,
  ExecuteWriterToolRequest,
  FindCompletedWriterRunRequest,
  AcquireLLMLeaseRequest,
  CredentialRequest,
  LLMLease,
  LLMLeaseLock,
  PiWriterRunActivityDeps,
  RecordAgentTraceEventRequest,
  RecordLLMActivityRequest,
  RecordWorkflowEventRequest,
  RecordUsageEventRequest,
  ResolvedLLMModule,
  ResolveModuleBindingRequest,
  ReleaseLLMLeaseRequest,
  AppendWriterThreadMessageRequest,
  CreateWriterApprovalRequest,
  SaveDraftRevisionRequest,
  RerankRecallRequest,
  RerankRecallResult,
  SearchAssetsArgs,
  SearchAssetsMode,
  SearchManuscriptArgs,
  UpdateWriterRunStatusRequest
} from "../activities/pi-writer-activities.js";
import { effectiveModelCapabilities } from "../llm/model-capabilities.js";
import { createPostgresQuotaStore } from "../llm/quota/postgres-quota-store.js";
import { reciprocalRankFusion, type FusionItem, type FusedItem } from "./recall-fusion.js";

export interface QueryExecutor {
  query<T extends Record<string, unknown>>(
    text: string,
    values?: readonly unknown[],
    context?: QueryTenantContext
  ): Promise<{ rows: T[] }>;
  transaction?<T>(
    context: QueryTenantContext,
    work: (executor: QueryExecutor) => Promise<T>
  ): Promise<T>;
}

export interface ClosableQueryExecutor extends QueryExecutor {
  close(): Promise<void>;
}

export interface QueryTenantContext {
  tenant_id: string;
  project_id?: string;
}

export interface CredentialDecryptContext {
  tenant_id: string;
  project_id: string;
  run_id: string;
  credential_ref: string;
}

export type CredentialDecryptor = (ciphertext: string, context: CredentialDecryptContext) => Promise<string>;

// Minimal HTTP contract for the asset query-embedding provider (OpenAI-compatible).
// Injectable so tests can stub the network and assert the degradation path.
export type QueryEmbeddingFetcher = (
  url: string,
  init: { method: string; headers: Record<string, string>; body: string }
) => Promise<{ ok: boolean; status: number; json(): Promise<unknown> }>;

export interface PostgresPiWriterDepsOptions {
  db: QueryExecutor;
  decryptCredential: CredentialDecryptor;
  composeDraft(request: ComposeDraftRequest): Promise<ComposeDraftResult>;
  leaseTtlSeconds?: number;
  fetchEmbedding?: QueryEmbeddingFetcher;
  /** Cross-encoder rerank execution (writer_retrieval_rerank); wired by the worker. */
  rerankRecall?: (request: RerankRecallRequest) => Promise<RerankRecallResult>;
}

interface RerankCandidateInput {
  id: string;
  title?: string;
  text: string;
  channels?: string[];
}

export function createPostgresPiWriterDeps(options: PostgresPiWriterDepsOptions): PiWriterRunActivityDeps {
  const quota = createPostgresQuotaStore(options.db);
  return {
    resolveModuleBinding: async (request) => resolveModuleBinding(options.db, request),
    executeWriterTool: async (request) => executeWriterTool(options, request),
    loadConsistencyCanon: async (request) => loadConsistencyCanon(options, request),
    loadAlwaysOnAssets: async (request) => loadAlwaysOnAssets(options, request),
    resolveCredential: async (request) => resolveCredential(options, request),
    reserveLLMQuota: async (request) => quota.reserve(request),
    finalizeLLMQuota: async (request) => quota.finalize(request),
    releaseLLMQuota: async (request) => quota.release(request),
    acquireLLMLease: async (request) => acquireLLMLease(options.db, request, options.leaseTtlSeconds ?? 300),
    composeDraft: options.composeDraft,
    releaseLLMLease: async (request) => releaseLLMLease(options.db, request),
    saveDraftRevision: async (request) => saveDraftRevision(options.db, request),
    appendWriterThreadMessage: async (request) => appendWriterThreadMessage(options.db, request),
    createWriterApproval: async (request) => createWriterApproval(options.db, request),
    recordLLMActivity: async (request) => recordLLMActivity(options.db, request),
    recordUsageEvent: async (request) => recordUsageEvent(options.db, request),
    recordAgentTraceEvent: async (request) => recordAgentTraceEvent(options.db, request),
    recordWorkflowEvent: async (request) => recordWorkflowEvent(options.db, request),
    updateWriterRunStatus: async (request) => updateWriterRunStatus(options.db, request),
    findCompletedWriterRun: async (request) => findCompletedWriterRun(options.db, request)
  };
}

export function createAesGcmCredentialDecryptor(keyMaterial: string): CredentialDecryptor {
  const key = parseKeyMaterial(keyMaterial);
  return async (ciphertext) => decryptAesGcm(ciphertext, key);
}

export function createPgPoolQueryExecutor(databaseUrl: string): ClosableQueryExecutor {
  const pool = new pg.Pool({ connectionString: databaseUrl });
  return {
    async query<T extends Record<string, unknown>>(
      text: string,
      values: readonly unknown[] = [],
      context?: QueryTenantContext
    ): Promise<{ rows: T[] }> {
      if (!context) {
        const result = await pool.query<T>(text, [...values]);
        return { rows: result.rows };
      }
      const client = await pool.connect();
      try {
        await client.query("BEGIN");
        await client.query(
          "SELECT app_set_tenant_context($1::uuid, NULLIF($2, '')::uuid, false)",
          [context.tenant_id.trim(), (context.project_id ?? "").trim()]
        );
        const result = await client.query<T>(text, [...values]);
        await client.query("COMMIT");
        return { rows: result.rows };
      } catch (error) {
        await client.query("ROLLBACK").catch(() => undefined);
        throw error;
      } finally {
        client.release();
      }
    },
    async transaction<T>(
      context: QueryTenantContext,
      work: (executor: QueryExecutor) => Promise<T>
    ): Promise<T> {
      const client = await pool.connect();
      try {
        await client.query("BEGIN");
        await client.query(
          "SELECT app_set_tenant_context($1::uuid, NULLIF($2, '')::uuid, false)",
          [context.tenant_id.trim(), (context.project_id ?? "").trim()]
        );
        const executor: QueryExecutor = {
          query: async <R extends Record<string, unknown>>(text: string, values: readonly unknown[] = []) => {
            const result = await client.query<R>(text, [...values]);
            return { rows: result.rows };
          }
        };
        const result = await work(executor);
        await client.query("COMMIT");
        return result;
      } catch (error) {
        await client.query("ROLLBACK").catch(() => undefined);
        throw error;
      } finally {
        client.release();
      }
    },
    async close(): Promise<void> {
      await pool.end();
    }
  };
}

function tenantContext(input: { tenant_id: string; project_id?: string }): QueryTenantContext {
  return {
    tenant_id: input.tenant_id,
    project_id: input.project_id
  };
}

async function queryWithTenantContext<T extends Record<string, unknown>>(
  db: QueryExecutor,
  request: { tenant_id: string; project_id?: string },
  text: string,
  values: readonly unknown[] = []
): Promise<{ rows: T[] }> {
  return db.query<T>(text, values, tenantContext(request));
}

async function execWithTenantContext(
  db: QueryExecutor,
  request: { tenant_id: string; project_id?: string },
  text: string,
  values: readonly unknown[] = []
): Promise<void> {
  await queryWithTenantContext(db, request, text, values);
}

async function resolveCredential(options: PostgresPiWriterDepsOptions, request: CredentialRequest): Promise<{ apiKey: string }> {
  const result = await queryWithTenantContext<{ encrypted_api_key?: string }>(
    options.db,
    request,
    `SELECT encrypted_api_key
       FROM llm_channels
      WHERE channel_id = $1
        AND enabled = TRUE
        AND (tenant_id = $2 OR tenant_id IS NULL)
      ORDER BY tenant_id NULLS LAST
      LIMIT 1`,
    [request.credential_ref, request.tenant_id]
  );
  const encryptedApiKey = result.rows[0]?.encrypted_api_key;
  if (typeof encryptedApiKey !== "string" || encryptedApiKey.trim() === "") {
    throw new Error("LLM_CREDENTIAL_UNAVAILABLE: credential reference is not available for tenant");
  }
  return {
    apiKey: await options.decryptCredential(encryptedApiKey, {
      tenant_id: request.tenant_id,
      project_id: request.project_id,
      run_id: request.run_id,
      credential_ref: request.credential_ref
    })
  };
}

async function resolveModuleBinding(db: QueryExecutor, request: ResolveModuleBindingRequest): Promise<ResolvedLLMModule> {
  let result: { rows: Array<Record<string, unknown>> };
  try {
    result = await queryWithTenantContext(
      db,
      request,
      `SELECT module_key, channel_id::text AS channel_id, model_id,
              provider, base_url, channel_id::text AS credential_ref,
              supports_tools, supports_json, settings_jsonb
         FROM (
           SELECT b.module_key, b.channel_id, b.model_id,
                  c.provider, c.base_url,
                  COALESCE(m.supports_tools, false) AS supports_tools,
                  COALESCE(m.supports_json, false) AS supports_json,
                  b.settings_jsonb,
                  CASE WHEN b.project_id = $2 THEN 0 ELSE 1 END AS binding_rank
             FROM llm_module_bindings b
             JOIN llm_channels c
               ON c.channel_id = b.channel_id
              AND c.enabled = TRUE
              AND (c.tenant_id = b.tenant_id OR c.tenant_id IS NULL)
             JOIN llm_models m
               ON m.channel_id = b.channel_id
              AND m.model_id = b.model_id
              AND (m.tenant_id = b.tenant_id OR m.tenant_id IS NULL)
              AND m.enabled = TRUE
            WHERE b.tenant_id = $1
              AND (b.project_id = $2 OR b.project_id IS NULL)
              AND b.module_key = $3
           UNION ALL
           SELECT d.module_key, d.channel_id, d.model_id,
                  c.provider, c.base_url,
                  COALESCE(m.supports_tools, false) AS supports_tools,
                  COALESCE(m.supports_json, false) AS supports_json,
                  d.settings_jsonb,
                  2 AS binding_rank
             FROM llm_platform_module_defaults d
             JOIN llm_channels c
               ON c.channel_id = d.channel_id
              AND c.enabled = TRUE
              AND c.tenant_id IS NULL
             JOIN llm_models m
               ON m.channel_id = d.channel_id
              AND m.model_id = d.model_id
              AND m.tenant_id IS NULL
              AND m.enabled = TRUE
            WHERE d.module_key = $3
         ) ranked_bindings
        ORDER BY binding_rank
        LIMIT 1`,
      [request.tenant_id, request.project_id, request.module_key]
    );
  } catch {
    throw new Error("LLM_BINDING_QUERY_FAILED: LLM module binding query failed");
  }
  const row = result.rows[0];
  if (!row) throw new Error(`LLM_MODULE_UNBOUND: ${request.module_key} module is not bound`);
  const modelId = requiredRowString(row, "model_id");
  // Catalog often keeps supports_* = false after sync; OR inference so chat models
  // are not rejected before any provider call (align with Go/Python resolvers).
  const caps = effectiveModelCapabilities(
    modelId,
    row.supports_json === true,
    row.supports_tools === true,
  );
  return {
    module_key: request.module_key,
    channel_id: requiredRowString(row, "channel_id"),
    model_id: modelId,
    provider: requiredRowString(row, "provider"),
    base_url: requiredRowString(row, "base_url"),
    credential_ref: requiredRowString(row, "credential_ref"),
    supports_tools: caps.supports_tools,
    supports_json: caps.supports_json,
    settings: objectValue(row.settings_jsonb)
  };
}

async function executeWriterTool(options: PostgresPiWriterDepsOptions, request: ExecuteWriterToolRequest): Promise<Record<string, unknown>> {
  const db = options.db;
  switch (request.tool_name) {
    case "search_assets":
      return executeSearchAssets(options, request);
    case "search_manuscript":
      return executeSearchManuscript(options, request);
    case "fuse_recall":
      return executeFuseRecall(options, request, buildRerankCallback(options, request));
    case "query_project_context": {
      const result = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT title, description, genre, language, status
           FROM projects WHERE tenant_id = $1 AND project_id = $2 LIMIT 1`,
        [request.tenant_id, request.project_id]);
      return { project: result.rows[0] ?? null };
    }
    case "query_chapter_scene": {
      const runResult = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT chapter_id::text, scene_id::text, mode
           FROM writer_runs
          WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3 LIMIT 1`,
        [request.tenant_id, request.project_id, request.run_id]);
      const runTarget = runResult.rows[0] ?? {};
      const chapterId = stringOrNull(runTarget.chapter_id) ?? request.chapter_id ?? null;
      const sceneId = stringOrNull(runTarget.scene_id) ?? request.scene_id ?? null;
      const mode = stringOrNull(runTarget.mode) ?? null;
      let chapter: Record<string, unknown> | null = null;
      let scene: Record<string, unknown> | null = null;
      let neighborScenes: Record<string, unknown>[] = [];
      if (chapterId) {
        const chapterResult = await queryWithTenantContext<Record<string, unknown>>(db, request,
          `SELECT chapter_id::text, title, status, chapter_order, brief, outline
             FROM chapters
            WHERE tenant_id = $1 AND project_id = $2 AND chapter_id = $3::uuid
            LIMIT 1`,
          [request.tenant_id, request.project_id, chapterId]);
        chapter = chapterResult.rows[0] ?? null;
      }
      if (sceneId) {
        const sceneResult = await queryWithTenantContext<Record<string, unknown>>(db, request,
          `SELECT scene_id::text, chapter_id::text, title, status, scene_order, brief, outline, content_text
             FROM scenes
            WHERE tenant_id = $1 AND project_id = $2 AND scene_id = $3::uuid
            LIMIT 1`,
          [request.tenant_id, request.project_id, sceneId]);
        scene = sceneResult.rows[0] ?? null;
      }
      if (chapterId) {
        const neighbors = await queryWithTenantContext<Record<string, unknown>>(db, request,
          `SELECT scene_id::text, title, scene_order, left(COALESCE(outline, brief, content_text, ''), 280) AS summary
             FROM scenes
            WHERE tenant_id = $1 AND project_id = $2 AND chapter_id = $3::uuid
            ORDER BY scene_order ASC
            LIMIT 12`,
          [request.tenant_id, request.project_id, chapterId]);
        neighborScenes = neighbors.rows;
      }
      return {
        target: {
          chapter_id: chapterId,
          scene_id: sceneId,
          mode
        },
        chapter,
        scene,
        neighbor_scenes: neighborScenes
      };
    }
    case "query_assets": {
      // Author-sovereign path only: return the explicitly selected assets. When
      // nothing is selected, on-demand semantic recall is search_assets' job — the
      // old top-50-by-recency dump is gone (doc 41 §3.2).
      if (!Array.isArray(request.selected_asset_ids) || request.selected_asset_ids.length === 0) {
        return { assets: [], selection: "none", recall: "search_assets" };
      }
      const result = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT asset_id::text, asset_type, category, lifecycle, title, summary, content_text, tags_jsonb
           FROM assets
          WHERE tenant_id = $1 AND project_id = $2 AND enabled = TRUE
            AND lifecycle IN ('seed', 'canon', 'material')
            AND asset_id = ANY($3::uuid[])
          ORDER BY pinned DESC, updated_at DESC LIMIT 50`,
        [request.tenant_id, request.project_id, request.selected_asset_ids]);
      return { assets: result.rows };
    }
    case "query_world_rules": {
      const seedRules = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT rule_evidence_id::text AS rule_evidence_id, rule_text, category,
                confidence::double precision AS confidence, 'seed_evidence' AS source
           FROM world_rule_evidence
          WHERE tenant_id = $1 AND project_id = $2
          ORDER BY created_at DESC
          LIMIT 40`,
        [request.tenant_id, request.project_id]);
      const assetRules = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT asset_id::text AS rule_evidence_id, COALESCE(NULLIF(content_text, ''), summary, title) AS rule_text,
                COALESCE(category, asset_type) AS category, NULL::double precision AS confidence,
                'canon_asset' AS source, lifecycle, title, summary
           FROM assets
          WHERE tenant_id = $1 AND project_id = $2
            AND enabled = TRUE
            AND lifecycle IN ('seed', 'canon', 'material')
            AND asset_type IN ('world_rule', 'worldview')
          ORDER BY pinned DESC, updated_at DESC
          LIMIT 40`,
        [request.tenant_id, request.project_id]);
      return { rules: [...seedRules.rows, ...assetRules.rows].slice(0, 50) };
    }
    case "query_character_profile": {
      const entityProfiles = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT entity.entity_id::text, entity.canonical_name, entity.entity_type,
                entity.importance, entity.state_summary,
                COALESCE(
                  jsonb_agg(alias.alias ORDER BY alias.alias)
                    FILTER (WHERE alias.alias_id IS NOT NULL),
                  '[]'::jsonb
                ) AS aliases,
                'entity' AS source
           FROM entities AS entity
           LEFT JOIN entity_aliases AS alias
             ON alias.tenant_id = entity.tenant_id
            AND alias.project_id = entity.project_id
            AND alias.entity_id = entity.entity_id
          WHERE entity.tenant_id = $1 AND entity.project_id = $2
            AND entity.entity_type = 'character'
          GROUP BY entity.entity_id, entity.canonical_name, entity.entity_type,
                   entity.importance, entity.state_summary, entity.updated_at
          ORDER BY entity.updated_at DESC
          LIMIT 40`,
        [request.tenant_id, request.project_id]);
      const assetProfiles = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT asset_id::text AS entity_id, title AS canonical_name, asset_type AS entity_type,
                NULL::text AS importance, COALESCE(summary, left(COALESCE(content_text, ''), 400)) AS state_summary,
                '[]'::jsonb AS aliases, 'canon_asset' AS source, lifecycle, category
           FROM assets
          WHERE tenant_id = $1 AND project_id = $2
            AND enabled = TRUE
            AND lifecycle IN ('seed', 'canon', 'material')
            AND asset_type IN ('character', 'seed_character')
          ORDER BY pinned DESC, updated_at DESC
          LIMIT 40`,
        [request.tenant_id, request.project_id]);
      return { profiles: [...entityProfiles.rows, ...assetProfiles.rows].slice(0, 50) };
    }
    case "query_graph_neighbors": {
      const result = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `WITH selected AS (
           SELECT node_id, node_type, title, summary, lifecycle
             FROM story_graph_nodes
            WHERE tenant_id = $1 AND project_id = $2
              AND node_id = ANY($3::uuid[])
         ), neighboring AS (
           SELECT selected.node_id AS selected_node_id,
                  neighbor.node_id, neighbor.node_type, neighbor.title, neighbor.summary, neighbor.lifecycle,
                  edge.edge_type, COALESCE(edge.label, edge.edge_type) AS relationship,
                  CASE WHEN edge.source_node_id = selected.node_id THEN 'outgoing' ELSE 'incoming' END AS direction
             FROM selected
             JOIN story_graph_edges edge
               ON edge.tenant_id = $1 AND edge.project_id = $2
              AND (edge.source_node_id = selected.node_id OR edge.target_node_id = selected.node_id)
             JOIN story_graph_nodes neighbor
               ON neighbor.tenant_id = edge.tenant_id AND neighbor.project_id = edge.project_id
              AND neighbor.node_id = CASE WHEN edge.source_node_id = selected.node_id THEN edge.target_node_id ELSE edge.source_node_id END
            ORDER BY edge.weight DESC, neighbor.importance DESC
            LIMIT 100
         )
         SELECT
           COALESCE((SELECT jsonb_agg(to_jsonb(selected) ORDER BY selected.title) FROM selected), '[]'::jsonb) AS nodes,
           COALESCE((SELECT jsonb_agg(to_jsonb(neighboring)) FROM neighboring), '[]'::jsonb) AS neighbors`,
        [request.tenant_id, request.project_id, request.graph_node_ids]);
      const row = result.rows[0] ?? {};
      const nodes = arrayValue(row.nodes);
      return { node: nodes[0] ?? null, nodes, neighbors: arrayValue(row.neighbors) };
    }
    case "query_asset_relationships": {
      // 召回一个、带出一串: 1-hop expansion over asset_links. Only enabled
      // seed/canon/material assets are visible — the writer lifecycle gate
      // (candidates/drafts never enter the writing context).
      const assetId = typeof request.tool_args?.asset_id === "string" ? request.tool_args.asset_id.trim() : "";
      if (!assetId) {
        throw new Error("VALIDATION_FAILED: query_asset_relationships requires a non-empty asset_id");
      }
      const relationTypes = Array.isArray(request.tool_args?.relation_types)
        ? request.tool_args.relation_types.filter((v): v is string => typeof v === "string" && v.trim() !== "")
        : [];
      const rawTopK = typeof request.tool_args?.top_k === "number" ? Math.floor(request.tool_args.top_k) : 10;
      const topK = Math.min(25, Math.max(1, rawTopK));
      const result = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT
           related.asset_id::text,
           related.asset_type,
           related.category,
           related.lifecycle,
           related.title,
           related.summary,
           link.relation_type,
           CASE
             WHEN link.asset_a_id = $3::uuid AND link.direction = 'a_to_b' THEN 'outgoing'
             WHEN link.asset_b_id = $3::uuid AND link.direction = 'a_to_b' THEN 'incoming'
             WHEN link.asset_a_id = $3::uuid AND link.direction = 'b_to_a' THEN 'incoming'
             WHEN link.asset_b_id = $3::uuid AND link.direction = 'b_to_a' THEN 'outgoing'
             ELSE 'undirected'
           END AS direction
         FROM asset_links link
         JOIN assets related
           ON related.tenant_id = link.tenant_id
          AND related.project_id = link.project_id
          AND related.asset_id = CASE WHEN link.asset_a_id = $3::uuid THEN link.asset_b_id ELSE link.asset_a_id END
          AND related.enabled = TRUE
          AND related.lifecycle IN ('seed', 'canon', 'material')
         WHERE link.tenant_id = $1
           AND link.project_id = $2
           AND (link.asset_a_id = $3::uuid OR link.asset_b_id = $3::uuid)
           AND (cardinality($4::text[]) = 0 OR link.relation_type = ANY($4::text[]))
         ORDER BY related.pinned DESC, related.updated_at DESC
         LIMIT $5`,
        [request.tenant_id, request.project_id, assetId, relationTypes, topK]);
      return { asset_id: assetId, relationships: result.rows };
    }
    case "query_worldline_paths": {
      const pathIds = Array.isArray(request.worldline_path_ids) ? request.worldline_path_ids.filter(Boolean) : [];
      if (pathIds.length === 0) {
        return { paths: [], canon_status: "reference_only", selection_required: true };
      }
      const result = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT path_id::text, title, summary, lifecycle, writer_instruction
           FROM worldline_saved_paths
          WHERE tenant_id = $1 AND project_id = $2
            AND path_id = ANY($3::uuid[])
          ORDER BY updated_at DESC LIMIT 20`,
        [request.tenant_id, request.project_id, pathIds]);
      return { paths: result.rows, canon_status: "reference_only" };
    }
    case "query_manuscript_context": {
      return queryManuscriptContext(db, request);
    }
    case "save_draft_revision":
      throw new Error("TOOL_PERMISSION_DENIED: draft persistence is runtime-owned");
  }
}

const MANUSCRIPT_CONTEXT_LIMIT = 32;
const MANUSCRIPT_NEARBY_LIMIT = 12;

async function queryManuscriptContext(
  db: QueryExecutor,
  request: ExecuteWriterToolRequest
): Promise<Record<string, unknown>> {
  const runResult = await queryWithTenantContext<Record<string, unknown>>(
    db,
    request,
    `SELECT chapter_id::text, scene_id::text
       FROM writer_runs
      WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3
      LIMIT 1`,
    [request.tenant_id, request.project_id, request.run_id]
  );
  const runTarget = runResult.rows[0] ?? {};
  const chapterId = stringOrNull(runTarget.chapter_id) ?? request.chapter_id ?? null;
  const sceneId = stringOrNull(runTarget.scene_id) ?? request.scene_id ?? null;

  if (sceneId) {
    const sceneBlocks = await queryWithTenantContext<Record<string, unknown>>(
      db,
      request,
      `SELECT block_id::text, chapter_id::text, scene_id::text, block_order, content_text, word_count
         FROM manuscript_blocks
        WHERE tenant_id = $1 AND project_id = $2
          AND status = 'active'
          AND scene_id = $3::uuid
        ORDER BY block_order ASC
        LIMIT $4`,
      [request.tenant_id, request.project_id, sceneId, MANUSCRIPT_CONTEXT_LIMIT]
    );
    if (sceneBlocks.rows.length > 0) {
      const remaining = Math.max(0, MANUSCRIPT_CONTEXT_LIMIT - sceneBlocks.rows.length);
      let nearby: Record<string, unknown>[] = [];
      if (remaining > 0 && chapterId) {
        const nearbyResult = await queryWithTenantContext<Record<string, unknown>>(
          db,
          request,
          `SELECT block_id::text, chapter_id::text, scene_id::text, block_order, content_text, word_count
             FROM manuscript_blocks
            WHERE tenant_id = $1 AND project_id = $2
              AND status = 'active'
              AND chapter_id = $3::uuid
              AND (scene_id IS DISTINCT FROM $4::uuid)
            ORDER BY block_order ASC
            LIMIT $5`,
          [request.tenant_id, request.project_id, chapterId, sceneId, Math.min(remaining, MANUSCRIPT_NEARBY_LIMIT)]
        );
        nearby = nearbyResult.rows;
      }
      return {
        target: { chapter_id: chapterId, scene_id: sceneId },
        manuscript_blocks: [...sceneBlocks.rows, ...nearby]
      };
    }
  }

  if (chapterId) {
    const chapterBlocks = await queryWithTenantContext<Record<string, unknown>>(
      db,
      request,
      `SELECT block_id::text, chapter_id::text, scene_id::text, block_order, content_text, word_count
         FROM manuscript_blocks
        WHERE tenant_id = $1 AND project_id = $2
          AND status = 'active'
          AND chapter_id = $3::uuid
        ORDER BY block_order ASC
        LIMIT $4`,
      [request.tenant_id, request.project_id, chapterId, MANUSCRIPT_CONTEXT_LIMIT]
    );
    if (chapterBlocks.rows.length > 0) {
      const remaining = Math.max(0, MANUSCRIPT_CONTEXT_LIMIT - chapterBlocks.rows.length);
      let nearby: Record<string, unknown>[] = [];
      if (remaining > 0) {
        const nearbyResult = await queryWithTenantContext<Record<string, unknown>>(
          db,
          request,
          `SELECT block_id::text, chapter_id::text, scene_id::text, block_order, content_text, word_count
             FROM manuscript_blocks
            WHERE tenant_id = $1 AND project_id = $2
              AND status = 'active'
              AND (chapter_id IS DISTINCT FROM $3::uuid)
            ORDER BY
              CASE
                WHEN chapter_id IS NULL THEN 2
                ELSE 1
              END,
              block_order ASC
            LIMIT $4`,
          [request.tenant_id, request.project_id, chapterId, Math.min(remaining, MANUSCRIPT_NEARBY_LIMIT)]
        );
        nearby = nearbyResult.rows;
      }
      return {
        target: { chapter_id: chapterId, scene_id: sceneId },
        manuscript_blocks: [...chapterBlocks.rows, ...nearby]
      };
    }
  }

  const fallback = await queryWithTenantContext<Record<string, unknown>>(
    db,
    request,
    `SELECT block_id::text, chapter_id::text, scene_id::text, block_order, content_text, word_count
       FROM manuscript_blocks
      WHERE tenant_id = $1 AND project_id = $2
        AND status = 'active'
      ORDER BY block_order DESC
      LIMIT $3`,
    [request.tenant_id, request.project_id, MANUSCRIPT_CONTEXT_LIMIT]
  );
  return {
    target: { chapter_id: chapterId, scene_id: sceneId },
    manuscript_blocks: fallback.rows.reverse()
  };
}

const ASSET_SEARCH_EMBEDDING_MODULE_KEY = "asset_search_embedding";
const SEARCH_ASSETS_DEFAULT_TOP_K = 10;
const SEARCH_ASSETS_MAX_TOP_K = 25;
const ASSET_QUERY_PREVIEW_MAX = 280;
// Writer-side safety gate: only author-sovereign canon may be recalled. Candidate,
// draft, and simulation assets never enter the writing context (mirrors query_assets).
const SEARCH_ASSETS_LIFECYCLES = ["seed", "canon", "material"] as const;

// Resolve the chapter_order the author is writing at, for the spoiler gate
// (doc 41 §4.5). Assets with reveal_after_chapter_order greater than this are
// withheld from recall. NULL (no target chapter) means only always-visible
// (gated-NULL) assets are recalled — the safe default.
async function resolveCurrentChapterOrder(
  db: QueryExecutor,
  request: ExecuteWriterToolRequest
): Promise<number | null> {
  const chapterId = request.chapter_id ?? null;
  if (!chapterId) return null;
  const result = await queryWithTenantContext<{ chapter_order?: number | string }>(
    db,
    request,
    `SELECT chapter_order FROM chapters
      WHERE tenant_id = $1 AND project_id = $2 AND chapter_id = $3::uuid LIMIT 1`,
    [request.tenant_id, request.project_id, chapterId]
  );
  const value = result.rows[0]?.chapter_order;
  const order = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  return Number.isInteger(order) && order >= 0 ? order : null;
}

interface QueryEmbeddingResult {
  embedding: number[];
  modelId: string;
}

interface SearchAssetsResolution {
  mode: SearchAssetsMode;
  degraded: boolean;
  degradeReason?: string;
  embedding?: QueryEmbeddingResult;
}

function parseSearchAssetsArgs(raw: Record<string, unknown> | undefined): SearchAssetsArgs {
  const args = (raw ?? {}) as Record<string, unknown>;
  const query = typeof args.query === "string" ? args.query.trim() : "";
  if (!query) {
    throw new Error("VALIDATION_FAILED: search_assets requires a non-empty query");
  }
  const mode: SearchAssetsMode =
    args.mode === "keyword" || args.mode === "vector" || args.mode === "hybrid" ? args.mode : "hybrid";
  let topK = SEARCH_ASSETS_DEFAULT_TOP_K;
  if (typeof args.top_k === "number" && Number.isFinite(args.top_k)) {
    topK = Math.min(SEARCH_ASSETS_MAX_TOP_K, Math.max(1, Math.floor(args.top_k)));
  }
  const assetTypes = Array.isArray(args.asset_types)
    ? args.asset_types.filter((value): value is string => typeof value === "string" && value.trim() !== "")
    : undefined;
  return {
    query,
    mode,
    top_k: topK,
    ...(assetTypes && assetTypes.length > 0 ? { asset_types: assetTypes } : {}),
    ...(args.expand_relations === true ? { expand_relations: true } : {})
  };
}

async function resolveSearchAssetsMode(
  options: PostgresPiWriterDepsOptions,
  request: ExecuteWriterToolRequest,
  args: SearchAssetsArgs
): Promise<SearchAssetsResolution> {
  const requested = args.mode ?? "hybrid";
  if (requested === "keyword") {
    return { mode: "keyword", degraded: false };
  }
  try {
    const embedding = await resolveQueryEmbedding(options, request, args.query);
    return { mode: requested, degraded: false, embedding };
  } catch (error) {
    // Explicit, visible degradation — never pretend hybrid when embeddings are unavailable.
    return { mode: "keyword", degraded: true, degradeReason: errorMessage(error) };
  }
}

async function resolveQueryEmbedding(
  options: PostgresPiWriterDepsOptions,
  request: ExecuteWriterToolRequest,
  query: string
): Promise<QueryEmbeddingResult> {
  const binding = await resolveModuleBinding(options.db, {
    tenant_id: request.tenant_id,
    project_id: request.project_id,
    run_id: request.run_id,
    module_key: ASSET_SEARCH_EMBEDDING_MODULE_KEY
  });
  const provider = binding.provider.trim().toLowerCase();
  if (provider !== "openai" && provider !== "openai-compatible") {
    throw new Error(`asset_search_embedding provider ${binding.provider} is not OpenAI-compatible`);
  }
  const { apiKey } = await resolveCredential(options, {
    tenant_id: request.tenant_id,
    project_id: request.project_id,
    run_id: request.run_id,
    module_key: ASSET_SEARCH_EMBEDDING_MODULE_KEY,
    channel_id: binding.channel_id,
    credential_ref: binding.credential_ref
  });
  const embedding = await requestQueryEmbedding(options, request, binding, apiKey, query);
  return { embedding, modelId: binding.model_id };
}

async function requestQueryEmbedding(
  options: PostgresPiWriterDepsOptions,
  request: ExecuteWriterToolRequest,
  binding: ResolvedLLMModule,
  apiKey: string,
  query: string
): Promise<number[]> {
  const body: Record<string, unknown> = { model: binding.model_id, input: [query] };
  const dimensions = positiveIntSetting(binding.settings, "embedding_dimensions");
  if (dimensions !== undefined) body.dimensions = dimensions;
  const fetcher: QueryEmbeddingFetcher =
    options.fetchEmbedding ??
    (async (url, init) => {
      const response = await fetch(url, { method: init.method, headers: init.headers, body: init.body });
      return { ok: response.ok, status: response.status, json: () => response.json() as Promise<unknown> };
    });
  const base = binding.base_url.trim().replace(/\/+$/, "");
  const url = base.endsWith("/embeddings") ? base : `${base}/embeddings`;
  const response = await fetcher(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "X-MiroFish-Tenant-Id": request.tenant_id,
      "X-MiroFish-Project-Id": request.project_id,
      "X-MiroFish-Module-Key": ASSET_SEARCH_EMBEDDING_MODULE_KEY
    },
    body: JSON.stringify(body)
  });
  if (!response.ok) {
    throw new Error(`asset query embedding provider request failed (status ${response.status})`);
  }
  const payload = (await response.json()) as { data?: Array<{ index?: number; embedding?: unknown }> };
  const first = payload.data?.[0];
  if (!payload.data || payload.data.length !== 1 || first?.index !== 0 || !Array.isArray(first.embedding)) {
    throw new Error("asset query embedding provider returned an invalid response");
  }
  return first.embedding as number[];
}

function positiveIntSetting(settings: Record<string, unknown>, key: string): number | undefined {
  const value = settings[key];
  if (typeof value === "number" && Number.isInteger(value) && value > 0) return value;
  return undefined;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function truncateAssetPreview(value: string): string {
  const trimmed = value.trim();
  return trimmed.length > ASSET_QUERY_PREVIEW_MAX ? `${trimmed.slice(0, ASSET_QUERY_PREVIEW_MAX)}…` : trimmed;
}

function toVectorLiteral(embedding: number[]): string {
  return `[${embedding.join(",")}]`;
}

const KEYED_MAX_MATCHES = 12;
const KEYED_ALIAS_MIN_LEN = 2;

// P1 (doc 41 §4.2): keyed/alias-triggered recall — the deterministic complement
// to vector search. Proper names (characters, places, techniques) defeat pure
// embeddings, so any asset whose title — or a character alias — appears in the
// current retrieval context is force-injected, bypassing relevance scoring.
// Drives the planner's "keyed" channel queries.
async function executeKeyedAssets(
  options: PostgresPiWriterDepsOptions,
  request: ExecuteWriterToolRequest,
  contextTexts: string[]
): Promise<Record<string, unknown>> {
  const db = options.db;
  const haystack = contextTexts.join("\n").toLowerCase();
  const currentChapterOrder = await resolveCurrentChapterOrder(db, request);
  if (!haystack.trim()) {
    return { count: 0, assets: [], citations: [], gated: gatedResult(currentChapterOrder) };
  }

  const assetRows = (
    await queryWithTenantContext<Record<string, unknown>>(
      db,
      request,
      `SELECT asset_id::text, asset_type, category, lifecycle, title, summary, content_text, pinned
         FROM assets
        WHERE tenant_id = $1 AND project_id = $2 AND enabled = TRUE
          AND lifecycle = ANY($3::text[])
          AND (reveal_after_chapter_order IS NULL OR reveal_after_chapter_order <= $4)`,
      [request.tenant_id, request.project_id, [...SEARCH_ASSETS_LIFECYCLES], currentChapterOrder]
    )
  ).rows;

  const aliasRows = (
    await queryWithTenantContext<Record<string, unknown>>(
      db,
      request,
      `SELECT e.entity_id::text AS entity_id, e.canonical_name AS canonical_name,
              e.state_summary AS state_summary, ea.alias AS alias
         FROM entity_aliases ea
         JOIN entities e
           ON e.tenant_id = ea.tenant_id AND e.project_id = ea.project_id AND e.entity_id = ea.entity_id
        WHERE ea.tenant_id = $1 AND ea.project_id = $2
          AND e.entity_type = 'character'`,
      [request.tenant_id, request.project_id]
    )
  ).rows;

  const matched = new Map<string, { row: Record<string, unknown>; key: string }>();
  for (const row of assetRows) {
    const title = typeof row.title === "string" ? row.title.trim() : "";
    if (title.length >= KEYED_ALIAS_MIN_LEN && haystack.includes(title.toLowerCase())) {
      matched.set(String(row.asset_id), { row, key: title });
    }
  }
  // Alias/name matches inject the character entity profile (the aliases live on
  // entities, not assets). Keyed by entity id so a character can't double-inject.
  for (const aliasRow of aliasRows) {
    const names = [aliasRow.canonical_name, aliasRow.alias]
      .map((n) => (typeof n === "string" ? n.trim() : ""))
      .filter((n) => n.length >= KEYED_ALIAS_MIN_LEN);
    const hit = names.find((n) => haystack.includes(n.toLowerCase()));
    if (!hit) continue;
    const key = `entity:${String(aliasRow.entity_id)}`;
    if (matched.has(key)) continue;
    matched.set(key, {
      key: hit,
      row: {
        asset_id: aliasRow.entity_id,
        asset_type: "character",
        category: "cast",
        lifecycle: "canon",
        title: aliasRow.canonical_name,
        summary: aliasRow.state_summary,
        content_text: aliasRow.state_summary,
        pinned: false
      }
    });
  }

  const assets = [...matched.values()]
    .sort((a, b) => Number(b.row.pinned === true) - Number(a.row.pinned === true))
    .slice(0, KEYED_MAX_MATCHES)
    .map(({ row, key }) => ({
      asset_id: row.asset_id,
      asset_type: row.asset_type,
      category: row.category,
      lifecycle: row.lifecycle,
      title: row.title,
      summary: row.summary,
      content_preview: truncateAssetPreview(typeof row.content_text === "string" ? row.content_text : ""),
      matched_key: key,
      channel: "keyed"
    }));

  return {
    count: assets.length,
    assets,
    citations: assets.map((asset) => ({
      asset_id: asset.asset_id,
      title: asset.title,
      lifecycle: asset.lifecycle,
      matched_key: asset.matched_key,
      channel: "keyed"
    })),
    ...gatedResult(currentChapterOrder)
  };
}

function gatedResult(currentChapterOrder: number | null): Record<string, unknown> {
  return { spoiler_gated: true, current_chapter_order: currentChapterOrder };
}

// P1 (doc 41 §4.2 always_on): the constant-injection channel. Core world laws
// and style/ban constraints must be present on every writing run whether or not
// the retrieval context names them. This is NOT scored like recall — the
// activity loads it unconditionally and injects it as fuse_recall's top channel.
// It still respects the safety gates (enabled + lifecycle whitelist + spoiler
// gate): an always_on asset revealed only later must not leak early. Capped
// small so the constant prefix can't flood the writing context.
const ALWAYS_ON_MAX = 8;
async function loadAlwaysOnAssets(
  options: PostgresPiWriterDepsOptions,
  request: ExecuteWriterToolRequest
): Promise<{ assets: import("../activities/pi-writer-activities.js").AlwaysOnAssetItem[] }> {
  const db = options.db;
  const currentChapterOrder = await resolveCurrentChapterOrder(db, request);
  const rows = (
    await queryWithTenantContext<Record<string, unknown>>(
      db,
      request,
      `SELECT asset_id::text, asset_type, category, lifecycle, title, summary, content_text
         FROM assets
        WHERE tenant_id = $1 AND project_id = $2 AND enabled = TRUE
          AND always_on = TRUE
          AND lifecycle = ANY($3::text[])
          AND (reveal_after_chapter_order IS NULL OR reveal_after_chapter_order <= $4)
        ORDER BY pinned DESC, updated_at DESC
        LIMIT $5`,
      [request.tenant_id, request.project_id, [...SEARCH_ASSETS_LIFECYCLES], currentChapterOrder, ALWAYS_ON_MAX]
    )
  ).rows;
  const assets = rows.map((row) => ({
    asset_id: String(row.asset_id),
    asset_type: String(row.asset_type),
    category: typeof row.category === "string" ? row.category : undefined,
    lifecycle: String(row.lifecycle),
    title: typeof row.title === "string" ? row.title : "",
    summary: typeof row.summary === "string" ? row.summary : undefined,
    content_preview: truncateAssetPreview(typeof row.content_text === "string" ? row.content_text : ""),
    channel: "always_on"
  }));
  return { assets };
}

const WRITER_RETRIEVAL_RERANK_MODULE_KEY = "writer_retrieval_rerank";

// Load the canon a draft is checked against for consistency (doc 41 §4.7):
// hard world rules + current character states, gated to author-sovereign canon
// and the same spoiler gate as recall (never check against unrevealed canon).
async function loadConsistencyCanon(
  options: PostgresPiWriterDepsOptions,
  request: ExecuteWriterToolRequest
): Promise<{ canon: import("../activities/pi-writer-activities.js").ConsistencyCanonItem[] }> {
  const db = options.db;
  const currentChapterOrder = await resolveCurrentChapterOrder(db, request);
  const ruleRows = (
    await queryWithTenantContext<Record<string, unknown>>(
      db,
      request,
      `SELECT title, COALESCE(NULLIF(content_text, ''), summary, title) AS rule_text
         FROM assets
        WHERE tenant_id = $1 AND project_id = $2 AND enabled = TRUE
          AND lifecycle = ANY($3::text[])
          AND asset_type IN ('world_rule', 'worldview')
          AND (reveal_after_chapter_order IS NULL OR reveal_after_chapter_order <= $4)
        ORDER BY pinned DESC, updated_at DESC
        LIMIT 40`,
      [request.tenant_id, request.project_id, [...SEARCH_ASSETS_LIFECYCLES], currentChapterOrder]
    )
  ).rows;
  const characterRows = (
    await queryWithTenantContext<Record<string, unknown>>(
      db,
      request,
      `SELECT canonical_name, COALESCE(state_summary, '') AS state_summary
         FROM entities
        WHERE tenant_id = $1 AND project_id = $2 AND entity_type = 'character'
        ORDER BY updated_at DESC
        LIMIT 40`,
      [request.tenant_id, request.project_id]
    )
  ).rows;
  const canon: import("../activities/pi-writer-activities.js").ConsistencyCanonItem[] = [];
  for (const row of ruleRows) {
    const text = typeof row.rule_text === "string" ? row.rule_text.trim() : "";
    if (!text) continue;
    canon.push({
      kind: "world_rule",
      label: typeof row.title === "string" && row.title.trim() ? row.title.trim() : text.slice(0, 24),
      text: text.slice(0, 400)
    });
  }
  for (const row of characterRows) {
    const name = typeof row.canonical_name === "string" ? row.canonical_name.trim() : "";
    const state = typeof row.state_summary === "string" ? row.state_summary.trim() : "";
    if (!name || !state) continue;
    canon.push({ kind: "character_state", label: name, text: state.slice(0, 400) });
  }
  return { canon };
}

// Build a rerank callback bound to this run's credential/binding, or undefined
// when no rerank execution is wired. The callback resolves the writer_retrieval_rerank
// module and calls the cross-encoder; failures propagate so the caller can degrade.
function buildRerankCallback(
  options: PostgresPiWriterDepsOptions,
  request: ExecuteWriterToolRequest
): ((query: string, candidates: RerankCandidateInput[]) => Promise<string[]>) | undefined {
  if (!options.rerankRecall) return undefined;
  return async (query, candidates) => {
    const binding = await resolveModuleBinding(options.db, {
      tenant_id: request.tenant_id,
      project_id: request.project_id,
      run_id: request.run_id,
      module_key: WRITER_RETRIEVAL_RERANK_MODULE_KEY
    });
    const { apiKey } = await resolveCredential(options, {
      tenant_id: request.tenant_id,
      project_id: request.project_id,
      run_id: request.run_id,
      module_key: WRITER_RETRIEVAL_RERANK_MODULE_KEY,
      channel_id: binding.channel_id,
      credential_ref: binding.credential_ref
    });
    const result = await options.rerankRecall!({
      tenant_id: request.tenant_id,
      project_id: request.project_id,
      run_id: request.run_id,
      module_key: binding.module_key,
      channel_id: binding.channel_id,
      model_id: binding.model_id,
      provider: binding.provider,
      base_url: binding.base_url,
      query,
      candidates,
      apiKey,
      settings: binding.settings
    });
    return result.ranked_ids;
  };
}

// P2 (doc 41 §4.6): fuse the run's multi-channel recall (keyed / hybrid /
// manuscript) into one RRF-ranked list. When the caller passes rerank:true with a
// query and the activity has wired a reranker, the writer_retrieval_rerank
// cross-encoder re-orders the fused list; reranker unavailable/failed degrades to
// the RRF order explicitly.
async function executeFuseRecall(
  options: PostgresPiWriterDepsOptions,
  request: ExecuteWriterToolRequest,
  rerank?: (query: string, candidates: RerankCandidateInput[]) => Promise<string[]>
): Promise<Record<string, unknown>> {
  const raw = (request.tool_args ?? {}) as Record<string, unknown>;
  const lists = Array.isArray(raw.channels) ? raw.channels : [];
  const channelLists: FusionItem[][] = lists.map((entry) => {
    const record = (entry ?? {}) as Record<string, unknown>;
    const channel = typeof record.channel === "string" ? record.channel : "unknown";
    const items = Array.isArray(record.items) ? record.items : [];
    return items
      .map((item): FusionItem | null => {
        const r = (item ?? {}) as Record<string, unknown>;
        const id = typeof r.asset_id === "string" ? r.asset_id
          : typeof r.block_id === "string" ? r.block_id
            : typeof r.id === "string" ? r.id : null;
        if (!id) return null;
        return {
          id,
          title: typeof r.title === "string" ? r.title : undefined,
          channel,
          payload: r
        };
      })
      .filter((x): x is FusionItem => x !== null);
  });
  const fused = reciprocalRankFusion(channelLists);
  const byId = new Map(fused.map((item) => [item.id, item]));

  // Optional cross-encoder rerank of the wide fused list (doc 41 §4.6 second half).
  let rerankedIds: string[] | null = null;
  let rerankDegraded: string | null = null;
  if (raw.rerank === true && typeof raw.query === "string" && raw.query.trim() && rerank && fused.length > 0) {
    try {
      const wide = fused.slice(0, 50).map((item) => ({
        id: item.id,
        title: item.title,
        text: rerankTextFor(item),
        channels: item.channels
      }));
      const ids = await rerank(raw.query.trim(), wide);
      rerankedIds = ids.filter((id) => byId.has(id));
    } catch (error) {
      rerankDegraded = errorMessage(error);
    }
  }

  const ordered: FusedItem[] = rerankedIds
    ? [...rerankedIds.map((id) => byId.get(id)!), ...fused.filter((item) => !rerankedIds!.includes(item.id))]
    : fused;
  const topK = typeof raw.top_k === "number" && Number.isInteger(raw.top_k) && raw.top_k > 0
    ? Math.min(25, raw.top_k)
    : ordered.length;
  const results = ordered.slice(0, topK).map((item) => ({
    id: item.id,
    title: item.title,
    channels: item.channels,
    rrf_score: Math.round(item.rrf_score * 10000) / 10000,
    best_rank: item.best_rank,
    payload: item.payload
  }));
  return {
    count: results.length,
    fused: results,
    reranked: rerankedIds !== null,
    ...(rerankDegraded ? { rerank_degraded: rerankDegraded } : {}),
    citations: results.map((item) => ({
      asset_id: item.id,
      title: item.title,
      channels: item.channels,
      rrf_score: item.rrf_score,
      channel: "fuse_recall"
    }))
  };
}

function rerankTextFor(item: FusionItem): string {
  const payload = (item.payload ?? {}) as Record<string, unknown>;
  const text = payload.content_preview ?? payload.snippet ?? payload.summary ?? item.title ?? "";
  return typeof text === "string" ? text.slice(0, 280) : "";
}

async function executeSearchAssets(
  options: PostgresPiWriterDepsOptions,
  request: ExecuteWriterToolRequest
): Promise<Record<string, unknown>> {
  const db = options.db;
  const rawArgs = (request.tool_args ?? {}) as Record<string, unknown>;
  // Keyed channel (planner "keyed" queries): deterministic alias/name-triggered
  // force-injection, bypassing relevance scoring entirely.
  if (rawArgs.channel === "keyed") {
    const queryText = typeof rawArgs.query === "string" ? rawArgs.query : "";
    return executeKeyedAssets(options, request, [queryText]);
  }
  const args = parseSearchAssetsArgs(request.tool_args);
  const resolution = await resolveSearchAssetsMode(options, request, args);
  const useVector = resolution.mode !== "keyword" && resolution.embedding !== undefined;
  const assetTypes = args.asset_types ?? [];
  // Spoiler gate (doc 41 §4.5): withhold assets revealed only after the chapter
  // being written. NULL current order => only always-visible assets are recalled.
  const currentChapterOrder = await resolveCurrentChapterOrder(db, request);
  // Hybrid ranking SQL mirrors SQLReader.SearchAssets (apps/api/internal/assets/assets.go:770):
  // same tsvector + ILIKE keyword score, cosine vector score, and recency/lifecycle/pinned boosts,
  // with the Writer lifecycle/enable/spoiler gate enforced here as parameters.
  const rows = (
    await queryWithTenantContext<Record<string, unknown>>(
      db,
      request,
      `WITH search_input AS (
         SELECT
           $1::text AS tenant_id,
           $2::text AS project_id,
           $3::text AS query_text,
           ('%' || $3::text || '%') AS keyword_pattern,
           $4::text AS search_mode,
           CASE WHEN $4::text = 'keyword' THEN NULL::vector ELSE $5::vector END AS query_embedding,
           $6::text AS embedding_model,
           $7::text[] AS asset_types,
           $8::text[] AS lifecycles
       ),
       candidate_scores AS (
         SELECT
           asset.asset_id,
           asset.asset_type,
           asset.category,
           asset.lifecycle,
           asset.title,
           asset.summary,
           asset.content_text,
           asset.tags_jsonb,
           asset.updated_at,
           asset.pinned,
           GREATEST(
             ts_rank_cd(search_doc.search_vector, websearch_to_tsquery('simple'::regconfig, input.query_text)),
             CASE
               WHEN search_doc.title ILIKE input.keyword_pattern
                 OR COALESCE(search_doc.body, '') ILIKE input.keyword_pattern
                 OR COALESCE(asset.content_text, '') ILIKE input.keyword_pattern THEN 0.5
               ELSE 0.0
             END
           )::float8 AS keyword_score,
           CASE
             WHEN input.search_mode = 'keyword' THEN 0.0
             ELSE GREATEST(0.0, LEAST(1.0, 1.0 - (embedding.embedding <=> input.query_embedding)))
           END::float8 AS vector_score
         FROM search_input input
         JOIN global_search_index search_doc
           ON search_doc.source = 'asset'
          AND search_doc.tenant_id::text = input.tenant_id
          AND search_doc.project_id::text = input.project_id
         JOIN assets asset
           ON asset.tenant_id = search_doc.tenant_id
          AND asset.project_id = search_doc.project_id
          AND asset.asset_id::text = search_doc.source_ref
          AND asset.enabled = TRUE
         LEFT JOIN asset_embeddings embedding
           ON embedding.tenant_id = asset.tenant_id
          AND embedding.project_id = asset.project_id
          AND embedding.asset_id = asset.asset_id
          AND embedding.embedding_model = input.embedding_model
          AND embedding.dimensions = vector_dims(input.query_embedding)
         WHERE (cardinality(input.asset_types) = 0 OR asset.asset_type = ANY(input.asset_types))
           AND asset.lifecycle = ANY(input.lifecycles)
           AND (asset.reveal_after_chapter_order IS NULL OR asset.reveal_after_chapter_order <= $10)
           AND (
             (
               input.search_mode = 'keyword'
               AND (
                 search_doc.search_vector @@ websearch_to_tsquery('simple'::regconfig, input.query_text)
                 OR search_doc.title ILIKE input.keyword_pattern
                 OR COALESCE(search_doc.body, '') ILIKE input.keyword_pattern
                 OR COALESCE(asset.content_text, '') ILIKE input.keyword_pattern
               )
             )
             OR (
               input.search_mode IN ('vector', 'hybrid')
               AND embedding.embedding_id IS NOT NULL
             )
           )
       ),
       boosted_scores AS (
         SELECT
           candidate.*,
           (0.05 / (1.0 + GREATEST(EXTRACT(EPOCH FROM (now() - candidate.updated_at)) / 86400.0, 0.0) / 365.0))::float8 AS recency_boost,
           CASE candidate.lifecycle
             WHEN 'canon' THEN 0.08
             WHEN 'manuscript' THEN 0.08
             WHEN 'seed' THEN 0.04
             WHEN 'material' THEN 0.04
             WHEN 'candidate' THEN 0.01
             ELSE 0.0
           END::float8 AS lifecycle_boost,
           CASE WHEN candidate.pinned THEN 0.05 ELSE 0.0 END::float8 AS pinned_boost
         FROM candidate_scores candidate
       ),
       final_scores AS (
         SELECT
           boosted.*,
           CASE input.search_mode
             WHEN 'keyword' THEN boosted.keyword_score
             WHEN 'vector' THEN boosted.vector_score
             ELSE (0.45 * boosted.keyword_score) + (0.55 * boosted.vector_score)
           END + boosted.recency_boost + boosted.lifecycle_boost + boosted.pinned_boost AS final_score
         FROM boosted_scores boosted
         CROSS JOIN search_input input
       )
       SELECT
         final_scores.asset_id::text,
         final_scores.asset_type,
         final_scores.category,
         final_scores.lifecycle,
         final_scores.title,
         final_scores.summary,
         final_scores.content_text,
         final_scores.tags_jsonb::text AS tags_jsonb,
         final_scores.keyword_score,
         final_scores.vector_score,
         final_scores.recency_boost,
         final_scores.lifecycle_boost,
         final_scores.pinned_boost,
         final_scores.final_score
       FROM final_scores
       ORDER BY final_scores.final_score DESC, final_scores.keyword_score DESC, final_scores.vector_score DESC, final_scores.asset_id ASC
       LIMIT $9`,
      [
        request.tenant_id,
        request.project_id,
        args.query,
        resolution.mode,
        useVector ? toVectorLiteral(resolution.embedding!.embedding) : null,
        useVector ? resolution.embedding!.modelId : "",
        assetTypes,
        [...SEARCH_ASSETS_LIFECYCLES],
        args.top_k ?? SEARCH_ASSETS_DEFAULT_TOP_K,
        currentChapterOrder
      ]
    )
  ).rows;

  const assets = rows.map((row) => {
    const contentText = typeof row.content_text === "string" ? row.content_text : "";
    return {
      asset_id: row.asset_id,
      asset_type: row.asset_type,
      category: row.category,
      lifecycle: row.lifecycle,
      title: row.title,
      summary: row.summary,
      content_preview: truncateAssetPreview(contentText),
      tags: safeParseJsonArray(row.tags_jsonb),
      score: row.final_score,
      scores: {
        keyword: row.keyword_score,
        vector: useVector ? row.vector_score : null,
        recency_boost: row.recency_boost,
        lifecycle_boost: row.lifecycle_boost,
        pinned_boost: row.pinned_boost
      }
    };
  });

  // 召回一个、带出一串: optionally attach each recalled asset's 1-hop relations.
  let relatedByAsset: Map<string, Record<string, unknown>[]> | undefined;
  if (args.expand_relations === true && assets.length > 0) {
    relatedByAsset = await loadRelatedAssets(db, request, assets.map((a) => String(a.asset_id)));
  }
  if (relatedByAsset) {
    for (const asset of assets) {
      const related = relatedByAsset.get(String(asset.asset_id));
      if (related && related.length > 0) {
        (asset as Record<string, unknown>).related = related;
      }
    }
  }

  return {
    query: args.query,
    mode_used: resolution.mode,
    degraded: resolution.degraded,
    ...(resolution.degradeReason ? { degrade_reason: resolution.degradeReason } : {}),
    count: assets.length,
    assets,
    citations: assets.map((asset) => ({
      asset_id: asset.asset_id,
      title: asset.title,
      lifecycle: asset.lifecycle,
      score: asset.score,
      channel: "search_assets"
    }))
  };
}

/**
 * Batch-load 1-hop related assets for a set of recalled asset ids, grouped by
 * the originating asset. Same lifecycle gate as query_asset_relationships.
 */
async function loadRelatedAssets(
  db: QueryExecutor,
  request: ExecuteWriterToolRequest,
  assetIds: string[]
): Promise<Map<string, Record<string, unknown>[]>> {
  const result = await queryWithTenantContext<Record<string, unknown>>(db, request,
    `SELECT
       CASE WHEN link.asset_a_id = related.asset_id THEN link.asset_b_id ELSE link.asset_a_id END::text AS origin_asset_id,
       related.asset_id::text,
       related.asset_type,
       related.lifecycle,
       related.title,
       related.summary,
       link.relation_type,
       CASE
         WHEN link.asset_a_id = related.asset_id AND link.direction = 'a_to_b' THEN 'incoming'
         WHEN link.asset_b_id = related.asset_id AND link.direction = 'a_to_b' THEN 'outgoing'
         WHEN link.asset_a_id = related.asset_id AND link.direction = 'b_to_a' THEN 'outgoing'
         WHEN link.asset_b_id = related.asset_id AND link.direction = 'b_to_a' THEN 'incoming'
         ELSE 'undirected'
       END AS direction
     FROM asset_links link
     JOIN assets related
       ON related.tenant_id = link.tenant_id
      AND related.project_id = link.project_id
      AND (link.asset_a_id = related.asset_id OR link.asset_b_id = related.asset_id)
      AND related.enabled = TRUE
      AND related.lifecycle IN ('seed', 'canon', 'material')
     WHERE link.tenant_id = $1
       AND link.project_id = $2
       AND (link.asset_a_id = ANY($3::uuid[]) OR link.asset_b_id = ANY($3::uuid[]))
     ORDER BY related.pinned DESC, related.updated_at DESC`,
    [request.tenant_id, request.project_id, assetIds]);
  const map = new Map<string, Record<string, unknown>[]>();
  for (const row of result.rows) {
    const origin = typeof row.origin_asset_id === "string" ? row.origin_asset_id : "";
    if (!origin || origin === row.asset_id) continue;
    const { origin_asset_id: _drop, ...related } = row;
    const list = map.get(origin) ?? [];
    if (list.length < 12) {
      list.push(related);
      map.set(origin, list);
    }
  }
  return map;
}

function safeParseJsonArray(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (typeof value === "string") {
    try {
      const parsed: unknown = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
}

const SEARCH_MANUSCRIPT_DEFAULT_TOP_K = 5;
const SEARCH_MANUSCRIPT_MAX_TOP_K = 12;
const MANUSCRIPT_SNIPPET_MAX = 240;

function parseSearchManuscriptArgs(raw: Record<string, unknown> | undefined): SearchManuscriptArgs {
  const args = (raw ?? {}) as Record<string, unknown>;
  const query = typeof args.query === "string" ? args.query.trim() : "";
  if (!query) {
    throw new Error("VALIDATION_FAILED: search_manuscript requires a non-empty query");
  }
  let topK = SEARCH_MANUSCRIPT_DEFAULT_TOP_K;
  if (typeof args.top_k === "number" && Number.isFinite(args.top_k)) {
    topK = Math.min(SEARCH_MANUSCRIPT_MAX_TOP_K, Math.max(1, Math.floor(args.top_k)));
  }
  return { query, top_k: topK };
}

// P1 (doc 41 §4.3): semantic recall over NON-adjacent prior prose — foreshadowing
// and callbacks the immediate scene window can't reach. Vector-only (no keyword
// fallback: full-text over prose is noisy); degrades explicitly when embeddings
// are unavailable. Timeline-gated to blocks at or before the current scene so the
// agent never recalls prose written after the point being written.
async function executeSearchManuscript(
  options: PostgresPiWriterDepsOptions,
  request: ExecuteWriterToolRequest
): Promise<Record<string, unknown>> {
  const db = options.db;
  const args = parseSearchManuscriptArgs(request.tool_args);
  const runTarget = await queryWithTenantContext<Record<string, unknown>>(
    db,
    request,
    `SELECT chapter_id::text, scene_id::text
       FROM writer_runs
      WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3
      LIMIT 1`,
    [request.tenant_id, request.project_id, request.run_id]
  );
  const chapterId = stringOrNull(runTarget.rows[0]?.chapter_id) ?? request.chapter_id ?? null;
  const sceneId = stringOrNull(runTarget.rows[0]?.scene_id) ?? request.scene_id ?? null;

  let embedding: QueryEmbeddingResult;
  try {
    embedding = await resolveQueryEmbedding(options, request, args.query);
  } catch (error) {
    return {
      query: args.query,
      mode_used: "unavailable",
      degraded: true,
      degrade_reason: errorMessage(error),
      count: 0,
      manuscript_blocks: [],
      citations: []
    };
  }

  // Current cursor = highest block_order of the target scene; recall is limited to
  // strictly earlier prose plus other scenes, never blocks after the cursor.
  const cursorResult = await queryWithTenantContext<Record<string, unknown>>(
    db,
    request,
    sceneId
      ? `SELECT COALESCE(MAX(block_order), -1)::int AS cursor_order
           FROM manuscript_blocks
          WHERE tenant_id = $1 AND project_id = $2 AND status = 'active' AND scene_id = $3::uuid`
      : `SELECT COALESCE(MAX(block_order), -1)::int AS cursor_order
           FROM manuscript_blocks
          WHERE tenant_id = $1 AND project_id = $2 AND status = 'active' AND chapter_id = $3::uuid`,
    [request.tenant_id, request.project_id, sceneId ?? chapterId ?? ""]
  );
  const cursorOrder = Number(cursorResult.rows[0]?.cursor_order ?? -1);

  const rows = (
    await queryWithTenantContext<Record<string, unknown>>(
      db,
      request,
      `SELECT
         block.block_id::text,
         block.chapter_id::text,
         block.scene_id::text,
         block.block_order,
         block.content_text,
         block.word_count,
         (1 - (embedding.embedding <=> $4::vector))::float8 AS score
       FROM manuscript_block_embeddings embedding
       JOIN manuscript_blocks block
         ON block.tenant_id = embedding.tenant_id
        AND block.project_id = embedding.project_id
        AND block.block_id = embedding.block_id
        AND block.status = 'active'
       WHERE embedding.tenant_id::text = $1
         AND embedding.project_id::text = $2
         AND embedding.embedding_model = $3
         AND embedding.dimensions = vector_dims($4::vector)
         AND (
           block.block_order < $5
           OR ($6::uuid IS NOT NULL AND block.scene_id IS DISTINCT FROM $6::uuid)
         )
       ORDER BY embedding.embedding <=> $4::vector ASC
       LIMIT $7`,
      [
        request.tenant_id,
        request.project_id,
        embedding.modelId,
        toVectorLiteral(embedding.embedding),
        cursorOrder,
        sceneId,
        args.top_k ?? SEARCH_MANUSCRIPT_DEFAULT_TOP_K
      ]
    )
  ).rows;

  const blocks = rows.map((row) => ({
    block_id: row.block_id,
    chapter_id: row.chapter_id,
    scene_id: row.scene_id,
    block_order: row.block_order,
    snippet: truncateAssetPreview(typeof row.content_text === "string" ? row.content_text.slice(0, MANUSCRIPT_SNIPPET_MAX) : ""),
    word_count: row.word_count,
    score: row.score
  }));

  return {
    query: args.query,
    mode_used: "vector",
    degraded: false,
    count: blocks.length,
    manuscript_blocks: blocks,
    citations: blocks.map((block) => ({
      block_id: block.block_id,
      chapter_id: block.chapter_id,
      block_order: block.block_order,
      score: block.score,
      channel: "search_manuscript"
    }))
  };
}

async function acquireLLMLease(db: QueryExecutor, request: AcquireLLMLeaseRequest, ttlSeconds: number): Promise<LLMLease> {
  await deleteExpiredLocks(db, request, "llm_channel", request.channel_id);
  const capacityResult = await queryWithTenantContext<{ max_concurrency?: number | string }>(
    db,
    request,
    `SELECT max_concurrency
       FROM llm_channels
      WHERE channel_id = $1
        AND enabled = TRUE
        AND (tenant_id = $2 OR tenant_id IS NULL)
      ORDER BY tenant_id NULLS LAST
      LIMIT 1`,
    [request.channel_id, request.tenant_id]
  );
  const maxConcurrency = Number(capacityResult.rows[0]?.max_concurrency);
  if (!Number.isInteger(maxConcurrency) || maxConcurrency <= 0) {
    throw new Error("LLM_CHANNEL_UNAVAILABLE: channel concurrency settings are unavailable");
  }

  const channelLock = await acquireLockSlot(db, {
    tenant_id: request.tenant_id,
    project_id: request.project_id,
    run_id: request.run_id,
    resource_type: "llm_channel",
    resource_id: request.channel_id,
    max_concurrency: maxConcurrency,
    ttl_seconds: ttlSeconds
  });
  if (!channelLock) {
    throw new Error("LLM_CONCURRENCY_LIMITED: no LLM channel concurrency slot is available");
  }

  if (!request.module_max_concurrency) {
    return {
      lease_id: channelLock.lease_id,
      channel_id: request.channel_id,
      lock_mode: channelLock.lock_mode
    };
  }

  await deleteExpiredLocks(db, request, "llm_module", request.module_key);
  const moduleLock = await acquireLockSlot(db, {
    tenant_id: request.tenant_id,
    project_id: request.project_id,
    run_id: request.run_id,
    resource_type: "llm_module",
    resource_id: request.module_key,
    max_concurrency: request.module_max_concurrency,
    ttl_seconds: ttlSeconds
  });
  if (!moduleLock) {
    await releaseLock(db, request, channelLock.lease_id);
    throw new Error("LLM_CONCURRENCY_LIMITED: no LLM module concurrency slot is available");
  }

  return {
    lease_id: channelLock.lease_id,
    channel_id: request.channel_id,
    lock_mode: channelLock.lock_mode,
    locks: [channelLock, moduleLock]
  };
}

async function releaseLLMLease(db: QueryExecutor, request: ReleaseLLMLeaseRequest): Promise<void> {
  if (request.locks?.length) {
    for (const lock of request.locks) {
      await releaseLock(db, request, lock.lease_id);
    }
    return;
  }
  await releaseLock(db, request, request.lease_id);
}

async function deleteExpiredLocks(
  db: QueryExecutor,
  request: { tenant_id: string; project_id?: string },
  resourceType: LLMLeaseLock["resource_type"],
  resourceID: string
): Promise<void> {
  await execWithTenantContext(
    db,
    request,
    `DELETE FROM resource_locks
      WHERE tenant_id = $1
        AND resource_type = $2
        AND resource_id = $3
        AND expires_at <= now()`,
    [request.tenant_id, resourceType, resourceID]
  );
}

async function acquireLockSlot(
  db: QueryExecutor,
  request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    resource_type: LLMLeaseLock["resource_type"];
    resource_id: string;
    max_concurrency: number;
    ttl_seconds: number;
  }
): Promise<LLMLeaseLock | null> {
  for (let slot = 0; slot < request.max_concurrency; slot += 1) {
    const lockMode = `slot:${slot}`;
    const result = await queryWithTenantContext<{ lock_id?: string; lock_mode?: string }>(
      db,
      request,
      `INSERT INTO resource_locks (
         tenant_id, resource_type, resource_id, owner_run_id, lock_mode, expires_at
       ) VALUES ($1, $2, $3, $4, $5, now() + ($6::integer * interval '1 second'))
       ON CONFLICT (tenant_id, resource_type, resource_id, lock_mode) DO NOTHING
       RETURNING lock_id, lock_mode`,
      [
        request.tenant_id,
        request.resource_type,
        request.resource_id,
        uuidOrNull(request.run_id),
        lockMode,
        request.ttl_seconds
      ]
    );
    const lockID = result.rows[0]?.lock_id;
    const acquiredMode = result.rows[0]?.lock_mode;
    if (typeof lockID === "string" && typeof acquiredMode === "string") {
      return {
        lease_id: lockID,
        resource_type: request.resource_type,
        resource_id: request.resource_id,
        lock_mode: acquiredMode
      };
    }
  }
  return null;
}

async function releaseLock(db: QueryExecutor, request: { tenant_id: string; project_id?: string }, leaseID: string): Promise<void> {
  await execWithTenantContext(
    db,
    request,
    `DELETE FROM resource_locks
      WHERE lock_id = $1
        AND tenant_id = $2`,
    [leaseID, request.tenant_id]
  );
}

async function findCompletedWriterRun(
  db: QueryExecutor,
  request: FindCompletedWriterRunRequest
): Promise<CompletedWriterRunReplay | undefined> {
  const result = await queryWithTenantContext<Record<string, unknown>>(
    db,
    request,
    `SELECT draft.draft_id::text,
       COALESCE((SELECT SUM(actual_prompt_tokens)::bigint
         FROM llm_quota_reservations
        WHERE tenant_id = writer.tenant_id AND run_id = writer.run_id AND status = 'finalized'), 0) AS prompt_tokens,
       COALESCE((SELECT SUM(actual_completion_tokens)::bigint
         FROM llm_quota_reservations
        WHERE tenant_id = writer.tenant_id AND run_id = writer.run_id AND status = 'finalized'), 0) AS completion_tokens,
       (SELECT CASE
          WHEN COUNT(*) = 0 OR COUNT(actual_cost_micros) <> COUNT(*) THEN NULL
          ELSE SUM(actual_cost_micros)::numeric / 1000000
        END
          FROM llm_quota_reservations
         WHERE tenant_id = writer.tenant_id AND run_id = writer.run_id AND status = 'finalized') AS cost_estimate
      FROM writer_runs AS writer
      JOIN LATERAL (
        SELECT draft_id
          FROM writer_drafts
         WHERE tenant_id = writer.tenant_id AND project_id = writer.project_id AND run_id = writer.run_id
           AND status = 'candidate'
         ORDER BY created_at ASC
         LIMIT 1
      ) AS draft ON TRUE
     WHERE writer.tenant_id = $1::uuid AND writer.project_id = $2::uuid AND writer.run_id = $3::uuid
       AND writer.status = 'completed'
     LIMIT 1`,
    [request.tenant_id, request.project_id, request.run_id]
  );
  const row = result.rows[0];
  if (!row) return undefined;
  const draftID = typeof row.draft_id === "string" ? row.draft_id.trim() : "";
  if (!draftID) throw new Error("WRITER_REPLAY_QUERY_FAILED: completed Writer run has no candidate draft");
  const promptTokens = requiredNonNegativeInteger(row.prompt_tokens, "WRITER_REPLAY_QUERY_FAILED");
  const completionTokens = requiredNonNegativeInteger(row.completion_tokens, "WRITER_REPLAY_QUERY_FAILED");
  const costEstimate = optionalNonNegativeNumber(row.cost_estimate, "WRITER_REPLAY_QUERY_FAILED");
  return {
    draft_id: draftID,
    usage: {
      prompt_tokens: promptTokens,
      completion_tokens: completionTokens,
      ...(costEstimate === undefined ? {} : { cost_estimate: costEstimate })
    }
  };
}

async function appendWriterThreadMessage(db: QueryExecutor, request: AppendWriterThreadMessageRequest): Promise<void> {
  const body = request.body.trim();
  if (!body) {
    return;
  }
  const metadata = request.metadata ?? {};
  await execWithTenantContext(
    db,
    request,
    `WITH ensured AS (
       SELECT thread_id
         FROM writer_threads
        WHERE tenant_id = $1::uuid AND project_id = $2::uuid AND status = 'active'
        ORDER BY updated_at DESC
        LIMIT 1
     ), created AS (
       INSERT INTO writer_threads (tenant_id, project_id, title, status)
       SELECT $1::uuid, $2::uuid, 'Writer thread', 'active'
        WHERE NOT EXISTS (SELECT 1 FROM ensured)
       RETURNING thread_id
     ), thread AS (
       SELECT thread_id FROM ensured
       UNION ALL
       SELECT thread_id FROM created
       LIMIT 1
     ), next_sequence AS (
       SELECT COALESCE(MAX(m.sequence), 0) + 1 AS sequence
         FROM writer_thread_messages m
         JOIN thread ON thread.thread_id = m.thread_id
        WHERE m.tenant_id = $1::uuid AND m.project_id = $2::uuid
     )
     INSERT INTO writer_thread_messages (
       tenant_id, project_id, thread_id, role, body, run_id, sequence, metadata_jsonb
     )
     SELECT $1::uuid, $2::uuid, thread.thread_id, $3, $4, NULLIF($5, '')::uuid, next_sequence.sequence, $6::jsonb
       FROM thread, next_sequence`,
    [
      request.tenant_id,
      request.project_id,
      request.role,
      body,
      request.run_id,
      JSON.stringify(metadata)
    ]
  );
  await execWithTenantContext(
    db,
    request,
    `UPDATE writer_threads
        SET updated_at = now()
      WHERE tenant_id = $1::uuid
        AND project_id = $2::uuid
        AND status = 'active'`,
    [request.tenant_id, request.project_id]
  );
}

async function createWriterApproval(db: QueryExecutor, request: CreateWriterApprovalRequest): Promise<{ approval_id: string }> {
  const result = await queryWithTenantContext<{ approval_id: string }>(
    db,
    request,
    `WITH thread AS (
       SELECT thread_id
         FROM writer_threads
        WHERE tenant_id = $1::uuid AND project_id = $2::uuid AND status = 'active'
        ORDER BY updated_at DESC
        LIMIT 1
     )
     INSERT INTO writer_approvals (
       tenant_id, project_id, run_id, thread_id, status, action, summary, consequence, reversible
     )
     SELECT $1::uuid, $2::uuid, $3::uuid, thread.thread_id, 'pending', $4, $5, COALESCE($6, ''), COALESCE($7, false)
       FROM thread
     RETURNING approval_id::text`,
    [
      request.tenant_id,
      request.project_id,
      request.run_id,
      request.action,
      request.summary,
      request.consequence ?? "",
      request.reversible ?? false
    ]
  );
  const approvalId = result.rows[0]?.approval_id;
  if (typeof approvalId !== "string" || approvalId.trim() === "") {
    throw new Error("WRITER_APPROVAL_CREATE_FAILED: database did not return approval_id");
  }
  return { approval_id: approvalId };
}

async function saveDraftRevision(db: QueryExecutor, request: SaveDraftRevisionRequest): Promise<{ draft_id: string }> {
  const result = await queryWithTenantContext<{ draft_id: string }>(
    db,
    request,
    `WITH locked AS MATERIALIZED (
       SELECT pg_advisory_xact_lock(hashtextextended($1::text || ':' || $2::text, 0))
     ), parent AS (
       SELECT writer_runs.run_id,
              COALESCE(NULLIF($4, '')::uuid, writer_runs.chapter_id) AS chapter_id,
              COALESCE(NULLIF($5, '')::uuid, writer_runs.scene_id) AS scene_id
         FROM writer_runs, locked
        WHERE writer_runs.tenant_id = $1::uuid
          AND writer_runs.run_id = $2::uuid
          AND writer_runs.project_id = $3::uuid
          AND writer_runs.status <> 'cancelled'
          AND (
            COALESCE(writer_runs.options_jsonb->>'source', '') <> 'character_console'
            OR EXISTS (
              SELECT 1
                FROM character_interaction_sessions AS interaction
               WHERE interaction.tenant_id = writer_runs.tenant_id
                 AND interaction.project_id = writer_runs.project_id
                 AND interaction.interaction_id::text = writer_runs.options_jsonb->>'character_interaction_id'
                 AND EXISTS (
                   SELECT 1
                     FROM character_interaction_turns AS turn
                    WHERE turn.tenant_id = interaction.tenant_id
                      AND turn.project_id = interaction.project_id
                      AND turn.interaction_id = interaction.interaction_id
                 )
            )
          )
     ), existing AS (
       SELECT draft_id
         FROM writer_drafts
         JOIN parent ON parent.run_id = writer_drafts.run_id
        WHERE writer_drafts.tenant_id = $1::uuid
          AND writer_drafts.project_id = $3::uuid
        ORDER BY created_at ASC LIMIT 1
     ), inserted AS (
       INSERT INTO writer_drafts (
         tenant_id, run_id, project_id, chapter_id, scene_id,
         content_text, word_count, status
       )
       SELECT $1::uuid, parent.run_id, $3::uuid,
              parent.chapter_id, parent.scene_id,
              $6, $7, $8
       FROM parent
       WHERE NOT EXISTS (SELECT 1 FROM existing)
       RETURNING draft_id
     )
     SELECT draft_id FROM existing
     UNION ALL
     SELECT draft_id FROM inserted
     LIMIT 1`,
    [
      request.tenant_id,
      request.run_id,
      request.project_id,
      request.chapter_id ?? "",
      request.scene_id ?? "",
      request.content,
      wordCount(request.content),
      request.status
    ]
  );
  const draftId = result.rows[0]?.draft_id;
  if (typeof draftId !== "string" || draftId.trim() === "") {
    throw new Error("WRITER_DRAFT_SAVE_FAILED: database did not return draft_id");
  }
  return { draft_id: draftId };
}

async function recordLLMActivity(db: QueryExecutor, request: RecordLLMActivityRequest): Promise<void> {
  const details = request.provider_call_id || request.error
    ? JSON.stringify({
      ...(request.provider_call_id ? { provider_call_id: request.provider_call_id } : {}),
      ...(request.error ? { error: request.error } : {})
    })
    : null;
  await execWithTenantContext(
    db,
    request,
    `INSERT INTO llm_activity (
       tenant_id, project_id, run_id, module_key, channel_id, model_id, status,
       prompt_tokens, completion_tokens, latency_ms, cost_estimate, error_jsonb
     ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12::jsonb)`,
    [
      request.tenant_id,
      request.project_id,
      request.run_id,
      request.module_key,
      request.channel_id,
      request.model_id,
      request.status,
      request.prompt_tokens ?? null,
      request.completion_tokens ?? null,
      request.latency_ms ?? null,
      request.cost_estimate ?? null,
      details
    ]
  );
}

async function recordUsageEvent(db: QueryExecutor, request: RecordUsageEventRequest): Promise<void> {
  await execWithTenantContext(
    db,
    request,
    `INSERT INTO usage_events (
       tenant_id, project_id, run_id, module_key, usage_type, quantity, unit, metadata_jsonb
     ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8::jsonb)`,
    [
      request.tenant_id,
      request.project_id,
      request.run_id,
      request.module_key,
      request.usage_type,
      request.quantity,
      request.unit,
      JSON.stringify(request.metadata)
    ]
  );
}

async function recordAgentTraceEvent(db: QueryExecutor, request: RecordAgentTraceEventRequest): Promise<void> {
  await execWithTenantContext(
    db,
    request,
    `INSERT INTO agent_traces (
       tenant_id, trace_id, run_id, project_id, module_key, agent_name, status
     ) VALUES ($1, $2, $3, $4, $5, $6, $7)
     ON CONFLICT (tenant_id, trace_id) DO UPDATE SET
       status = EXCLUDED.status,
       completed_at = CASE
         WHEN EXCLUDED.status IN ('completed', 'failed') THEN now()
         ELSE agent_traces.completed_at
       END`,
    [
      request.tenant_id,
      request.trace_id,
      request.run_id,
      request.project_id,
      request.module_key,
      request.agent_name,
      request.status
    ]
  );
  await execWithTenantContext(
    db,
    request,
    `INSERT INTO agent_trace_events (
       tenant_id, trace_id, event_order, event_type, payload_jsonb, redaction_level
     ) VALUES ($1, $2, $3, $4, $5::jsonb, $6)
     ON CONFLICT (tenant_id, trace_id, event_order) DO UPDATE SET
       event_type = EXCLUDED.event_type,
       payload_jsonb = EXCLUDED.payload_jsonb,
       redaction_level = EXCLUDED.redaction_level`,
    [
      request.tenant_id,
      request.trace_id,
      request.event_order,
      request.event_type,
      JSON.stringify(request.payload),
      request.redaction_level
    ]
  );
}

async function recordWorkflowEvent(db: QueryExecutor, request: RecordWorkflowEventRequest): Promise<void> {
  const payload = {
    ...sanitizePublicRuntimePayload(request.payload) as Record<string, unknown>,
    ...(request.idempotency_key ? { runtime_event_key: request.idempotency_key } : {})
  };
  const result = await queryWithTenantContext<{ inserted?: number | string }>(
    db,
    request,
    `WITH locked AS MATERIALIZED (
       SELECT pg_advisory_xact_lock(hashtextextended($1::text || ':' || $2::text || ':writer-events', 0))
     ), parent AS (
       SELECT writer_runs.run_id, writer_runs.project_id
       FROM writer_runs
       CROSS JOIN locked
       JOIN workflow_runs
         ON workflow_runs.tenant_id = writer_runs.tenant_id
        AND workflow_runs.run_id = writer_runs.workflow_run_id
        AND workflow_runs.workflow_type = $3
       WHERE writer_runs.tenant_id = $1::uuid
         AND writer_runs.project_id = $4::uuid
         AND writer_runs.run_id = $2::uuid
         AND writer_runs.status <> 'cancelled'
       LIMIT 1
     ),
     next_sequence AS (
       SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence
       FROM workflow_events
       WHERE tenant_id = $1::uuid
         AND run_id = $2::uuid
     ),
     inserted AS (
       INSERT INTO workflow_events (
         tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
       )
       SELECT
         $1::uuid, parent.run_id, $3, parent.project_id, $5,
         next_sequence.sequence,
         $6::jsonb
       FROM parent
       CROSS JOIN next_sequence
       WHERE $7::text IS NULL OR NOT EXISTS (
         SELECT 1 FROM workflow_events existing_event
          WHERE existing_event.tenant_id = $1::uuid
            AND existing_event.run_id = $2::uuid
            AND existing_event.payload_jsonb->>'runtime_event_key' = $7
       )
       RETURNING 1
     )
     SELECT CASE
       WHEN EXISTS (SELECT 1 FROM parent) THEN 1
       ELSE 0
     END AS inserted`,
    [
      request.tenant_id,
      request.run_id,
      request.workflow_type,
      request.project_id,
      request.event_type,
      JSON.stringify(payload),
      request.idempotency_key ?? null
    ]
  );
  if (numericCount(result.rows[0]?.inserted) < 1) {
    throw new Error("WORKFLOW_RUN_NOT_FOUND: writer run admission parent rows are missing");
  }
}

async function updateWriterRunStatus(db: QueryExecutor, request: UpdateWriterRunStatusRequest): Promise<void> {
  const result = await queryWithTenantContext<{ writer_updated?: number | string; workflow_updated?: number | string }>(
    db,
    request,
    `WITH writer_update AS (
       UPDATE writer_runs
          SET status = $4,
              error_code = $6,
              error_message = $7,
              updated_at = now()
        WHERE tenant_id = $1
          AND project_id = $2
          AND run_id = $3
          AND NOT (status = 'cancelled' AND $4 <> 'cancelled')
       RETURNING 1
     ),
     workflow_update AS (
       UPDATE workflow_runs
          SET status = $4,
              progress = CASE WHEN $4 = 'completed' THEN 100 WHEN $4 = 'failed' THEN 100 ELSE progress END,
              result_jsonb = CASE WHEN $5::text IS NULL THEN result_jsonb ELSE jsonb_build_object('draft_id', $5::text) END,
              error_code = $6,
              error_message = $7,
              updated_at = now()
        WHERE tenant_id = $1
          AND project_id = $2
          AND run_id = $3
          AND NOT (status = 'cancelled' AND $4 <> 'cancelled')
       RETURNING 1
     )
     SELECT
       (SELECT COUNT(*) FROM writer_update) AS writer_updated,
       (SELECT COUNT(*) FROM workflow_update) AS workflow_updated`,
    [
      request.tenant_id,
      request.project_id,
      request.run_id,
      request.status,
      request.draft_id ?? null,
      request.error?.code ?? null,
      request.error?.message ?? null
    ]
  );
  const writerUpdated = numericCount(result.rows[0]?.writer_updated);
  const workflowUpdated = numericCount(result.rows[0]?.workflow_updated);
  if (writerUpdated < 1 || workflowUpdated < 1) {
    throw new Error("WORKFLOW_RUN_NOT_FOUND: writer run admission parent rows are missing");
  }
}

function numericCount(value: number | string | undefined): number {
  const parsed = typeof value === "number" ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function requiredNonNegativeInteger(value: unknown, code: string): number {
  const parsed = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  if (!Number.isSafeInteger(parsed) || parsed < 0) {
    throw new Error(`${code}: persisted Writer usage is invalid`);
  }
  return parsed;
}

function optionalNonNegativeNumber(value: unknown, code: string): number | undefined {
  if (value === null || value === undefined) return undefined;
  const parsed = typeof value === "number" ? value : typeof value === "string" ? Number(value) : NaN;
  if (!Number.isFinite(parsed) || parsed < 0) {
    throw new Error(`${code}: persisted Writer cost usage is invalid`);
  }
  return parsed;
}

function sanitizePublicRuntimePayload(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map((item) => sanitizePublicRuntimePayload(item));
  }
  if (value && typeof value === "object") {
    const output: Record<string, unknown> = {};
    for (const [key, nested] of Object.entries(value as Record<string, unknown>)) {
      if (isHighRiskRuntimePayloadKey(key)) {
        continue;
      }
      output[key] = sanitizePublicRuntimePayload(nested);
    }
    return output;
  }
  return value;
}

function isHighRiskRuntimePayloadKey(key: string): boolean {
  const normalized = key.toLowerCase().trim().replace(/[-_\s]/g, "");
  return new Set([
    "apikey",
    "authorization",
    "body",
    "bodytext",
    "candidatebody",
    "candidateeventbody",
    "content",
    "contenttext",
    "credential",
    "credentialref",
    "credentials",
    "draft",
    "encryptedapikey",
    "eventbody",
    "inputtext",
    "manuscript",
    "materialtext",
    "objectkey",
    "outputtext",
    "prompt",
    "rawbody",
    "rawcontent",
    "rawtext",
    "response",
    "sourcematerial",
    "sourceobjectkey",
    "sourcetext",
    "text"
  ]).has(normalized);
}

function decryptAesGcm(envelope: string, key: Buffer): string {
  const [algorithm, version, iv, authTag, ciphertext] = envelope.split(":");
  if (algorithm !== "aes-256-gcm" || version !== "v1" || !iv || !authTag || !ciphertext) {
    throw new Error("unsupported credential cipher");
  }
  const decipher = createDecipheriv("aes-256-gcm", key, Buffer.from(iv, "base64"));
  decipher.setAuthTag(Buffer.from(authTag, "base64"));
  return Buffer.concat([
    decipher.update(Buffer.from(ciphertext, "base64")),
    decipher.final()
  ]).toString("utf8");
}

function parseKeyMaterial(keyMaterial: string): Buffer {
  const trimmed = keyMaterial.trim();
  const key = /^[0-9a-f]{64}$/i.test(trimmed)
    ? Buffer.from(trimmed, "hex")
    : Buffer.from(trimmed, "base64");
  if (key.byteLength !== 32) {
    throw new Error("LLM_CREDENTIAL_KEY_INVALID: expected 32-byte AES key material");
  }
  return key;
}

function wordCount(content: string): number {
  return Array.from(content.trim()).length;
}

function uuidOrNull(value: string): string | null {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value)
    ? value
    : null;
}

function stringOrNull(value: unknown): string | null {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function requiredRowString(row: Record<string, unknown>, key: string): string {
  const value = row[key];
  if (typeof value !== "string" || value.trim() === "") {
    throw new Error("LLM_BINDING_QUERY_FAILED: LLM module binding is incomplete");
  }
  return value;
}

function objectValue(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) return value as Record<string, unknown>;
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
    } catch {
      return {};
    }
  }
  return {};
}

function arrayValue(value: unknown): unknown[] {
  if (Array.isArray(value)) return value;
  if (typeof value === "string") {
    try {
      const parsed = JSON.parse(value);
      return Array.isArray(parsed) ? parsed : [];
    } catch {
      return [];
    }
  }
  return [];
}
