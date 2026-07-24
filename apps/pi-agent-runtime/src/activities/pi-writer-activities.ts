import { validateWriterWorkflowPayload } from "../worker-spec.js";
import type { WriterRunInput } from "../contracts/writer-run.js";
import { runtimeContextFromInput, type RuntimeContext } from "../contracts/writer-run.js";
import type { AgentEvent, ToolExecutionMode } from "@earendil-works/pi-agent-core";
import {
  providerCallBudget,
  stableProviderCallId,
  usageCostMicros,
  validateProviderUsage,
  type PricingStatus
} from "../llm/quota/provider-call.js";

type LLMResolution = NonNullable<WriterRunInput["options"]["llm_resolution"]>;

export interface PiWriterActivityResult {
  tenant_id: string;
  project_id: string;
  run_id: string;
  status: "completed" | "failed";
  draft_id?: string;
  usage?: PiWriterUsage;
  error?: {
    code: string;
    message: string;
  };
}

export interface PiWriterUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
  cost_estimate?: number;
}

export interface CredentialRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  module_key: string;
  channel_id: string;
  credential_ref: string;
}

export interface Credential {
  apiKey: string;
}

export interface ComposeDraftRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  module_key: string;
  channel_id: string;
  model_id: string;
  provider: string;
  base_url: string;
  instruction: string;
  writing_brief?: string;
  target_words?: number;
  mode?: WriterRunInput["mode"];
  revise?: WriterRunInput["options"]["revise"];
  thinking_level?: WriterRunInput["options"]["thinking_level"];
  apiKey: string;
  settings: Record<string, unknown>;
  provider_call_id?: string;
  abort_signal?: AbortSignal;
  onToken?(token: string): Promise<void>;
}

export interface ComposeDraftResult {
  content: string;
  usage?: PiWriterUsage;
}

export type WriterToolName =
  | "query_project_context"
  | "query_chapter_scene"
  | "query_assets"
  | "search_assets"
  | "search_manuscript"
  | "fuse_recall"
  | "query_world_rules"
  | "query_character_profile"
  | "query_graph_neighbors"
  | "query_worldline_paths"
  | "query_manuscript_context"
  | "save_draft_revision";

export type SearchAssetsMode = "keyword" | "vector" | "hybrid";

export interface SearchAssetsArgs {
  query: string;
  asset_types?: string[];
  top_k?: number;
  mode?: SearchAssetsMode;
}

export interface SearchManuscriptArgs {
  query: string;
  top_k?: number;
}

export interface ResolvedLLMModule {
  // Any registry module key — writer prose modules or asset_search_embedding.
  module_key: string;
  channel_id: string;
  model_id: string;
  provider: string;
  base_url: string;
  credential_ref: string;
  supports_tools: boolean;
  supports_json: boolean;
  settings: Record<string, unknown>;
}

export interface ResolveModuleBindingRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  // Any registry module key — writer composer/orchestrator for prose, and
  // asset_search_embedding for retrieval embeddings. Mirrors the Go resolver.
  module_key: string;
}

export interface ExecuteWriterToolRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  chapter_id?: string;
  scene_id?: string;
  selected_asset_ids: string[];
  graph_node_ids: string[];
  worldline_path_ids: string[];
  tool_name: WriterToolName;
  tool_args?: Record<string, unknown>;
}

export interface OrchestrateWritingBriefRequest extends Omit<ComposeDraftRequest, "writing_brief" | "onToken"> {
  mode: WriterRunInput["mode"];
  chapter_id?: string;
  scene_id?: string;
  selected_asset_ids: string[];
  graph_node_ids: string[];
  worldline_path_ids: string[];
  tool_execution?: ToolExecutionMode;
  tool_names: WriterToolName[];
  runtime_context: RuntimeContext;
  /** Structured retrieval plan from writer_retrieval_planner; steers the loop. */
  retrieval_plan?: RetrievalPlan;
  executeTool(toolName: WriterToolName, toolCallId: string, args?: Record<string, unknown>): Promise<Record<string, unknown>>;
  onAgentEvent?(event: AgentEvent): Promise<void>;
}

export interface OrchestrateWritingBriefResult {
  writing_brief: string;
  usage?: PiWriterUsage;
}

// ── Retrieval planning (P1, doc 41 §4.1) ────────────────────────────────

/** One retrieval channel the planner can route a query through. */
export type RetrievalQueryChannel = "keyed" | "hybrid" | "graph" | "manuscript";

export interface RetrievalQuery {
  channel: RetrievalQueryChannel;
  text: string;
  asset_types?: string[];
  top_k?: number;
}

export interface RetrievalBudget {
  max_context_tokens?: number;
}

/** The structured retrieval plan produced by writer_retrieval_planner. */
export interface RetrievalPlan {
  intent: string;
  coverage: string[];
  queries: RetrievalQuery[];
  budget?: RetrievalBudget;
}

export interface PlanRetrievalRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  module_key: string;
  channel_id: string;
  model_id: string;
  provider: string;
  base_url: string;
  mode: WriterRunInput["mode"];
  instruction: string;
  chapter_id?: string;
  scene_id?: string;
  selected_asset_ids: string[];
  target_words?: number;
  thinking_level?: WriterRunInput["options"]["thinking_level"];
  apiKey: string;
  settings: Record<string, unknown>;
  provider_call_id?: string;
  abort_signal?: AbortSignal;
}

export interface PlanRetrievalResult {
  plan: RetrievalPlan;
  usage?: PiWriterUsage;
}

export interface AcquireLLMLeaseRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  module_key: string;
  channel_id: string;
  model_id: string;
  module_max_concurrency?: number;
}

export interface LLMLeaseLock {
  lease_id: string;
  resource_type: "llm_channel" | "llm_module";
  resource_id: string;
  lock_mode: string;
}

export interface LLMLease {
  lease_id: string;
  channel_id: string;
  lock_mode: string;
  locks?: LLMLeaseLock[];
}

export interface ReleaseLLMLeaseRequest extends LLMLease {
  tenant_id: string;
  project_id: string;
  run_id: string;
}

export interface SaveDraftRevisionRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  chapter_id?: string;
  scene_id?: string;
  content: string;
  status: "candidate";
  metadata?: Record<string, unknown>;
}

export interface SaveDraftRevisionResult {
  draft_id: string;
}

export interface RecordLLMActivityRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  module_key: string;
  channel_id: string;
  model_id: string;
  provider_call_id?: string;
  status: "completed" | "failed";
  prompt_tokens?: number;
  completion_tokens?: number;
  latency_ms?: number;
  cost_estimate?: number;
  error?: {
    code: string;
    message: string;
  };
}

export interface RecordUsageEventRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  module_key: string;
  usage_type: "llm_tokens";
  quantity: number;
  unit: "tokens";
  metadata: Record<string, unknown>;
}

export interface RecordAgentTraceEventRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  trace_id: string;
  module_key: string;
  agent_name: "pi_writer";
  status: "running" | "completed" | "failed";
  event_order: number;
  event_type:
    | "prompt_snapshot"
    | "llm_call_started"
    | "llm_call_completed"
    | "tool_call"
    | "tool_result"
    | "assistant_message"
    | "artifact_written"
    | "error";
  redaction_level: "public" | "summary" | "full";
  payload: Record<string, unknown>;
}

export interface RecordWorkflowEventRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  workflow_type: "writer_run";
  event_type:
    | "writer.run.started"
    | "writer.token"
    | "writer.tool.started"
    | "writer.tool.completed"
    | "writer.draft.saved"
    | "writer.retrieval_plan.completed"
    | "writer.retrieval_plan.degraded"
    | "writer.retrieval_plan.skipped"
    | "writer.context_budget.trimmed"
    | "writer.revision.proposed"
    | "writer.approval.required"
    | "writer.approval.resolved"
    | "writer.run.failed"
    | "writer.run.completed"
    | "writer.run.cancelled";
  payload: Record<string, unknown>;
  idempotency_key?: string;
}

export interface UpdateWriterRunStatusRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  status: "running" | "completed" | "failed";
  draft_id?: string;
  error?: {
    code: string;
    message: string;
  };
}

export interface ReserveLLMQuotaRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  module_key: string;
  channel_id: string;
  model_id: string;
  provider_call_id: string;
  reserved_tokens: number;
  reserved_cost_micros: number;
  pricing_status: PricingStatus;
  ttl_seconds: number;
}

export interface LLMQuotaReservation {
  reservation_id: string;
  provider_call_id: string;
  status: "reserved" | "finalized";
  expires_at: string;
  actual_prompt_tokens?: number;
  actual_completion_tokens?: number;
  actual_cost_micros?: number;
}

export interface FinalizeLLMQuotaRequest {
  tenant_id: string;
  project_id: string;
  reservation_id: string;
  provider_call_id: string;
  prompt_tokens: number;
  completion_tokens: number;
  actual_cost_micros?: number;
  pricing_status: PricingStatus;
}

export interface ReleaseLLMQuotaRequest {
  tenant_id: string;
  project_id: string;
  reservation_id: string;
  provider_call_id: string;
}

export interface CompletedWriterRunReplay {
  draft_id: string;
  usage?: PiWriterUsage;
}

export interface ProviderStageCheckpoint {
  provider_call_id: string;
  result: unknown;
  reservation: LLMQuotaReservation;
  lease: LLMLease;
}

export interface FindCompletedWriterRunRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
}

export interface PiWriterRunActivityDeps {
  cancellationSignal?(): AbortSignal | undefined;
  loadProviderStageCheckpoint?(providerCallID: string): Promise<ProviderStageCheckpoint | undefined>;
  saveProviderStageCheckpoint?(checkpoint: ProviderStageCheckpoint): Promise<void>;
  resolveModuleBinding?(request: ResolveModuleBindingRequest): Promise<ResolvedLLMModule>;
  planRetrieval?(request: PlanRetrievalRequest): Promise<PlanRetrievalResult>;
  orchestrateWritingBrief?(request: OrchestrateWritingBriefRequest): Promise<OrchestrateWritingBriefResult>;
  executeWriterTool?(request: ExecuteWriterToolRequest): Promise<Record<string, unknown>>;
  resolveCredential(request: CredentialRequest): Promise<Credential>;
  reserveLLMQuota?(request: ReserveLLMQuotaRequest): Promise<LLMQuotaReservation>;
  finalizeLLMQuota?(request: FinalizeLLMQuotaRequest): Promise<void>;
  releaseLLMQuota?(request: ReleaseLLMQuotaRequest): Promise<void>;
  acquireLLMLease(request: AcquireLLMLeaseRequest): Promise<LLMLease>;
  composeDraft(request: ComposeDraftRequest): Promise<ComposeDraftResult>;
  releaseLLMLease(request: ReleaseLLMLeaseRequest): Promise<void>;
  saveDraftRevision(request: SaveDraftRevisionRequest): Promise<SaveDraftRevisionResult>;
  appendWriterThreadMessage?(request: AppendWriterThreadMessageRequest): Promise<void>;
  createWriterApproval?(request: CreateWriterApprovalRequest): Promise<{ approval_id: string }>;
  recordLLMActivity(request: RecordLLMActivityRequest): Promise<void>;
  recordUsageEvent(request: RecordUsageEventRequest): Promise<void>;
  recordAgentTraceEvent(request: RecordAgentTraceEventRequest): Promise<void>;
  recordWorkflowEvent(request: RecordWorkflowEventRequest): Promise<void>;
  updateWriterRunStatus(request: UpdateWriterRunStatusRequest): Promise<void>;
  findCompletedWriterRun?(request: FindCompletedWriterRunRequest): Promise<CompletedWriterRunReplay | undefined>;
}

export interface AppendWriterThreadMessageRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  role: "user" | "agent" | "system" | "approval";
  body: string;
  metadata?: Record<string, unknown>;
}

export interface CreateWriterApprovalRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  action: string;
  summary: string;
  consequence?: string;
  reversible?: boolean;
}

export function createPiWriterRunActivity(deps: Partial<PiWriterRunActivityDeps> = {}) {
  return async function runPiWriterRunActivity(payload: unknown): Promise<PiWriterActivityResult> {
    const input = validateWriterWorkflowPayload(payload);
    if (deps.resolveModuleBinding && deps.orchestrateWritingBrief && deps.executeWriterTool) {
      return runDualStagePiWriterActivity(input, deps as PiWriterRunActivityDeps);
    }
    const resolution = input.options.llm_resolution;
    if (!resolution) {
      return failed(input, "LLM_MODULE_UNBOUND", `${input.options.module_key} must be resolved through LLM Facility before Pi writer execution`);
    }
    if (!resolution.credential_ref) {
      return failed(input, "LLM_PROVIDER_ERROR", "resolved LLM credential is unavailable");
    }
    if (!deps.resolveCredential || !deps.acquireLLMLease || !deps.composeDraft || !deps.releaseLLMLease || !deps.saveDraftRevision || !deps.recordLLMActivity || !deps.recordUsageEvent || !deps.recordAgentTraceEvent || !deps.recordWorkflowEvent || !deps.updateWriterRunStatus) {
      return failed(input, "LLM_PROVIDER_ERROR", "Pi writer provider invocation requires secure LLM Facility key handoff, agent trace writer, and workflow event writer");
    }

    const activityDeps = deps as PiWriterRunActivityDeps;
    const startedAt = Date.now();
    let lease: LLMLease | undefined;
    let eventOrder = 0;
    const recordTrace = (
      event_type: RecordAgentTraceEventRequest["event_type"],
      redaction_level: RecordAgentTraceEventRequest["redaction_level"],
      payload: Record<string, unknown>,
      status: RecordAgentTraceEventRequest["status"] = "running"
    ) => activityDeps.recordAgentTraceEvent({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      trace_id: input.trace_id,
      module_key: resolution.module_key,
      agent_name: "pi_writer",
      status,
      event_order: ++eventOrder,
      event_type,
      redaction_level,
      payload
    });
    const recordWorkflow = (
      event_type: RecordWorkflowEventRequest["event_type"],
      payload: Record<string, unknown>
    ) => activityDeps.recordWorkflowEvent({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      workflow_type: "writer_run",
      event_type,
      payload
    });
    try {
      await runPiWriterStep("Pi writer workflow event recording failed", () => recordWorkflow("writer.run.started", {
        mode: input.mode,
        module_key: resolution.module_key,
        channel_id: resolution.channel_id,
        model_id: resolution.model_id
      }));
      await runPiWriterStep("Pi writer status update failed", () => activityDeps.updateWriterRunStatus({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "running"
      }));
      const credential = await runPiWriterStep("Pi writer credential resolution failed", () => activityDeps.resolveCredential({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        module_key: resolution.module_key,
        channel_id: resolution.channel_id,
        credential_ref: resolution.credential_ref
      }));
      lease = await runPiWriterStep("Pi writer LLM lease acquisition failed", () => activityDeps.acquireLLMLease({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        module_key: resolution.module_key,
        channel_id: resolution.channel_id,
        model_id: resolution.model_id,
        module_max_concurrency: positiveIntegerSetting(resolution.settings, "max_concurrency")
      }));
      await runPiWriterStep("Pi writer trace recording failed", () => recordTrace("prompt_snapshot", "full", {
        mode: input.mode,
        instruction: input.instruction,
        selected_asset_ids: input.selected_asset_ids,
        graph_node_ids: input.graph_node_ids,
        worldline_path_ids: input.worldline_path_ids
      }));
      await runPiWriterStep("Pi writer trace recording failed", () => recordTrace("llm_call_started", "summary", {
        module_key: resolution.module_key,
        channel_id: resolution.channel_id,
        model_id: resolution.model_id,
        provider: resolution.provider
      }));
      let draft: ComposeDraftResult;
      let composeError: Error | undefined;
      try {
        draft = await activityDeps.composeDraft({
          tenant_id: input.tenant_id,
          project_id: input.project_id,
          run_id: input.run_id,
          module_key: resolution.module_key,
          channel_id: resolution.channel_id,
          model_id: resolution.model_id,
          provider: resolution.provider,
          base_url: resolution.base_url,
          instruction: input.instruction,
          mode: input.mode,
          revise: input.options.revise,
          apiKey: credential.apiKey,
          settings: resolution.settings
        });
      } catch {
        composeError = new Error("Pi writer provider call failed");
        draft = { content: "" };
      }
      const releaseError = await releaseLeaseAfterFailure(activityDeps, input, lease);
      lease = undefined;
      if (composeError) {
        throw new Error(appendFailureMessage(composeError.message, releaseError));
      }
      if (releaseError) {
        throw new Error(releaseError);
      }
      if (!draft.content.trim()) {
        return failed(input, "WRITER_CONTEXT_EMPTY", "Pi writer provider returned an empty draft");
      }
      if (input.mode === "revise" && input.options.revise) {
        await runPiWriterStep("Pi writer revision event recording failed", () => recordWorkflow("writer.revision.proposed", {
          block_id: input.options.revise!.block_id,
          selection_text: input.options.revise!.selection_text,
          selection_start: input.options.revise!.selection_start,
          selection_end: input.options.revise!.selection_end,
          proposed_text: draft.content,
          instruction: input.instruction,
          status: "candidate"
        }));
      }
      const saved = await runPiWriterStep("Pi writer draft persistence failed", () => activityDeps.saveDraftRevision({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        chapter_id: input.chapter_id,
        scene_id: input.scene_id,
        content: draft.content,
        status: "candidate",
        metadata: {
          module_key: resolution.module_key,
          channel_id: resolution.channel_id,
          model_id: resolution.model_id,
          provider: resolution.provider,
          mode: input.mode,
          revise: input.options.revise
        }
      }));
      await runPiWriterStep("Pi writer workflow event recording failed", () => recordWorkflow("writer.draft.saved", {
        draft_id: saved.draft_id,
        status: "candidate"
      }));
      await runPiWriterStep("Pi writer LLM activity recording failed", () => activityDeps.recordLLMActivity({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        module_key: resolution.module_key,
        channel_id: resolution.channel_id,
        model_id: resolution.model_id,
        status: "completed",
        prompt_tokens: draft.usage?.prompt_tokens,
        completion_tokens: draft.usage?.completion_tokens,
        latency_ms: Date.now() - startedAt,
        cost_estimate: draft.usage?.cost_estimate
      }));
      await runPiWriterStep("Pi writer usage recording failed", () => activityDeps.recordUsageEvent({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        module_key: resolution.module_key,
        usage_type: "llm_tokens",
        quantity: tokenQuantity(draft.usage),
        unit: "tokens",
        metadata: {
          channel_id: resolution.channel_id,
          model_id: resolution.model_id,
          provider: resolution.provider,
          prompt_tokens: draft.usage?.prompt_tokens,
          completion_tokens: draft.usage?.completion_tokens,
          cost_estimate: draft.usage?.cost_estimate
        }
      }));
      await runPiWriterStep("Pi writer trace recording failed", () => recordTrace("llm_call_completed", "summary", {
        module_key: resolution.module_key,
        channel_id: resolution.channel_id,
        model_id: resolution.model_id,
        provider: resolution.provider,
        prompt_tokens: draft.usage?.prompt_tokens,
        completion_tokens: draft.usage?.completion_tokens,
        cost_estimate: draft.usage?.cost_estimate,
        latency_ms: Date.now() - startedAt
      }));
      await runPiWriterStep("Pi writer trace recording failed", () => recordTrace("artifact_written", "summary", {
        draft_id: saved.draft_id,
        artifact_type: "writer_draft",
        status: "candidate"
      }, "completed"));
      if (activityDeps.appendWriterThreadMessage) {
        try {
          await activityDeps.appendWriterThreadMessage({
            tenant_id: input.tenant_id,
            project_id: input.project_id,
            run_id: input.run_id,
            role: "agent",
            body: candidateReadyThreadBody(draft.content),
            metadata: {
              draft_id: saved.draft_id,
              mode: input.mode,
              status: "candidate",
              kind: "candidate_ready"
            }
          });
        } catch {
          // Thread persistence must not fail the writer run after draft is saved.
        }
      }
      await runPiWriterStep("Pi writer workflow event recording failed", () => recordWorkflow("writer.run.completed", {
        draft_id: saved.draft_id,
        status: "completed"
      }));
      await runPiWriterStep("Pi writer status update failed", () => activityDeps.updateWriterRunStatus({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "completed",
        draft_id: saved.draft_id
      }));

      return {
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "completed",
        draft_id: saved.draft_id,
        usage: draft.usage
      };
    } catch (error) {
      let message = stablePiWriterFailureMessage(error);
      if (lease) {
        const releaseError = await releaseLeaseAfterFailure(activityDeps, input, lease);
        lease = undefined;
        message = appendFailureMessage(message, releaseError);
      }
      const recordError = await recordFailedLLMActivity(activityDeps, input, resolution, startedAt, message);
      message = appendFailureMessage(message, recordError);
      const traceError = await recordFailedTrace(recordTrace, message);
      message = appendFailureMessage(message, traceError);
      const workflowError = await recordFailedWorkflowEvent(recordWorkflow, message);
      message = appendFailureMessage(message, workflowError);
      const statusError = await updateFailedWriterRunStatus(activityDeps, input, message);
      message = appendFailureMessage(message, statusError);
      return failed(input, "LLM_PROVIDER_ERROR", message);
    }
  };
}

async function releaseLeaseAfterFailure(
  deps: PiWriterRunActivityDeps,
  input: WriterRunInput,
  lease: LLMLease
): Promise<string | null> {
  try {
    await deps.releaseLLMLease({
          ...lease,
          tenant_id: input.tenant_id,
          project_id: input.project_id,
          run_id: input.run_id
        });
    return null;
  } catch {
    return "Pi writer LLM lease release failed";
  }
}

async function recordFailedLLMActivity(
  deps: PiWriterRunActivityDeps,
  input: WriterRunInput,
  resolution: LLMResolution,
  startedAt: number,
  message: string
): Promise<string | null> {
  try {
    await deps.recordLLMActivity({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      module_key: resolution.module_key,
      channel_id: resolution.channel_id,
      model_id: resolution.model_id,
      status: "failed",
      latency_ms: Date.now() - startedAt,
      error: {
        code: "LLM_PROVIDER_ERROR",
        message
      }
    });
    return null;
  } catch {
    return "Pi writer LLM activity failure recording failed";
  }
}

async function recordFailedTrace(
  recordTrace: (
    event_type: RecordAgentTraceEventRequest["event_type"],
    redaction_level: RecordAgentTraceEventRequest["redaction_level"],
    payload: Record<string, unknown>,
    status?: RecordAgentTraceEventRequest["status"]
  ) => Promise<void>,
  message: string
): Promise<string | null> {
  try {
    await recordTrace("error", "summary", {
      error_code: "LLM_PROVIDER_ERROR",
      message
    }, "failed");
    return null;
  } catch {
    return "Pi writer trace failure recording failed";
  }
}

async function recordFailedWorkflowEvent(
  recordWorkflow: (
    event_type: RecordWorkflowEventRequest["event_type"],
    payload: Record<string, unknown>
  ) => Promise<void>,
  message: string
): Promise<string | null> {
  try {
    await recordWorkflow("writer.run.failed", {
      error_code: "LLM_PROVIDER_ERROR",
      message
    });
    return null;
  } catch {
    return "Pi writer workflow event failure recording failed";
  }
}

async function updateFailedWriterRunStatus(
  deps: PiWriterRunActivityDeps,
  input: WriterRunInput,
  message: string
): Promise<string | null> {
  try {
    await deps.updateWriterRunStatus({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      status: "failed",
      error: {
        code: "LLM_PROVIDER_ERROR",
        message
      }
    });
    return null;
  } catch {
    return "Pi writer status update failed";
  }
}

async function runPiWriterStep<T>(publicMessage: string, action: () => Promise<T>): Promise<T> {
  try {
    return await action();
  } catch {
    throw new Error(publicMessage);
  }
}

function stablePiWriterFailureMessage(error: unknown): string {
  if (error instanceof Error && error.message.startsWith("Pi writer ")) {
    return error.message;
  }
  return "Pi writer runtime dependency failed";
}

function appendFailureMessage(message: string, addition: string | null): string {
  return addition ? `${message}; ${addition}` : message;
}

function tokenQuantity(usage: PiWriterUsage | undefined): number {
  return (usage?.prompt_tokens ?? 0) + (usage?.completion_tokens ?? 0);
}

function positiveIntegerSetting(settings: Record<string, unknown>, key: string): number | undefined {
  const value = settings[key];
  const numberValue = typeof value === "number" || typeof value === "string" ? Number(value) : NaN;
  return Number.isInteger(numberValue) && numberValue > 0 ? numberValue : undefined;
}

function failed(input: WriterRunInput, code: string, message: string): PiWriterActivityResult {
  return {
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    status: "failed",
    error: {
      code,
      message
    }
  };
}

export const runPiWriterRunActivity = createPiWriterRunActivity();

async function runDualStagePiWriterActivity(
  input: WriterRunInput,
  deps: PiWriterRunActivityDeps
): Promise<PiWriterActivityResult> {
  const startedAt = Date.now();
  let eventOrder = 0;
  let chunkIndex = 0;
  const recordTrace = async (
    moduleKey: string,
    eventType: RecordAgentTraceEventRequest["event_type"],
    payload: Record<string, unknown>,
    redaction: RecordAgentTraceEventRequest["redaction_level"] = "summary",
    status: RecordAgentTraceEventRequest["status"] = "running"
  ) => deps.recordAgentTraceEvent({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    trace_id: input.trace_id,
    module_key: moduleKey,
    agent_name: "pi_writer",
    status,
    event_order: ++eventOrder,
    event_type: eventType,
    redaction_level: redaction,
    payload
  });
  const recordWorkflow = (
    eventType: RecordWorkflowEventRequest["event_type"],
    payload: Record<string, unknown>,
    key: string
  ) => deps.recordWorkflowEvent({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    workflow_type: "writer_run",
    event_type: eventType,
    payload,
    idempotency_key: key
  });

  try {
    if (deps.findCompletedWriterRun) {
      const replay = await deps.findCompletedWriterRun({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id
      });
      if (replay) {
        return {
          tenant_id: input.tenant_id,
          project_id: input.project_id,
          run_id: input.run_id,
          status: "completed",
          draft_id: replay.draft_id,
          usage: replay.usage
        };
      }
    }
    await recordWorkflow("writer.run.started", { mode: input.mode, stage: "orchestrator" }, "run:started");
    await deps.updateWriterRunStatus({ tenant_id: input.tenant_id, project_id: input.project_id, run_id: input.run_id, status: "running" });
    await recordTrace("writer_orchestrator", "prompt_snapshot", {
      instruction: input.instruction,
      mode: input.mode,
      chapter_id: input.chapter_id,
      scene_id: input.scene_id,
      selected_asset_ids: input.selected_asset_ids,
      graph_node_ids: input.graph_node_ids,
      worldline_path_ids: input.worldline_path_ids
    }, "full");

    // P1 (doc 41 §4.1): an independent retrieval-planner stage runs BEFORE the
    // orchestrator. It analyses the request and emits a structured RetrievalPlan
    // that steers the orchestrator's search_assets calls. Planner failure degrades
    // to free recall (never blocks writing) but is always recorded so the
    // degradation is visible.
    let retrievalPlan: RetrievalPlan | undefined;
    let plannerUsage: PiWriterUsage | undefined;
    if (deps.planRetrieval && deps.resolveModuleBinding) {
      let planner: ResolvedLLMModule | undefined;
      try {
        planner = await resolveRequiredModule(deps, input, "writer_retrieval_planner");
      } catch (error) {
        await recordWorkflow("writer.retrieval_plan.skipped", {
          reason: errorCode(error) === "LLM_MODULE_UNBOUND" ? "planner_unbound" : "planner_binding_failed"
        }, "retrieval_plan:skipped");
      }
      if (planner) {
        try {
          const plannerCall = await executeLLMStage(
            deps,
            input,
            planner,
            "planner",
            0,
            async (apiKey, providerCallID) => {
              await recordTrace(planner!.module_key, "llm_call_started", resolutionSummary(planner!));
              const result = await deps.planRetrieval!({
                tenant_id: input.tenant_id,
                project_id: input.project_id,
                run_id: input.run_id,
                module_key: planner!.module_key,
                channel_id: planner!.channel_id,
                model_id: planner!.model_id,
                provider: planner!.provider,
                base_url: planner!.base_url,
                mode: input.mode,
                instruction: input.instruction,
                chapter_id: input.chapter_id,
                scene_id: input.scene_id,
                selected_asset_ids: input.selected_asset_ids,
                target_words: input.options.target_words,
                thinking_level: input.options.thinking_level,
                apiKey,
                settings: planner!.settings,
                provider_call_id: providerCallID,
                abort_signal: deps.cancellationSignal?.()
              });
              return result;
            }
          );
          retrievalPlan = plannerCall.result.plan;
          plannerUsage = plannerCall.result.usage;
          await recordTrace(planner.module_key, "llm_call_completed", {
            intent: retrievalPlan.intent,
            coverage: retrievalPlan.coverage,
            query_count: retrievalPlan.queries.length
          }, "summary", "completed");
          await recordWorkflow("writer.retrieval_plan.completed", {
            intent: retrievalPlan.intent,
            coverage: retrievalPlan.coverage,
            queries: retrievalPlan.queries,
            budget: retrievalPlan.budget
          }, "retrieval_plan:completed");
        } catch (error) {
          await recordTrace("writer_retrieval_planner", "error", { message: errorMessageText(error) }, "summary", "failed");
          await recordWorkflow("writer.retrieval_plan.degraded", {
            reason: "planner_call_failed",
            message: errorMessageText(error)
          }, "retrieval_plan:degraded");
        }
      }
    }

    const orchestrator = await resolveRequiredModule(deps, input, "writer_orchestrator");
    if (!orchestrator.supports_tools) {
      throw runtimeFailure(
        "LLM_MODEL_TOOLS_UNSUPPORTED",
        "writer_orchestrator binding must support tools",
      );
    }

    const orchestratorCall = await executeLLMStage(
      deps,
      input,
      orchestrator,
      "orchestrator",
      0,
      async (apiKey, providerCallID) => {
      let eventWriteChain = Promise.resolve();
      await recordTrace(orchestrator.module_key, "llm_call_started", resolutionSummary(orchestrator));
      const toolNames: WriterToolName[] = [
        "query_project_context",
        "query_chapter_scene",
        "query_assets",
        "search_assets",
        "search_manuscript",
        "fuse_recall",
        "query_world_rules",
        "query_character_profile",
        "query_graph_neighbors",
        "query_worldline_paths",
        "query_manuscript_context"
      ];
      const runtimeContext = runtimeContextFromInput(input);
      // Token-budget context packer (doc 41 §4.4): bound what the retrieval tools
      // hand the orchestrator so recall can't flood the writing context.
      const retrievalBudget = resolveRetrievalTokenBudget(retrievalPlan);
      const packed = { remainingTokens: retrievalBudget, dropped: 0, channels: new Set<string>() };
      const result = await deps.orchestrateWritingBrief!({
        ...composeRequest(input, orchestrator, apiKey, providerCallID, deps.cancellationSignal?.()),
        mode: input.mode,
        chapter_id: input.chapter_id,
        scene_id: input.scene_id,
        selected_asset_ids: input.selected_asset_ids,
        graph_node_ids: input.graph_node_ids,
        worldline_path_ids: input.worldline_path_ids,
        tool_execution: input.options.tool_execution,
        tool_names: toolNames,
        retrieval_plan: retrievalPlan,
        runtime_context: {
          ...runtimeContext,
          permissions: { tools: toolNames, can_write_draft: false }
        },
        executeTool: async (toolName, toolCallId, args) => {
          const raw = await deps.executeWriterTool!({
            tenant_id: input.tenant_id,
            project_id: input.project_id,
            run_id: input.run_id,
            chapter_id: input.chapter_id,
            scene_id: input.scene_id,
            selected_asset_ids: input.selected_asset_ids,
            graph_node_ids: input.graph_node_ids,
            worldline_path_ids: input.worldline_path_ids,
            tool_name: toolName,
            tool_args: args
          });
          return packRetrievalToolResult(toolName, raw, packed);
        },
        onAgentEvent: (event) => {
          eventWriteChain = eventWriteChain.then(async () => {
          if (event.type === "tool_execution_start") {
            await recordWorkflow("writer.tool.started", {
              tool_call_id: event.toolCallId,
              tool_name: event.toolName,
              status: "running"
            }, `tool:${event.toolCallId}:started`);
            await recordTrace(orchestrator.module_key, "tool_call", {
              tool_call_id: event.toolCallId,
              tool_name: event.toolName,
              args: event.args
            }, "full");
          }
          if (event.type === "tool_execution_end") {
            const toolResult = event.result?.details ?? event.result;
            await recordWorkflow("writer.tool.completed", {
              tool_call_id: event.toolCallId,
              tool_name: event.toolName,
              status: event.isError ? "failed" : "completed",
              is_error: event.isError,
              result: publicWriterToolResult(event.toolName, toolResult)
            }, `tool:${event.toolCallId}:completed`);
            await recordTrace(orchestrator.module_key, "tool_result", {
              tool_call_id: event.toolCallId,
              tool_name: event.toolName,
              is_error: event.isError,
              result: toolResult
            }, "full");
          }
          });
          return eventWriteChain;
        }
      });
      await eventWriteChain;
      if (packed.dropped > 0) {
        await recordWorkflow("writer.context_budget.trimmed", {
          dropped_items: packed.dropped,
          budget_tokens: retrievalBudget,
          channels: [...packed.channels]
        }, "context_budget:trimmed");
      }
      return result;
      }
    );
    const writingBrief = orchestratorCall.result;
    await recordStageTelemetry(
      deps,
      input,
      orchestrator,
      writingBrief.usage,
      Date.now() - startedAt,
      orchestratorCall.provider_call_id
    );
    await recordTrace(orchestrator.module_key, "llm_call_completed", {
      ...resolutionSummary(orchestrator),
      ...writingBrief.usage
    });

    const composer = await resolveRequiredModule(deps, input, "writer_composer");
    const composerCall = await executeLLMStage(deps, input, composer, "composer", 0, async (apiKey, providerCallID) => {
      await recordTrace(composer.module_key, "llm_call_started", resolutionSummary(composer));
      const result = await deps.composeDraft({
        ...composeRequest(input, composer, apiKey, providerCallID, deps.cancellationSignal?.()),
        writing_brief: writingBrief.writing_brief,
        onToken: async (token) => {
          const index = ++chunkIndex;
          await recordWorkflow("writer.token", { token, chunk_index: index }, `composer:token:${index}`);
        }
      });
      return result;
    });
    const draft = composerCall.result;
    await recordStageTelemetry(
      deps,
      input,
      composer,
      draft.usage,
      Date.now() - startedAt,
      composerCall.provider_call_id
    );
    await recordTrace(composer.module_key, "llm_call_completed", {
      ...resolutionSummary(composer),
      ...draft.usage
    });
    await recordTrace(composer.module_key, "assistant_message", { content: draft.content }, "full");

    if (input.mode === "revise" && input.options.revise) {
      await recordWorkflow("writer.revision.proposed", {
        block_id: input.options.revise.block_id,
        selection_text: input.options.revise.selection_text,
        selection_start: input.options.revise.selection_start,
        selection_end: input.options.revise.selection_end,
        proposed_text: draft.content,
        instruction: input.instruction,
        status: "candidate"
      }, "revision:proposed");
    }

    let saved: SaveDraftRevisionResult;
    try {
      saved = await deps.saveDraftRevision({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        chapter_id: input.chapter_id,
        scene_id: input.scene_id,
        content: draft.content,
        status: "candidate",
        metadata: {
          orchestrator_model_id: orchestrator.model_id,
          composer_model_id: composer.model_id,
          mode: input.mode,
          revise: input.options.revise,
          source_metadata: writerSourceMetadata(input)
        }
      });
    } catch {
      throw runtimeFailure("WRITER_DRAFT_SAVE_FAILED", "Pi writer draft persistence failed", composer.module_key);
    }
    const sourceMetadata = writerSourceMetadata(input);
    await recordWorkflow("writer.draft.saved", {
      draft_id: saved.draft_id,
      status: "candidate",
      source_metadata: sourceMetadata
    }, "draft:saved");
    await recordTrace(composer.module_key, "artifact_written", {
      draft_id: saved.draft_id,
      artifact_type: "writer_draft",
      status: "candidate",
      source_metadata: sourceMetadata
    }, "summary", "completed");
    // CONN-009: durable agent status for persistent Writer threads (best-effort).
    // Keep the full prose on the canvas only — the thread stores a short status line.
    if (deps.appendWriterThreadMessage) {
      try {
        await deps.appendWriterThreadMessage({
          tenant_id: input.tenant_id,
          project_id: input.project_id,
          run_id: input.run_id,
          role: "agent",
          body: candidateReadyThreadBody(draft.content),
          metadata: {
            draft_id: saved.draft_id,
            mode: input.mode,
            status: "candidate",
            kind: "candidate_ready"
          }
        });
      } catch {
        // Thread persistence must not fail the writer run after draft is saved.
      }
    }
    await recordWorkflow("writer.run.completed", { draft_id: saved.draft_id, status: "completed" }, "run:completed");
    await deps.updateWriterRunStatus({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      status: "completed",
      draft_id: saved.draft_id
    });
    return {
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      status: "completed",
      draft_id: saved.draft_id,
      usage: combineUsage(writingBrief.usage, draft.usage)
    };
  } catch (error) {
    if (deps.cancellationSignal?.()?.aborted) throw error;
    const failure = normalizeRuntimeFailure(error);
    await recordTrace(failure.module_key ?? "writer_composer", "error", {
      error_code: failure.code,
      message: failure.message
    }, "summary", "failed").catch(() => undefined);
    await recordWorkflow("writer.run.failed", {
      error_code: failure.code,
      message: failure.message
    }, "run:failed").catch(() => undefined);
    await deps.updateWriterRunStatus({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      status: "failed",
      error: { code: failure.code, message: failure.message }
    }).catch(() => undefined);
    return failed(input, failure.code, failure.message);
  }
}

function writerSourceMetadata(input: WriterRunInput): Record<string, unknown> {
  return {
    asset_ids: input.selected_asset_ids,
    graph_node_ids: input.graph_node_ids,
    worldline_path_ids: input.worldline_path_ids,
    reference_counts: {
      assets: input.selected_asset_ids.length,
      graph_nodes: input.graph_node_ids.length,
      worldline_paths: input.worldline_path_ids.length
    }
  };
}

/**
 * Thread messages stay short: full candidate prose lives on the canvas.
 * Count Unicode code points so CJK length matches the author-facing status line.
 */
function candidateReadyThreadBody(content: string): string {
  const chars = [...content.trim()].length;
  if (chars <= 0) {
    return "候选稿已写好，见左侧画布。";
  }
  return `候选稿已写好（${chars} 字），见左侧画布。`;
}

function publicWriterToolResult(toolName: string, value: unknown): Record<string, unknown> {
  const source = objectRecord(value);
  if (toolName === "query_assets") {
    return { items: recordArray(source.assets).map((item) => pickFields(item, ["asset_id", "asset_type", "category", "lifecycle", "title", "summary"])) };
  }
  if (toolName === "search_assets") {
    return {
      mode_used: typeof source.mode_used === "string" ? source.mode_used : "keyword",
      degraded: source.degraded === true,
      items: recordArray(source.citations).map((item) => pickFields(item, ["asset_id", "title", "lifecycle", "score", "channel"]))
    };
  }
  if (toolName === "search_manuscript") {
    return {
      mode_used: typeof source.mode_used === "string" ? source.mode_used : "unavailable",
      degraded: source.degraded === true,
      items: recordArray(source.citations).map((item) => pickFields(item, ["block_id", "chapter_id", "block_order", "score", "channel"]))
    };
  }
  if (toolName === "query_world_rules") {
    return {
      items: recordArray(source.rules).map((item) => pickFields(item, [
        "rule_evidence_id", "category", "confidence", "source", "lifecycle", "title"
      ]))
    };
  }
  if (toolName === "query_character_profile") {
    return {
      items: recordArray(source.profiles).map((item) => pickFields(item, [
        "entity_id", "canonical_name", "entity_type", "importance", "state_summary", "source", "lifecycle", "category"
      ]))
    };
  }
  if (toolName === "query_graph_neighbors") {
    return {
      node: pickFields(objectRecord(source.node), ["node_id", "node_type", "title", "summary", "lifecycle"]),
      neighbors: recordArray(source.neighbors).map((item) => pickFields(item, ["node_id", "node_type", "title", "summary", "lifecycle", "relationship", "edge_type", "direction"]))
    };
  }
  if (toolName === "query_worldline_paths") {
    return {
      items: recordArray(source.paths).map((item) => pickFields(item, ["path_id", "title", "summary", "lifecycle", "writer_instruction", "selected_event_ids"])),
      ...(source.selection_required === true ? { selection_required: true } : {}),
      ...(typeof source.canon_status === "string" ? { canon_status: source.canon_status } : {})
    };
  }
  if (toolName === "query_chapter_scene") {
    return { target: pickFields(objectRecord(source.target), ["chapter_id", "scene_id", "mode"]) };
  }
  if (toolName === "query_project_context") {
    return { project: pickFields(objectRecord(source.project), ["title", "genre", "language", "status"]) };
  }
  return {};
}

function objectRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordArray(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(objectRecord) : [];
}

function pickFields(source: Record<string, unknown>, fields: string[]): Record<string, unknown> {
  return Object.fromEntries(fields.filter((field) => source[field] !== undefined).map((field) => [field, source[field]]));
}

// ── Token-budget context packer (doc 41 §4.4) ────────────────────────────

const DEFAULT_RETRIEVAL_TOKEN_BUDGET = 12000;

interface RetrievalPackState {
  remainingTokens: number;
  dropped: number;
  channels: Set<string>;
}

function resolveRetrievalTokenBudget(plan: RetrievalPlan | undefined): number {
  const value = plan?.budget?.max_context_tokens;
  return typeof value === "number" && Number.isInteger(value) && value > 0 ? value : DEFAULT_RETRIEVAL_TOKEN_BUDGET;
}

// Rough token estimate: ~1 token per 4 latin chars, ~1.5 per CJK char.
function estimateTokens(value: unknown): number {
  const text = typeof value === "string" ? value : JSON.stringify(value) ?? "";
  let tokens = 0;
  for (const ch of text) {
    tokens += ch.charCodeAt(0) > 0xff ? 1.5 : 0.25;
  }
  return Math.max(1, Math.ceil(tokens));
}

// Cap a recall result (search_assets / search_manuscript) to the shared budget.
// Lower-ranked items (the tools return best-first) are trimmed first — never the
// deterministic structural context (rules, chapter, scene), which other tools
// supply and the composer must always see. Budget exhaustion degrades visibly:
// the orchestrator and the workflow log both see what was dropped.
function packRetrievalToolResult(
  toolName: WriterToolName,
  result: Record<string, unknown>,
  state: RetrievalPackState
): Record<string, unknown> {
  if (toolName !== "search_assets" && toolName !== "search_manuscript") {
    return result;
  }
  const itemKey = toolName === "search_assets" ? "assets" : "manuscript_blocks";
  const items = Array.isArray(result[itemKey]) ? (result[itemKey] as Record<string, unknown>[]) : null;
  if (!items) return result;

  const kept: Record<string, unknown>[] = [];
  let droppedHere = 0;
  for (const item of items) {
    const cost = estimateTokens(item.content_preview ?? item.snippet ?? item.title ?? "");
    if (state.remainingTokens - cost < 0) {
      droppedHere += 1;
      continue;
    }
    state.remainingTokens -= cost;
    kept.push(item);
  }
  if (droppedHere > 0) {
    state.dropped += droppedHere;
    const channel = toolName === "search_assets" ? "search_assets" : "search_manuscript";
    state.channels.add(channel);
  }
  return {
    ...result,
    [itemKey]: kept,
    count: kept.length,
    ...(droppedHere > 0 ? { budget_trimmed: droppedHere } : {})
  };
}

async function resolveRequiredModule(
  deps: PiWriterRunActivityDeps,
  input: WriterRunInput,
  moduleKey: ResolvedLLMModule["module_key"]
): Promise<ResolvedLLMModule> {
  try {
    const resolution = await deps.resolveModuleBinding!({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      module_key: moduleKey
    });
    if (resolution.module_key !== moduleKey || !resolution.channel_id || !resolution.model_id || !resolution.provider || !resolution.base_url || !resolution.credential_ref) {
      throw runtimeFailure("LLM_PROVIDER_ERROR", `${moduleKey} binding is incomplete`, moduleKey);
    }
    return resolution;
  } catch (error) {
    if (error instanceof RuntimeFailure) throw error;
    const code = errorCode(error) === "LLM_MODULE_UNBOUND" ? "LLM_MODULE_UNBOUND" : "LLM_BINDING_QUERY_FAILED";
    throw runtimeFailure(code, code === "LLM_MODULE_UNBOUND" ? `${moduleKey} module is not bound` : "LLM module binding query failed", moduleKey);
  }
}

interface ExecutedLLMStage<T> {
  result: T;
  provider_call_id: string;
}

async function executeLLMStage<T extends { usage?: PiWriterUsage }>(
  deps: PiWriterRunActivityDeps,
  input: WriterRunInput,
  resolution: ResolvedLLMModule,
  stage: "orchestrator" | "composer" | "planner",
  callIndex: number,
  execute: (apiKey: string, providerCallID: string) => Promise<T>
): Promise<ExecutedLLMStage<T>> {
  const providerCallID = stableProviderCallId({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    module_key: resolution.module_key,
    stage,
    call_index: callIndex
  });
  let reservation: LLMQuotaReservation | undefined;
  let lease: LLMLease | undefined;
  let providerUsageObserved = false;
  try {
    assertQuotaDeps(deps, resolution.module_key);
    const credential = await deps.resolveCredential({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      module_key: resolution.module_key,
      channel_id: resolution.channel_id,
      credential_ref: resolution.credential_ref
    });
    const budget = providerCallBudget(resolution.settings);
    reservation = await deps.reserveLLMQuota!({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      module_key: resolution.module_key,
      channel_id: resolution.channel_id,
      model_id: resolution.model_id,
      provider_call_id: providerCallID,
      reserved_tokens: budget.reserved_tokens,
      reserved_cost_micros: budget.reserved_cost_micros,
      pricing_status: budget.pricing_status,
      ttl_seconds: positiveIntegerSetting(resolution.settings, "quota_reservation_ttl_seconds") ?? 300
    });
    if (reservation.provider_call_id !== providerCallID) {
      throw runtimeFailure("LLM_PROVIDER_CALL_CONFLICT", "Pi writer provider call identity conflicts with its reservation", resolution.module_key);
    }
    const checkpoint = await deps.loadProviderStageCheckpoint?.(providerCallID);
    if (checkpoint) {
      const result = checkpoint.result as T;
      const usage = validateProviderUsage(result.usage);
      if (reservation.status === "reserved") {
        await deps.finalizeLLMQuota!({
          tenant_id: input.tenant_id,
          project_id: input.project_id,
          reservation_id: reservation.reservation_id,
          provider_call_id: providerCallID,
          prompt_tokens: usage.prompt_tokens,
          completion_tokens: usage.completion_tokens,
          actual_cost_micros: usageCostMicros(usage, budget.pricing_status),
          pricing_status: budget.pricing_status
        });
      }
      const cleanup = await releaseStageResources(deps, input, checkpoint.lease, undefined);
      if (cleanup) throw cleanup;
      return { result, provider_call_id: providerCallID };
    }
    if (reservation.status === "finalized") {
      throw runtimeFailure(
        "LLM_PROVIDER_CALL_ALREADY_FINALIZED",
        "Pi writer provider call is already finalized and requires run recovery",
        resolution.module_key
      );
    }
    lease = await deps.acquireLLMLease({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      module_key: resolution.module_key,
      channel_id: resolution.channel_id,
      model_id: resolution.model_id,
      module_max_concurrency: positiveIntegerSetting(resolution.settings, "max_concurrency")
    });
    const result = await execute(credential.apiKey, providerCallID);
    const usage = validateProviderUsage(result.usage);
    providerUsageObserved = true;
    await deps.saveProviderStageCheckpoint?.({
      provider_call_id: providerCallID,
      result,
      reservation,
      lease
    });
    await deps.finalizeLLMQuota!({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      reservation_id: reservation.reservation_id,
      provider_call_id: providerCallID,
      prompt_tokens: usage.prompt_tokens,
      completion_tokens: usage.completion_tokens,
      actual_cost_micros: usageCostMicros(usage, budget.pricing_status),
      pricing_status: budget.pricing_status
    });
    const cleanup = await releaseStageResources(deps, input, lease, undefined);
    lease = undefined;
    if (cleanup) throw cleanup;
    return { result, provider_call_id: providerCallID };
  } catch (error) {
    const failure = normalizeStageFailure(error, resolution.module_key);
    const cleanup = await releaseStageResources(
      deps,
      input,
      lease,
      reservation?.status === "reserved" && !providerUsageObserved ? reservation : undefined
    );
    lease = undefined;
    reservation = undefined;
    const surfaced = cleanup
      ? runtimeFailure(cleanup.code, `${failure.message}; ${cleanup.message}`, resolution.module_key)
      : failure;
    await deps.recordLLMActivity({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      module_key: resolution.module_key,
      channel_id: resolution.channel_id,
      model_id: resolution.model_id,
      provider_call_id: providerCallID,
      status: "failed",
      error: { code: surfaced.code, message: surfaced.message }
    }).catch(() => undefined);
    throw surfaced;
  }
}

function composeRequest(
  input: WriterRunInput,
  resolution: ResolvedLLMModule,
  apiKey: string,
  providerCallID: string,
  abortSignal?: AbortSignal
): ComposeDraftRequest {
  return {
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    module_key: resolution.module_key,
    channel_id: resolution.channel_id,
    model_id: resolution.model_id,
    provider: resolution.provider,
    base_url: resolution.base_url,
    instruction: input.instruction,
    mode: input.mode,
    revise: input.options.revise,
    target_words: input.options.target_words,
    thinking_level: input.options.thinking_level,
    apiKey,
    settings: resolution.settings,
    provider_call_id: providerCallID,
    abort_signal: abortSignal
  };
}

async function recordStageTelemetry(
  deps: PiWriterRunActivityDeps,
  input: WriterRunInput,
  resolution: ResolvedLLMModule,
  usage: PiWriterUsage | undefined,
  latency: number,
  providerCallID: string
): Promise<void> {
  await deps.recordLLMActivity({
    tenant_id: input.tenant_id, project_id: input.project_id, run_id: input.run_id,
    module_key: resolution.module_key, channel_id: resolution.channel_id, model_id: resolution.model_id,
    provider_call_id: providerCallID,
    status: "completed", prompt_tokens: usage?.prompt_tokens, completion_tokens: usage?.completion_tokens,
    latency_ms: latency, cost_estimate: usage?.cost_estimate
  });
}

function assertQuotaDeps(deps: PiWriterRunActivityDeps, moduleKey: string): void {
  if (!deps.reserveLLMQuota || !deps.finalizeLLMQuota || !deps.releaseLLMQuota) {
    throw runtimeFailure(
      "LLM_QUOTA_BACKEND_UNCONFIGURED",
      "Pi writer LLM quota backend is not configured",
      moduleKey
    );
  }
}

async function releaseStageResources(
  deps: PiWriterRunActivityDeps,
  input: WriterRunInput,
  lease?: LLMLease,
  reservation?: LLMQuotaReservation
): Promise<RuntimeFailure | undefined> {
  const failures: RuntimeFailure[] = [];
  if (lease) {
    try {
      await boundedCleanup(() => deps.releaseLLMLease({
        ...lease,
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id
      }));
    } catch {
      failures.push(runtimeFailure("LLM_CONCURRENCY_RELEASE_FAILED", "Pi writer LLM concurrency lease release failed"));
    }
  }
  if (reservation && deps.releaseLLMQuota) {
    try {
      await boundedCleanup(() => deps.releaseLLMQuota!({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        reservation_id: reservation.reservation_id,
        provider_call_id: reservation.provider_call_id
      }));
    } catch {
      failures.push(runtimeFailure("LLM_QUOTA_RELEASE_FAILED", "Pi writer LLM quota reservation release failed"));
    }
  }
  if (!failures.length) return undefined;
  return runtimeFailure(
    failures[0]!.code,
    failures.map((failure) => failure.message).join("; ")
  );
}

async function boundedCleanup(cleanup: () => Promise<void>): Promise<void> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    await Promise.race([
      cleanup(),
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error("cleanup timed out")), 5_000);
      })
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

function normalizeStageFailure(error: unknown, moduleKey: string): RuntimeFailure {
  if (error instanceof RuntimeFailure) return error;
  const code = errorCode(error) || "LLM_PROVIDER_ERROR";
  const messages: Record<string, string> = {
    LLM_CONCURRENCY_LIMITED: "Pi writer LLM concurrency is limited",
    LLM_QUOTA_POLICY_UNAVAILABLE: "Pi writer LLM quota policy is unavailable",
    LLM_QUOTA_PRICING_UNAVAILABLE: "Pi writer LLM pricing is required by the active quota policy",
    LLM_QUOTA_TOKENS_EXCEEDED: "Pi writer LLM token quota is exceeded",
    LLM_QUOTA_COST_EXCEEDED: "Pi writer LLM cost quota is exceeded",
    LLM_QUOTA_CONCURRENCY_EXCEEDED: "Pi writer LLM quota concurrency is exceeded",
    LLM_PROVIDER_USAGE_MISSING: "Pi writer provider usage is unavailable",
    LLM_PROVIDER_USAGE_INVALID: "Pi writer provider usage is invalid",
    LLM_PROVIDER_COST_MISSING: "Pi writer provider cost usage is unavailable",
    LLM_PROVIDER_COST_INVALID: "Pi writer provider cost usage is invalid",
    LLM_QUOTA_FINALIZE_FAILED: "Pi writer LLM quota finalization failed"
  };
  return runtimeFailure(code, messages[code] ?? "Pi writer provider call failed", moduleKey);
}

function resolutionSummary(resolution: ResolvedLLMModule): Record<string, unknown> {
  return { module_key: resolution.module_key, channel_id: resolution.channel_id, model_id: resolution.model_id, provider: resolution.provider };
}

class RuntimeFailure extends Error {
  constructor(readonly code: string, message: string, readonly module_key?: string) { super(message); }
}

function runtimeFailure(code: string, message: string, moduleKey?: string): RuntimeFailure {
  return new RuntimeFailure(code, message, moduleKey);
}

function normalizeRuntimeFailure(error: unknown): RuntimeFailure {
  return error instanceof RuntimeFailure ? error : runtimeFailure("LLM_PROVIDER_ERROR", "Pi writer runtime dependency failed");
}

function errorCode(error: unknown): string {
  if (!(error instanceof Error)) return "";
  const match = /^([A-Z][A-Z0-9_]+):/.exec(error.message);
  return match?.[1] ?? "";
}

function errorMessageText(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function combineUsage(first?: PiWriterUsage, second?: PiWriterUsage): PiWriterUsage {
  return {
    prompt_tokens: (first?.prompt_tokens ?? 0) + (second?.prompt_tokens ?? 0),
    completion_tokens: (first?.completion_tokens ?? 0) + (second?.completion_tokens ?? 0),
    cost_estimate: (first?.cost_estimate ?? 0) + (second?.cost_estimate ?? 0)
  };
}
