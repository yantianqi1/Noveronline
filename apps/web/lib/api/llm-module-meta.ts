/**
 * Frontend-owned display metadata for every LLM module: a Chinese name, a
 * Chinese description, and a capability tier ("how strong a model does this
 * task actually need").
 *
 * Why this lives in the web app and not in Go: the registry
 * (apps/api/internal/llm/registry.go) ships English labels and has no notion
 * of capability tiers. Rather than touch the control plane, the settings
 * surface translates and grades every module here. The Go records stay the
 * source of truth for identity (module_key, group); this table is the source
 * of truth for how a module reads and how heavy it is.
 *
 * `tests/llm-module-meta.test.mjs` cross-checks this table against registry.go
 * so a module added upstream without a translation fails the suite loudly.
 */

/** How much model capability a module's workload demands, heaviest first. */
export type CapabilityTier = "heavy" | "high" | "standard" | "light";

export type ModuleMeta = {
  tier: CapabilityTier;
  /** Chinese display name. */
  labelZh: string;
  /** Chinese one-line description (shown on hover / as the row sub-label). */
  descZh: string;
};

/**
 * Display order + Chinese labels for the four capability tiers, heaviest
 * workload first so the user reads "needs the strongest model" at the top.
 */
export const TIER_ORDER: { key: CapabilityTier; label: string; hint: string }[] = [
  { key: "heavy", label: "极重推理", hint: "全书级规划与整合，需要最强模型" },
  { key: "high", label: "重推理", hint: "长程一致性与复杂决策，配主力模型" },
  { key: "standard", label: "均衡", hint: "常规生成与抽取，标准模型即可" },
  { key: "light", label: "轻任务", hint: "向量化、重排等机械任务，轻量模型够用" },
];

/**
 * The translation + grading table. One entry per module_key in registry.go —
 * coverage is enforced by test, so keep it complete when the registry grows.
 */
export const MODULE_META: Record<string, ModuleMeta> = {
  // ── Seed / Graph ──────────────────────────────────────────────────────
  story_ontology: { tier: "heavy", labelZh: "故事本体生成", descZh: "生成整部作品的故事本体框架。" },
  local_block_facts: { tier: "standard", labelZh: "局部事实抽取", descZh: "从文本块中抽取局部事实。" },
  contextual_block_analysis: { tier: "high", labelZh: "上下文块分析", descZh: "结合项目上下文分析文本块。" },
  anchor_point_summary: { tier: "standard", labelZh: "叙事锚点摘要", descZh: "对叙事锚点做摘要。" },
  entity_resolution: { tier: "standard", labelZh: "实体归一", descZh: "消解别名、归并出标准实体。" },
  novel_chapter_summarizer: { tier: "standard", labelZh: "章节摘要", descZh: "对章节级叙事状态做摘要。" },
  sequential_reading: { tier: "high", labelZh: "顺序通读", descZh: "按顺序通读原文并产出结构化笔记。" },
  analysis_planner: { tier: "heavy", labelZh: "分析任务规划", descZh: "规划小说分析任务并写入分析工作区任务包。" },
  analysis_worker: { tier: "standard", labelZh: "分析执行", descZh: "处理原文片段,把分析笔记与候选写入工作区。" },
  character_agent_profile: { tier: "high", labelZh: "角色档案生成", descZh: "为智能体生成角色档案。" },
  graph_bond_generator: { tier: "standard", labelZh: "图谱关系生成", descZh: "生成候选的图谱关联与关系。" },

  // ── Archive / Assets ──────────────────────────────────────────────────
  narrative_archives: { tier: "standard", labelZh: "叙事档案", descZh: "构建叙事档案记录。" },
  asset_ingestion: { tier: "standard", labelZh: "素材入库", descZh: "把自由素材整理入库为资产。" },
  asset_search_embedding: { tier: "light", labelZh: "检索向量化", descZh: "把资产检索 query 向量化,用于向量与混合检索。" },
  style_extractor: { tier: "standard", labelZh: "风格提取", descZh: "提取可复用的风格与语气资产。" },

  // ── Character Console ─────────────────────────────────────────────────
  character_dialogue: { tier: "high", labelZh: "角色对话", descZh: "生成角色对话回合与候选状态更新。" },

  // ── Worldline ─────────────────────────────────────────────────────────
  parallel_world_config: { tier: "standard", labelZh: "平行世界配置", descZh: "准备世界线运行配置。" },
  worldline_cast_planner: { tier: "high", labelZh: "世界线阵容规划", descZh: "分析推演目标,选出参与的智能体与上下文引用。" },
  worldline_agent_prepare: { tier: "standard", labelZh: "世界线角色准备", descZh: "准备世界线角色智能体。" },
  worldline_agent_dialogue: { tier: "standard", labelZh: "世界线角色对话", descZh: "生成世界线智能体的对话回合。" },
  worldline_character_proposal: { tier: "standard", labelZh: "角色行动提案", descZh: "在世界线运行中提出角色行动。" },
  worldline_director: { tier: "heavy", labelZh: "世界线导演", descZh: "调度世界线推演的每一步。" },
  worldline_agent_action: { tier: "standard", labelZh: "世界线角色行动", descZh: "生成世界线智能体的行动。" },
  worldline_goal_evaluator: { tier: "high", labelZh: "世界线目标评估", descZh: "评估世界线运行目标是否达成。" },

  // ── Writer ────────────────────────────────────────────────────────────
  writer_retrieval_planner: { tier: "standard", labelZh: "写作检索规划", descZh: "写作前规划检索。" },
  writer_retrieval_rerank: { tier: "light", labelZh: "检索重排", descZh: "成稿前对召回候选按相关性重排。" },
  writer_consistency: { tier: "high", labelZh: "一致性审校", descZh: "成稿后对照设定检查草稿矛盾。" },
  writer_orchestrator: { tier: "heavy", labelZh: "写作编排", descZh: "调用工具并组装写作上下文。" },
  writer_composer: { tier: "heavy", labelZh: "成稿写作", descZh: "根据写作简报撰写正文草稿。" },
  writer_dedup_extractor: { tier: "standard", labelZh: "重复模式提取", descZh: "从采用稿件中提取易重复的模式。" },
  writer_book_planner: { tier: "heavy", labelZh: "书籍规划", descZh: "为持久化的书籍草稿规划生成候选方案。" },
  writer_asset_distiller: { tier: "high", labelZh: "资产蒸馏", descZh: "把采用稿件蒸馏成带证据的候选资产。" },
  writer_reviewer: { tier: "high", labelZh: "稿件评审", descZh: "从风格、连贯性与重复度评审草稿。" },
};

/**
 * Display metadata for one module. Unknown keys (a module the registry added
 * before this table was updated) fall back to the raw key as the name and the
 * middle "standard" tier — the UI stays honest, and the coverage test fails so
 * the missing translation is surfaced rather than silently wrong.
 */
export function metaFor(moduleKey: string): ModuleMeta {
  return MODULE_META[moduleKey] ?? { tier: "standard", labelZh: moduleKey, descZh: "" };
}

/** The TIER_ORDER entry for a tier, for labels/hints/colours at the call site. */
export function tierInfo(tier: CapabilityTier): { key: CapabilityTier; label: string; hint: string } {
  return TIER_ORDER.find((t) => t.key === tier) ?? TIER_ORDER[TIER_ORDER.length - 1];
}

/**
 * Tailwind classes for one tier's dot / badge, reusing the existing semantic
 * tokens (no new colours): accent for the heaviest workload, warning for high,
 * neutral ink for standard, success for light. Both the group tabs and the
 * per-row badge read from this so the four tiers stay visually consistent.
 */
export const TIER_STYLES: Record<CapabilityTier, { dot: string; badge: string }> = {
  heavy: { dot: "bg-accent", badge: "bg-accent-wash text-accent-strong" },
  high: { dot: "bg-warning", badge: "bg-warning-wash text-warning" },
  standard: { dot: "bg-muted/70", badge: "bg-paper-deep text-muted" },
  light: { dot: "bg-success", badge: "bg-success-wash text-success" },
};
