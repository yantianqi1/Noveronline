/**
 * 种子管线四大章节定义与 stage→chapter 映射。
 * 与 backend/app/services/seed_pipeline_chapters.py 保持同步。
 */

export const PIPELINE_CHAPTERS = [
  {
    key: "text_prep",
    label: "文本准备",
    stages: ["uploading", "extract_text", "segment_chapters", "build_blocks"],
  },
  {
    key: "world_scan",
    label: "世界扫描",
    stages: ["skeleton_timeline", "anchor_generation"],
  },
  {
    key: "fact_extract",
    label: "事实提取",
    stages: [
      "extract_local_facts",
      "merge_story_memory",
      "entity_resolution",
      "contextual_block_analysis",
      "chapter_card_generation",
      "consistency_audit",
      "build_continuity",
    ],
  },
  {
    key: "output_settle",
    label: "成果沉淀",
    stages: ["seed_analysis", "ontology", "completed", "failed"],
  },
];

export const STAGE_TO_CHAPTER = Object.fromEntries(
  PIPELINE_CHAPTERS.flatMap((ch) => ch.stages.map((s) => [s, ch.key])),
);

export const CHAPTER_LABELS = Object.fromEntries(
  PIPELINE_CHAPTERS.map((ch) => [ch.key, ch.label]),
);

/**
 * 将 timeline 事件按 group_key 分组到章节，并计算每章节汇总。
 * @param {Array} timeline - 已标准化的 timeline 事件数组
 * @returns {Array<{key, label, status, steps, stepCount, elapsedMs, llmCallCount}>}
 */
export function buildChapterViewModel(timeline, activeStageKey = "") {
  const activeChapterKey = STAGE_TO_CHAPTER[activeStageKey] || "";
  const chapterMap = new Map();

  for (const ch of PIPELINE_CHAPTERS) {
    chapterMap.set(ch.key, {
      key: ch.key,
      label: ch.label,
      status: "pending",
      steps: [],
      stepCount: 0,
      elapsedMs: 0,
      llmCallCount: 0,
    });
  }

  // 收集有 step_id 的 complete 事件作为步骤
  for (const event of timeline) {
    const groupKey = event.meta?.group_key;
    const stepId = event.meta?.step_id;
    if (!groupKey || !stepId) continue;

    const chapter = chapterMap.get(groupKey);
    if (!chapter) continue;

    // 只取 complete 事件作为步骤计数来源（start 事件不重复统计）
    if (event.status === "completed") {
      chapter.steps.push({
        stepId,
        stepKind: event.meta?.step_kind || "",
        title: event.title || "",
        stage: event.stage || "",
        status: "completed",
        elapsedMs: event.meta?.elapsed_ms || 0,
        llmCallCount: event.meta?.llm_call_count || 0,
        hasTrace: event.meta?.has_trace || false,
        timestamp: event.timestamp || "",
      });
      chapter.elapsedMs += event.meta?.elapsed_ms || 0;
      chapter.llmCallCount += event.meta?.llm_call_count || 0;
    } else if (event.status === "active") {
      // 活动中步骤
      chapter.steps.push({
        stepId,
        stepKind: event.meta?.step_kind || "",
        title: event.title || "",
        stage: event.stage || "",
        status: "active",
        elapsedMs: 0,
        llmCallCount: 0,
        hasTrace: false,
        timestamp: event.timestamp || "",
      });
    }
  }

  // 去重（一个 step_id 可能出现 start + complete 两条事件）
  for (const chapter of chapterMap.values()) {
    const seen = new Map();
    for (const step of chapter.steps) {
      const existing = seen.get(step.stepId);
      if (!existing || step.status === "completed") {
        seen.set(step.stepId, step);
      }
    }
    chapter.steps = Array.from(seen.values());
    chapter.stepCount = chapter.steps.length;
  }

  // 推算章节状态
  for (const chapter of chapterMap.values()) {
    const hasActive = chapter.steps.some((s) => s.status === "active");
    const hasCompleted = chapter.steps.some((s) => s.status === "completed");
    if (hasActive || chapter.key === activeChapterKey) {
      chapter.status = "active";
    } else if (hasCompleted) {
      chapter.status = "completed";
    }
  }

  return Array.from(chapterMap.values());
}
