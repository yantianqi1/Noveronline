const AUTO_TASK_POLL_INTERVAL_MS = 1500;

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export function createWorldlineAutoTaskPoller({
  getTask,
  sleep: sleepImpl = sleep,
} = {}) {
  if (typeof getTask !== "function") {
    throw new Error("createWorldlineAutoTaskPoller requires a getTask function");
  }

  return async function pollWorldlineAutoTask(taskId, onUpdate = () => {}) {
    while (true) {
      const response = await getTask(taskId);
      const task = response.data || {};
      onUpdate(task);
      if (task.status === "completed") {
        return task;
      }
      if (task.status === "failed") {
        throw new Error(task.error || "世界线自动演化失败");
      }
      await sleepImpl(AUTO_TASK_POLL_INTERVAL_MS);
    }
  };
}
