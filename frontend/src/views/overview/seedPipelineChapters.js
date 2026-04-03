/**
 * 种子管线四大章节定义与 stage→chapter 映射。
 * 与 backend/app/services/seed_pipeline_chapters.py 保持同步。
 */

export const PIPELINE_CHAPTERS = [
  {
    key: "text_prep",
    label: "文本准备",
    stages: ["uploading", "extract_text", "smart_segmentation"],
  },
  {
    key: "deep_reading",
    label: "深度阅读",
    stages: ["sequential_reading", "arc_summary"],
  },
  {
    key: "integration",
    label: "全局整合",
    stages: ["global_integration", "ontology"],
  },
  {
    key: "agent_build",
    label: "角色构建",
    stages: ["agent_profiles", "completed", "failed"],
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

  // 收集有 step_id 的事件作为步骤
  // 跳过 note 类型的伪步骤（没有 trace bundle，只是信息记录）
  for (const event of timeline) {
    const groupKey = event.meta?.group_key;
    const stepId = event.meta?.step_id;
    if (!groupKey || !stepId) continue;

    const chapter = chapterMap.get(groupKey);
    if (!chapter) continue;

    const stepKind = event.meta?.step_kind || "";

    // 只取 complete 事件作为步骤计数来源（start 事件不重复统计）
    if (event.status === "completed") {
      // note 类型事件：没有 trace，不作为可展开的步骤显示
      // 只保留有 trace 或有实际执行过程的步骤（非 note/kind=note）
      const isNote = stepKind === "note" || event.meta?.kind === "note" || event.meta?.kind === "migration";
      if (isNote) {
        // 仍然计入章节统计
        chapter.elapsedMs += event.meta?.elapsed_ms || 0;
        chapter.llmCallCount += event.meta?.llm_call_count || 0;
        continue;
      }

      chapter.steps.push({
        stepId,
        stepKind,
        title: event.title || "",
        detail: event.detail || "",
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
        stepKind,
        title: event.title || "",
        detail: event.detail || "",
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
