/**
 * Prepare-task poller: polls backend task + prepare status until
 * the prepare step completes or fails.
 *
 * Ported from: src-vue/views/worldline/worldlinePrepareTaskPoller.js
 */

import type { ApiResponse } from "@/api/http";

const PREPARE_TASK_POLL_INTERVAL_MS = 1500;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

export interface PrepareSnapshot {
  status?: string;
  can_start?: boolean;
  task_progress?: number;
  task_message?: string;
  error?: string;
  [key: string]: unknown;
}

function buildPrepareTaskSnapshot(
  task: Record<string, unknown>,
  prepareSnapshot: Record<string, unknown> | null,
): PrepareSnapshot {
  return {
    ...(prepareSnapshot || {}),
    task_progress: (task.progress as number) || 0,
    task_message: (task.message as string) || "",
  };
}

export interface PrepareTaskPollerDeps {
  getTask: (taskId: string) => Promise<ApiResponse>;
  getPreparedSession: (prepareId: string) => Promise<ApiResponse>;
  sleepImpl?: (ms: number) => Promise<void>;
}

export function createWorldlinePrepareTaskPoller(
  deps: PrepareTaskPollerDeps,
): (
  taskId: string,
  prepareId: string,
  onUpdate?: (snapshot: PrepareSnapshot) => void,
) => Promise<PrepareSnapshot> {
  const {
    getTask,
    getPreparedSession,
    sleepImpl = sleep,
  } = deps;

  return async function pollPrepareTask(
    taskId: string,
    prepareId: string,
    onUpdate: (snapshot: PrepareSnapshot) => void = () => {},
  ): Promise<PrepareSnapshot> {
    for (;;) {
      let taskResponse: ApiResponse;
      let prepareResponse: ApiResponse;
      try {
        [taskResponse, prepareResponse] = await Promise.all([
          getTask(taskId),
          getPreparedSession(prepareId),
        ]);
      } catch (pollErr) {
        throw pollErr;
      }
      const task = (taskResponse.data ?? {}) as Record<string, unknown>;
      const snapshot = buildPrepareTaskSnapshot(
        task,
        (prepareResponse.data ?? {}) as Record<string, unknown>,
      );
      onUpdate(snapshot);

      if (task.status === "completed") {
        return snapshot;
      }
      if (task.status === "failed") {
        throw new Error(
          (task.error as string) || "世界线 prepare 失败",
        );
      }

      await sleepImpl(PREPARE_TASK_POLL_INTERVAL_MS);
    }
  };
}
