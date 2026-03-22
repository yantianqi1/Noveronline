const GRAPH_TASK_POLL_INTERVAL_MS = 1500;

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export function createGraphBuildTaskPoller({
  getTask,
  sleep: sleepImpl = sleep,
} = {}) {
  if (typeof getTask !== "function") {
    throw new Error("createGraphBuildTaskPoller requires a getTask function");
  }

  return async function pollGraphBuildTask(taskId, onUpdate = () => {}) {
    while (true) {
      const response = await getTask(taskId);
      const task = response.data || {};
      onUpdate(task);
      if (task.status === "completed") {
        return task;
      }
      if (task.status === "failed") {
        throw new Error(task.error || "图谱构建失败");
      }
      await sleepImpl(GRAPH_TASK_POLL_INTERVAL_MS);
    }
  };
}
