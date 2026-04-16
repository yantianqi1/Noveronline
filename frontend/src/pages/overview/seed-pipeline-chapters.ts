/**
 * Seed pipeline chapter definitions and stage-to-chapter mapping.
 * Ported from src-vue/views/overview/seedPipelineChapters.js
 *
 * Must stay in sync with backend/app/services/seed_pipeline_chapters.py.
 */

import type { TimelineEvent } from "@/lib/seed-upload-task-state";

/* ---------- Chapter definitions ---------- */

export interface PipelineChapter {
  key: string;
  label: string;
  stages: string[];
}

export const PIPELINE_CHAPTERS: readonly PipelineChapter[] = [
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

export const STAGE_TO_CHAPTER: Record<string, string> = Object.fromEntries(
  PIPELINE_CHAPTERS.flatMap((ch) => ch.stages.map((s) => [s, ch.key])),
);

export const CHAPTER_LABELS: Record<string, string> = Object.fromEntries(
  PIPELINE_CHAPTERS.map((ch) => [ch.key, ch.label]),
);

/* ---------- Chapter view model ---------- */

export interface ChapterStep {
  stepId: string;
  stepKind: string;
  title: string;
  detail: string;
  stage: string;
  status: "active" | "completed";
  elapsedMs: number;
  llmCallCount: number;
  hasTrace: boolean;
  timestamp: string;
}

export interface ChapterViewModel {
  key: string;
  label: string;
  status: "pending" | "active" | "completed";
  steps: ChapterStep[];
  stepCount: number;
  elapsedMs: number;
  llmCallCount: number;
}

/**
 * Build chapter view models from timeline events, grouped by group_key.
 */
export function buildChapterViewModel(
  timeline: TimelineEvent[],
  activeStageKey = "",
): ChapterViewModel[] {
  const activeChapterKey = STAGE_TO_CHAPTER[activeStageKey] || "";
  const chapterMap = new Map<string, ChapterViewModel>();

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

  for (const event of timeline) {
    const meta = event.meta as Record<string, unknown>;
    const groupKey = meta?.group_key as string | undefined;
    const stepId = meta?.step_id as string | undefined;
    if (!groupKey || !stepId) continue;

    const chapter = chapterMap.get(groupKey as string);
    if (!chapter) continue;

    const stepKind = (meta?.step_kind as string) || "";

    if (event.status === "completed") {
      const isNote =
        stepKind === "note" ||
        meta?.kind === "note" ||
        meta?.kind === "migration";
      if (isNote) {
        chapter.elapsedMs += (meta?.elapsed_ms as number) || 0;
        chapter.llmCallCount += (meta?.llm_call_count as number) || 0;
        continue;
      }

      chapter.steps.push({
        stepId,
        stepKind,
        title: event.title || "",
        detail: event.detail || "",
        stage: event.stage || "",
        status: "completed",
        elapsedMs: (meta?.elapsed_ms as number) || 0,
        llmCallCount: (meta?.llm_call_count as number) || 0,
        hasTrace: !!meta?.has_trace,
        timestamp: event.timestamp || "",
      });
      chapter.elapsedMs += (meta?.elapsed_ms as number) || 0;
      chapter.llmCallCount += (meta?.llm_call_count as number) || 0;
    } else if (event.status === "active") {
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

  // De-duplicate (a step_id may appear as start + complete)
  for (const chapter of chapterMap.values()) {
    const seen = new Map<string, ChapterStep>();
    for (const step of chapter.steps) {
      const existing = seen.get(step.stepId);
      if (!existing || step.status === "completed") {
        seen.set(step.stepId, step);
      }
    }
    chapter.steps = Array.from(seen.values());
    chapter.stepCount = chapter.steps.length;
  }

  // Derive chapter status
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
