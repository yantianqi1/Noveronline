/**
 * Polling utility for graph build tasks.
 * Ported from src-vue/views/story-graph/graphBuildTaskPoller.js.
 */

import type { ApiResponse } from "@/api/http";

const GRAPH_TASK_POLL_INTERVAL_MS = 1500;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export interface TaskData {
  status: string;
  progress?: number;
  error?: string;
  result?: Record<string, unknown>;
  metadata?: {
    stages?: StageEvent[];
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface StageEvent {
  stage: string;
  progress?: number;
  elapsed_ms?: number;
  counts?: Record<string, unknown>;
  sample?: unknown[];
  error_summary?: string;
  traceback?: string;
  failed_after?: string;
}

export interface GraphBuildTaskPollerDeps {
  getTask: (taskId: string) => Promise<ApiResponse>;
  sleepImpl?: (ms: number) => Promise<void>;
}

export function createGraphBuildTaskPoller({
  getTask,
  sleepImpl = sleep,
}: GraphBuildTaskPollerDeps) {
  return async function pollGraphBuildTask(
    taskId: string,
    onUpdate: (task: TaskData) => void = () => {},
  ): Promise<TaskData> {
    for (;;) {
      const response = await getTask(taskId);
      const task = (response.data || {}) as TaskData;
      onUpdate(task);
      if (task.status === "completed") {
        return task;
      }
      if (task.status === "failed") {
        throw new Error(task.error || "\u56FE\u8C31\u6784\u5EFA\u5931\u8D25");
      }
      await sleepImpl(GRAPH_TASK_POLL_INTERVAL_MS);
    }
  };
}
