type Locale = "zh-CN" | "en";

/**
 * Centralized author-language mapping (docs/refactor-saas/35, "统一作者词典").
 *
 * Author-facing surfaces must never echo internal tool keys, enum values, or
 * error names. Unknown values fall back to a safe generic label; raw values
 * are only visible inside the authorized Technical Details drawer.
 *
 * Kept free of Next/locale module imports so Node focused tests can import this
 * file with `--experimental-strip-types`.
 */

function tx(locale: Locale, zh: string, en: string): string {
  return locale === "en" ? en : zh;
}

const TOOL_LABELS: Record<string, { zh: string; en: string }> = {
  query_project_context: { zh: "查看本书设定", en: "Reviewing story bible" },
  query_chapter_scene: { zh: "查看章节与场景", en: "Reviewing chapters and scenes" },
  query_assets: { zh: "查找人物与设定", en: "Looking up characters and lore" },
  query_manuscript_context: { zh: "查看前文", en: "Reading earlier passages" },
  query_world_rules: { zh: "核对世界规则", en: "Checking world rules" },
  query_character_profile: { zh: "核对人物设定", en: "Checking character profiles" },
  query_graph_neighbors: { zh: "核对人物关系", en: "Checking relationships" },
  query_worldline_paths: { zh: "参考剧情推演", en: "Consulting worldline paths" },
  save_draft_revision: { zh: "保存修改建议", en: "Saving the suggestion" },
};

/** Author-facing label for a writer tool. Unknown tools use a generic label. */
export function authorToolLabel(locale: Locale, toolName: string): string {
  const entry = TOOL_LABELS[toolName];
  if (entry) {
    return tx(locale, entry.zh, entry.en);
  }
  return tx(locale, "处理写作请求", "Working on the request");
}

/** Author-facing run status label. Unknown statuses fall back to a safe value. */
export function authorRunStatusLabel(locale: Locale, status: string): string {
  switch (status) {
    case "queued":
      return tx(locale, "等待开始", "Waiting to start");
    case "running":
      return tx(locale, "正在处理", "In progress");
    case "completed":
      return tx(locale, "已完成", "Completed");
    case "failed":
      return tx(locale, "未完成", "Did not finish");
    case "cancelled":
      return tx(locale, "已取消", "Cancelled");
    default:
      return tx(locale, "正在处理", "In progress");
  }
}

/**
 * Collapsed task-status-line labels (docs/refactor-saas/36 §4.3 / §5.2).
 * One short line; never echoes tool keys, event IDs, or byte counts.
 */
export type TaskStatusPhase =
  | "idle"
  | "understanding"
  | "retrieving"
  | "drafting"
  | "saving"
  | "completed"
  | "failed"
  | "cancelled"
  | "awaiting_approval"
  | "revision_ready"
  | "reconnecting"
  | "interrupted";

export function authorTaskStatusLine(
  locale: Locale,
  phase: TaskStatusPhase,
  extras?: { toolCompletedCount?: number; draftCharCount?: number; failureDetail?: string },
): string {
  const tools = extras?.toolCompletedCount ?? 0;
  const chars = extras?.draftCharCount ?? 0;
  switch (phase) {
    case "idle":
      return tx(locale, "等待指令", "Ready for direction");
    case "understanding":
      return tx(locale, "正在分析需求", "Understanding the request");
    case "retrieving":
      return tools > 0
        ? tx(locale, `正在查阅资料 · 已完成 ${tools} 项`, `Looking up context · ${tools} done`)
        : tx(locale, "正在查阅资料", "Looking up context");
    case "drafting":
      return chars > 0
        ? tx(locale, `正在起草正文 · ${chars} 字`, `Drafting prose · ${chars} characters`)
        : tx(locale, "正在起草正文", "Drafting prose");
    case "saving":
      return tx(locale, "正在保存候选稿", "Saving candidate draft");
    case "completed":
      return chars > 0
        ? tx(locale, `已完成 · 生成候选稿 ${chars} 字`, `Completed · candidate draft ${chars} characters`)
        : tx(locale, "已完成", "Completed");
    case "failed":
      return extras?.failureDetail
        ? tx(locale, `未完成 · ${extras.failureDetail}`, `Did not finish · ${extras.failureDetail}`)
        : tx(locale, "未完成", "Did not finish");
    case "cancelled":
      return tx(locale, "已取消", "Cancelled");
    case "awaiting_approval":
      return tx(locale, "等待你的确认", "Waiting for your confirmation");
    case "revision_ready":
      return tx(locale, "修改建议已准备好", "Revision suggestion is ready");
    case "reconnecting":
      return tx(locale, "连接中断，正在重连…", "Connection interrupted, reconnecting…");
    case "interrupted":
      return tx(locale, "实时更新已中断", "Live updates interrupted");
    default:
      return tx(locale, "正在处理", "In progress");
  }
}
