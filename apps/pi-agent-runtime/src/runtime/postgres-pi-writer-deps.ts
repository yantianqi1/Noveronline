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
  SaveDraftRevisionRequest,
  UpdateWriterRunStatusRequest
} from "../activities/pi-writer-activities.js";
import { createPostgresQuotaStore } from "../llm/quota/postgres-quota-store.js";

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

export interface PostgresPiWriterDepsOptions {
  db: QueryExecutor;
  decryptCredential: CredentialDecryptor;
  composeDraft(request: ComposeDraftRequest): Promise<ComposeDraftResult>;
  leaseTtlSeconds?: number;
}

export function createPostgresPiWriterDeps(options: PostgresPiWriterDepsOptions): PiWriterRunActivityDeps {
  const quota = createPostgresQuotaStore(options.db);
  return {
    resolveModuleBinding: async (request) => resolveModuleBinding(options.db, request),
    executeWriterTool: async (request) => executeWriterTool(options.db, request),
    resolveCredential: async (request) => resolveCredential(options, request),
    reserveLLMQuota: async (request) => quota.reserve(request),
    finalizeLLMQuota: async (request) => quota.finalize(request),
    releaseLLMQuota: async (request) => quota.release(request),
    acquireLLMLease: async (request) => acquireLLMLease(options.db, request, options.leaseTtlSeconds ?? 300),
    composeDraft: options.composeDraft,
    releaseLLMLease: async (request) => releaseLLMLease(options.db, request),
    saveDraftRevision: async (request) => saveDraftRevision(options.db, request),
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
  return {
    module_key: request.module_key,
    channel_id: requiredRowString(row, "channel_id"),
    model_id: requiredRowString(row, "model_id"),
    provider: requiredRowString(row, "provider"),
    base_url: requiredRowString(row, "base_url"),
    credential_ref: requiredRowString(row, "credential_ref"),
    supports_tools: row.supports_tools === true,
    supports_json: row.supports_json === true,
    settings: objectValue(row.settings_jsonb)
  };
}

async function executeWriterTool(db: QueryExecutor, request: ExecuteWriterToolRequest): Promise<Record<string, unknown>> {
  switch (request.tool_name) {
    case "query_project_context": {
      const result = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT title, description, genre, language, status
           FROM projects WHERE tenant_id = $1 AND project_id = $2 LIMIT 1`,
        [request.tenant_id, request.project_id]);
      return { project: result.rows[0] ?? null };
    }
    case "query_chapter_scene": {
      const result = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT chapter_id::text, scene_id::text, mode
           FROM writer_runs
          WHERE tenant_id = $1 AND project_id = $2 AND run_id = $3 LIMIT 1`,
        [request.tenant_id, request.project_id, request.run_id]);
      return { target: result.rows[0] ?? { chapter_id: request.chapter_id ?? null, scene_id: request.scene_id ?? null } };
    }
    case "query_assets": {
      const result = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT asset_id::text, asset_type, category, lifecycle, title, summary, content_text, tags_jsonb
           FROM assets
          WHERE tenant_id = $1 AND project_id = $2 AND enabled = TRUE
            AND lifecycle IN ('seed', 'canon', 'material')
            AND ($3::uuid[] = '{}'::uuid[] OR asset_id = ANY($3::uuid[]))
          ORDER BY pinned DESC, updated_at DESC LIMIT 50`,
        [request.tenant_id, request.project_id, request.selected_asset_ids]);
      return { assets: result.rows };
    }
    case "query_world_rules": {
      const result = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT rule_evidence_id::text, rule_text, category, confidence::double precision AS confidence
           FROM world_rule_evidence
          WHERE tenant_id = $1 AND project_id = $2
          ORDER BY created_at DESC
          LIMIT 50`,
        [request.tenant_id, request.project_id]);
      return { rules: result.rows };
    }
    case "query_character_profile": {
      const result = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT entity.entity_id::text, entity.canonical_name, entity.entity_type,
                entity.importance, entity.state_summary,
                COALESCE(
                  jsonb_agg(alias.alias ORDER BY alias.alias)
                    FILTER (WHERE alias.alias_id IS NOT NULL),
                  '[]'::jsonb
                ) AS aliases
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
          LIMIT 50`,
        [request.tenant_id, request.project_id]);
      return { profiles: result.rows };
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
    case "query_worldline_paths": {
      const result = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT path_id::text, title, summary, lifecycle, writer_instruction
           FROM worldline_saved_paths
          WHERE tenant_id = $1 AND project_id = $2
            AND ($3::uuid[] = '{}'::uuid[] OR path_id = ANY($3::uuid[]))
          ORDER BY updated_at DESC LIMIT 20`,
        [request.tenant_id, request.project_id, request.worldline_path_ids]);
      return { paths: result.rows, canon_status: "reference_only" };
    }
    case "query_manuscript_context": {
      const result = await queryWithTenantContext<Record<string, unknown>>(db, request,
        `SELECT block_id::text, chapter_id::text, block_order, content_text, word_count
           FROM manuscript_blocks
          WHERE tenant_id = $1 AND project_id = $2
          ORDER BY block_order DESC LIMIT 20`,
        [request.tenant_id, request.project_id]);
      return { manuscript_blocks: result.rows.reverse() };
    }
    case "save_draft_revision":
      throw new Error("TOOL_PERMISSION_DENIED: draft persistence is runtime-owned");
  }
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

async function saveDraftRevision(db: QueryExecutor, request: SaveDraftRevisionRequest): Promise<{ draft_id: string }> {
  const result = await queryWithTenantContext<{ draft_id: string }>(
    db,
    request,
    `WITH locked AS MATERIALIZED (
       SELECT pg_advisory_xact_lock(hashtextextended($1::text || ':' || $2::text, 0))
     ), parent AS (
       SELECT writer_runs.run_id
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
              NULLIF($4, '')::uuid, NULLIF($5, '')::uuid,
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
