import { normalizeSeedTaskDetail } from "../views/overview/seedUploadTaskView.js";

export const DEFAULT_TASK_METRICS = {
  chapterCount: 0,
  blockCount: 0,
  completedBlocks: 0,
  totalBlocks: 0,
  activeWorkers: 0,
};

export const DEFAULT_LLM_ACTIVITY = {
  enabled: false,
  mode: "idle",
  model: "",
  action: "等待开始分析",
  targetType: "",
  targetLabel: "",
};

function structuredTaskMetrics() {
  return {
    chapter_count: 0,
    block_count: 0,
    completed_blocks: 0,
    total_blocks: 0,
    active_workers: 0,
  };
}

function structuredLlmActivity(action = DEFAULT_LLM_ACTIVITY.action) {
  return {
    enabled: false,
    mode: "idle",
    model: "",
    action,
    target_type: "",
    target_label: "",
  };
}

export function applyStructuredView(state, task) {
  const view = normalizeSeedTaskDetail(task);
  state.activeStage = view.activeStage;
  state.taskMetrics = view.taskMetrics;
  state.llmActivity = view.llmActivity;
  state.timeline = view.timeline;
  state.taskStartedAt = view.taskStartedAt || state.taskStartedAt;
  return view;
}

export function buildUploadingTask(startedAt, progress, title, detail) {
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

export function buildFailedTask(startedAt, progress, message) {
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

export function resetStructuredView(state) {
  state.activeStage = { key: "", label: "", progress: 0, status: "pending" };
  state.taskMetrics = { ...DEFAULT_TASK_METRICS };
  state.llmActivity = { ...DEFAULT_LLM_ACTIVITY };
  state.timeline = [];
  state.taskStartedAt = "";
}
