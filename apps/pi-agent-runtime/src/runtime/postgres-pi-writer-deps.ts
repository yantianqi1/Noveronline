import { createDecipheriv } from "node:crypto";

import pg from "pg";

import type {
  ComposeDraftRequest,
  ComposeDraftResult,
  AcquireLLMLeaseRequest,
  CredentialRequest,
  LLMLease,
  LLMLeaseLock,
  PiWriterRunActivityDeps,
  RecordAgentTraceEventRequest,
  RecordLLMActivityRequest,
  RecordWorkflowEventRequest,
  RecordUsageEventRequest,
  ReleaseLLMLeaseRequest,
  SaveDraftRevisionRequest,
  UpdateWriterRunStatusRequest
} from "../activities/pi-writer-activities.js";

export interface QueryExecutor {
  query<T extends Record<string, unknown>>(
    text: string,
    values?: readonly unknown[],
    context?: QueryTenantContext
  ): Promise<{ rows: T[] }>;
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
  return {
    resolveCredential: async (request) => resolveCredential(options, request),
    acquireLLMLease: async (request) => acquireLLMLease(options.db, request, options.leaseTtlSeconds ?? 300),
    composeDraft: options.composeDraft,
    releaseLLMLease: async (request) => releaseLLMLease(options.db, request),
    saveDraftRevision: async (request) => saveDraftRevision(options.db, request),
    recordLLMActivity: async (request) => recordLLMActivity(options.db, request),
    recordUsageEvent: async (request) => recordUsageEvent(options.db, request),
    recordAgentTraceEvent: async (request) => recordAgentTraceEvent(options.db, request),
    recordWorkflowEvent: async (request) => recordWorkflowEvent(options.db, request),
    updateWriterRunStatus: async (request) => updateWriterRunStatus(options.db, request)
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

async function saveDraftRevision(db: QueryExecutor, request: SaveDraftRevisionRequest): Promise<{ draft_id: string }> {
  const result = await queryWithTenantContext<{ draft_id: string }>(
    db,
    request,
    `INSERT INTO writer_drafts (
       tenant_id, run_id, project_id, content_text, word_count, status
     ) VALUES ($1, $2, $3, $4, $5, $6)
     RETURNING draft_id`,
    [
      request.tenant_id,
      request.run_id,
      request.project_id,
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
      request.error ? JSON.stringify(request.error) : null
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
  const result = await queryWithTenantContext<{ inserted?: number | string }>(
    db,
    request,
    `WITH parent AS (
       SELECT writer_runs.run_id, writer_runs.project_id
       FROM writer_runs
       JOIN workflow_runs
         ON workflow_runs.tenant_id = writer_runs.tenant_id
        AND workflow_runs.run_id = writer_runs.workflow_run_id
        AND workflow_runs.workflow_type = $3
       WHERE writer_runs.tenant_id = $1
         AND writer_runs.project_id = $4
         AND writer_runs.run_id = $2
       LIMIT 1
     ),
     next_sequence AS (
       SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence
       FROM workflow_events
       WHERE tenant_id = $1
         AND run_id = $2
     ),
     inserted AS (
       INSERT INTO workflow_events (
         tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
       )
       SELECT
         $1, parent.run_id, $3, parent.project_id, $5,
         next_sequence.sequence,
         $6::jsonb
       FROM parent
       CROSS JOIN next_sequence
       RETURNING 1
     )
     SELECT COUNT(*) AS inserted FROM inserted`,
    [
      request.tenant_id,
      request.run_id,
      request.workflow_type,
      request.project_id,
      request.event_type,
      JSON.stringify(sanitizePublicRuntimePayload(request.payload))
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
