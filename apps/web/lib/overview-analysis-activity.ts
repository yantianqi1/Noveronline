import { formatBeijingTime } from "./beijing-time";
import { type Locale, tx } from "./locale";
import type { WorkflowRunEvent } from "./api";
import { scrubInternalRuntimeBranding } from "./user-facing-copy";

export type OverviewActivityLogLine = {
  id: string;
  tone: "running" | "done" | "failed" | "info";
  message: string;
  timeLabel: string | null;
};

export const ANALYSIS_PIPELINE_STAGE_ORDER = [
  "bootstrap",
  "preprocess",
  "analysis_planner",
  "analysis_worker",
  "candidates",
  "finalize",
] as const;

export const ANALYSIS_STAGE_PROGRESS: Record<string, number> = {
  bootstrap: 8,
  preprocess: 20,
  analysis_planner: 45,
  analysis_worker: 85,
  candidates: 95,
  finalize: 100,
};

export function analysisStageLabel(locale: Locale, stage: string) {
  const labels: Record<string, [string, string]> = {
    bootstrap: ["准备分析工作区", "Prepare analysis workspace"],
    preprocess: ["读取并分段原文", "Read and segment source"],
    analysis_planner: ["规划分析任务", "Plan analysis tasks"],
    analysis_worker: ["执行文本拆解", "Run text analysis"],
    candidates: ["整理并入库", "Collect and import"],
    finalize: ["收尾", "Finalize"],
  };
  const pair = labels[stage];
  return pair ? tx(locale, pair[0], pair[1]) : stage;
}

export function analysisStageFromEvent(event: {
  event_type: string;
  payload: Record<string, unknown>;
}): string | null {
  if (typeof event.payload?.stage === "string" && event.payload.stage.trim()) {
    const stage = event.payload.stage.trim();
    if (stage === "analysis_planner" || stage === "analysis_worker") return stage;
    if (stage in ANALYSIS_STAGE_PROGRESS) return stage;
  }
  if (event.event_type === "analysis.run.started" || event.event_type === "workflow.queued") {
    return "bootstrap";
  }
  if (event.event_type === "analysis.file.written") {
    const path = typeof event.payload?.path === "string" ? event.payload.path : "";
    if (path.startsWith("10-source/")) return "preprocess";
    if (path.startsWith("00-plan/")) return "analysis_planner";
    if (path.startsWith("20-notes/") || path.startsWith("30-candidates/") || path.startsWith("90-review/")) {
      return "analysis_worker";
    }
    return "bootstrap";
  }
  if (
    event.event_type === "analysis.stage.started"
    || event.event_type === "analysis.stage.completed"
    || event.event_type === "analysis.stage.failed"
  ) {
    const stage = typeof event.payload?.stage === "string" ? event.payload.stage : "";
    return stage || null;
  }
  if (event.event_type === "analysis.candidates.saved") return "candidates";
  if (event.event_type === "analysis.assets.imported") return "candidates";
  if (event.event_type === "analysis.run.completed") return "finalize";
  if (event.event_type === "analysis.run.failed") return "finalize";
  if (event.event_type.startsWith("analysis.tool.")) {
    const stage = typeof event.payload?.stage === "string" ? event.payload.stage : "";
    return stage || "analysis_worker";
  }
  return null;
}

export function publicAnalysisFailureHint(locale: Locale, code: string) {
  if (code === "LLM_MODULE_CAPABILITY_MISSING") {
    return tx(
      locale,
      "绑定模型不支持结构化输出，请在模型设置中换用支持工具/JSON 的模型后重试。",
      "The bound model lacks required capability. Bind a tools/JSON-capable model and retry.",
    );
  }
  if (code === "LLM_QUOTA_RESERVATION_UNAVAILABLE") {
    return tx(
      locale,
      "模型已绑定，但预算预留失败：缺少输出上限或模型上下文窗口。",
      "Quota reservation failed: set an output limit and context window metadata.",
    );
  }
  if (code === "LLM_PROVIDER_ERROR") {
    return tx(
      locale,
      "模型服务调用失败。请确认通道地址、密钥与模型名称可用后重试。",
      "The model provider call failed. Verify channel URL, API key, and model name, then retry.",
    );
  }
  if (code === "LLM_MODULE_UNBOUND") {
    return tx(
      locale,
      "分析所需模型尚未绑定。若已连接写作模型，请点「重试」自动补齐；或到模型设置绑定「分析规划 / 分析执行」。",
      "Analysis modules are unbound. Retry to inherit from your writing model, or bind Analysis Planner/Worker in model settings.",
    );
  }
  if (code === "ANALYSIS_RUNTIME_UNCONFIGURED") {
    return tx(
      locale,
      "分析服务暂不可用，请稍后重试。",
      "The analysis service is temporarily unavailable. Try again shortly.",
    );
  }
  if (code === "SOURCE_TEXT_UNAVAILABLE" || code === "SOURCE_SEGMENTS_EMPTY") {
    return tx(
      locale,
      "无法读取上传小说正文。请确认文件已上传成功，且为 txt/md 纯文本后重试。",
      "Could not read the uploaded novel text. Confirm plain text/markdown upload, then retry.",
    );
  }
  if (code === "SOURCE_FORMAT_UNSUPPORTED") {
    return tx(
      locale,
      "当前分析仅支持纯文本/Markdown 上传。",
      "Analysis currently supports plain text/Markdown uploads only.",
    );
  }
  if (code === "OBJECT_STORAGE_UNCONFIGURED" || code === "OBJECT_STORAGE_READ_FAILED") {
    return tx(
      locale,
      "对象存储读取失败，分析 worker 无法拿到原文。",
      "Object storage read failed; the analysis worker could not load the source text.",
    );
  }
  if (code === "LLM_CREDENTIAL_UNCONFIGURED") {
    return tx(
      locale,
      "模型通道密钥不可用。请到模型设置检查通道密钥。",
      "The model channel credential is unavailable. Check channel keys in settings.",
    );
  }
  if (code === "ANALYSIS_ARTIFACTS_INCOMPLETE") {
    return tx(
      locale,
      "分析未产出完整结果，请重试。",
      "Analysis did not produce complete results. Please retry.",
    );
  }
  if (code === "TOOL_PERMISSION_DENIED") {
    return tx(
      locale,
      "分析收尾写入权限不足（已修复）。请直接点「重试」完成入库。",
      "Analysis finish lacked write permission (now fixed). Retry to complete import.",
    );
  }
  return "";
}

export function analysisActivityLineFromEvent(
  locale: Locale,
  event: WorkflowRunEvent,
): OverviewActivityLogLine | null {
  const timeLabel = formatBeijingTime(locale, event.created_at);
  const stage = analysisStageFromEvent(event);
  const stageLabel = stage ? analysisStageLabel(locale, stage) : "";
  const payloadMessage = typeof event.payload?.message === "string"
    ? scrubInternalRuntimeBranding(event.payload.message.trim())
    : "";
  const path = typeof event.payload?.path === "string" ? event.payload.path : "";

  if (event.event_type === "workflow.queued") {
    return {
      id: event.event_id || `queued-${event.sequence}`,
      tone: "info",
      message: tx(locale, "任务已入队", "Run queued"),
      timeLabel: timeLabel || null,
    };
  }
  if (event.event_type === "analysis.run.started") {
    return {
      id: event.event_id || `started-${event.sequence}`,
      tone: "running",
      message: tx(locale, "分析已开始", "Analysis started"),
      timeLabel: timeLabel || null,
    };
  }
  if (event.event_type === "analysis.stage.started" && stageLabel) {
    return {
      id: event.event_id || `stage-start-${event.sequence}`,
      tone: "running",
      message: payloadMessage || tx(locale, `开始：${stageLabel}`, `Starting: ${stageLabel}`),
      timeLabel: timeLabel || null,
    };
  }
  if (event.event_type === "analysis.stage.completed" && stageLabel) {
    return {
      id: event.event_id || `stage-done-${event.sequence}`,
      tone: "done",
      message: payloadMessage || tx(locale, `完成：${stageLabel}`, `Completed: ${stageLabel}`),
      timeLabel: timeLabel || null,
    };
  }
  if (event.event_type === "analysis.stage.failed" && stageLabel) {
    const errorCode = typeof event.payload?.error_code === "string" ? event.payload.error_code : "";
    const hint = errorCode ? publicAnalysisFailureHint(locale, errorCode) : "";
    const scrubbed = /could not determine data type of parameter|parse_param|42P08|permission denied for table/i.test(payloadMessage)
      ? ""
      : payloadMessage;
    return {
      id: event.event_id || `stage-fail-${event.sequence}`,
      tone: "failed",
      message: scrubbed
        || (hint
          ? tx(locale, `${stageLabel}失败：${hint}`, `${stageLabel} failed: ${hint}`)
          : tx(locale, `${stageLabel}失败`, `${stageLabel} failed`)),
      timeLabel: timeLabel || null,
    };
  }
  if (event.event_type === "analysis.tool.started" || event.event_type === "analysis.tool.completed") {
    const toolName = typeof event.payload?.tool_name === "string" && event.payload.tool_name.trim()
      ? event.payload.tool_name.trim()
      : "tool";
    const isError = event.payload?.is_error === true;
    const started = event.event_type === "analysis.tool.started";
    return {
      id: event.event_id || `tool-${event.sequence}`,
      tone: started ? "running" : isError ? "failed" : "done",
      message: `tool_${toolName}`,
      timeLabel: timeLabel || null,
    };
  }
  if (event.event_type === "analysis.file.written") {
    // Plan / notes / candidates / review are the author-visible decomposition trail.
    if (
      path.startsWith("00-plan/")
      || path.startsWith("20-notes/")
      || path.startsWith("30-candidates/")
      || path.startsWith("90-review/")
    ) {
      return {
        id: event.event_id || `file-${event.sequence}`,
        tone: "info",
        message: tx(locale, `产出：${path}`, `Produced: ${path}`),
        timeLabel: timeLabel || null,
      };
    }
    return null;
  }
  if (event.event_type === "analysis.candidates.saved") {
    const count = typeof event.payload?.candidate_count === "number" ? event.payload.candidate_count : 0;
    return {
      id: event.event_id || `candidates-${event.sequence}`,
      tone: "done",
      message: tx(locale, `已整理 ${count} 项拆解结果`, `Saved ${count} analysis results`),
      timeLabel: timeLabel || null,
    };
  }
  if (event.event_type === "analysis.assets.imported") {
    const count = typeof event.payload?.asset_count === "number"
      ? event.payload.asset_count
      : typeof event.payload?.candidate_count === "number"
        ? event.payload.candidate_count
        : 0;
    return {
      id: event.event_id || `assets-imported-${event.sequence}`,
      tone: "done",
      message: tx(locale, `已自动入库 ${count} 项素材`, `Auto-imported ${count} materials into Assets`),
      timeLabel: timeLabel || null,
    };
  }
  if (event.event_type === "analysis.run.completed") {
    return {
      id: event.event_id || `completed-${event.sequence}`,
      tone: "done",
      message: tx(locale, "分析完成，素材已入库", "Analysis completed; materials imported"),
      timeLabel: timeLabel || null,
    };
  }
  if (event.event_type === "analysis.run.failed") {
    const errorCode = typeof event.payload?.error_code === "string" ? event.payload.error_code : "";
    const hint = errorCode ? publicAnalysisFailureHint(locale, errorCode) : "";
    const raw = payloadMessage;
    const scrubbed = /could not determine data type of parameter|parse_param|42P08|permission denied for table/i.test(raw)
      ? ""
      : raw;
    return {
      id: event.event_id || `failed-${event.sequence}`,
      tone: "failed",
      message: scrubbed || hint || tx(locale, "分析失败", "Analysis failed"),
      timeLabel: timeLabel || null,
    };
  }
  return null;
}

export function analysisActivityLogFromEvents(
  locale: Locale,
  events: readonly WorkflowRunEvent[],
  limit = 36,
): OverviewActivityLogLine[] {
  const lines: OverviewActivityLogLine[] = [];
  for (const event of events) {
    const line = analysisActivityLineFromEvent(locale, event);
    if (line) lines.push(line);
  }
  // Newest first so the latest step is always visible at the top.
  const newestFirst = [...lines].reverse();
  if (newestFirst.length <= limit) return newestFirst;
  return newestFirst.slice(0, limit);
}

export function mergeWorkflowRunEvents(
  existing: readonly WorkflowRunEvent[],
  incoming: readonly WorkflowRunEvent[],
): WorkflowRunEvent[] {
  if (incoming.length === 0) return [...existing];
  const byId = new Map<string, WorkflowRunEvent>();
  for (const event of existing) {
    if (event.event_id) byId.set(event.event_id, event);
  }
  for (const event of incoming) {
    if (event.event_id) byId.set(event.event_id, event);
  }
  return [...byId.values()].sort((a, b) => {
    if (a.sequence !== b.sequence) return a.sequence - b.sequence;
    return a.created_at.localeCompare(b.created_at);
  });
}

export function latestWorkflowEventId(events: readonly WorkflowRunEvent[]): string {
  let latest = "";
  let sequence = -1;
  for (const event of events) {
    if (typeof event.sequence === "number" && event.sequence >= sequence && event.event_id) {
      sequence = event.sequence;
      latest = event.event_id;
    }
  }
  return latest;
}

export function analysisStreamReachedTerminal(events: readonly WorkflowRunEvent[]): boolean {
  return events.some((event) =>
    event.event_type === "analysis.run.completed"
    || event.event_type === "analysis.run.failed"
    || event.event_type === "analysis.run.cancelled"
  );
}
