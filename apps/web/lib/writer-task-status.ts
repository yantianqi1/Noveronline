import type { WriterRunEvent } from "./api.ts";
import {
  authorTaskStatusLine,
  authorToolLabel,
  type TaskStatusPhase,
} from "./author-copy.ts";

type Locale = "zh-CN" | "en";

function tx(locale: Locale, zh: string, en: string): string {
  return locale === "en" ? en : zh;
}

export type TaskStatusStepStatus = "running" | "completed" | "failed" | "pending";

export type TaskStatusStep = {
  id: string;
  label: string;
  status: TaskStatusStepStatus;
};

export type WriterTaskStatusSummary = {
  phase: TaskStatusPhase;
  line: string;
  steps: TaskStatusStep[];
  draftCharCount: number;
  toolCompletedCount: number;
  terminal: boolean;
};

export type WriterConnectionHint = "streaming" | "reconnecting" | "interrupted" | "idle";

/**
 * Aggregate writer-run events into one collapsed status line + expandable steps.
 *
 * Connection interruptions override the in-flight phase so the author sees a single
 * narrative line instead of a separate connection banner + stage chip + timeline.
 *
 * Self-contained for Node `--experimental-strip-types` tests (no extensionless imports).
 */
export function summarizeWriterTaskStatus(
  locale: Locale,
  events: readonly WriterRunEvent[],
  connection: WriterConnectionHint = "idle",
): WriterTaskStatusSummary {
  const draftText = draftTextFromEvents(events);
  const draftCharCount = [...draftText].length;
  const toolCompletedCount = events.filter((event) => event.event_type === "writer.tool.completed").length;
  const steps = stepsFromEvents(locale, events);
  const phase = resolvePhase(events, connection, draftCharCount);
  const failureDetail = failureDetailFromEvents(locale, events);
  const line = authorTaskStatusLine(locale, phase, {
    toolCompletedCount,
    draftCharCount,
    failureDetail,
  });

  return {
    phase,
    line,
    steps,
    draftCharCount,
    toolCompletedCount,
    terminal: phase === "completed" || phase === "failed" || phase === "cancelled",
  };
}

function draftTextFromEvents(events: readonly WriterRunEvent[]): string {
  return [...events]
    .sort((left, right) => left.sequence - right.sequence)
    .filter((event) => event.event_type === "writer.token")
    .map((event) => stringField(event.payload, "token"))
    .join("");
}

function progressStage(events: readonly WriterRunEvent[]): number {
  const eventTypes = new Set(events.map((event) => event.event_type));
  if (eventTypes.has("writer.draft.saved") || eventTypes.has("writer.run.completed")) return 3;
  if (eventTypes.has("writer.token")) return 2;
  if (eventTypes.has("writer.tool.started") || eventTypes.has("writer.tool.completed")) return 1;
  return 0;
}

function resolvePhase(
  events: readonly WriterRunEvent[],
  connection: WriterConnectionHint,
  draftCharCount: number,
): TaskStatusPhase {
  const types = new Set(events.map((event) => event.event_type));

  if (types.has("writer.run.cancelled")) return "cancelled";
  if (types.has("writer.run.failed")) return "failed";
  if (types.has("writer.run.completed") || types.has("writer.draft.saved")) {
    if (hasUnresolvedApproval(events)) return "awaiting_approval";
    if (types.has("writer.revision.proposed") && !types.has("writer.run.completed")) {
      return "revision_ready";
    }
    return "completed";
  }
  if (hasUnresolvedApproval(events)) return "awaiting_approval";
  if (types.has("writer.revision.proposed")) return "revision_ready";

  if (connection === "reconnecting") return "reconnecting";
  if (connection === "interrupted") return "interrupted";

  const stage = progressStage(events);
  if (stage >= 3) return "saving";
  if (stage === 2 || draftCharCount > 0) return "drafting";
  if (stage === 1) return "retrieving";
  if (types.has("writer.run.started")) return "understanding";
  return "idle";
}

function hasUnresolvedApproval(events: readonly WriterRunEvent[]): boolean {
  const resolved = new Set<string>();
  for (const event of events) {
    if (event.event_type === "writer.approval.resolved") {
      const id = stringField(event.payload, "approval_id");
      if (id) resolved.add(id);
    }
  }
  for (const event of events) {
    if (event.event_type !== "writer.approval.required") continue;
    const id = stringField(event.payload, "approval_id") || event.event_id;
    if (!resolved.has(id)) return true;
  }
  return false;
}

/**
 * Prefer a short author-safe failure hint. Never echo SCREAMING_SNAKE codes.
 */
function failureDetailFromEvents(locale: Locale, events: readonly WriterRunEvent[]): string | undefined {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.event_type !== "writer.run.failed") continue;
    const message = stringField(event.payload, "message") || stringField(event.payload, "error");
    const code = stringField(event.payload, "error_code") || stringField(event.payload, "code");
    if (code === "LLM_MODEL_TOOLS_UNSUPPORTED" || /tools?/i.test(message)) {
      return tx(locale, "模型不支持工具调用", "Model does not support tools");
    }
    if (code === "LLM_MODULE_UNBOUND" || /not bound/i.test(message)) {
      return tx(locale, "写作助手尚未连接", "Writing assistant is not connected");
    }
    if (code === "LLM_PROVIDER_ERROR" || /provider/i.test(message)) {
      return tx(locale, "模型服务无法访问", "Model service unavailable");
    }
    if (message && !/^[A-Z][A-Z0-9_]+$/.test(message) && message.length <= 40) {
      return message;
    }
    return undefined;
  }
  return undefined;
}

/**
 * Expandable step list: author-language tool/write/approval rows only.
 * Collapsed line hides noise; the expand layer keeps the short author narrative.
 */
function stepsFromEvents(locale: Locale, events: readonly WriterRunEvent[]): TaskStatusStep[] {
  const steps: TaskStatusStep[] = [];
  const openTools = new Map<string, number>();

  for (const event of events) {
    if (event.event_type === "writer.token") continue;
    const payload = event.payload ?? {};

    if (event.event_type === "writer.tool.started") {
      const toolName = stringField(payload, "tool_name") || "tool";
      const step: TaskStatusStep = {
        id: event.event_id,
        label: authorToolLabel(locale, toolName),
        status: "running",
      };
      openTools.set(toolName, steps.length);
      steps.push(step);
      continue;
    }
    if (event.event_type === "writer.tool.completed") {
      const toolName = stringField(payload, "tool_name") || "tool";
      const isError = payload.is_error === true;
      const completed: TaskStatusStep = {
        id: event.event_id,
        label: authorToolLabel(locale, toolName),
        status: isError ? "failed" : "completed",
      };
      const openIndex = openTools.get(toolName);
      if (openIndex !== undefined && steps[openIndex]?.status === "running") {
        steps[openIndex] = { ...completed, id: steps[openIndex].id };
        openTools.delete(toolName);
      } else {
        steps.push(completed);
      }
      continue;
    }
    if (event.event_type === "writer.draft.saved") {
      steps.push({
        id: event.event_id,
        label: tx(locale, "保存候选稿", "Save candidate draft"),
        status: "completed",
      });
      continue;
    }
    if (event.event_type === "writer.revision.proposed") {
      steps.push({
        id: event.event_id,
        label: tx(locale, "准备修改建议", "Prepare revision"),
        status: "pending",
      });
      continue;
    }
    if (event.event_type === "writer.approval.required") {
      steps.push({
        id: event.event_id,
        label: tx(locale, "等待你的确认", "Waiting for your confirmation"),
        status: "pending",
      });
    }
  }

  return steps;
}

function stringField(payload: Record<string, unknown> | undefined, key: string): string {
  const value = payload?.[key];
  return typeof value === "string" ? value : "";
}
