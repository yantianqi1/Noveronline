import { formatSessionScope } from "../../utils/chineseDisplay.js";

const IDLE_STATUS = Object.freeze({ label: "未创建会话", tone: "warn" });
const READY_STATUS = Object.freeze({ label: "会话已启动", tone: "ok" });
const PREPARE_ERROR_STATUS = Object.freeze({ label: "整备失败", tone: "danger" });
const ERROR_STATUS = Object.freeze({ label: "操作异常", tone: "danger" });
const PENDING_SCOPE_TEXT = "待创建";

export function countWorldlineVariables(text = "") {
  return text.split("\n").map(line => line.trim()).filter(Boolean).length;
}

export function resolveWorldlineSessionStatus({ sessionId = "", error = "" } = {}) {
  if (error) {
    return sessionId ? ERROR_STATUS : PREPARE_ERROR_STATUS;
  }
  if (sessionId) {
    return READY_STATUS;
  }
  return IDLE_STATUS;
}

export function resolvePrepareTaskMessage({ prepareSnapshot = null, error = "" } = {}) {
  if (prepareSnapshot?.error) {
    return prepareSnapshot.error;
  }
  if (error) {
    return error;
  }
  if (prepareSnapshot?.task_message) {
    return prepareSnapshot.task_message;
  }
  if (prepareSnapshot?.status === "ready") {
    return "所有 agent 已完成 LLM 整备，可以直接开始推演。";
  }
  return "正在为当前世界线物化完整 agent dossier。";
}

function resolveScopeText(sessionId, sessionScope) {
  if (!sessionId) {
    return PENDING_SCOPE_TEXT;
  }
  return formatSessionScope(sessionScope);
}

export function buildWorldlineSessionSummary({
  selectedArchives = [],
  variablesText = "",
  sessionId = "",
  sessionScope = "",
} = {}) {
  return [
    { label: "已选档案", value: `${selectedArchives.length} 份` },
    { label: "初始变量", value: `${countWorldlineVariables(variablesText)} 条` },
    { label: "会话范围", value: resolveScopeText(sessionId, sessionScope) },
  ];
}
