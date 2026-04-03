import { reactive } from "vue";
import { getTask, uploadStorySeed } from "../api/project";
import {
  applyStructuredView,
  buildFailedTask,
  buildUploadingTask,
  DEFAULT_LLM_ACTIVITY,
  DEFAULT_TASK_METRICS,
  resetStructuredView,
} from "./seedUploadTaskState";

const DEFAULT_GOAL = "提取全部有名角色、组织和关系，用于世界线推演。";
let activeUploadPromise = null;
let activeUploadRequest = null;
const TASK_POLL_INTERVAL_MS = 1200;
const state = reactive({
  projectName: "我的小说项目",
  analysisGoal: DEFAULT_GOAL,
  additionalContext: "",
  segmentTokenLimit: 50000,
  files: [],
  dragActive: false,
  uploadBusy: false,
  uploadPhase: "idle",
  progressPercent: 0,
  statusText: "等待上传",
  stageLabel: "",
  uploadedBytes: 0,
  totalBytes: 0,
  taskId: "",
  taskStatus: "",
  result: null,
  error: "",
  completedProjectId: "",
  lastUploadedFiles: [],
  activeStage: { key: "", label: "", progress: 0, status: "pending" },
  taskMetrics: { ...DEFAULT_TASK_METRICS },
  llmActivity: { ...DEFAULT_LLM_ACTIVITY },
  timeline: [],
  taskStartedAt: "",
});

function fileKey(file) {
  return `${file.name}_${file.size}_${file.lastModified}`;
}

function isSupported(file) {
  return /\.(txt|md|markdown|pdf)$/i.test(file.name || "");
}

function hasFile(existingFiles, incomingFile) {
  return existingFiles.some((item) => fileKey(item) === fileKey(incomingFile));
}

function appendFiles(nextFiles) {
  const merged = [...state.files];
  for (const file of nextFiles) {
    if (!isSupported(file) || hasFile(merged, file)) {
      continue;
    }
    merged.push(file);
  }
  state.files = merged;
}

function removeFile(file) {
  state.files = state.files.filter((item) => fileKey(item) !== fileKey(file));
}

function formatSize(size) {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function markUploadStart() {
  const startedAt = new Date().toISOString();
  state.uploadBusy = true;
  state.uploadPhase = "uploading";
  state.progressPercent = 0;
  state.statusText = "正在上传文件...";
  state.stageLabel = "文件上传";
  state.uploadedBytes = 0;
  state.totalBytes = 0;
  state.taskId = "";
  state.taskStatus = "";
  state.result = null;
  state.error = "";
  state.lastUploadedFiles = state.files.map((item) => item.name);
  state.taskStartedAt = startedAt;
  applyStructuredView(
    state,
    buildUploadingTask(startedAt, 0, "开始上传文件", "文件正在发送到后端，稍后将切换到后台分析日志。"),
  );
}

function updateProgress(progress) {
  if (progress.phase !== "uploading") {
    return;
  }
  state.uploadPhase = "uploading";
  state.progressPercent = Math.max(0, Math.min(99, progress.percent));
  state.uploadedBytes = progress.loaded;
  state.totalBytes = progress.total;
  state.stageLabel = "文件上传";
  state.statusText = `正在上传文件... ${state.progressPercent}%`;
  applyStructuredView(
    state,
    buildUploadingTask(
      state.taskStartedAt,
      state.progressPercent,
      "文件上传中",
      `${formatSize(progress.loaded)} / ${formatSize(progress.total || 0)}`,
    ),
  );
}

function beginTaskProcessing(data) {
  state.uploadPhase = "processing";
  state.taskId = data?.task_id || "";
  state.taskStatus = "processing";
  state.completedProjectId = data?.project_id || "";
  state.progressPercent = 0;
  state.stageLabel = "后台分析";
  state.statusText = "文件已上传，后台正在分析小说...";
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function updateTaskProgress(task) {
  state.uploadPhase = "processing";
  state.taskStatus = task.status || "processing";
  const view = applyStructuredView(state, task);
  state.progressPercent = Math.max(0, Math.min(99, view.activeStage.progress));
  state.stageLabel = view.activeStage.label;
  state.statusText = task.message || view.activeStage.label;
}

async function waitForTaskCompletion(taskId) {
  while (true) {
    const response = await getTask(taskId);
    const task = response.data || {};
    if (task.status === "completed") {
      return task;
    }
    if (task.status === "failed") {
      throw new Error(task.error || task.message || "后台分析失败");
    }
    updateTaskProgress(task);
    await sleep(TASK_POLL_INTERVAL_MS);
  }
}

function finishUpload(projectData, taskData) {
  state.uploadBusy = false;
  state.uploadPhase = "success";
  state.taskStatus = "completed";
  state.result = {
    project_id: projectData?.project_id || "",
    project_name: projectData?.project_name || "",
    task_id: projectData?.task_id || "",
    task_result: taskData?.result || {},
    task_message: taskData?.message || "",
  };
  state.completedProjectId = projectData?.project_id || "";
  const view = applyStructuredView(state, taskData);
  state.progressPercent = Math.max(0, Math.min(100, view.activeStage.progress));
  state.stageLabel = view.activeStage.label;
  state.statusText = taskData?.message || view.activeStage.label;
  activeUploadPromise = null;
  activeUploadRequest = null;
}

function failUpload(message) {
  state.uploadBusy = false;
  state.uploadPhase = "error";
  state.taskStatus = "failed";
  state.error = message;
  const view = applyStructuredView(state, buildFailedTask(state.taskStartedAt, state.progressPercent, message));
  state.stageLabel = view.activeStage.label;
  state.statusText = message;
  activeUploadPromise = null;
  activeUploadRequest = null;
}

async function submitUpload() {
  if (state.uploadBusy && activeUploadPromise) {
    return activeUploadPromise;
  }
  if (!state.analysisGoal.trim()) {
    throw new Error("请先填写分析目标。");
  }
  if (!state.files.length) {
    throw new Error("请至少选择一个小说文件。");
  }
  markUploadStart();
  try {
    activeUploadPromise = uploadStorySeed({
      projectName: state.projectName.trim() || "我的小说项目",
      analysisGoal: state.analysisGoal.trim(),
      additionalContext: state.additionalContext.trim(),
      segmentTokenLimit: state.segmentTokenLimit,
      files: state.files,
      onProgress: updateProgress,
      onRequest: (xhr) => {
        activeUploadRequest = xhr;
      },
    });
    const response = await activeUploadPromise;
    beginTaskProcessing(response.data);
    if (!response.data?.task_id) {
      throw new Error("上传成功但未返回 task_id");
    }
    const taskData = await waitForTaskCompletion(response.data.task_id);
    finishUpload(response.data, taskData);
    return state.result;
  } catch (error) {
    failUpload(error.message || "上传失败");
    throw error;
  }
}

function clearNotice() {
  if (state.uploadBusy) {
    return;
  }
  state.uploadPhase = "idle";
  state.progressPercent = 0;
  state.statusText = "等待上传";
  state.stageLabel = "";
  state.taskId = "";
  state.taskStatus = "";
  state.result = null;
  state.error = "";
  resetStructuredView(state);
}

export function useSeedUpload() {
  return {
    state,
    fileKey,
    appendFiles,
    removeFile,
    formatSize,
    submitUpload,
    clearNotice,
  };
}
