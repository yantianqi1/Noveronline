import { validateWriterWorkflowPayload } from "../worker-spec.js";
import type { WriterRunInput } from "../contracts/writer-run.js";

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
  apiKey: string;
  settings: Record<string, unknown>;
}

export interface ComposeDraftResult {
  content: string;
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
    | "writer.run.failed"
    | "writer.run.completed"
    | "writer.run.cancelled";
  payload: Record<string, unknown>;
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

export interface PiWriterRunActivityDeps {
  resolveCredential(request: CredentialRequest): Promise<Credential>;
  acquireLLMLease(request: AcquireLLMLeaseRequest): Promise<LLMLease>;
  composeDraft(request: ComposeDraftRequest): Promise<ComposeDraftResult>;
  releaseLLMLease(request: ReleaseLLMLeaseRequest): Promise<void>;
  saveDraftRevision(request: SaveDraftRevisionRequest): Promise<SaveDraftRevisionResult>;
  recordLLMActivity(request: RecordLLMActivityRequest): Promise<void>;
  recordUsageEvent(request: RecordUsageEventRequest): Promise<void>;
  recordAgentTraceEvent(request: RecordAgentTraceEventRequest): Promise<void>;
  recordWorkflowEvent(request: RecordWorkflowEventRequest): Promise<void>;
  updateWriterRunStatus(request: UpdateWriterRunStatusRequest): Promise<void>;
}

export function createPiWriterRunActivity(deps: Partial<PiWriterRunActivityDeps> = {}) {
  return async function runPiWriterRunActivity(payload: unknown): Promise<PiWriterActivityResult> {
    const input = validateWriterWorkflowPayload(payload);
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
      const saved = await runPiWriterStep("Pi writer draft persistence failed", () => activityDeps.saveDraftRevision({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        content: draft.content,
        status: "candidate",
        metadata: {
          module_key: resolution.module_key,
          channel_id: resolution.channel_id,
          model_id: resolution.model_id,
          provider: resolution.provider
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
