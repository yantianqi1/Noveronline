import { randomUUID } from "node:crypto";

import type { AgentEvent, ToolExecutionMode } from "@earendil-works/pi-agent-core";
import { Connection, Client } from "@temporalio/client";

import {
  WORLDLINE_CAST_MODULE_KEY,
  WORLDLINE_CAST_TOOLS,
  type WorldlineCastCommit,
  type WorldlineCastToolName,
  type WorldlineGoalStartInput
} from "../contracts/worldline-cast-run.js";
import { validateWorldlineGoalStartPayload } from "../contracts/worldline-cast-worker-spec.js";
import type { WorldlineCastStageRequest, WorldlineCastStageResult } from "../runtime/pi-worldline-cast-agent.js";

export interface PiWorldlineCastUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
  cost_estimate?: number;
}

export interface PiWorldlineGoalStartActivityResult {
  tenant_id: string;
  project_id: string;
  run_id: string;
  status: "ready" | "failed";
  prepare_id?: string;
  session_id?: string;
  agent_ref_count?: number;
  source_ref_count?: number;
  usage?: PiWorldlineCastUsage;
  error?: {
    code: string;
    message: string;
  };
}

export interface WorldlineCastLLMResolution {
  module_key: typeof WORLDLINE_CAST_MODULE_KEY;
  channel_id: string;
  model_id: string;
  provider: string;
  base_url: string;
  credential_ref: string;
  supports_tools: boolean;
  supports_json: boolean;
  settings: Record<string, unknown>;
}

export interface PiWorldlineCastDeps {
  resolveModuleBinding?(request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    module_key: typeof WORLDLINE_CAST_MODULE_KEY;
  }): Promise<WorldlineCastLLMResolution>;
  resolveCredential?(request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    module_key: string;
    channel_id: string;
    credential_ref: string;
  }): Promise<{ apiKey: string }>;
  acquireLLMLease?(request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    module_key: string;
    channel_id: string;
    model_id: string;
  }): Promise<{ lease_id: string; release(): Promise<void> }>;
  reserveQuota?(request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    module_key: string;
    provider_call_id: string;
    estimated_tokens: number;
  }): Promise<{ reservation_id: string; finalize(usage: PiWorldlineCastUsage): Promise<void> }>;
  runCastStage?(request: WorldlineCastStageRequest): Promise<WorldlineCastStageResult>;
  executeCastTool?(request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    tool_name: WorldlineCastToolName;
    args?: Record<string, unknown>;
  }): Promise<Record<string, unknown>>;
  commitCast?(request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    cast: WorldlineCastCommit;
  }): Promise<WorldlineCastCommit>;
  getCommittedCast?(request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
  }): Promise<WorldlineCastCommit | null>;
  updateGoalStartStatus?(request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    status: "casting" | "preparing" | "starting" | "ready" | "failed";
    prepare_id?: string;
    session_id?: string;
    error_code?: string;
    error_message?: string;
    result?: Record<string, unknown>;
  }): Promise<void>;
  admitPreparation?(request: {
    tenant_id: string;
    project_id: string;
    actor_user_id: string;
    request_id: string;
    goal: string;
    anchor_path_id?: string;
    agent_refs: WorldlineCastCommit["agent_refs"];
    source_refs: WorldlineCastCommit["source_refs"];
  }): Promise<{ prepare_id: string; run_id: string; temporal_workflow_id: string }>;
  waitPreparationReady?(request: {
    tenant_id: string;
    project_id: string;
    prepare_id: string;
    timeout_ms?: number;
  }): Promise<{ status: "completed" | "failed"; error_message?: string }>;
  startSession?(request: {
    tenant_id: string;
    project_id: string;
    actor_user_id: string;
    request_id: string;
    goal: string;
    anchor_path_id?: string;
    prepare_id: string;
  }): Promise<{ session_id: string; run_id: string }>;
  recordWorkflowEvent?(event: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    event_type: string;
    payload: Record<string, unknown>;
    idempotency_key?: string;
  }): Promise<void>;
  findReadyGoalStart?(request: {
    tenant_id: string;
    project_id: string;
    run_id: string;
  }): Promise<PiWorldlineGoalStartActivityResult | null>;
  startPreparationWorkflow?(request: {
    temporal_workflow_id: string;
    prepare_id: string;
    run_id: string;
    tenant_id: string;
    project_id: string;
    actor_user_id: string;
    request_id: string;
  }): Promise<void>;
  cancellationSignal?(): AbortSignal | undefined;
}

export function createPiWorldlineGoalStartActivity(deps: PiWorldlineCastDeps = {}) {
  return async function runPiWorldlineGoalStartActivity(payload: unknown): Promise<PiWorldlineGoalStartActivityResult> {
    const input = validateWorldlineGoalStartPayload(payload);
    const record = async (
      event_type: string,
      eventPayload: Record<string, unknown>,
      idempotency_key?: string
    ) => {
      await deps.recordWorkflowEvent?.({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        event_type,
        payload: eventPayload,
        idempotency_key
      });
    };

    try {
      const ready = await deps.findReadyGoalStart?.({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id
      });
      if (ready) return ready;

      await deps.updateGoalStartStatus?.({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "casting"
      });
      await record("worldline.goal_start.started", { status: "casting" }, "run:started");
      await record("worldline.goal_start.stage.started", { stage: "cast", status: "running" }, "stage:cast:started");

      const cast = await runCast(deps, input);
      await record("worldline.goal_start.cast.committed", {
        agent_ref_count: cast.agent_refs.length,
        source_ref_count: cast.source_refs.length,
        rationale: cast.rationale.slice(0, 500)
      }, "cast:committed");
      await record("worldline.goal_start.stage.completed", {
        stage: "cast",
        status: "completed",
        agent_ref_count: cast.agent_refs.length
      }, "stage:cast:completed");

      await deps.updateGoalStartStatus?.({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "preparing",
        result: { rationale: cast.rationale }
      });
      await record("worldline.goal_start.stage.started", { stage: "prepare", status: "running" }, "stage:prepare:started");

      if (!deps.admitPreparation || !deps.startPreparationWorkflow || !deps.waitPreparationReady) {
        throw Object.assign(new Error("WORLDLINE_CAST_RUNTIME_UNCONFIGURED: preparation chaining is unavailable"), {
          code: "WORLDLINE_CAST_RUNTIME_UNCONFIGURED"
        });
      }
      const preparation = await deps.admitPreparation({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        actor_user_id: input.requested_by,
        request_id: `goal-start-prepare:${input.run_id}`,
        goal: input.goal,
        anchor_path_id: input.anchor_path_id,
        agent_refs: cast.agent_refs,
        source_refs: cast.source_refs
      });
      await deps.updateGoalStartStatus?.({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "preparing",
        prepare_id: preparation.prepare_id
      });
      await deps.startPreparationWorkflow({
        temporal_workflow_id: preparation.temporal_workflow_id,
        prepare_id: preparation.prepare_id,
        run_id: preparation.run_id,
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        actor_user_id: input.requested_by,
        request_id: `goal-start-prepare:${input.run_id}`
      });
      const prepareResult = await deps.waitPreparationReady({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        prepare_id: preparation.prepare_id,
        timeout_ms: 30 * 60 * 1000
      });
      if (prepareResult.status !== "completed") {
        throw Object.assign(new Error(prepareResult.error_message || "worldline preparation failed"), {
          code: "WORLDLINE_PREPARATION_FAILED"
        });
      }
      await record("worldline.goal_start.stage.completed", {
        stage: "prepare",
        status: "completed",
        prepare_id: preparation.prepare_id
      }, "stage:prepare:completed");

      await deps.updateGoalStartStatus?.({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "starting",
        prepare_id: preparation.prepare_id
      });
      await record("worldline.goal_start.stage.started", { stage: "session", status: "running" }, "stage:session:started");
      if (!deps.startSession) {
        throw Object.assign(new Error("WORLDLINE_CAST_RUNTIME_UNCONFIGURED: session start is unavailable"), {
          code: "WORLDLINE_CAST_RUNTIME_UNCONFIGURED"
        });
      }
      const session = await deps.startSession({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        actor_user_id: input.requested_by,
        request_id: `goal-start-session:${input.run_id}`,
        goal: input.goal,
        anchor_path_id: input.anchor_path_id,
        prepare_id: preparation.prepare_id
      });
      await deps.updateGoalStartStatus?.({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "ready",
        prepare_id: preparation.prepare_id,
        session_id: session.session_id,
        result: {
          rationale: cast.rationale,
          prepare_id: preparation.prepare_id,
          session_id: session.session_id,
          agent_ref_count: cast.agent_refs.length,
          source_ref_count: cast.source_refs.length
        }
      });
      await record("worldline.goal_start.stage.completed", {
        stage: "session",
        status: "completed",
        session_id: session.session_id
      }, "stage:session:completed");
      await record("worldline.goal_start.completed", {
        status: "ready",
        prepare_id: preparation.prepare_id,
        session_id: session.session_id,
        agent_ref_count: cast.agent_refs.length,
        source_ref_count: cast.source_refs.length
      }, "run:completed");

      return {
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "ready",
        prepare_id: preparation.prepare_id,
        session_id: session.session_id,
        agent_ref_count: cast.agent_refs.length,
        source_ref_count: cast.source_refs.length
      };
    } catch (error) {
      const code = errorCode(error);
      const message = error instanceof Error ? error.message : "worldline goal-start failed";
      await deps.updateGoalStartStatus?.({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "failed",
        error_code: code,
        error_message: publicErrorMessage(code, message)
      });
      await record("worldline.goal_start.failed", {
        status: "failed",
        error_code: code,
        error_message: publicErrorMessage(code, message)
      }, "run:failed");
      return {
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "failed",
        error: { code, message: publicErrorMessage(code, message) }
      };
    }
  };
}

export async function runPiWorldlineGoalStartActivity(payload: unknown): Promise<PiWorldlineGoalStartActivityResult> {
  return createPiWorldlineGoalStartActivity()(payload);
}

async function runCast(deps: PiWorldlineCastDeps, input: WorldlineGoalStartInput): Promise<WorldlineCastCommit> {
  if (!deps.resolveModuleBinding || !deps.resolveCredential || !deps.runCastStage || !deps.executeCastTool || !deps.commitCast) {
    throw Object.assign(new Error("WORLDLINE_CAST_RUNTIME_UNCONFIGURED: cast planner runtime is unavailable"), {
      code: "WORLDLINE_CAST_RUNTIME_UNCONFIGURED"
    });
  }
  const resolution = await deps.resolveModuleBinding({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    module_key: WORLDLINE_CAST_MODULE_KEY
  });
  const credential = await deps.resolveCredential({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    module_key: WORLDLINE_CAST_MODULE_KEY,
    channel_id: resolution.channel_id,
    credential_ref: resolution.credential_ref
  });
  const providerCallId = `worldline-cast:${input.run_id}:${randomUUID()}`;
  const lease = await deps.acquireLLMLease?.({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    module_key: WORLDLINE_CAST_MODULE_KEY,
    channel_id: resolution.channel_id,
    model_id: resolution.model_id
  });
  const reservation = await deps.reserveQuota?.({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    module_key: WORLDLINE_CAST_MODULE_KEY,
    provider_call_id: providerCallId,
    estimated_tokens: 8000
  });
  try {
    await deps.runCastStage({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      module_key: WORLDLINE_CAST_MODULE_KEY,
      channel_id: resolution.channel_id,
      model_id: resolution.model_id,
      provider: resolution.provider,
      base_url: resolution.base_url,
      apiKey: credential.apiKey,
      goal: input.goal,
      thinking_level: input.options.thinking_level,
      tool_execution: (input.options.tool_execution ?? "sequential") as ToolExecutionMode,
      tool_names: [...WORLDLINE_CAST_TOOLS],
      settings: resolution.settings,
      provider_call_id: providerCallId,
      abort_signal: deps.cancellationSignal?.(),
      executeTool: async (toolName, _toolCallId, args) => {
        if (toolName === "commit_worldline_cast") {
          const cast = normalizeCommitArgs(args);
          const committed = await deps.commitCast!({
            tenant_id: input.tenant_id,
            project_id: input.project_id,
            run_id: input.run_id,
            cast
          });
          return {
            agent_refs: committed.agent_refs,
            source_refs: committed.source_refs,
            rationale: committed.rationale,
            committed: true
          };
        }
        return deps.executeCastTool!({
          tenant_id: input.tenant_id,
          project_id: input.project_id,
          run_id: input.run_id,
          tool_name: toolName,
          args
        });
      },
      onAgentEvent: async (_event: AgentEvent) => undefined
    });
  } finally {
    await reservation?.finalize({});
    await lease?.release();
  }

  const committed = await deps.getCommittedCast?.({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id
  });
  if (!committed || committed.agent_refs.length < 1) {
    throw Object.assign(new Error("worldline cast planner did not commit agent_refs"), {
      code: "WORLDLINE_CAST_NOT_COMMITTED"
    });
  }
  return committed;
}

function normalizeCommitArgs(args?: Record<string, unknown>): WorldlineCastCommit {
  const agentRefs = normalizeRefs(args?.agent_refs, ["asset", "entity"]);
  const sourceRefs = normalizeRefs(args?.source_refs, ["asset", "entity", "saved_path", "worldline_event"]);
  const rationale = typeof args?.rationale === "string" ? args.rationale.trim() : "";
  if (agentRefs.length < 1 || agentRefs.length > 8) {
    throw Object.assign(new Error("commit_worldline_cast requires 1-8 agent_refs"), {
      code: "WORLDLINE_CAST_INVALID"
    });
  }
  if (!rationale) {
    throw Object.assign(new Error("commit_worldline_cast requires rationale"), {
      code: "WORLDLINE_CAST_INVALID"
    });
  }
  return { agent_refs: agentRefs, source_refs: sourceRefs, rationale };
}

function normalizeRefs(
  value: unknown,
  allowed: string[]
): Array<{ source_kind: "asset" | "entity" | "saved_path" | "worldline_event"; source_id: string }> {
  if (!Array.isArray(value)) return [];
  const allowedSet = new Set(allowed);
  const out: Array<{ source_kind: "asset" | "entity" | "saved_path" | "worldline_event"; source_id: string }> = [];
  const seen = new Set<string>();
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const record = item as Record<string, unknown>;
    const sourceKind = typeof record.source_kind === "string" ? record.source_kind.trim().toLowerCase() : "";
    const sourceId = typeof record.source_id === "string" ? record.source_id.trim() : "";
    if (!allowedSet.has(sourceKind) || !isUuid(sourceId)) continue;
    const key = `${sourceKind}:${sourceId}`;
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({
      source_kind: sourceKind as "asset" | "entity" | "saved_path" | "worldline_event",
      source_id: sourceId
    });
  }
  return out;
}

function isUuid(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(value);
}

function errorCode(error: unknown): string {
  if (error && typeof error === "object" && "code" in error && typeof (error as { code: unknown }).code === "string") {
    return (error as { code: string }).code;
  }
  if (error instanceof Error && error.message.includes(":")) {
    return error.message.split(":")[0] ?? "WORLDLINE_GOAL_START_FAILED";
  }
  return "WORLDLINE_GOAL_START_FAILED";
}

function publicErrorMessage(code: string, message: string): string {
  if (code === "WORLDLINE_CAST_NOT_COMMITTED") {
    return "Pi cast planner did not select any participating agents";
  }
  if (code === "WORLDLINE_PREPARATION_FAILED") {
    return "worldline preparation failed after cast selection";
  }
  if (message.length > 240) return message.slice(0, 240);
  return message;
}

export async function startWorldlinePreparationWorkflow(request: {
  temporalAddress?: string;
  namespace?: string;
  taskQueue?: string;
  temporal_workflow_id: string;
  prepare_id: string;
  run_id: string;
  tenant_id: string;
  project_id: string;
  actor_user_id: string;
  request_id: string;
}): Promise<void> {
  const address = request.temporalAddress ?? process.env.TEMPORAL_ADDRESS ?? "127.0.0.1:7233";
  const namespace = request.namespace ?? process.env.TEMPORAL_NAMESPACE ?? "default";
  const taskQueue = request.taskQueue ?? process.env.WORLDLINE_TASK_QUEUE ?? "worldline-interactive";
  const connection = await Connection.connect({ address });
  try {
    const client = new Client({ connection, namespace });
    await client.workflow.start("WorldlinePrepareWorkflow", {
      workflowId: request.temporal_workflow_id,
      taskQueue,
      args: [{
        context: {
          tenant_id: request.tenant_id,
          project_id: request.project_id,
          run_id: request.run_id,
          workflow_type: "worldline_preparation",
          actor_user_id: request.actor_user_id,
          module_key: "worldline_agent_prepare",
          trace_id: `trace_${request.run_id}`,
          permissions: { worldline_agent_prepare: ["run"] }
        },
        prepare_id: request.prepare_id,
        request_id: request.request_id
      }]
    });
  } finally {
    await connection.close();
  }
}
