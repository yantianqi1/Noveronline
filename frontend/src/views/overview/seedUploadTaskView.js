export const IDLE_TIMELINE = [
  ["extract_text", "提取上传文本", "读取文稿、清洗格式并准备分析输入。"],
  ["smart_segmentation", "智能分段", "按令牌预算将章节分组为阅读段。"],
  ["sequential_reading", "顺序深度阅读", "LLM逐段精读小说，提取角色、关系和剧情。"],
  ["global_integration", "全局整合", "整合阅读笔记，聚合角色、组织与关系。"],
  ["ontology", "梳理故事结构", "归纳实体类型、关系类型与故事主轴。"],
  ["agent_profiles", "角色Agent档案", "为重要角色生成可用于对话和模拟的完整档案。"],
];

const STAGE_PROGRESS_RANGE = {
  sequential_reading: { start: 10, end: 75 },
};

const STRUCTURED_PROGRESS_ERROR = "Expected structured progress_detail";
const DETAIL_KEYS = ["stage", "stage_label", "active_stage", "task_metrics", "llm_activity", "timeline"];
const ACTIVE_STAGE_KEYS = ["key", "label", "progress", "status"];
const METRIC_KEYS = ["chapter_count", "block_count", "completed_blocks", "total_blocks", "active_workers", "segment_count"];
const LLM_ACTIVITY_KEYS = ["enabled", "mode", "model", "action", "target_type", "target_label"];
const TIMELINE_EVENT_KEYS = ["id", "timestamp", "stage", "level", "status", "title", "detail", "meta"];

export function buildIdleLogPreview() {
  return IDLE_TIMELINE.map(([stage, title, detail], index) => ({
    id: `idle_${stage}`,
    timestamp: "",
    stage,
    level: "info",
    status: "pending",
    title,
    detail,
    meta: { order: index + 1, kind: "preview" },
  }));
}

export function normalizeSeedTaskDetail(task = {}) {
  const detail = requireObject(task.progress_detail, "progress_detail");
  requireKeys(detail, DETAIL_KEYS, "progress_detail");
  return {
    activeStage: normalizeActiveStage(detail.active_stage),
    taskMetrics: normalizeMetrics(detail.task_metrics),
    llmActivity: normalizeLlmActivity(detail.llm_activity),
    timeline: normalizeTimeline(detail.timeline),
    taskStartedAt: typeof task.created_at === "string" ? task.created_at : "",
  };
}

export function formatElapsedDuration(startedAt, now = Date.now()) {
  if (!startedAt) {
    return "00:00";
  }
  const startedAtMs = new Date(startedAt).getTime();
  if (Number.isNaN(startedAtMs)) {
    return "00:00";
  }
  const totalSeconds = Math.max(0, Math.floor((now - startedAtMs) / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  if (hours > 0) {
    return `${pad(hours)}:${pad(minutes)}:${pad(seconds)}`;
  }
  return `${pad(minutes)}:${pad(seconds)}`;
}

export function formatTimelineTimestamp(timestamp) {
  if (!timestamp) {
    return "--:--:--";
  }
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) {
    return "--:--:--";
  }
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

export function buildEventChips(event) {
  const meta = event?.meta || {};
  const chips = [];
  if (meta.block_id) {
    chips.push(meta.block_id);
  }
  const range = meta.chapter_range || {};
  if (range.start_order && range.end_order) {
    chips.push(`第 ${range.start_order}-${range.end_order} 章`);
  }
  if (meta.artifact) {
    chips.push(meta.artifact);
  }
  if (Array.isArray(meta.source_names) && meta.source_names.length) {
    chips.push(`${meta.source_names.length} 份来源`);
  }
  return chips;
}

export function deriveStageProgress(activeStage = {}, taskMetrics = {}, timeline = []) {
  const currentProgress = readSafeNumber(activeStage?.progress);
  const stageKey = typeof activeStage?.key === "string" ? activeStage.key : "";
  const counts = resolveStageCounts(stageKey, taskMetrics, timeline);
  if (!counts.total) {
    return { percent: currentProgress, detail: "-", completed: 0, total: 0 };
  }
  const bounds = STAGE_PROGRESS_RANGE[stageKey];
  if (!bounds) {
    return {
      percent: currentProgress,
      detail: `${counts.completed}/${counts.total} ${counts.unit}`,
      completed: counts.completed,
      total: counts.total,
    };
  }
  const stagePercent = interpolateStageProgress(bounds, counts.completed, counts.total);
  return {
    percent: Math.max(currentProgress, stagePercent),
    detail: `${counts.completed}/${counts.total} ${counts.unit}`,
    completed: counts.completed,
    total: counts.total,
  };
}

function normalizeActiveStage(activeStage) {
  const value = requireObject(activeStage, "progress_detail.active_stage");
  requireKeys(value, ACTIVE_STAGE_KEYS, "progress_detail.active_stage");
  return {
    key: readString(value.key, "progress_detail.active_stage.key"),
    label: readString(value.label, "progress_detail.active_stage.label"),
    progress: readNumber(value.progress, "progress_detail.active_stage.progress"),
    status: readString(value.status, "progress_detail.active_stage.status"),
  };
}

function resolveStageCounts(stageKey, taskMetrics, timeline) {
  if (stageKey === "sequential_reading") {
    return {
      completed: readSafeNumber(taskMetrics?.completedBlocks),
      total: readSafeNumber(taskMetrics?.segmentCount || taskMetrics?.totalBlocks),
      unit: "段",
    };
  }
  return { completed: 0, total: 0, unit: "" };
}

function interpolateStageProgress(bounds, completed, total) {
  if (!total) {
    return readSafeNumber(bounds.start);
  }
  const span = Math.max(0, readSafeNumber(bounds.end) - readSafeNumber(bounds.start));
  return readSafeNumber(bounds.start) + Math.round((completed / total) * span);
}

function normalizeMetrics(metrics) {
  const value = requireObject(metrics, "progress_detail.task_metrics");
  requireKeys(value, METRIC_KEYS, "progress_detail.task_metrics");
  return {
    chapterCount: readNumber(value.chapter_count, "progress_detail.task_metrics.chapter_count"),
    blockCount: readNumber(value.block_count, "progress_detail.task_metrics.block_count"),
    completedBlocks: readNumber(value.completed_blocks, "progress_detail.task_metrics.completed_blocks"),
    totalBlocks: readNumber(value.total_blocks, "progress_detail.task_metrics.total_blocks"),
    activeWorkers: readNumber(value.active_workers, "progress_detail.task_metrics.active_workers"),
    segmentCount: readNumber(value.segment_count, "progress_detail.task_metrics.segment_count"),
  };
}

function normalizeLlmActivity(llmActivity) {
  const value = requireObject(llmActivity, "progress_detail.llm_activity");
  requireKeys(value, LLM_ACTIVITY_KEYS, "progress_detail.llm_activity");
  return {
    enabled: readBoolean(value.enabled, "progress_detail.llm_activity.enabled"),
    mode: readString(value.mode, "progress_detail.llm_activity.mode"),
    model: readString(value.model, "progress_detail.llm_activity.model"),
    action: readString(value.action, "progress_detail.llm_activity.action"),
    targetType: readString(value.target_type, "progress_detail.llm_activity.target_type"),
    targetLabel: readString(value.target_label, "progress_detail.llm_activity.target_label"),
  };
}

function normalizeTimeline(timeline) {
  if (!Array.isArray(timeline)) {
    throw new Error(`${STRUCTURED_PROGRESS_ERROR}: missing progress_detail.timeline`);
  }
  return timeline.map((item, index) => normalizeTimelineEvent(item, index));
}

function normalizeTimelineEvent(item, index) {
  const path = `progress_detail.timeline[${index}]`;
  const value = requireObject(item, path);
  requireKeys(value, TIMELINE_EVENT_KEYS, path);
  const meta = requireObject(value.meta, `${path}.meta`);
  return {
    id: readString(value.id, `${path}.id`),
    timestamp: readString(value.timestamp, `${path}.timestamp`),
    stage: readString(value.stage, `${path}.stage`),
    level: readString(value.level, `${path}.level`),
    status: readString(value.status, `${path}.status`),
    title: readString(value.title, `${path}.title`),
    detail: readString(value.detail, `${path}.detail`),
    meta: {
      ...meta,
      step_id: meta.step_id || "",
      step_kind: meta.step_kind || "",
      group_key: meta.group_key || "",
      group_label: meta.group_label || "",
      has_trace: !!meta.has_trace,
      elapsed_ms: typeof meta.elapsed_ms === "number" ? meta.elapsed_ms : 0,
      llm_call_count: typeof meta.llm_call_count === "number" ? meta.llm_call_count : 0,
    },
  };
}

function requireObject(value, path) {
  if (!value || Array.isArray(value) || typeof value !== "object") {
    throw new Error(`${STRUCTURED_PROGRESS_ERROR}: missing ${path}`);
  }
  return value;
}

function requireKeys(value, keys, path) {
  for (const key of keys) {
    if (!Object.prototype.hasOwnProperty.call(value, key)) {
      throw new Error(`${STRUCTURED_PROGRESS_ERROR}: missing ${path}.${key}`);
    }
  }
}

function readString(value, path) {
  if (typeof value !== "string") {
    throw new Error(`${STRUCTURED_PROGRESS_ERROR}: invalid ${path}`);
  }
  return value;
}

function readNumber(value, path) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    throw new Error(`${STRUCTURED_PROGRESS_ERROR}: invalid ${path}`);
  }
  return value;
}

function readBoolean(value, path) {
  if (typeof value !== "boolean") {
    throw new Error(`${STRUCTURED_PROGRESS_ERROR}: invalid ${path}`);
  }
  return value;
}

function readSafeNumber(value) {
  return typeof value === "number" && !Number.isNaN(value) ? value : 0;
}

function pad(value) {
  return String(value).padStart(2, "0");
}
