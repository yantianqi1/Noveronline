import { computed, ref } from "vue";

import { getTask } from "../../api/project.js";
import { startWorldlineAutoEvolve } from "../../api/worldline.js";
import { createWorldlineAutoTaskPoller } from "./worldlineAutoTaskPoller.js";
import {
  MAIN_WORLD_BRANCH_ID,
  buildAutoEvolvePayload,
  createInitialAutoTaskMap,
  mergeAutoTaskSnapshot,
} from "./worldlineAutoEvolutionState.js";

function buildTaskSnapshot(task, taskInfo) {
  return {
    branch_id: task.progress_detail?.branch_id || taskInfo.branch_id || MAIN_WORLD_BRANCH_ID,
    branch_title: task.progress_detail?.branch_title || taskInfo.branch_title || "当前世界",
    task_id: task.task_id || taskInfo.task_id,
    status: task.status || "processing",
    progress: task.progress || 0,
    message: task.message || "",
    stop_reason: task.result?.stop_reason || task.progress_detail?.stop_reason || "",
    goal_verdict: task.result?.goal_verdict || task.progress_detail?.goal_verdict || null,
    latest_event: task.result?.latest_event || task.progress_detail?.latest_event || null,
    error: task.error || "",
  };
}

function hasTrackedTasks(taskMap = {}) {
  return Object.values(taskMap).some((item) => item.task_id || item.status !== "idle");
}

export function useWorldlineAutoEvolution({
  refreshWorldline,
  setFeedback,
  setError,
} = {}) {
  const createMode = ref("manual");
  const goalText = ref("");
  const maxSteps = ref(6);
  const branchTaskMap = ref({});
  const currentTask = computed(() => branchTaskMap.value[MAIN_WORLD_BRANCH_ID] || null);
  const pollTask = createWorldlineAutoTaskPoller({ getTask });

  function syncWorld(currentWorld = null) {
    if (createMode.value === "manual" && !hasTrackedTasks(branchTaskMap.value)) {
      return;
    }
    const title = currentWorld?.title || "当前世界";
    branchTaskMap.value = mergeAutoTaskSnapshot(branchTaskMap.value, {
      branch_id: MAIN_WORLD_BRANCH_ID,
      branch_title: title,
    });
  }

  function prepareAfterSessionCreate(currentWorld = null) {
    if (createMode.value === "manual") {
      branchTaskMap.value = {};
      return false;
    }
    branchTaskMap.value = createInitialAutoTaskMap([currentWorld].filter(Boolean));
    syncWorld(currentWorld);
    return true;
  }

  async function startForSession(sessionId) {
    const payload = buildAutoEvolvePayload({
      createMode: createMode.value,
      goalText: goalText.value,
      maxSteps: maxSteps.value,
    });
    if (!payload) {
      return [];
    }
    const response = await startWorldlineAutoEvolve({ session_id: sessionId, ...payload });
    const tasks = response.data?.tasks || [];
    for (const item of tasks) {
      branchTaskMap.value = mergeAutoTaskSnapshot(branchTaskMap.value, {
        branch_id: item.branch_id || MAIN_WORLD_BRANCH_ID,
        branch_title: item.branch_title || "当前世界",
        task_id: item.task_id,
        status: "pending",
        progress: 0,
        message: "自动演化任务已提交",
      });
      void trackTask(item);
    }
    return tasks;
  }

  async function trackTask(taskInfo) {
    try {
      await pollTask(taskInfo.task_id, (task) => {
        branchTaskMap.value = mergeAutoTaskSnapshot(
          branchTaskMap.value,
          buildTaskSnapshot(task, taskInfo),
        );
        void refreshWorldline?.();
      });
    } catch (err) {
      setError?.(err.message);
    } finally {
      void refreshWorldline?.();
      const latest = branchTaskMap.value[MAIN_WORLD_BRANCH_ID];
      if (latest?.status === "completed") {
        setFeedback?.("当前世界自动演化已完成");
      }
    }
  }

  return {
    createMode,
    goalText,
    maxSteps,
    branchTaskMap,
    currentTask,
    syncWorld,
    prepareAfterSessionCreate,
    startForSession,
  };
}
