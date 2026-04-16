/**
 * Seed upload hook — orchestrates file upload, task polling, auto-resume.
 *
 * Uses the Zustand store for state and imperative helpers for the async
 * upload / poll lifecycle. Ported from src-vue/composables/useSeedUpload.js.
 */

import { useCallback, useEffect, useRef } from "react";

import { cancelTask, getTask, uploadStorySeed } from "@/api/project";
import type { UploadProgress } from "@/api/http";
import {
  applyStructuredView,
  buildFailedTask,
  buildUploadingTask,
  resetStructuredView,
} from "@/lib/seed-upload-task-state";
import {
  clearPersistedActiveTask,
  fileKey,
  loadPersistedActiveTask,
  persistActiveTask,
  useSeedUploadStore,
} from "@/stores/seed-upload-store";
import type { SeedUploadResult } from "@/stores/seed-upload-store";

/* ---------- Constants ---------- */

const TASK_POLL_INTERVAL_MS = 1200;
const MAX_POLL_ATTEMPTS = 300; // ~6 minutes at 1.2s interval

/* ---------- Utilities ---------- */

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/* ---------- Hook ---------- */

export function useSeedUpload() {
  const store = useSeedUploadStore();
  const resumedRef = useRef(false);

  /* ---- internal: apply structured view to store ---- */
  function applyView(task: Record<string, unknown>): ReturnType<typeof applyStructuredView> {
    const view = applyStructuredView(task);
    store.patchView({
      activeStage: view.activeStage,
      taskMetrics: view.taskMetrics,
      llmActivity: view.llmActivity,
      timeline: view.timeline,
      taskStartedAt: view.taskStartedAt || store.taskStartedAt,
    });
    return view;
  }

  /* ---- internal: mark upload start ---- */
  function markUploadStart(): void {
    const startedAt = new Date().toISOString();
    store.patchState({
      uploadBusy: true,
      uploadPhase: "uploading",
      progressPercent: 0,
      statusText: "正在上传文件...",
      stageLabel: "文件上传",
      uploadedBytes: 0,
      totalBytes: 0,
      taskId: "",
      taskStatus: "",
      result: null,
      error: "",
      taskStartedAt: startedAt,
    });
    applyView(
      buildUploadingTask(startedAt, 0, "开始上传文件", "文件正在发送到后端，稍后将切换到后台分析日志。") as Record<string, unknown>,
    );
  }

  /* ---- internal: update upload progress ---- */
  function handleUploadProgress(progress: UploadProgress): void {
    if (progress.phase !== "uploading") return;
    const percent = Math.max(0, Math.min(99, progress.percent));
    const state = useSeedUploadStore.getState();
    store.patchState({
      uploadPhase: "uploading",
      progressPercent: percent,
      uploadedBytes: progress.loaded,
      totalBytes: progress.total,
      stageLabel: "文件上传",
      statusText: `正在上传文件... ${percent}%`,
    });
    applyView(
      buildUploadingTask(
        state.taskStartedAt,
        percent,
        "文件上传中",
        `${formatSize(progress.loaded)} / ${formatSize(progress.total || 0)}`,
      ) as Record<string, unknown>,
    );
  }

  /* ---- internal: transition to task processing ---- */
  function beginTaskProcessing(data: Record<string, unknown>): void {
    const taskId = (data.task_id as string) || "";
    const projectId = (data.project_id as string) || "";
    const state = useSeedUploadStore.getState();
    store.patchState({
      uploadPhase: "processing",
      taskId,
      taskStatus: "processing",
      completedProjectId: projectId,
      progressPercent: 0,
      stageLabel: "后台分析",
      statusText: "文件已上传，后台正在分析小说...",
    });
    if (taskId) {
      persistActiveTask({
        taskId,
        projectId,
        projectName: state.projectName,
        taskStartedAt: state.taskStartedAt,
      });
    }
  }

  /* ---- internal: update during task polling ---- */
  function updateTaskProgress(task: Record<string, unknown>): void {
    store.patchState({
      uploadPhase: "processing",
      taskStatus: (task.status as string) || "processing",
    });
    const view = applyView(task);
    store.patchState({
      progressPercent: Math.max(0, Math.min(99, view.activeStage.progress)),
      stageLabel: view.activeStage.label,
      statusText: (task.message as string) || view.activeStage.label,
    });
  }

  /* ---- internal: poll until completion ---- */
  async function waitForTaskCompletion(taskId: string): Promise<Record<string, unknown>> {
    for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
      const response = await getTask(taskId);
      const task = (response.data ?? {}) as Record<string, unknown>;
      if (task.status === "completed") return task;
      if (task.status === "failed") {
        throw new Error(
          (task.error as string) || (task.message as string) || "后台分析失败",
        );
      }
      updateTaskProgress(task);
      await sleep(TASK_POLL_INTERVAL_MS);
    }
    throw new Error("任务轮询超时，请检查后台服务状态后重试");
  }

  /* ---- internal: finish upload ---- */
  function finishUpload(
    projectData: Record<string, unknown>,
    taskData: Record<string, unknown>,
  ): void {
    const result: SeedUploadResult = {
      project_id: (projectData.project_id as string) || "",
      project_name: (projectData.project_name as string) || "",
      task_id: (projectData.task_id as string) || "",
      task_result: (taskData.result as Record<string, unknown>) || {},
      task_message: (taskData.message as string) || "",
    };
    const view = applyView(taskData);
    store.patchState({
      uploadBusy: false,
      uploadPhase: "success",
      taskStatus: "completed",
      result,
      completedProjectId: result.project_id,
      progressPercent: Math.max(0, Math.min(100, view.activeStage.progress)),
      stageLabel: view.activeStage.label,
      statusText: (taskData.message as string) || view.activeStage.label,
    });
    clearPersistedActiveTask();
  }

  /* ---- internal: fail upload ---- */
  function failUpload(message: string): void {
    const state = useSeedUploadStore.getState();
    const view = applyView(
      buildFailedTask(state.taskStartedAt, state.progressPercent, message) as Record<string, unknown>,
    );
    store.patchState({
      uploadBusy: false,
      uploadPhase: "error",
      taskStatus: "failed",
      error: message,
      stageLabel: view.activeStage.label,
      statusText: message,
    });
    clearPersistedActiveTask();
  }

  /* ---- public: submit upload ---- */
  const submitUpload = useCallback(async (): Promise<SeedUploadResult | undefined> => {
    const state = useSeedUploadStore.getState();
    if (state.uploadBusy) return undefined;
    if (!state.analysisGoal.trim()) throw new Error("请先填写分析目标。");
    if (!state.files.length) throw new Error("请至少选择一个小说文件。");

    markUploadStart();

    try {
      const response = await uploadStorySeed({
        projectName: state.projectName.trim() || "我的小说项目",
        analysisGoal: state.analysisGoal.trim(),
        additionalContext: state.additionalContext.trim(),
        segmentTokenLimit: state.segmentTokenLimit,
        files: state.files,
        onProgress: handleUploadProgress,
      });
      const data = (response.data ?? {}) as Record<string, unknown>;
      beginTaskProcessing(data);
      if (!data.task_id) throw new Error("上传成功但未返回 task_id");

      const taskData = await waitForTaskCompletion(data.task_id as string);
      finishUpload(data, taskData);
      return useSeedUploadStore.getState().result ?? undefined;
    } catch (err) {
      const message = err instanceof Error ? err.message : "上传失败";
      failUpload(message);
      throw err;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---- public: cancel upload ---- */
  const cancelUpload = useCallback(async (): Promise<void> => {
    const state = useSeedUploadStore.getState();
    if (!state.taskId || state.taskStatus !== "processing") return;
    try {
      await cancelTask(state.taskId);
      const viewReset = resetStructuredView();
      store.patchState({
        uploadBusy: false,
        uploadPhase: "error",
        taskStatus: "cancelled",
        error: "分析任务已取消",
        statusText: "分析任务已取消",
        ...viewReset,
      });
      clearPersistedActiveTask();
    } catch (err) {
      store.patchState({
        error: err instanceof Error ? err.message : "取消失败",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---- auto-resume persisted task on mount ---- */
  useEffect(() => {
    if (resumedRef.current) return;
    resumedRef.current = true;

    const state = useSeedUploadStore.getState();
    if (state.uploadBusy || state.taskId) return;

    const persisted = loadPersistedActiveTask();
    if (!persisted?.taskId) return;

    (async () => {
      let task: Record<string, unknown>;
      try {
        const response = await getTask(persisted.taskId);
        task = (response.data ?? {}) as Record<string, unknown>;
      } catch {
        console.warn("[seedUpload] failed to resume task, clearing persistence");
        clearPersistedActiveTask();
        return;
      }
      if (
        !task ||
        !task.status ||
        task.status === "completed" ||
        task.status === "failed" ||
        task.status === "cancelled"
      ) {
        clearPersistedActiveTask();
        return;
      }

      // Restore processing state
      store.patchState({
        uploadBusy: true,
        uploadPhase: "processing",
        taskId: persisted.taskId,
        taskStatus: (task.status as string) || "processing",
        completedProjectId: persisted.projectId || "",
        projectName: persisted.projectName || state.projectName,
        taskStartedAt: persisted.taskStartedAt || state.taskStartedAt,
        stageLabel: "后台分析",
        statusText: (task.message as string) || "正在恢复后台分析进度...",
      });
      updateTaskProgress(task);

      try {
        const finalTask = await waitForTaskCompletion(persisted.taskId);
        finishUpload(
          {
            project_id: persisted.projectId,
            project_name: persisted.projectName,
            task_id: persisted.taskId,
          },
          finalTask,
        );
      } catch (err) {
        failUpload(err instanceof Error ? err.message : "恢复任务失败");
      }
    })().catch((err) => {
      console.warn("[seedUpload] resume error", err);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    /* state (from store) */
    ...store,
    /* helpers */
    fileKey,
    formatSize,
    /* actions */
    submitUpload,
    cancelUpload,
  };
}
