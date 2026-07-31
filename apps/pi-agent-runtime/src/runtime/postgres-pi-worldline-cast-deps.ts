import { createHash, randomUUID } from "node:crypto";

import type {
  PiWorldlineCastDeps,
  PiWorldlineGoalStartActivityResult,
  WorldlineCastLLMResolution
} from "../activities/pi-worldline-cast-activities.js";
import { startWorldlinePreparationWorkflow } from "../activities/pi-worldline-cast-activities.js";
import {
  WORLDLINE_CAST_MODULE_KEY,
  type WorldlineCastCommit,
  type WorldlineCastToolName
} from "../contracts/worldline-cast-run.js";
import { worldlineCastRuntimeContextFromInput } from "../contracts/worldline-cast-run.js";
import { assertWorldlineCastToolAllowed } from "../tools/worldline-cast-permissions.js";
import { effectiveModelCapabilities } from "../llm/model-capabilities.js";
import { createPostgresQuotaStore } from "../llm/quota/postgres-quota-store.js";
import { usageCostMicros, validateProviderUsage } from "../llm/quota/provider-call.js";
import {
  acquireLLMLease as acquirePostgresLLMLease,
  releaseLLMLease as releasePostgresLLMLease
} from "./postgres-pi-writer-deps.js";
import type { CredentialDecryptor, QueryExecutor } from "./postgres-pi-writer-deps.js";

const GOAL_START_WORKFLOW_TYPE = "worldline_goal_start";

export interface PostgresPiWorldlineCastDepsOptions {
  db: QueryExecutor;
  decryptCredential: CredentialDecryptor;
}

export function createPostgresPiWorldlineCastDeps(options: PostgresPiWorldlineCastDepsOptions): PiWorldlineCastDeps {
  const db = options.db;
  const quota = createPostgresQuotaStore(db);
  return {
    resolveModuleBinding: async (request) => resolveModuleBinding(db, request),
    resolveCredential: async (request) => resolveCredential(options, request),
    acquireLLMLease: async (request) => {
      const lease = await acquirePostgresLLMLease(db, request, 300);
      return {
        lease_id: lease.lease_id,
        release: async () => releasePostgresLLMLease(db, { ...request, ...lease })
      };
    },
    reserveQuota: async (request) => {
      const reservation = await quota.reserve(request);
      return {
        reservation_id: reservation.reservation_id,
        status: reservation.status,
        finalize: async (usage) => {
          const normalized = validateProviderUsage(usage);
          await quota.finalize({
            tenant_id: request.tenant_id,
            project_id: request.project_id,
            reservation_id: reservation.reservation_id,
            provider_call_id: request.provider_call_id,
            prompt_tokens: normalized.prompt_tokens,
            completion_tokens: normalized.completion_tokens,
            actual_cost_micros: usageCostMicros(normalized, request.pricing_status),
            pricing_status: request.pricing_status
          });
        },
        release: async () => quota.release({
          tenant_id: request.tenant_id,
          project_id: request.project_id,
          reservation_id: reservation.reservation_id,
          provider_call_id: request.provider_call_id
        })
      };
    },
    executeCastTool: async (request) => executeCastTool(db, request),
    commitCast: async (request) => commitCast(db, request),
    getCommittedCast: async (request) => getCommittedCast(db, request),
    updateGoalStartStatus: async (request) => updateGoalStartStatus(db, request),
    admitPreparation: async (request) => admitPreparation(db, request),
    waitPreparationReady: async (request) => waitPreparationReady(db, request),
    startSession: async (request) => startSession(db, request),
    recordWorkflowEvent: async (request) => recordWorkflowEvent(db, request),
    findReadyGoalStart: async (request) => findReadyGoalStart(db, request),
    startPreparationWorkflow: async (request) => startWorldlinePreparationWorkflow(request)
  };
}

async function resolveModuleBinding(
  db: QueryExecutor,
  request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    module_key: typeof WORLDLINE_CAST_MODULE_KEY;
  }
): Promise<WorldlineCastLLMResolution> {
  const result = await queryWithTenant(db, request, `
SELECT module_key, channel_id::text AS channel_id, model_id,
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
  ) ranked
 ORDER BY binding_rank ASC
 LIMIT 1`, [request.tenant_id, request.project_id, request.module_key]);
  const row = result.rows[0];
  if (!row) {
    throw Object.assign(new Error("LLM_MODULE_UNBOUND: worldline_cast_planner module is not bound"), {
      code: "LLM_MODULE_UNBOUND"
    });
  }
  const supportsTools = Boolean(row.supports_tools);
  const supportsJson = Boolean(row.supports_json);
  const caps = effectiveModelCapabilities(String(row.model_id), supportsJson, supportsTools);
  if (!caps.supports_tools || !caps.supports_json) {
    throw Object.assign(new Error("LLM_MODULE_CAPABILITY_MISSING: worldline_cast_planner binding must support tools and JSON"), {
      code: "LLM_MODULE_CAPABILITY_MISSING"
    });
  }
  return {
    module_key: WORLDLINE_CAST_MODULE_KEY,
    channel_id: String(row.channel_id),
    model_id: String(row.model_id),
    provider: String(row.provider),
    base_url: String(row.base_url),
    credential_ref: String(row.credential_ref),
    supports_tools: supportsTools,
    supports_json: supportsJson,
    settings: (row.settings_jsonb && typeof row.settings_jsonb === "object"
      ? row.settings_jsonb
      : {}) as Record<string, unknown>
  };
}

async function resolveCredential(
  options: PostgresPiWorldlineCastDepsOptions,
  request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    module_key: string;
    channel_id: string;
    credential_ref: string;
  }
): Promise<{ apiKey: string }> {
  const result = await queryWithTenant(options.db, request, `
SELECT encrypted_api_key
  FROM llm_channels
 WHERE channel_id = $1
   AND enabled = TRUE
   AND (tenant_id = $2 OR tenant_id IS NULL)
 ORDER BY tenant_id NULLS LAST
 LIMIT 1`, [request.credential_ref, request.tenant_id]);
  const encryptedApiKey = result.rows[0]?.encrypted_api_key;
  if (typeof encryptedApiKey !== "string" || encryptedApiKey.trim() === "") {
    throw Object.assign(new Error("LLM_CREDENTIAL_UNAVAILABLE: credential reference is not available for tenant"), {
      code: "LLM_CREDENTIAL_UNAVAILABLE"
    });
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

async function executeCastTool(
  db: QueryExecutor,
  request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    tool_name: WorldlineCastToolName;
    args?: Record<string, unknown>;
  }
): Promise<Record<string, unknown>> {
  const context = worldlineCastRuntimeContextFromInput(request);
  assertWorldlineCastToolAllowed(request.tool_name, request.args, context);
  switch (request.tool_name) {
    case "query_project_context": {
      const result = await queryWithTenant(db, request, `
SELECT project_id::text, title AS name, description AS summary, status
  FROM projects
 WHERE tenant_id = $1 AND project_id = $2
 LIMIT 1`, [request.tenant_id, request.project_id]);
      return { project: result.rows[0] ?? null };
    }
    case "query_character_profile": {
      const entities = await queryWithTenant(db, request, `
SELECT entity.entity_id::text AS source_id, 'entity' AS source_kind,
       entity.canonical_name AS title, entity.entity_type, entity.state_summary AS summary
  FROM entities AS entity
 WHERE entity.tenant_id = $1 AND entity.project_id = $2
   AND entity.entity_type = 'character'
 ORDER BY entity.updated_at DESC
 LIMIT 40`, [request.tenant_id, request.project_id]);
      const assets = await queryWithTenant(db, request, `
SELECT asset_id::text AS source_id, 'asset' AS source_kind,
       title, asset_type AS entity_type,
       COALESCE(summary, left(COALESCE(content_text, ''), 400)) AS summary
  FROM assets
 WHERE tenant_id = $1 AND project_id = $2
   AND enabled = TRUE
   AND lifecycle IN ('seed', 'canon', 'material')
   AND asset_type IN ('character', 'seed_character')
 ORDER BY pinned DESC, updated_at DESC
 LIMIT 40`, [request.tenant_id, request.project_id]);
      const nodes = await queryWithTenant(db, request, `
SELECT node_id::text AS source_id, 'entity' AS source_kind,
       title, node_type AS entity_type, summary
  FROM story_graph_nodes
 WHERE tenant_id = $1 AND project_id = $2
   AND lifecycle <> 'archived'
   AND node_type IN ('character', 'organization', 'location')
 ORDER BY updated_at DESC
 LIMIT 60`, [request.tenant_id, request.project_id]);
      return {
        profiles: [...entities.rows, ...assets.rows, ...nodes.rows].slice(0, 80)
      };
    }
    case "query_assets": {
      const result = await queryWithTenant(db, request, `
SELECT asset_id::text AS source_id, 'asset' AS source_kind,
       title, asset_type, lifecycle,
       COALESCE(summary, left(COALESCE(content_text, ''), 400)) AS summary
  FROM assets
 WHERE tenant_id = $1 AND project_id = $2
   AND enabled = TRUE
   AND lifecycle IN ('seed', 'canon', 'material')
 ORDER BY pinned DESC, updated_at DESC
 LIMIT 50`, [request.tenant_id, request.project_id]);
      return { assets: result.rows };
    }
    case "query_graph_neighbors": {
      const nodeIds = Array.isArray(request.args?.graph_node_ids)
        ? request.args.graph_node_ids.filter((value): value is string => typeof value === "string" && value.trim() !== "")
        : [];
      if (nodeIds.length === 0) {
        return { nodes: [], neighbors: [] };
      }
      const result = await queryWithTenant(db, request, `
WITH selected AS (
  SELECT node_id, node_type, title, summary, lifecycle
    FROM story_graph_nodes
   WHERE tenant_id = $1 AND project_id = $2
     AND node_id = ANY($3::uuid[])
), neighboring AS (
  SELECT selected.node_id AS selected_node_id,
         neighbor.node_id::text AS neighbor_id, neighbor.node_type, neighbor.title, neighbor.summary,
         edge.edge_type, COALESCE(edge.label, edge.edge_type) AS relationship
    FROM selected
    JOIN story_graph_edges edge
      ON edge.tenant_id = $1 AND edge.project_id = $2
     AND (edge.source_node_id = selected.node_id OR edge.target_node_id = selected.node_id)
    JOIN story_graph_nodes neighbor
      ON neighbor.tenant_id = edge.tenant_id AND neighbor.project_id = edge.project_id
     AND neighbor.node_id = CASE WHEN edge.source_node_id = selected.node_id THEN edge.target_node_id ELSE edge.source_node_id END
   ORDER BY edge.weight DESC
   LIMIT 100
)
SELECT
  COALESCE((SELECT jsonb_agg(to_jsonb(selected)) FROM selected), '[]'::jsonb) AS nodes,
  COALESCE((SELECT jsonb_agg(to_jsonb(neighboring)) FROM neighboring), '[]'::jsonb) AS neighbors`,
      [request.tenant_id, request.project_id, nodeIds]);
      const row = result.rows[0] ?? {};
      return {
        nodes: Array.isArray(row.nodes) ? row.nodes : [],
        neighbors: Array.isArray(row.neighbors) ? row.neighbors : []
      };
    }
    case "commit_worldline_cast":
      throw Object.assign(new Error("commit_worldline_cast is handled by the activity runtime"), {
        code: "WORLDLINE_CAST_INVALID"
      });
    default:
      throw Object.assign(new Error(`unsupported cast tool: ${request.tool_name}`), {
        code: "TOOL_PERMISSION_DENIED"
      });
  }
}

async function commitCast(
  db: QueryExecutor,
  request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    cast: WorldlineCastCommit;
  }
): Promise<WorldlineCastCommit> {
  await queryWithTenant(db, request, `
UPDATE worldline_goal_starts
   SET agent_refs_jsonb = $3::jsonb,
       source_refs_jsonb = $4::jsonb,
       rationale = $5,
       updated_at = now()
 WHERE tenant_id = $1::uuid
   AND project_id = $2::uuid
   AND run_id = $6::uuid
   AND status IN ('queued', 'casting', 'preparing')`, [
    request.tenant_id,
    request.project_id,
    JSON.stringify(request.cast.agent_refs),
    JSON.stringify(request.cast.source_refs),
    request.cast.rationale,
    request.run_id
  ]);
  return request.cast;
}

async function getCommittedCast(
  db: QueryExecutor,
  request: { tenant_id: string; project_id: string; run_id: string }
): Promise<WorldlineCastCommit | null> {
  const result = await queryWithTenant(db, request, `
SELECT agent_refs_jsonb, source_refs_jsonb, rationale
  FROM worldline_goal_starts
 WHERE tenant_id = $1::uuid AND project_id = $2::uuid AND run_id = $3::uuid
 LIMIT 1`, [request.tenant_id, request.project_id, request.run_id]);
  const row = result.rows[0];
  if (!row) return null;
  const agentRefs = Array.isArray(row.agent_refs_jsonb) ? row.agent_refs_jsonb : [];
  if (agentRefs.length < 1) return null;
  return {
    agent_refs: agentRefs as WorldlineCastCommit["agent_refs"],
    source_refs: (Array.isArray(row.source_refs_jsonb) ? row.source_refs_jsonb : []) as WorldlineCastCommit["source_refs"],
    rationale: typeof row.rationale === "string" ? row.rationale : ""
  };
}

async function updateGoalStartStatus(
  db: QueryExecutor,
  request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    status: "casting" | "preparing" | "starting" | "ready" | "failed";
    prepare_id?: string;
    session_id?: string;
    error_code?: string;
    error_message?: string;
    result?: Record<string, unknown>;
  }
): Promise<void> {
  const workflowStatus = request.status === "ready"
    ? "completed"
    : request.status === "failed"
      ? "failed"
      : "running";
  await queryWithTenant(db, request, `
WITH goal_update AS (
  UPDATE worldline_goal_starts
     SET status = $4,
         prepare_id = COALESCE(NULLIF($5, '')::uuid, prepare_id),
         session_id = COALESCE(NULLIF($6, '')::uuid, session_id),
         error_code = CASE WHEN $4 = 'failed' THEN $7 ELSE NULL END,
         error_message = CASE WHEN $4 = 'failed' THEN $8 ELSE NULL END,
         result_jsonb = CASE
           WHEN $9::text IS NULL OR $9::text = '' THEN result_jsonb
           ELSE COALESCE(result_jsonb, '{}'::jsonb) || $9::jsonb
         END,
         updated_at = now()
   WHERE tenant_id = $1::uuid AND project_id = $2::uuid AND run_id = $3::uuid
  RETURNING workflow_run_id
)
UPDATE workflow_runs
   SET status = $10,
       progress = CASE
         WHEN $4 = 'casting' THEN GREATEST(progress, 10)
         WHEN $4 = 'preparing' THEN GREATEST(progress, 40)
         WHEN $4 = 'starting' THEN GREATEST(progress, 75)
         WHEN $4 = 'ready' THEN 100
         WHEN $4 = 'failed' THEN 100
         ELSE progress
       END,
       message = $4,
       error_code = CASE WHEN $4 = 'failed' THEN $7 ELSE NULL END,
       error_message = CASE WHEN $4 = 'failed' THEN $8 ELSE NULL END,
       updated_at = now()
 WHERE tenant_id = $1::uuid
   AND project_id = $2::uuid
   AND run_id = COALESCE((SELECT workflow_run_id FROM goal_update), $3::uuid)`, [
    request.tenant_id,
    request.project_id,
    request.run_id,
    request.status,
    request.prepare_id ?? "",
    request.session_id ?? "",
    request.error_code ?? null,
    request.error_message ?? null,
    request.result ? JSON.stringify(request.result) : null,
    workflowStatus
  ]);
}

async function admitPreparation(
  db: QueryExecutor,
  request: {
    tenant_id: string;
    project_id: string;
    actor_user_id: string;
    request_id: string;
    goal: string;
    anchor_path_id?: string;
    agent_refs: WorldlineCastCommit["agent_refs"];
    source_refs: WorldlineCastCommit["source_refs"];
  }
): Promise<{ prepare_id: string; run_id: string; temporal_workflow_id: string }> {
	const existing = await queryWithTenant(db, request, `
SELECT preparation.prepare_id::text, preparation.run_id::text, workflow.temporal_workflow_id
  FROM worldline_preparations preparation
  JOIN workflow_runs workflow
    ON workflow.tenant_id = preparation.tenant_id AND workflow.run_id = preparation.run_id
  JOIN workflow_events event
    ON event.tenant_id = workflow.tenant_id AND event.run_id = workflow.run_id
   AND event.event_type = 'workflow.queued'
 WHERE preparation.tenant_id = $1::uuid AND preparation.project_id = $2::uuid
   AND event.payload_jsonb->>'request_id' = $3
 LIMIT 1`, [request.tenant_id, request.project_id, request.request_id]);
	if (existing.rows[0]) {
		return {
			prepare_id: String(existing.rows[0].prepare_id),
			run_id: String(existing.rows[0].run_id),
			temporal_workflow_id: String(existing.rows[0].temporal_workflow_id)
		};
	}
	const runId = stableUUID(`${request.tenant_id}:${request.project_id}:${request.request_id}:preparation-run`);
	const prepareId = stableUUID(`${request.tenant_id}:${request.project_id}:${request.request_id}:preparation`);
	const eventId = stableUUID(`${request.tenant_id}:${request.project_id}:${request.request_id}:preparation-event`);
  const temporalWorkflowId = `worldline_preparation_${runId}`;
  const options = {
    agent_refs: request.agent_refs,
    ...(request.source_refs.length > 0 ? { source_refs: request.source_refs } : {}),
    source: "worldline_goal_start"
  };
  const payload = {
    status: "queued",
    workflow_type: "worldline_preparation",
    request_id: request.request_id,
    trace_id: `trace_${runId}`,
    prepare_id: prepareId,
    anchor_path_id: request.anchor_path_id ?? "",
    agent_ref_count: request.agent_refs.length,
    source_ref_count: request.source_refs.length,
    options
  };
  await queryWithTenant(db, request, `
WITH workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id, run_id, workflow_type, project_id, status, progress, message,
    started_by, temporal_workflow_id
  )
  VALUES (
    $1::uuid, $3::uuid, 'worldline_preparation', $2::uuid, 'queued', 0,
    'queued', NULLIF($7, '')::uuid, $8
  )
  ON CONFLICT (run_id) DO NOTHING
  RETURNING tenant_id, run_id, project_id
), preparation_insert AS (
  INSERT INTO worldline_preparations (
    tenant_id, prepare_id, project_id, run_id, status, lifecycle,
    goal_summary, anchor_path_id, created_by
  )
  SELECT
    workflow_insert.tenant_id, $4::uuid, workflow_insert.project_id,
    workflow_insert.run_id, 'queued', 'preparing', $5,
    NULLIF($6, '')::uuid, NULLIF($7, '')::uuid
  FROM workflow_insert
  RETURNING tenant_id, prepare_id, project_id, run_id
)
INSERT INTO workflow_events (
  tenant_id, event_id, run_id, workflow_type, project_id, event_type,
  sequence, payload_jsonb
)
SELECT
  preparation_insert.tenant_id, $9::uuid, preparation_insert.run_id,
  'worldline_preparation', preparation_insert.project_id, 'workflow.queued',
  1, $10::jsonb
FROM preparation_insert`, [
    request.tenant_id,
    request.project_id,
    runId,
    prepareId,
    request.goal,
    request.anchor_path_id ?? "",
    request.actor_user_id,
    temporalWorkflowId,
    eventId,
    JSON.stringify(payload)
  ]);
  return { prepare_id: prepareId, run_id: runId, temporal_workflow_id: temporalWorkflowId };
}

async function waitPreparationReady(
  db: QueryExecutor,
  request: {
    tenant_id: string;
    project_id: string;
    prepare_id: string;
    timeout_ms?: number;
    abort_signal?: AbortSignal;
  }
): Promise<{ status: "completed" | "failed"; error_message?: string }> {
  const timeoutMs = request.timeout_ms ?? 30 * 60 * 1000;
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
	if (request.abort_signal?.aborted) {
		throw new Error("WORKFLOW_CANCELLED: worldline preparation wait was cancelled");
	}
    const result = await queryWithTenant(db, request, `
SELECT status, lifecycle
  FROM worldline_preparations
 WHERE tenant_id = $1::uuid AND project_id = $2::uuid AND prepare_id = $3::uuid
 LIMIT 1`, [request.tenant_id, request.project_id, request.prepare_id]);
    const row = result.rows[0];
    if (!row) {
      return { status: "failed", error_message: "worldline preparation disappeared" };
    }
    if (row.status === "completed" && row.lifecycle === "ready") {
      return { status: "completed" };
    }
    if (row.status === "failed" || row.status === "cancelled") {
      return { status: "failed", error_message: `worldline preparation ${String(row.status)}` };
    }
	await sleep(2000, request.abort_signal);
  }
  return { status: "failed", error_message: "worldline preparation timed out" };
}

async function startSession(
  db: QueryExecutor,
  request: {
    tenant_id: string;
    project_id: string;
    actor_user_id: string;
    request_id: string;
    goal: string;
    anchor_path_id?: string;
    prepare_id: string;
  }
): Promise<{ session_id: string; run_id: string }> {
	const existing = await queryWithTenant(db, request, `
SELECT session.session_id::text, session.run_id::text
  FROM worldline_sessions session
  JOIN workflow_events event
    ON event.tenant_id = session.tenant_id AND event.run_id = session.run_id
   AND event.event_type = 'workflow.queued'
 WHERE session.tenant_id = $1::uuid AND session.project_id = $2::uuid
   AND event.payload_jsonb->>'request_id' = $3
 LIMIT 1`, [request.tenant_id, request.project_id, request.request_id]);
	if (existing.rows[0]) {
		return { session_id: String(existing.rows[0].session_id), run_id: String(existing.rows[0].run_id) };
	}
	const runId = stableUUID(`${request.tenant_id}:${request.project_id}:${request.request_id}:session-run`);
	const sessionId = stableUUID(`${request.tenant_id}:${request.project_id}:${request.request_id}:session`);
	const eventId = stableUUID(`${request.tenant_id}:${request.project_id}:${request.request_id}:session-event`);
  const eventPayload = {
    status: "queued",
    workflow_type: "worldline_session",
    request_id: request.request_id,
    trace_id: `trace_${runId}`,
    session_id: sessionId,
    anchor_path_id: request.anchor_path_id ?? "",
    options: { prepare_id: request.prepare_id, source: "worldline_goal_start" }
  };
  await queryWithTenant(db, request, `
WITH workflow_insert AS (
  INSERT INTO workflow_runs (
    tenant_id, run_id, workflow_type, project_id, status, progress, message,
    started_by, temporal_workflow_id
  )
  VALUES (
    $1::uuid, $3::uuid, 'worldline_session', $2::uuid, 'queued', 0,
    'queued', NULLIF($6, '')::uuid, ''
  )
  ON CONFLICT (run_id) DO NOTHING
  RETURNING run_id
),
session_insert AS (
  INSERT INTO worldline_sessions (
    tenant_id, session_id, project_id, run_id, status, lifecycle,
    goal_summary, anchor_path_id, created_by
  )
  SELECT
    $1::uuid, $4::uuid, $2::uuid, workflow_insert.run_id, 'queued', 'active',
    $5, NULLIF($7, '')::uuid, NULLIF($6, '')::uuid
  FROM workflow_insert
  RETURNING session_id, run_id, project_id
)
INSERT INTO workflow_events (
  tenant_id, event_id, run_id, workflow_type, project_id, event_type,
  sequence, payload_jsonb
)
SELECT
  $1::uuid, $8::uuid, session_insert.run_id, 'worldline_session',
  session_insert.project_id, 'workflow.queued', 1, $9::jsonb
FROM session_insert`, [
    request.tenant_id,
    request.project_id,
    runId,
    sessionId,
    request.goal,
    request.actor_user_id,
    request.anchor_path_id ?? "",
    eventId,
    JSON.stringify(eventPayload)
  ]);
  return { session_id: sessionId, run_id: runId };
}

async function recordWorkflowEvent(
  db: QueryExecutor,
  request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    event_type: string;
    payload: Record<string, unknown>;
    idempotency_key?: string;
  }
): Promise<void> {
  const payload = {
    ...sanitizePublicPayload(request.payload),
    ...(request.idempotency_key ? { runtime_event_key: request.idempotency_key } : {})
  };
  await queryWithTenant(db, request, `
WITH locked AS MATERIALIZED (
  SELECT pg_advisory_xact_lock(hashtextextended($1::text || ':' || $2::text || ':worldline-goal-start-events', 0))
), parent AS (
  SELECT goal_start.run_id, goal_start.project_id, goal_start.workflow_run_id
  FROM worldline_goal_starts goal_start
  CROSS JOIN locked
  WHERE goal_start.tenant_id = $1::uuid
    AND goal_start.project_id = $3::uuid
    AND goal_start.run_id = $2::uuid
  LIMIT 1
),
next_sequence AS (
  SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence
  FROM workflow_events
  WHERE tenant_id = $1::uuid
    AND run_id = COALESCE((SELECT workflow_run_id FROM parent), $2::uuid)
)
INSERT INTO workflow_events (
  tenant_id, run_id, workflow_type, project_id, event_type, sequence, payload_jsonb
)
SELECT
  $1::uuid,
  COALESCE(parent.workflow_run_id, parent.run_id),
  $4,
  parent.project_id,
  $5,
  next_sequence.sequence,
  $6::jsonb
FROM parent
CROSS JOIN next_sequence
WHERE $7::text IS NULL OR NOT EXISTS (
  SELECT 1 FROM workflow_events existing_event
   WHERE existing_event.tenant_id = $1::uuid
     AND existing_event.run_id = COALESCE(parent.workflow_run_id, parent.run_id)
     AND existing_event.payload_jsonb->>'runtime_event_key' = $7
)`, [
    request.tenant_id,
    request.run_id,
    request.project_id,
    GOAL_START_WORKFLOW_TYPE,
    request.event_type,
    JSON.stringify(payload),
    request.idempotency_key ?? null
  ]);
}

async function findReadyGoalStart(
  db: QueryExecutor,
  request: { tenant_id: string; project_id: string; run_id: string }
): Promise<PiWorldlineGoalStartActivityResult | null> {
  const result = await queryWithTenant(db, request, `
SELECT status, COALESCE(prepare_id::text, '') AS prepare_id,
       COALESCE(session_id::text, '') AS session_id,
       jsonb_array_length(agent_refs_jsonb) AS agent_ref_count,
       jsonb_array_length(source_refs_jsonb) AS source_ref_count
  FROM worldline_goal_starts
 WHERE tenant_id = $1::uuid AND project_id = $2::uuid AND run_id = $3::uuid
 LIMIT 1`, [request.tenant_id, request.project_id, request.run_id]);
  const row = result.rows[0];
  if (!row || row.status !== "ready") return null;
  return {
    tenant_id: request.tenant_id,
    project_id: request.project_id,
    run_id: request.run_id,
    status: "ready",
    prepare_id: String(row.prepare_id || "") || undefined,
    session_id: String(row.session_id || "") || undefined,
    agent_ref_count: Number(row.agent_ref_count ?? 0),
    source_ref_count: Number(row.source_ref_count ?? 0)
  };
}

async function queryWithTenant(
  db: QueryExecutor,
  request: { tenant_id: string; project_id?: string },
  text: string,
  values: readonly unknown[] = []
): Promise<{ rows: Array<Record<string, unknown>> }> {
  return db.query(text, values, {
    tenant_id: request.tenant_id,
    project_id: request.project_id
  });
}

function sanitizePublicPayload(payload: Record<string, unknown>): Record<string, unknown> {
  const blocked = new Set([
    "api_key", "credential_ref", "prompt", "raw_body", "encrypted_api_key", "response"
  ]);
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(payload)) {
    if (blocked.has(key.toLowerCase())) continue;
    out[key] = value;
  }
  return out;
}

function stableUUID(value: string): string {
  const hex = createHash("sha256").update(value).digest("hex").slice(0, 32).split("");
  hex[12] = "5";
  hex[16] = ((Number.parseInt(hex[16] ?? "0", 16) & 0x3) | 0x8).toString(16);
  return `${hex.slice(0, 8).join("")}-${hex.slice(8, 12).join("")}-${hex.slice(12, 16).join("")}-${hex.slice(16, 20).join("")}-${hex.slice(20).join("")}`;
}

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new Error("WORKFLOW_CANCELLED: worldline preparation wait was cancelled"));
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new Error("WORKFLOW_CANCELLED: worldline preparation wait was cancelled"));
    }, { once: true });
  });
}
