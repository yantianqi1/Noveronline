import { pathToFileURL, fileURLToPath } from "node:url";

import { NativeConnection, Worker } from "@temporalio/worker";
import { CancelledFailure, Context } from "@temporalio/activity";

import {
  createPiWorldlineGoalStartActivity,
  runPiWorldlineGoalStartActivity
} from "./activities/pi-worldline-cast-activities.js";
import { WORLDLINE_CAST_TASK_QUEUE } from "./contracts/worldline-cast-worker-spec.js";
import {
  createAesGcmCredentialDecryptor,
  createPgPoolQueryExecutor,
  type ClosableQueryExecutor
} from "./runtime/postgres-pi-writer-deps.js";
import { createPostgresPiWorldlineCastDeps } from "./runtime/postgres-pi-worldline-cast-deps.js";
import { createPiWorldlineCastExecution } from "./runtime/pi-worldline-cast-agent.js";

export async function createWorldlineCastWorkerActivityBundle(options: {
  env?: Record<string, string | undefined>;
  createDb?(databaseUrl: string): Promise<ClosableQueryExecutor> | ClosableQueryExecutor;
  cancellationSignal?(): AbortSignal | undefined;
} = {}): Promise<{
  activities: { runPiWorldlineGoalStartActivity: typeof runPiWorldlineGoalStartActivity };
  close(): Promise<void>;
}> {
  const env = options.env ?? process.env;
  const databaseUrl = env.DATABASE_URL?.trim();
  const credentialKey = env.LLM_CREDENTIAL_ENCRYPTION_KEY?.trim();
  if (!databaseUrl) {
    return {
      activities: { runPiWorldlineGoalStartActivity },
      close: async () => undefined
    };
  }
  const db = await (options.createDb ? options.createDb(databaseUrl) : createPgPoolQueryExecutor(databaseUrl));
  const decryptCredential = credentialKey
    ? createAesGcmCredentialDecryptor(credentialKey)
    : async () => {
      throw new Error("LLM_CREDENTIAL_KEY_UNCONFIGURED: LLM_CREDENTIAL_ENCRYPTION_KEY is required");
    };
  const castExecution = createPiWorldlineCastExecution();
  const deps = createPostgresPiWorldlineCastDeps({
    db,
    decryptCredential
  });
  deps.runCastStage = castExecution.runCastStage;
  deps.cancellationSignal = options.cancellationSignal;
  return {
    activities: {
      runPiWorldlineGoalStartActivity: createPiWorldlineGoalStartActivity(deps)
    },
    close: async () => {
      await db.close();
    }
  };
}

export async function runWorldlineCastWorker(): Promise<void> {
  const temporalAddress = process.env.TEMPORAL_ADDRESS ?? "127.0.0.1:7233";
  const namespace = process.env.TEMPORAL_NAMESPACE ?? "default";
  const taskQueue = process.env.WORLDLINE_CAST_TASK_QUEUE ?? WORLDLINE_CAST_TASK_QUEUE;
  const activityBundle = await createWorldlineCastWorkerActivityBundle({
    cancellationSignal: () => Context.current().cancellationSignal
  });
  const connection = await NativeConnection.connect({ address: temporalAddress });
  try {
    const worker = await Worker.create({
      connection,
      namespace,
      taskQueue,
      workflowsPath: fileURLToPath(new URL("./workflows/pi-worldline-goal-start-workflow.js", import.meta.url)),
      activities: {
        runPiWorldlineGoalStartActivity: withCastCancellation(activityBundle.activities.runPiWorldlineGoalStartActivity)
      }
    });
    await worker.run();
  } finally {
    await activityBundle.close();
    await connection.close();
  }
}

function withCastCancellation(
  activity: typeof runPiWorldlineGoalStartActivity
): typeof runPiWorldlineGoalStartActivity {
  return async (payload: unknown) => {
    const context = Context.current();
    context.heartbeat({ stage: "started" });
    const heartbeat = () => {
      try {
        void Promise.resolve(context.heartbeat({ stage: "running" })).catch((error: unknown) => {
          console.warn("Pi worldline cast heartbeat failed", error);
        });
      } catch (error) {
        console.warn("Pi worldline cast heartbeat failed", error);
      }
    };
    const timer = setInterval(heartbeat, 2000);
    try {
      const result = await activity(payload);
      if (context.cancellationSignal.aborted) {
        throw new CancelledFailure("Pi worldline cast activity cancelled after cleanup");
      }
      return result;
    } catch (error) {
      if (context.cancellationSignal.aborted) {
        throw new CancelledFailure("Pi worldline cast activity cancelled");
      }
      throw error;
    } finally {
      clearInterval(timer);
    }
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  runWorldlineCastWorker().catch((error) => {
    console.error(error);
    process.exitCode = 1;
  });
}
