/**
 * Auto-task poller: polls the auto-evolution task until it completes or fails.
 *
 * Ported from: src-vue/views/worldline/worldlineAutoTaskPoller.js
 */

import type { ApiResponse } from "@/api/http";

const AUTO_TASK_POLL_INTERVAL_MS = 1500;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export interface AutoTaskPollerDeps {
  getTask: (taskId: string) => Promise<ApiResponse>;
  sleepImpl?: (ms: number) => Promise<void>;
}

export function createWorldlineAutoTaskPoller(
  deps: AutoTaskPollerDeps,
): (
  taskId: string,
  onUpdate?: (task: Record<string, unknown>) => void,
) => Promise<Record<string, unknown>> {
  const { getTask, sleepImpl = sleep } = deps;

  return async function pollWorldlineAutoTask(
    taskId: string,
    onUpdate: (task: Record<string, unknown>) => void = () => {},
  ): Promise<Record<string, unknown>> {
    for (;;) {
      const response: ApiResponse = await getTask(taskId);
      const task = (response.data ?? {}) as Record<string, unknown>;
      onUpdate(task);
      if (task.status === "completed") return task;
      if (task.status === "failed") {
        throw new Error(
          (task.error as string) || "世界线自动演化失败",
        );
      }
      await sleepImpl(AUTO_TASK_POLL_INTERVAL_MS);
    }
  };
}
