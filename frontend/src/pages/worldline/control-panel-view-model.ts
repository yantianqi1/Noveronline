/**
 * Control panel view model: session status, summary, and prepare task message.
 *
 * Ported from: src-vue/views/worldline/worldlineControlPanelViewModel.js
 */

export interface SessionStatus {
  label: string;
  tone: "ok" | "warn" | "danger" | "default";
}

const IDLE_STATUS: SessionStatus = Object.freeze({
  label: "未创建会话",
  tone: "warn",
});
const READY_STATUS: SessionStatus = Object.freeze({
  label: "会话已启动",
  tone: "ok",
});
const PREPARE_ERROR_STATUS: SessionStatus = Object.freeze({
  label: "整备失败",
  tone: "danger",
});
const ERROR_STATUS: SessionStatus = Object.freeze({
  label: "操作异常",
  tone: "danger",
});

export function countWorldlineVariables(text = ""): number {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean).length;
}

export function resolveWorldlineSessionStatus(opts: {
  sessionId?: string;
  error?: string;
}): SessionStatus {
  const { sessionId = "", error = "" } = opts;
  if (error) return sessionId ? ERROR_STATUS : PREPARE_ERROR_STATUS;
  if (sessionId) return READY_STATUS;
  return IDLE_STATUS;
}

export function resolvePrepareTaskMessage(opts: {
  prepareSnapshot?: { error?: string; task_message?: string; status?: string } | null;
  error?: string;
}): string {
  const { prepareSnapshot = null, error = "" } = opts;
  if (prepareSnapshot?.error) return prepareSnapshot.error;
  if (error) return error;
  if (prepareSnapshot?.task_message) return prepareSnapshot.task_message;
  if (prepareSnapshot?.status === "ready") {
    return "所有 agent 已完成 LLM 整备，可以直接开始推演。";
  }
  return "正在为当前世界线物化完整 agent dossier。";
}

export interface SessionSummaryItem {
  label: string;
  value: string;
}

function resolveScopeText(sessionId: string, sessionScope: string): string {
  if (!sessionId) return "待创建";
  return sessionScope || "项目范围";
}

export function buildWorldlineSessionSummary(opts: {
  selectedArchives?: unknown[];
  variablesText?: string;
  sessionId?: string;
  sessionScope?: string;
}): SessionSummaryItem[] {
  const {
    selectedArchives = [],
    variablesText = "",
    sessionId = "",
    sessionScope = "",
  } = opts;
  return [
    { label: "已选档案", value: `${selectedArchives.length} 份` },
    {
      label: "初始变量",
      value: `${countWorldlineVariables(variablesText)} 条`,
    },
    {
      label: "会话范围",
      value: resolveScopeText(sessionId, sessionScope),
    },
  ];
}
