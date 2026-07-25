/**
 * Present backend errors to the author in Chinese. The Go API and the agent
 * runtime emit English error codes/messages (e.g. "workflow run is not
 * retryable"); the workbench never surfaces raw English to the author. Map by
 * error code first (stable), then by known English-message fragments, falling
 * back to a calm generic line rather than leaking the raw text.
 */

const CODE_MESSAGES: Record<string, string> = {
  WORKFLOW_RETRY_NOT_ALLOWED: "这次分析暂时重试不了。请刷新页面看最新状态；若仍是失败，稍后重试或重新上传。",
  WORKFLOW_RETRY_BACKEND_UNCONFIGURED: "重试服务暂时不可用，请稍后再试。",
  RUNTIME_FACTS_WRITE_FAILED: "写入故事事实失败。已读出的部分不会丢，修好后可重试。",
  READING_NOTES_WRITE_FAILED: "写入精读笔记失败。已读出的部分不会丢，修好后可重试。",
  SCHEMA_VALIDATION_FAILED: "分析返回的内容格式不正确。这通常是模型输出不稳定，可重试。",
  READING_NOTES_WRITER_UNCONFIGURED: "分析存储服务未配置好，请联系管理员。",
  RUNTIME_FACTS_WRITER_UNCONFIGURED: "分析存储服务未配置好，请联系管理员。",
  WORKFLOW_RUN_NOT_FOUND: "找不到这次分析记录。",
  AUTH_ACCESS_DENIED: "没有权限执行这个操作。",
  TENANT_REQUIRED: "缺少工作区上下文，请返回书架重新进入项目。",
  FORBIDDEN: "没有权限执行这个操作。",
  VALIDATION_FAILED: "请求内容不完整或不正确。",
};

const ENGLISH_FRAGMENT_MESSAGES: Array<[RegExp, string]> = [
  [/not retryable/i, "这次分析暂时重试不了。请刷新页面看最新状态；若仍是失败，稍后重试或重新上传。"],
  [/runtime facts write failed/i, "写入故事事实失败。已读出的部分不会丢，修好后可重试。"],
  [/reading notes write failed/i, "写入精读笔记失败。已读出的部分不会丢，修好后可重试。"],
  [/schema validation/i, "分析返回的内容格式不正确。这通常是模型输出不稳定，可重试。"],
  [/workflow run is not found|not found/i, "找不到这次分析记录。"],
  [/access is denied|forbidden/i, "没有权限执行这个操作。"],
  [/unconfigured/i, "相关服务未配置好，请联系管理员。"],
  [/timeout|timed out/i, "请求超时，请稍后再试。"],
  [/network|fetch failed|failed to fetch/i, "网络连接异常，请检查网络后重试。"],
];

/** True when a string looks like raw English/technical output we should not show. */
function looksTechnical(message: string): boolean {
  // Mostly-ASCII with no CJK characters => treat as a technical/English message.
  return !/[一-鿿]/.test(message) && /[A-Za-z]/.test(message);
}

/**
 * Localize an unknown error for author display. `fallback` is used when we can
 * neither map the code nor recognize the message.
 */
export function presentError(error: unknown, fallback: string): string {
  if (error == null) return fallback;
  const code = (error as { code?: unknown }).code;
  if (typeof code === "string" && code && CODE_MESSAGES[code]) {
    return CODE_MESSAGES[code];
  }
  const raw = error instanceof Error ? error.message : typeof error === "string" ? error : "";
  if (!raw) return fallback;
  if (!looksTechnical(raw)) return raw; // already Chinese / author-facing
  for (const [pattern, message] of ENGLISH_FRAGMENT_MESSAGES) {
    if (pattern.test(raw)) return message;
  }
  return fallback;
}
