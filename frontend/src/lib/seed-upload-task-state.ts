/**
 * Seed upload task state helpers — ported from src-vue/composables/seedUploadTaskState.js
 *
 * Provides default shapes and the `applyStructuredView` / `resetStructuredView` helpers
 * that transform raw backend task payloads into the structured view consumed by the UI.
 */

import { normalizeSeedTaskDetail } from "@/lib/seed-upload-task-view";
import type { SeedUploadViewState } from "@/stores/seed-upload-store";

/* ---------- Defaults ---------- */

export interface TaskMetrics {
  chapterCount: number;
  blockCount: number;
  completedBlocks: number;
  totalBlocks: number;
  activeWorkers: number;
  segmentCount: number;
}

export interface SeedLlmActivity {
  enabled: boolean;
  mode: string;
  model: string;
  action: string;
  targetType: string;
  targetLabel: string;
}

export interface ActiveStage {
  key: string;
  label: string;
  progress: number;
  status: string;
}

export interface TimelineEvent {
  id: string;
  timestamp: string;
  stage: string;
  level: string;
  status: string;
  title: string;
  detail: string;
  meta: Record<string, unknown>;
}

export const DEFAULT_TASK_METRICS: TaskMetrics = {
  chapterCount: 0,
  blockCount: 0,
  completedBlocks: 0,
  totalBlocks: 0,
  activeWorkers: 0,
  segmentCount: 0,
};

export const DEFAULT_LLM_ACTIVITY: SeedLlmActivity = {
  enabled: false,
  mode: "idle",
  model: "",
  action: "等待开始分析",
  targetType: "",
  targetLabel: "",
};

export const DEFAULT_ACTIVE_STAGE: ActiveStage = {
  key: "",
  label: "",
  progress: 0,
  status: "pending",
};

/* ---------- Task builders ---------- */

function structuredTaskMetrics(): Record<string, number> {
  return {
    chapter_count: 0,
    block_count: 0,
    completed_blocks: 0,
    total_blocks: 0,
    active_workers: 0,
    segment_count: 0,
  };
}

function structuredLlmActivity(action = DEFAULT_LLM_ACTIVITY.action): Record<string, unknown> {
  return {
    enabled: false,
    mode: "idle",
    model: "",
    action,
    target_type: "",
    target_label: "",
  };
}

export function buildUploadingTask(
  startedAt: string,
  progress: number,
  title: string,
  detail: string,
): Record<string, unknown> {
  return {
    status: "processing",
    progress,
    created_at: startedAt,
    message: title,
    progress_detail: {
      stage: "uploading",
      stage_label: "文件上传",
      active_stage: {
        key: "uploading",
        label: "文件上传",
        progress,
        status: "processing",
      },
      task_metrics: structuredTaskMetrics(),
      llm_activity: structuredLlmActivity(),
      timeline: [
        {
          id: `upload_${progress}`,
          timestamp: new Date().toISOString(),
          stage: "uploading",
          level: "info",
          status: "active",
          title,
          detail,
          meta: { kind: "upload" },
        },
      ],
    },
  };
}

export function buildFailedTask(
  startedAt: string,
  progress: number,
  message: string,
): Record<string, unknown> {
  return {
    status: "failed",
    progress,
    created_at: startedAt,
    message,
    progress_detail: {
      stage: "failed",
      stage_label: "上传失败",
      active_stage: {
        key: "failed",
        label: "上传失败",
        progress,
        status: "failed",
      },
      task_metrics: structuredTaskMetrics(),
      llm_activity: structuredLlmActivity(message),
      timeline: [
        {
          id: "upload_failed",
          timestamp: new Date().toISOString(),
          stage: "failed",
          level: "error",
          status: "failed",
          title: "上传或分析失败",
          detail: message,
          meta: { kind: "task" },
        },
      ],
    },
  };
}

/* ---------- View application ---------- */

export interface StructuredView {
  activeStage: ActiveStage;
  taskMetrics: TaskMetrics;
  llmActivity: SeedLlmActivity;
  timeline: TimelineEvent[];
  taskStartedAt: string;
}

export function applyStructuredView(
  task: Record<string, unknown>,
): StructuredView {
  const view = normalizeSeedTaskDetail(task);
  return view;
}

export function resetStructuredView(): SeedUploadViewState {
  return {
    activeStage: { ...DEFAULT_ACTIVE_STAGE },
    taskMetrics: { ...DEFAULT_TASK_METRICS },
    llmActivity: { ...DEFAULT_LLM_ACTIVITY },
    timeline: [],
    taskStartedAt: "",
  };
}
