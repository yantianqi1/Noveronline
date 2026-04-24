/**
 * Seed upload hook — orchestrates file upload, task polling, auto-resume.
 *
 * Uses the Zustand store for state and imperative helpers for the async
 * upload / poll lifecycle. Ported from src-vue/composables/useSeedUpload.js.
 */

import { useCallback, useEffect, useRef } from "react";

import { cancelTask, getTask, rerunSeedPipeline, retryFailedSegments, uploadStorySeed } from "@/api/project";
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
// Timeout only fires when the task stops making progress (not based on total runtime).
// Seed pipelines on large novels routinely exceed an hour of wall time, so we must not
// cap by attempt count — that used to interrupt healthy tasks with a spurious
// "任务轮询超时" message even when the backend was still producing LLM output.
const STUCK_TIMEOUT_MS = 20 * 60 * 1000; // 20 min with no backend-side progress
const FETCH_ERROR_TOLERANCE = 10; // consecutive transient poll fetch failures

/* ---------- Utilities ---------- */

function formatSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Build a compact string signature of the fields that should change each time the
 * backend makes progress (timeline length, current stage, completed segment count).
 * The polling loop uses this to detect "no progress for N minutes" rather than
 * timing out based on total elapsed time.
 */
function snapshotProgress(task: Record<string, unknown>): string {
  const detail = (task.progress_detail ?? {}) as Record<string, unknown>;
  const timeline = Array.isArray(detail.timeline) ? detail.timeline : [];
  const activeStage = (detail.active_stage ?? {}) as Record<string, unknown>;
  const metrics = (detail.task_metrics ?? {}) as Record<string, unknown>;
  const parts = [
    String(task.status ?? ""),
    String(task.message ?? ""),
    String(timeline.length),
    String(activeStage.key ?? ""),
    String(activeStage.progress ?? ""),
    String(metrics.completed_blocks ?? ""),
    String(metrics.segment_count ?? ""),
  ];
  return parts.join("|");
}

/**
 * Thrown when the polling loop gives up but the backend task may still be
 * alive (stuck detection, fetch retries exhausted). The UI uses this to
 * preserve localStorage persistence so the user can rejoin the task later
 * via refresh or the project card.
 */
class PollingInterruptedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "PollingInterruptedError";
  }
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
      sequentialReadingRetry: view.sequentialReadingRetry,
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
    let lastProgressSnapshot = "";
    let lastProgressAt = Date.now();
    let consecutiveFetchErrors = 0;

    while (true) {
      let task: Record<string, unknown>;
      try {
        const response = await getTask(taskId);
        task = (response.data ?? {}) as Record<string, unknown>;
        consecutiveFetchErrors = 0;
      } catch (err) {
        consecutiveFetchErrors += 1;
        if (consecutiveFetchErrors >= FETCH_ERROR_TOLERANCE) {
          throw new PollingInterruptedError(
            `无法获取任务状态（已连续失败 ${consecutiveFetchErrors} 次），请检查网络与后端服务`,
          );
        }
        console.warn(
          `[seedUpload] getTask failed (${consecutiveFetchErrors}/${FETCH_ERROR_TOLERANCE}), retrying`,
          err,
        );
        await sleep(TASK_POLL_INTERVAL_MS);
        continue;
      }

      if (task.status === "completed") return task;
      if (task.status === "failed") {
        throw new Error(
          (task.error as string) || (task.message as string) || "后台分析失败",
        );
      }
      if (task.status === "cancelled") {
        throw new Error("任务已取消");
      }

      updateTaskProgress(task);

      const snapshot = snapshotProgress(task);
      if (snapshot !== lastProgressSnapshot) {
        lastProgressSnapshot = snapshot;
        lastProgressAt = Date.now();
      } else if (Date.now() - lastProgressAt > STUCK_TIMEOUT_MS) {
        throw new PollingInterruptedError(
          `任务长时间未推进（超过 ${Math.round(STUCK_TIMEOUT_MS / 60000)} 分钟无新事件），请检查后台服务与 LLM 中转站状态`,
        );
      }

      await sleep(TASK_POLL_INTERVAL_MS);
    }
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

  /* ---- internal: run polling + finish in background ----
   *
   * Lets the caller (resume button, rejoin button, rerun button) return as
   * soon as the task is accepted by the backend, while the UI's store-based
   * workflow stream keeps updating from `waitForTaskCompletion`. Without
   * this, the caller's toast sits in "loading" for the full lifetime of the
   * task (potentially 30+ min on a 500-chapter novel).
   */
  function startBackgroundPolling(
    taskId: string,
    finishArgs: { projectId: string; projectName: string },
    failFallback: string,
  ): void {
    void (async () => {
      try {
        const finalTask = await waitForTaskCompletion(taskId);
        finishUpload(
          {
            project_id: finishArgs.projectId,
            project_name: finishArgs.projectName,
            task_id: taskId,
          },
          finalTask,
        );
      } catch (err) {
        reportFailure(err, failFallback);
      }
    })();
  }

  /* ---- public: trigger manual retry of retry_needed segments ---- */
  async function retrySegments(projectId: string): Promise<void> {
    if (!projectId) return;
    const state = useSeedUploadStore.getState();
    store.patchState({
      uploadBusy: true,
      uploadPhase: "processing",
      taskStatus: "processing",
      error: "",
      statusText: "正在重读失败段落...",
      stageLabel: "重读失败段落",
      taskStartedAt: new Date().toISOString(),
      sequentialReadingRetry: undefined,
    });
    let response;
    try {
      response = await retryFailedSegments(projectId);
    } catch (err) {
      reportFailure(err, "触发重读任务失败");
      return;
    }
    if (!response?.success || !response.data) {
      failUpload(response?.error || "触发重读任务失败");
      return;
    }
    const data = response.data as Record<string, unknown>;
    const taskId = (data.task_id as string) || "";
    store.patchState({
      taskId,
      completedProjectId: projectId,
    });
    persistActiveTask({
      taskId,
      projectId,
      projectName: state.projectName || state.result?.project_name || "",
      taskStartedAt: new Date().toISOString(),
    });
    startBackgroundPolling(
      taskId,
      {
        projectId,
        projectName: state.result?.project_name || state.projectName || "",
      },
      "重读任务失败",
    );
  }

  /* ---- internal: fail upload ----
   *
   * `recoverable=true` means the backend task may still be running (polling
   * timed out or network glitches exhausted). In that case we keep the
   * localStorage persistence so the user can rejoin via refresh or by
   * clicking the seed_processing project card.
   */
  function failUpload(message: string, recoverable = false): void {
    const state = useSeedUploadStore.getState();
    const view = applyView(
      buildFailedTask(state.taskStartedAt, state.progressPercent, message) as Record<string, unknown>,
    );
    store.patchState({
      uploadBusy: false,
      uploadPhase: "error",
      taskStatus: recoverable ? "processing" : "failed",
      error: message,
      stageLabel: view.activeStage.label,
      statusText: message,
    });
    if (!recoverable) {
      clearPersistedActiveTask();
    }
  }

  function reportFailure(err: unknown, fallback: string): void {
    const message = err instanceof Error ? err.message : fallback;
    const recoverable = err instanceof PollingInterruptedError;
    failUpload(message, recoverable);
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
      reportFailure(err, "上传失败");
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

  /* ---- public: rejoin a backend task that is still running ----
   *
   * Used when the frontend fell out of the polling loop (timeout, reload,
   * navigation) but the backend task is still producing LLM output. Seeds
   * the store with the task's current progress then resumes polling.
   */
  const rejoinActiveTask = useCallback(
    async (args: { taskId: string; projectId: string; projectName?: string }): Promise<void> => {
      if (!args.taskId) return;
      const current = useSeedUploadStore.getState();
      // If we're already polling this task, no-op.
      if (current.uploadBusy && current.taskId === args.taskId) return;

      let task: Record<string, unknown>;
      try {
        const response = await getTask(args.taskId);
        task = (response.data ?? {}) as Record<string, unknown>;
      } catch (err) {
        failUpload(err instanceof Error ? err.message : "无法连接到正在运行的任务");
        return;
      }

      const status = (task?.status as string) || "";
      if (!status || status === "completed" || status === "failed" || status === "cancelled") {
        failUpload(
          (task?.error as string) || (task?.message as string) ||
            "该任务已不在运行中，请刷新项目列表。",
        );
        return;
      }

      const startedAt = ((task?.created_at as string) || new Date().toISOString());
      store.patchState({
        uploadBusy: true,
        uploadPhase: "processing",
        taskId: args.taskId,
        taskStatus: status,
        completedProjectId: args.projectId,
        projectName: args.projectName || current.projectName,
        taskStartedAt: startedAt,
        error: "",
        stageLabel: "后台分析",
        statusText: (task.message as string) || "正在重新接入后台任务...",
      });
      persistActiveTask({
        taskId: args.taskId,
        projectId: args.projectId,
        projectName: args.projectName || current.projectName || "",
        taskStartedAt: startedAt,
      });
      updateTaskProgress(task);

      startBackgroundPolling(
        args.taskId,
        {
          projectId: args.projectId,
          projectName: args.projectName || current.projectName || "",
        },
        "重新接入任务失败",
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

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
        reportFailure(err, "恢复任务失败");
      }
    })().catch((err) => {
      console.warn("[seedUpload] resume error", err);
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---- public: dismiss a stuck/errored workflow ----
   *
   * Resets the local UI back to idle so the user can leave the frozen
   * workflow stream behind. Does NOT touch the backend task — the task's
   * status is governed by cancelUpload or by the backend itself. Use this
   * when the user has decided they no longer want to watch a stuck view.
   */
  const dismissError = useCallback((): void => {
    const viewReset = resetStructuredView();
    store.patchState({
      uploadBusy: false,
      uploadPhase: "idle",
      taskStatus: "",
      taskId: "",
      error: "",
      statusText: "等待上传",
      stageLabel: "",
      progressPercent: 0,
      ...viewReset,
    });
    clearPersistedActiveTask();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---- public: rerun the seed pipeline for a project with already-uploaded files ----
   *
   * Calls POST /api/project/seed/rerun/:project_id which creates a fresh
   * seed_extract task reusing the existing project files, then starts
   * polling it. Used by the "重新开始" button on the error banner.
   */
  const rerunSeed = useCallback(
    async (projectId: string): Promise<void> => {
      if (!projectId) {
        failUpload("缺少 project_id，无法重新开始分析");
        return;
      }
      const current = useSeedUploadStore.getState();
      const viewReset = resetStructuredView();
      const startedAt = new Date().toISOString();
      store.patchState({
        ...viewReset,
        uploadBusy: true,
        uploadPhase: "processing",
        taskStatus: "processing",
        error: "",
        statusText: "正在重新启动种子分析...",
        stageLabel: "重新启动",
        taskId: "",
        taskStartedAt: startedAt,
        completedProjectId: projectId,
      });

      let response;
      try {
        response = await rerunSeedPipeline(projectId);
      } catch (err) {
        reportFailure(err, "重新启动分析失败");
        return;
      }
      if (!response?.success || !response.data) {
        failUpload(response?.error || "重新启动分析失败");
        return;
      }
      const data = response.data as Record<string, unknown>;
      const taskId = (data.task_id as string) || "";
      if (!taskId) {
        failUpload("后端未返回新的 task_id");
        return;
      }
      const projectName = current.projectName || current.result?.project_name || "";
      store.patchState({ taskId });
      persistActiveTask({
        taskId,
        projectId,
        projectName,
        taskStartedAt: startedAt,
      });
      startBackgroundPolling(
        taskId,
        { projectId, projectName },
        "重新分析任务失败",
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  /* ---- public: continue a broken task from the last checkpoint ----
   *
   * Best-effort "breakpoint resume":
   *   1. If the backend task is still alive → rejoin it (no re-processing).
   *   2. If it died but reading_notes.json has `retry_needed` segments →
   *      run the retry-failed-segments pipeline to fill in the gaps.
   *   3. Otherwise → report that there's nothing to resume.
   *
   * The backend has no true "resume from byte X" endpoint for the seed
   * pipeline, but these two paths cover the common cases without re-reading
   * segments that already succeeded.
   */
  const continueFromCheckpoint = useCallback(
    async (args: {
      projectId: string;
      projectName?: string;
      seedTaskId?: string | null;
    }): Promise<"rejoined" | "retried" | "nothing"> => {
      const { projectId, projectName = "", seedTaskId } = args;
      if (!projectId) {
        failUpload("缺少 project_id，无法继续分析");
        return "nothing";
      }

      // 1) Try to rejoin a still-running task.
      if (seedTaskId) {
        try {
          const response = await getTask(seedTaskId);
          const task = (response.data ?? {}) as Record<string, unknown>;
          const status = (task?.status as string) || "";
          if (status === "processing" || status === "pending") {
            await rejoinActiveTask({
              taskId: seedTaskId,
              projectId,
              projectName,
            });
            return "rejoined";
          }
        } catch (err) {
          console.warn("[seedUpload] rejoin probe failed, will try retry path", err);
        }
      }

      // 2) Fall back to retry-failed-segments (picks up segments previously
      //    marked retry_needed in reading_notes.json).
      await retrySegments(projectId);
      const after = useSeedUploadStore.getState();
      if (after.taskStatus === "failed" || after.uploadPhase === "error") {
        return "nothing";
      }
      return "retried";
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [rejoinActiveTask],
  );

  return {
    /* state (from store) */
    ...store,
    /* helpers */
    fileKey,
    formatSize,
    /* actions */
    submitUpload,
    cancelUpload,
    retrySegments,
    rejoinActiveTask,
    dismissError,
    rerunSeed,
    continueFromCheckpoint,
  };
}
