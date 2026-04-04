const PREPARE_TASK_POLL_INTERVAL_MS = 1500;

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function buildPrepareTaskSnapshot(task, prepareSnapshot) {
  return {
    ...(prepareSnapshot || {}),
    task_progress: task.progress || 0,
    task_message: task.message || "",
  };
}

export function createWorldlinePrepareTaskPoller({
  getTask,
  getPreparedSession,
  sleep: sleepImpl = sleep,
} = {}) {
  if (typeof getTask !== "function") {
    throw new Error("createWorldlinePrepareTaskPoller requires a getTask function");
  }
  if (typeof getPreparedSession !== "function") {
    throw new Error("createWorldlinePrepareTaskPoller requires a getPreparedSession function");
  }

  return async function pollPrepareTask(taskId, prepareId, onUpdate = () => {}) {
    console.log("[prepare-poller] start polling", { taskId, prepareId });
    while (true) {
      let taskResponse, prepareResponse;
      try {
        [taskResponse, prepareResponse] = await Promise.all([
          getTask(taskId),
          getPreparedSession(prepareId),
        ]);
      } catch (pollErr) {
        console.error("[prepare-poller] poll request failed", pollErr);
        throw pollErr;
      }
      const task = taskResponse.data || {};
      console.log("[prepare-poller] task status:", task.status, "progress:", task.progress);
      const snapshot = buildPrepareTaskSnapshot(task, prepareResponse.data || {});
      onUpdate(snapshot);

      if (task.status === "completed") {
        console.log("[prepare-poller] task completed");
        return snapshot;
      }
      if (task.status === "failed") {
        console.error("[prepare-poller] task failed:", task.error);
        throw new Error(task.error || "世界线 prepare 失败");
      }

      await sleepImpl(PREPARE_TASK_POLL_INTERVAL_MS);
    }
  };
}
