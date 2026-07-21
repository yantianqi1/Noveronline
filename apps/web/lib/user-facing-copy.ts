import { type Locale, tx } from "./locale";

/**
 * Author-facing copy helpers. Internal error codes and IDs stay off the default UI;
 * use data-code attributes or Technical Details for diagnostics.
 */

const FAILURE_MESSAGES: Record<string, [string, string]> = {
  UNAUTHENTICATED: ["请先登录后再试。", "Sign in and try again."],
  FORBIDDEN: ["你没有权限执行此操作。", "You do not have permission for this action."],
  VALIDATION_FAILED: ["请检查填写内容后重试。", "Check the form and try again."],
  NOT_FOUND: ["找不到请求的内容。", "The requested item was not found."],
  RATE_LIMITED: ["操作过于频繁，请稍后再试。", "Too many attempts. Try again shortly."],
  AUTH_RECOVERY_RATE_LIMITED: ["重置请求过于频繁，请稍后再试。", "Reset requests are limited. Try again shortly."],
  PASSWORD_LOGIN_FAILED: ["邮箱或密码不正确。", "Email or password is incorrect."],
  PASSWORD_RESET_TOKEN_INVALID: ["重置链接无效，请重新申请。", "This reset link is invalid. Request a new one."],
  PASSWORD_RESET_TOKEN_EXPIRED: ["重置链接已过期，请重新申请。", "This reset link expired. Request a new one."],
  PASSWORD_RESET_TOKEN_ALREADY_USED: ["重置链接已使用，请重新申请。", "This reset link was already used. Request a new one."],
  LLM_BINDING_UPDATE_FAILED: ["模型绑定未能保存。", "Could not save the model binding."],
  LLM_BINDING_CLEAR_FAILED: ["未能恢复默认绑定。", "Could not restore the default binding."],
  LLM_BINDING_BATCH_UPDATED: ["批量绑定已更新。", "Batch bindings updated."],
  LLM_BINDING_TARGET_NOT_FOUND: ["所选渠道与模型不匹配，请先同步模型。", "Channel and model do not match. Sync models first."],
  LLM_CHANNEL_CREATE_FAILED: ["渠道创建失败。", "Could not create the channel."],
  LLM_CHANNEL_UPDATE_FAILED: ["渠道更新失败。", "Could not update the channel."],
  LLM_MODELS_SYNC_FAILED: ["模型同步失败。", "Could not sync models."],
  LLM_MODEL_UPDATE_FAILED: ["模型设置更新失败。", "Could not update the model."],
  LLM_QUOTA_POLICY_UNAVAILABLE: ["缺少调用预算策略。", "A usage budget policy is missing."],
  LLM_QUOTA_RESERVATION_UNAVAILABLE: [
    "模型额度暂时不可用，请检查模型设置中的输出上限与上下文窗口后重试。",
    "Model quota reservation is unavailable. Check output limits and context window in model settings, then retry.",
  ],
  LLM_QUOTA_RESERVATION_CLOSED: [
    "上次额度预留已关闭，请重试。若仍失败，检查模型通道是否可用。",
    "The previous quota reservation closed. Retry, or check that the model channel is available.",
  ],
  LLM_QUOTA_EXCEEDED: ["调用额度已用尽。", "Token quota has been exceeded."],
  LLM_QUOTA_TOKENS_EXCEEDED: ["调用额度已用尽。", "Token quota has been exceeded."],
  LLM_QUOTA_COST_EXCEEDED: ["调用费用额度已用尽。", "Cost quota has been exceeded."],
  LLM_QUOTA_CONCURRENCY_EXCEEDED: ["并发调用已达上限，请稍后再试。", "Concurrency limit reached. Try again shortly."],
  WORLDLINE_PREPARATION_NOT_SELECTED: [
    "尚未选择世界线准备会话，请先选择或创建推演。",
    "No worldline preparation is selected. Choose or create a simulation first.",
  ],
  WORLDLINE_SESSION_NOT_SELECTED: [
    "尚未载入世界线会话，请选择或创建世界线后开始推演。",
    "No worldline session is loaded. Select or create a worldline to continue.",
  ],
  PROVIDER_UNAVAILABLE: ["模型服务暂时不可用。", "The model provider is temporarily unavailable."],
  RATE_LIMIT_BACKEND_UNAVAILABLE: ["服务暂时繁忙，请稍后再试。", "The service is busy. Try again shortly."],
  WORKFLOW_FAILED: ["写作任务未能启动，请检查 Writer 模型绑定与服务状态。", "Could not start the writer run. Check Writer model bindings and service status."],
  WORKFLOW_START_FAILED: ["写作任务未能启动，请稍后重试。", "Could not start the writer run. Try again shortly."],
  TEMPORAL_UNAVAILABLE: ["写作队列服务暂不可用，请稍后重试。", "The writer queue is temporarily unavailable. Try again shortly."],
  PI_WRITER_UNAVAILABLE: ["写作助手暂时不可用，请稍后重试。", "The writing assistant is temporarily unavailable. Try again shortly."],
  MODULE_BINDING_MISSING: ["尚未绑定「正文创作」模型，请先到模型设施完成绑定。", "Writer composer is unbound. Bind a model in LLM facility first."],
  LLM_MODULE_BINDING_MISSING: ["尚未绑定「正文创作」模型，请先到模型设施完成绑定。", "Writer composer is unbound. Bind a model in LLM facility first."],
  MODULE_NOT_BOUND: ["尚未绑定「正文创作」模型，请先到模型设施完成绑定。", "Writer composer is unbound. Bind a model in LLM facility first."],
  LLM_MODULE_UNBOUND: ["写作相关模型未绑定，请到模型设施绑定「写作编排」与「正文创作」。", "Writer modules are unbound. Bind Writer orchestrator and composer in LLM facility."],
  LLM_MODEL_TOOLS_UNSUPPORTED: [
    "「写作编排」绑定的模型不支持工具调用。请到模型设施为 writer_orchestrator 更换支持 tools 的对话模型（如 DeepSeek Chat / GPT），或重新同步模型后重试。",
    "The Writer orchestrator model does not support tool calling. In LLM facility, bind writer_orchestrator to a chat model with tools (e.g. DeepSeek Chat / GPT), or re-sync models.",
  ],
  LLM_PROVIDER_ERROR: ["模型服务返回错误，请检查渠道与模型绑定后重试。", "The model provider returned an error. Check channel and model bindings, then retry."],
  WRITER_RUN_FAILED: ["写作任务失败，请查看活动时间线后重试。", "Writer run failed. Check the activity timeline and retry."],
  WRITER_WORKSPACE_UNAVAILABLE: ["手稿工作区服务暂不可用。", "Manuscript workspace is temporarily unavailable."],
  WRITER_WORKSPACE_INVALID_RESPONSE: ["手稿工作区返回异常，请刷新后重试。", "Manuscript workspace returned an unexpected response. Refresh and retry."],
  OPTIMISTIC_CONFLICT: ["正文版本冲突：请比较本地草稿与服务端正文后再保存。", "Manuscript version conflict. Compare local draft with server content, then save."],
  HTTP_400: ["请求无效，请检查章节/场景是否仍存在。", "Invalid request. Check that the chapter or scene still exists."],
  HTTP_401: ["请先登录后再试。", "Sign in and try again."],
  HTTP_403: ["你没有权限执行此操作。", "You do not have permission for this action."],
  HTTP_404: ["找不到对应的章节、场景或片段。", "Chapter, scene, or manuscript section was not found."],
  HTTP_409: ["正文版本冲突，请刷新后重试。", "Manuscript version conflict. Refresh and try again."],
  HTTP_500: ["服务内部错误，请稍后重试。", "Internal service error. Try again shortly."],
  HTTP_502: ["上游服务暂不可用，请稍后重试。", "Upstream service is temporarily unavailable. Try again shortly."],
  HTTP_503: ["服务暂不可用，请稍后重试。", "Service is temporarily unavailable. Try again shortly."],
};

const STATUS_LABELS: Record<string, [string, string]> = {
  active: ["进行中", "Active"],
  adopted: ["已采纳", "Adopted"],
  archived: ["已归档", "Archived"],
  billing_ready: ["可计费", "Billing ready"],
  cancelled: ["已取消", "Cancelled"],
  candidate: ["候选", "Candidate"],
  canon: ["正史", "Canon"],
  completed: ["已完成", "Completed"],
  disabled: ["已停用", "Disabled"],
  draft: ["草稿", "Draft"],
  enabled: ["已启用", "Enabled"],
  error: ["错误", "Error"],
  exceeded: ["已超额", "Exceeded"],
  expired: ["已过期", "Expired"],
  failed: ["失败", "Failed"],
  finalized: ["已结算", "Finalized"],
  healthy: ["连接正常", "Healthy"],
  idle: ["空闲", "Idle"],
  pending: ["等待中", "Pending"],
  pricing_unavailable: ["缺少价格", "Pricing unavailable"],
  queued: ["排队中", "Queued"],
  released: ["已释放", "Released"],
  reserved: ["已预留", "Reserved"],
  running: ["运行中", "Running"],
  success: ["成功", "Success"],
  unavailable: ["不可用", "Unavailable"],
  unconfigured: ["未配置", "Unconfigured"],
  unbound: ["未绑定", "Unbound"],
};

const MODULE_LABELS: Record<string, [string, string]> = {
  anchor_point_summary: ["锚点摘要", "Anchor point summary"],
  asset_ingestion: ["资产导入", "Asset ingestion"],
  asset_search_embedding: ["资产检索向量", "Asset search embedding"],
  character_agent_profile: ["角色档案", "Character profile"],
  contextual_block_analysis: ["上下文文本分析", "Contextual block analysis"],
  entity_resolution: ["实体消歧", "Entity resolution"],
  graph_bond_generator: ["图谱关系生成", "Graph bond generator"],
  local_block_facts: ["局部文本事实", "Local block facts"],
  narrative_archives: ["叙事档案", "Narrative archives"],
  novel_chapter_summarizer: ["章节摘要", "Chapter summarizer"],
  parallel_world_config: ["世界线配置", "Worldline config"],
  sequential_reading: ["顺序精读", "Sequential reading"],
  story_ontology: ["故事本体", "Story ontology"],
  style_extractor: ["风格提取", "Style extractor"],
  worldline_agent_action: ["世界线角色行动", "Worldline agent action"],
  worldline_agent_dialogue: ["世界线角色对话", "Worldline agent dialogue"],
  worldline_agent_prepare: ["世界线角色准备", "Worldline agent preparation"],
  worldline_character_proposal: ["世界线角色提案", "Worldline character proposal"],
  worldline_director: ["世界线导演", "Worldline director"],
  worldline_goal_evaluator: ["世界线目标评估", "Worldline goal evaluator"],
  writer_book_planner: ["书籍计划", "Book planner"],
  writer_composer: ["正文创作", "Writer composer"],
  writer_dedup_extractor: ["重复风险提取", "Dedup extractor"],
  writer_orchestrator: ["写作编排", "Writer orchestrator"],
  writer_retrieval_planner: ["写作检索规划", "Retrieval planner"],
  writer_reviewer: ["写作审校", "Writer reviewer"],
};

export function humanizeFailure(
  locale: Locale,
  code: string | null | undefined,
  fallbackMessage?: string,
): string {
  const normalized = (code || "").trim().toUpperCase();
  const mapped = FAILURE_MESSAGES[normalized];
  if (mapped) {
    return tx(locale, mapped[0], mapped[1]);
  }
  const fromMessage = inferFailureCodeFromMessage(fallbackMessage);
  if (fromMessage) {
    const inferred = FAILURE_MESSAGES[fromMessage];
    if (inferred) {
      return tx(locale, inferred[0], inferred[1]);
    }
  }
  if (fallbackMessage && !looksLikeInternalCode(fallbackMessage) && !looksLikeProviderDiagnostic(fallbackMessage)) {
    return scrubInternalRuntimeBranding(fallbackMessage);
  }
  return tx(locale, "操作未完成，请稍后重试。", "The action could not be completed. Try again shortly.");
}

/**
 * Strip internal runtime vendor names (e.g. Pi) from author-visible copy.
 * Error codes / package paths may still mention them; UI strings must not.
 */
export function scrubInternalRuntimeBranding(message: string): string {
  return message
    .replace(/\bPi\s+Writer\b/gi, "写作助手")
    .replace(/\bPi\s+[Aa]gent\b/g, "智能助手")
    .replace(/\bPi\s+analysis\b/gi, "analysis")
    .replace(/\bPi\s+worker\b/gi, "analysis service")
    .replace(/\bPi\s+智能体/g, "智能助手")
    .replace(/\bPi\s+分析/g, "分析")
    .replace(/\bPi\s+拆解/g, "拆解")
    .replace(/\bPi\s+规划/g, "规划")
    .replace(/\bPi\s+执行/g, "执行")
    .replace(/\bPi\s+Writer\b/g, "写作助手")
    .trim();
}

/** Map common provider/runtime diagnostics into stable failure codes. */
function inferFailureCodeFromMessage(message: string | null | undefined): string | null {
  if (!message) {
    return null;
  }
  const lower = message.toLowerCase();
  if (lower.includes("must support tools") || lower.includes("support tools")) {
    return "LLM_MODEL_TOOLS_UNSUPPORTED";
  }
  if (lower.includes("module is not bound") || lower.includes("llm_module_unbound")) {
    return "LLM_MODULE_UNBOUND";
  }
  if (lower.includes("pi writer") || lower.includes("pi-agent-runtime") || lower.includes("pi writer unavailable")) {
    return "PI_WRITER_UNAVAILABLE";
  }
  return null;
}

function looksLikeProviderDiagnostic(message: string): boolean {
  const lower = message.toLowerCase();
  return (
    lower.includes("binding must") ||
    lower.includes("llm_provider") ||
    lower.includes("writer_orchestrator") ||
    lower.includes(" · ")
  );
}

export function statusLabel(locale: Locale, value: string | null | undefined): string {
  const normalized = (value || "").trim().toLowerCase();
  if (!normalized) {
    return tx(locale, "—", "—");
  }
  const mapped = STATUS_LABELS[normalized];
  if (mapped) {
    return tx(locale, mapped[0], mapped[1]);
  }
  return humanizeToken(value || "");
}

export function moduleLabel(locale: Locale, moduleKey: string, fallback?: string): string {
  const mapped = MODULE_LABELS[moduleKey];
  if (mapped) {
    return tx(locale, mapped[0], mapped[1]);
  }
  if (fallback && fallback !== moduleKey && !looksLikeInternalCode(fallback)) {
    return fallback;
  }
  return humanizeToken(moduleKey);
}

export function shortId(value: string | null | undefined, visible = 8): string {
  const text = (value || "").trim();
  if (!text) {
    return "—";
  }
  if (text.length <= visible + 2) {
    return text;
  }
  return `${text.slice(0, visible)}…`;
}

export function providerHealthSummary(
  locale: Locale,
  input: {
    status: string;
    latency_ms?: number;
    supports_tools?: boolean;
    supports_json?: boolean;
  },
): string {
  const status = statusLabel(locale, input.status);
  const latency = typeof input.latency_ms === "number"
    ? tx(locale, `约 ${Math.round(input.latency_ms)}ms`, `~${Math.round(input.latency_ms)}ms`)
    : "";
  // When capability flags are absent, do not claim the provider lacks tools/JSON —
  // that was a false catalog default, not a live probe result.
  const tools = input.supports_tools
    ? tx(locale, "支持工具调用", "Tools supported")
    : input.supports_tools === false
      ? tx(locale, "目录标记：工具调用未启用", "Catalog: tools not marked")
      : "";
  const json = input.supports_json
    ? tx(locale, "支持 JSON", "JSON supported")
    : input.supports_json === false
      ? tx(locale, "目录标记：JSON 未启用", "Catalog: JSON not marked")
      : "";
  return [status, latency, tools, json].filter(Boolean).join(" · ");
}

function looksLikeInternalCode(value: string): boolean {
  const text = value.trim();
  if (!text) {
    return false;
  }
  if (/^[A-Z][A-Z0-9_]{2,}$/.test(text)) {
    return true;
  }
  if (/^[a-z]+(_[a-z0-9]+)+$/.test(text)) {
    return true;
  }
  return false;
}

function humanizeToken(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}
