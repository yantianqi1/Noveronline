import { createHash } from "node:crypto";

import type { AgentEvent, ToolExecutionMode } from "@earendil-works/pi-agent-core";

import {
  type AnalysisModuleKey,
  type AnalysisRunInput,
  type AnalysisToolName
} from "../contracts/analysis-run.js";
import { validateAnalysisWorkflowPayload } from "../contracts/analysis-worker-spec.js";
import { extractAnalysisCandidatesFromWorkspaceFiles } from "../runtime/analysis-candidate-extract.js";

export interface PiAnalysisActivityResult {
  tenant_id: string;
  project_id: string;
  run_id: string;
  status: "completed" | "failed";
  candidate_count?: number;
  file_count?: number;
  usage?: PiAnalysisUsage;
  error?: {
    code: string;
    message: string;
  };
}

export interface PiAnalysisUsage {
  prompt_tokens?: number;
  completion_tokens?: number;
  cost_estimate?: number;
}

export interface AnalysisLLMResolution {
  module_key: AnalysisModuleKey;
  channel_id: string;
  model_id: string;
  provider: string;
  base_url: string;
  credential_ref: string;
  supports_tools: boolean;
  supports_json: boolean;
  settings: Record<string, unknown>;
}

export interface ResolveAnalysisModuleRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  module_key: AnalysisModuleKey;
}

export interface AnalysisToolRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  tool_name: AnalysisToolName;
  args?: Record<string, unknown>;
}

export interface WorkspaceFileWriteInput {
  tenant_id: string;
  project_id: string;
  run_id: string;
  path: string;
  kind: string;
  content: string;
  mime_type?: string;
}

export interface WorkspaceFileRecord {
  path: string;
  kind: string;
  size_bytes: number;
  content_sha256: string;
  content_text?: string;
}

export interface AnalysisCandidateInput {
  tenant_id: string;
  project_id: string;
  run_id: string;
  candidate_type: string;
  name: string;
  payload: Record<string, unknown>;
  workspace_path?: string;
}

export interface SourceSegmentRecord {
  segment_index: number;
  title?: string;
  char_count?: number;
  preview?: string;
}

export interface PiAnalysisDeps {
  resolveModuleBinding?(request: ResolveAnalysisModuleRequest): Promise<AnalysisLLMResolution>;
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
  }): Promise<{ reservation_id: string; finalize(usage: PiAnalysisUsage): Promise<void> }>;
  runAnalysisStage?(request: AnalysisStageRequest): Promise<AnalysisStageResult>;
  executeAnalysisTool?(request: AnalysisToolRequest): Promise<Record<string, unknown>>;
  writeWorkspaceFile?(input: WorkspaceFileWriteInput): Promise<WorkspaceFileRecord>;
  listWorkspaceFiles?(input: { tenant_id: string; project_id: string; run_id: string }): Promise<WorkspaceFileRecord[]>;
  listSourceSegments?(input: { tenant_id: string; project_id: string; source_file_id?: string; limit?: number }): Promise<SourceSegmentRecord[]>;
  readSourceSegment?(input: {
    tenant_id: string;
    project_id: string;
    segment_index: number;
    source_file_id?: string;
  }): Promise<{ segment_index: number; content: string }>;
  saveAnalysisCandidates?(input: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    replace_run?: boolean;
    import_to_assets?: boolean;
    candidates: Array<{ candidate_type: string; name: string; payload: Record<string, unknown>; workspace_path?: string }>;
  }): Promise<{ candidate_count: number; asset_count?: number }>;
  preprocessSource?(input: AnalysisRunInput & {
    source_object_key?: string;
    source_filename?: string;
    source_mime_type?: string;
    source_size_bytes?: number;
    source_sha256?: string;
  }): Promise<{ segment_count: number }>;
  recordWorkflowEvent?(event: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    event_type: string;
    payload: Record<string, unknown>;
    idempotency_key?: string;
  }): Promise<void>;
  updateAnalysisRunStatus?(input: {
    tenant_id: string;
    project_id: string;
    run_id: string;
    status: "running" | "completed" | "failed" | "cancelled";
    error_code?: string;
    error_message?: string;
    result?: Record<string, unknown>;
  }): Promise<void>;
  findCompletedAnalysisRun?(input: {
    tenant_id: string;
    project_id: string;
    run_id: string;
  }): Promise<PiAnalysisActivityResult | null>;
  cancellationSignal?(): AbortSignal | undefined;
}

export interface AnalysisStageRequest {
  tenant_id: string;
  project_id: string;
  run_id: string;
  module_key: AnalysisModuleKey;
  channel_id: string;
  model_id: string;
  provider: string;
  base_url: string;
  apiKey: string;
  instruction: string;
  mode: AnalysisRunInput["mode"];
  hints: Record<string, unknown>;
  thinking_level?: AnalysisRunInput["options"]["thinking_level"];
  tool_execution?: ToolExecutionMode;
  tool_names: AnalysisToolName[];
  settings: Record<string, unknown>;
  provider_call_id?: string;
  abort_signal?: AbortSignal;
  executeTool(toolName: AnalysisToolName, toolCallId: string, args?: Record<string, unknown>): Promise<Record<string, unknown>>;
  onAgentEvent?(event: AgentEvent): Promise<void>;
  onToken?(token: string): Promise<void>;
}

export interface AnalysisStageResult {
  summary: string;
  usage?: PiAnalysisUsage;
}

const PLANNER_TOOLS: AnalysisToolName[] = [
  "list_workspace_files",
  "read_workspace_file",
  "list_source_segments",
  "write_workspace_file",
  "update_todo"
];

const WORKER_TOOLS: AnalysisToolName[] = [
  "list_workspace_files",
  "read_workspace_file",
  "list_source_segments",
  "read_source_segment",
  "write_workspace_file",
  "update_todo"
];

export function createPiAnalysisRunActivity(deps: PiAnalysisDeps = {}) {
  return async function runPiAnalysisRunActivity(payload: unknown): Promise<PiAnalysisActivityResult> {
    const input = validateAnalysisWorkflowPayload(payload);
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
      const completed = await deps.findCompletedAnalysisRun?.({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id
      });
      if (completed) {
        return completed;
      }

      await deps.updateAnalysisRunStatus?.({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "running"
      });
      await record("analysis.run.started", { status: "running" }, "run:started");

      // Bootstrap workspace plan files before LLM stages.
      await record("analysis.stage.started", {
        stage: "bootstrap",
        status: "running"
      }, "stage:bootstrap:started");
      await bootstrapWorkspace(deps, input, payload as Record<string, unknown>);
      await record("analysis.stage.completed", {
        stage: "bootstrap",
        status: "completed"
      }, "stage:bootstrap:completed");

      await record("analysis.stage.started", {
        stage: "preprocess",
        status: "running"
      }, "stage:preprocess:started");
      if (!deps.preprocessSource) {
        throw Object.assign(new Error("ANALYSIS_RUNTIME_UNCONFIGURED: source preprocess is unavailable"), {
          code: "ANALYSIS_RUNTIME_UNCONFIGURED"
        });
      }
      const preprocess = await deps.preprocessSource({
        ...input,
        source_object_key: optionalString((payload as Record<string, unknown>).source_object_key),
        source_filename: optionalString((payload as Record<string, unknown>).source_filename),
        source_mime_type: optionalString((payload as Record<string, unknown>).source_mime_type),
        source_size_bytes: typeof (payload as Record<string, unknown>).source_size_bytes === "number"
          ? (payload as Record<string, unknown>).source_size_bytes as number
          : undefined,
        source_sha256: optionalString((payload as Record<string, unknown>).source_sha256)
      });
      await record("analysis.file.written", {
        path: "10-source/manifest.json",
        kind: "source_manifest",
        segment_count: preprocess.segment_count
      }, "preprocess:manifest");
      await record("analysis.stage.completed", {
        stage: "preprocess",
        status: "completed",
        segment_count: preprocess.segment_count
      }, "stage:preprocess:completed");

      const usage: PiAnalysisUsage = {};
      await runStage(deps, input, "analysis_planner", PLANNER_TOOLS, usage, record);
      await runStage(deps, input, "analysis_worker", WORKER_TOOLS, usage, record);

      const files = await deps.listWorkspaceFiles?.({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id
      }) ?? [];
      assertRequiredWorkspaceArtifacts(files);
      await record("analysis.stage.started", {
        stage: "candidates",
        status: "running"
      }, "stage:candidates:started");
      const candidates = await finalizeCandidates(deps, input, files);
      await record("analysis.candidates.saved", {
        candidate_count: candidates.candidate_count,
        asset_count: candidates.asset_count ?? candidates.candidate_count,
        file_count: files.length
      }, "candidates:saved");
      await record("analysis.assets.imported", {
        candidate_count: candidates.candidate_count,
        asset_count: candidates.asset_count ?? candidates.candidate_count,
        status: "completed"
      }, "assets:imported");
      await record("analysis.stage.completed", {
        stage: "candidates",
        status: "completed",
        candidate_count: candidates.candidate_count,
        asset_count: candidates.asset_count ?? candidates.candidate_count
      }, "stage:candidates:completed");
      await record("analysis.stage.started", {
        stage: "finalize",
        status: "running"
      }, "stage:finalize:started");
      await record("analysis.run.completed", {
        status: "completed",
        candidate_count: candidates.candidate_count,
        asset_count: candidates.asset_count ?? candidates.candidate_count,
        file_count: files.length
      }, "run:completed");
      await record("analysis.stage.completed", {
        stage: "finalize",
        status: "completed"
      }, "stage:finalize:completed");
      await deps.updateAnalysisRunStatus?.({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "completed",
        result: {
          candidate_count: candidates.candidate_count,
          asset_count: candidates.asset_count ?? candidates.candidate_count,
          file_count: files.length
        }
      });
      return {
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "completed",
        candidate_count: candidates.candidate_count,
        file_count: files.length,
        usage
      };
    } catch (error) {
      const code = errorCode(error);
      const message = errorMessage(error);
      await record("analysis.run.failed", { error_code: code, message }, "run:failed");
      await deps.updateAnalysisRunStatus?.({
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "failed",
        error_code: code,
        error_message: message
      });
      return {
        tenant_id: input.tenant_id,
        project_id: input.project_id,
        run_id: input.run_id,
        status: "failed",
        error: { code, message }
      };
    }
  };
}

// Default export for Temporal worker registration when deps are not injected.
export async function runPiAnalysisRunActivity(payload: unknown): Promise<PiAnalysisActivityResult> {
  return createPiAnalysisRunActivity()(payload);
}

async function bootstrapWorkspace(
  deps: PiAnalysisDeps,
  input: AnalysisRunInput,
  rawPayload: Record<string, unknown>
): Promise<void> {
  const hints = {
    ...input.hints,
    mode: input.mode,
    upload_id: input.upload_id,
    source_file_id: input.source_file_id,
    source_filename: optionalString(rawPayload.source_filename)
  };
  const taskPack = [
    "# 分析任务包",
    "",
    `模式：${input.mode}`,
    "",
    "## 语言要求",
    "- 计划、笔记、候选摘要/描述/规则正文、复盘一律使用简体中文。",
    "- JSON 字段名保持英文；专有名词与原文引用保持原样。",
    "- 内容须详细，不得把原文丰富设定压缩成一句英文空话。",
    "",
    "## 作者指令",
    input.instruction,
    "",
    "## 提示",
    "```json",
    JSON.stringify(hints, null, 2),
    "```",
    "",
    "## 必交产出",
    "- 00-plan/todo.json",
    "- 20-notes/sequential/*.md（中文精读笔记）",
    "- 30-candidates/characters.json",
    "- 30-candidates/relationships.json",
    "- 30-candidates/world_rules.json",
    "- 90-review/summary.md"
  ].join("\n");
  const todo = {
    items: [
      { id: "plan", title: "撰写分析计划", status: "pending" },
      { id: "read", title: "阅读源文分段", status: "pending" },
      { id: "notes", title: "写顺序精读笔记", status: "pending" },
      { id: "candidates", title: "抽取候选资产", status: "pending" },
      { id: "review", title: "撰写复盘摘要", status: "pending" }
    ]
  };
  await deps.writeWorkspaceFile?.({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    path: "00-plan/hints.json",
    kind: "hints",
    content: JSON.stringify(hints, null, 2),
    mime_type: "application/json"
  });
  await deps.writeWorkspaceFile?.({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    path: "00-plan/task-pack.md",
    kind: "plan",
    content: taskPack,
    mime_type: "text/markdown"
  });
  await deps.writeWorkspaceFile?.({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    path: "00-plan/todo.json",
    kind: "todo",
    content: JSON.stringify(todo, null, 2),
    mime_type: "application/json"
  });
}

async function runStage(
  deps: PiAnalysisDeps,
  input: AnalysisRunInput,
  moduleKey: AnalysisModuleKey,
  toolNames: AnalysisToolName[],
  usage: PiAnalysisUsage,
  record: (event_type: string, payload: Record<string, unknown>, key?: string) => Promise<void>
): Promise<void> {
  if (!deps.resolveModuleBinding || !deps.runAnalysisStage) {
    throw Object.assign(
      new Error("ANALYSIS_RUNTIME_UNCONFIGURED: Pi analysis worker is missing LLM stage execution"),
      { code: "ANALYSIS_RUNTIME_UNCONFIGURED" }
    );
  }
  await record("analysis.stage.started", {
    stage: moduleKey,
    status: "running"
  }, `stage:${moduleKey}:started`);
  const resolution = await deps.resolveModuleBinding({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    module_key: moduleKey
  });
  const credential = await deps.resolveCredential?.({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    module_key: moduleKey,
    channel_id: resolution.channel_id,
    credential_ref: resolution.credential_ref
  });
  if (!credential?.apiKey) {
    throw Object.assign(new Error("LLM credential resolution failed"), {
      code: "LLM_CREDENTIAL_UNCONFIGURED"
    });
  }
  const providerCallId = analysisProviderCallId(input, moduleKey);
  const lease = await deps.acquireLLMLease?.({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    module_key: moduleKey,
    channel_id: resolution.channel_id,
    model_id: resolution.model_id
  });
  const reservation = await deps.reserveQuota?.({
    tenant_id: input.tenant_id,
    project_id: input.project_id,
    run_id: input.run_id,
    module_key: moduleKey,
    provider_call_id: providerCallId,
    estimated_tokens: 128_000
  });
  try {
    const stage = await deps.runAnalysisStage({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      module_key: moduleKey,
      channel_id: resolution.channel_id,
      model_id: resolution.model_id,
      provider: resolution.provider,
      base_url: resolution.base_url,
      apiKey: credential.apiKey,
      instruction: input.instruction,
      mode: input.mode,
      hints: input.hints,
      thinking_level: input.options.thinking_level,
      tool_execution: input.options.tool_execution,
      tool_names: toolNames,
      settings: resolution.settings,
      provider_call_id: providerCallId,
      abort_signal: deps.cancellationSignal?.(),
      executeTool: async (toolName, toolCallId, args) => {
        await record("analysis.tool.started", {
          tool_name: toolName,
          tool_call_id: toolCallId,
          stage: moduleKey
        }, `tool:${toolCallId}:started`);
        if (!deps.executeAnalysisTool) {
          throw Object.assign(new Error("ANALYSIS_RUNTIME_UNCONFIGURED: analysis tools are unavailable"), {
            code: "ANALYSIS_RUNTIME_UNCONFIGURED"
          });
        }
        const result = await deps.executeAnalysisTool({
          tenant_id: input.tenant_id,
          project_id: input.project_id,
          run_id: input.run_id,
          tool_name: toolName,
          args
        });
        await record("analysis.tool.completed", {
          tool_name: toolName,
          tool_call_id: toolCallId,
          stage: moduleKey,
          result: publicToolResult(result)
        }, `tool:${toolCallId}:completed`);
        if (toolName === "write_workspace_file" && typeof result.path === "string") {
          await record("analysis.file.written", {
            path: result.path,
            kind: result.kind,
            content_sha256: result.content_sha256,
            size_bytes: result.size_bytes,
            stage: moduleKey
          }, `file:${result.path}`);
        }
        return result;
      },
      onToken: async (token) => {
        await record("analysis.token", { token: token.slice(0, 64), stage: moduleKey });
      }
    });
    mergeUsage(usage, stage.usage);
    if (stage.usage) {
      await reservation?.finalize(stage.usage);
    }
    await record("analysis.stage.completed", {
      stage: moduleKey,
      status: "completed",
      summary: stage.summary.slice(0, 500)
    }, `stage:${moduleKey}:completed`);
  } catch (error) {
    await record("analysis.stage.failed", {
      stage: moduleKey,
      status: "failed",
      error_code: errorCode(error),
      message: errorMessage(error)
    }, `stage:${moduleKey}:failed`);
    throw error;
  } finally {
    await lease?.release();
  }
}

function analysisProviderCallId(input: AnalysisRunInput, moduleKey: string): string {
  const digest = createHash("sha256")
    .update([input.tenant_id, input.project_id, input.run_id, moduleKey].join("\0"))
    .digest("hex");
  return `pi-analysis:v1:${moduleKey}:${digest}`;
}

function assertRequiredWorkspaceArtifacts(files: WorkspaceFileRecord[]): void {
  const paths = new Set(files.map((file) => file.path));
  const required = [
    "00-plan/task-pack.md",
    "10-source/manifest.json",
    "30-candidates/characters.json",
    "90-review/summary.md"
  ];
  const missing = required.filter((path) => !paths.has(path));
  const hasNotes = [...paths].some((path) => path.startsWith("20-notes/"));
  if (missing.length > 0 || !hasNotes) {
    throw Object.assign(
      new Error(
        `ANALYSIS_ARTIFACTS_INCOMPLETE: missing ${[...missing, !hasNotes ? "20-notes/*" : ""].filter(Boolean).join(", ")}`
      ),
      { code: "ANALYSIS_ARTIFACTS_INCOMPLETE" }
    );
  }
  const characters = files.find((file) => file.path === "30-candidates/characters.json");
  if (characters?.content_text?.includes("Source placeholder")) {
    throw Object.assign(new Error("ANALYSIS_ARTIFACTS_INCOMPLETE: candidates still reference source placeholder"), {
      code: "ANALYSIS_ARTIFACTS_INCOMPLETE"
    });
  }
}

async function finalizeCandidates(
  deps: PiAnalysisDeps,
  input: AnalysisRunInput,
  files: WorkspaceFileRecord[]
): Promise<{ candidate_count: number; asset_count?: number }> {
  const candidates = extractAnalysisCandidatesFromWorkspaceFiles(files);
  if (deps.saveAnalysisCandidates) {
    return deps.saveAnalysisCandidates({
      tenant_id: input.tenant_id,
      project_id: input.project_id,
      run_id: input.run_id,
      replace_run: true,
      import_to_assets: true,
      candidates
    });
  }
  return { candidate_count: candidates.length };
}

function publicToolResult(value: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {};
  for (const key of ["path", "kind", "size_bytes", "content_sha256", "file_count", "segment_count", "candidate_count", "status", "ok"]) {
    if (key in value) out[key] = value[key];
  }
  return Object.keys(out).length > 0 ? out : { ok: true };
}

function mergeUsage(target: PiAnalysisUsage, source?: PiAnalysisUsage): void {
  if (!source) return;
  target.prompt_tokens = (target.prompt_tokens ?? 0) + (source.prompt_tokens ?? 0);
  target.completion_tokens = (target.completion_tokens ?? 0) + (source.completion_tokens ?? 0);
  target.cost_estimate = (target.cost_estimate ?? 0) + (source.cost_estimate ?? 0);
}

function optionalString(value: unknown): string | undefined {
  return typeof value === "string" && value.trim() !== "" ? value.trim() : undefined;
}

function errorCode(error: unknown): string {
  if (error && typeof error === "object" && "code" in error && typeof (error as { code: unknown }).code === "string") {
    const pgOrAppCode = (error as { code: string }).code;
    if (pgOrAppCode === "42P08" || pgOrAppCode.startsWith("LLM_") || pgOrAppCode.startsWith("ANALYSIS_") || pgOrAppCode.startsWith("SOURCE_") || pgOrAppCode.startsWith("OBJECT_") || pgOrAppCode.startsWith("TOOL_")) {
      if (pgOrAppCode === "42P08") return "ANALYSIS_RUNTIME_UNCONFIGURED";
      return pgOrAppCode;
    }
  }
  const message = errorMessage(error);
  if (/could not determine data type of parameter/i.test(message)) {
    return "ANALYSIS_RUNTIME_UNCONFIGURED";
  }
  if (message.includes("ANALYSIS_RUNTIME_UNCONFIGURED") || message.includes("UNCONFIGURED")) {
    return message.includes("LLM_CREDENTIAL") ? "LLM_CREDENTIAL_UNCONFIGURED" : "ANALYSIS_RUNTIME_UNCONFIGURED";
  }
  if (message.includes("LLM_MODULE_UNBOUND")) return "LLM_MODULE_UNBOUND";
  if (message.includes("LLM_MODULE_CAPABILITY_MISSING")) return "LLM_MODULE_CAPABILITY_MISSING";
  if (message.includes("provider") || message.includes("LLM_PROVIDER")) return "LLM_PROVIDER_ERROR";
  if (message.includes("permission")) return "TOOL_PERMISSION_DENIED";
  if (message.includes("OBJECT_STORAGE")) return "OBJECT_STORAGE_READ_FAILED";
  return "ANALYSIS_RUN_FAILED";
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    const message = error.message.trim();
    if (/could not determine data type of parameter/i.test(message)) {
      return "ANALYSIS_RUNTIME_UNCONFIGURED: analysis status update failed";
    }
    // Never leak raw Postgres/driver internals into author-facing workflow events.
    if (/^error:\s/i.test(message) || /\b42P\d{2}\b/.test(message) || /parse_param\.c/i.test(message)) {
      return "ANALYSIS_RUNTIME_UNCONFIGURED: analysis runtime persistence failed";
    }
    return message;
  }
  return "analysis run failed";
}
