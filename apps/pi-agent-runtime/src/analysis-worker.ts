import { pathToFileURL, fileURLToPath } from "node:url";

import { NativeConnection, Worker } from "@temporalio/worker";
import { CancelledFailure, Context } from "@temporalio/activity";

import {
  createPiAnalysisRunActivity,
  runPiAnalysisRunActivity
} from "./activities/pi-analysis-activities.js";
import { ANALYSIS_TASK_QUEUE } from "./contracts/analysis-worker-spec.js";
import {
  createAesGcmCredentialDecryptor,
  createPgPoolQueryExecutor,
  type ClosableQueryExecutor
} from "./runtime/postgres-pi-writer-deps.js";
import { createPostgresPiAnalysisDeps } from "./runtime/postgres-pi-analysis-deps.js";
import { createPiAnalysisExecution } from "./runtime/pi-analysis-agent.js";
import { objectStoreFromEnv } from "./runtime/object-store.js";

export async function createAnalysisWorkerActivityBundle(options: {
  env?: Record<string, string | undefined>;
  createDb?(databaseUrl: string): Promise<ClosableQueryExecutor> | ClosableQueryExecutor;
  cancellationSignal?(): AbortSignal | undefined;
} = {}): Promise<{
  activities: { runPiAnalysisRunActivity: typeof runPiAnalysisRunActivity };
  close(): Promise<void>;
}> {
  const env = options.env ?? process.env;
  const databaseUrl = env.DATABASE_URL?.trim();
  const credentialKey = env.LLM_CREDENTIAL_ENCRYPTION_KEY?.trim();
  if (!databaseUrl) {
    return {
      activities: { runPiAnalysisRunActivity },
      close: async () => undefined
    };
  }
  const db = await (options.createDb ? options.createDb(databaseUrl) : createPgPoolQueryExecutor(databaseUrl));
  const decryptCredential = credentialKey
    ? createAesGcmCredentialDecryptor(credentialKey)
    : async () => {
      throw new Error("LLM_CREDENTIAL_KEY_UNCONFIGURED: LLM_CREDENTIAL_ENCRYPTION_KEY is required");
    };
  const analysisExecution = createPiAnalysisExecution();
  const objectStore = objectStoreFromEnv(env);
  const deps = createPostgresPiAnalysisDeps({
    db,
    decryptCredential,
    objectStore: objectStore ?? undefined
  });
  deps.runAnalysisStage = analysisExecution.runAnalysisStage;
  deps.cancellationSignal = options.cancellationSignal;
  return {
    activities: {
      runPiAnalysisRunActivity: createPiAnalysisRunActivity(deps)
    },
    close: async () => {
      await db.close();
    }
  };
}

export async function runAnalysisWorker(): Promise<void> {
  const temporalAddress = process.env.TEMPORAL_ADDRESS ?? "127.0.0.1:7233";
  const namespace = process.env.TEMPORAL_NAMESPACE ?? "default";
  const taskQueue = process.env.ANALYSIS_TASK_QUEUE ?? ANALYSIS_TASK_QUEUE;
  const activityBundle = await createAnalysisWorkerActivityBundle({
    cancellationSignal: () => Context.current().cancellationSignal
  });
  const connection = await NativeConnection.connect({ address: temporalAddress });
  try {
    const worker = await Worker.create({
      connection,
      namespace,
      taskQueue,
      workflowsPath: fileURLToPath(new URL("./workflows/pi-analysis-workflow.js", import.meta.url)),
      activities: {
        runPiAnalysisRunActivity: withAnalysisCancellation(activityBundle.activities.runPiAnalysisRunActivity)
      }
    });
    await worker.run();
  } finally {
    await activityBundle.close();
    await connection.close();
  }
}

function withAnalysisCancellation(
  activity: typeof runPiAnalysisRunActivity
): typeof runPiAnalysisRunActivity {
  return async (payload: unknown) => {
    const context = Context.current();
    context.heartbeat({ stage: "started" });
    const timer = setInterval(() => context.heartbeat({ stage: "running" }), 2000);
    try {
      const result = await activity(payload);
      if (context.cancellationSignal.aborted) {
        throw new CancelledFailure("Pi analysis activity cancelled after cleanup");
      }
      return result;
    } catch (error) {
      if (context.cancellationSignal.aborted) {
        throw new CancelledFailure("Pi analysis activity cancelled after cleanup");
      }
      throw error;
    } finally {
      clearInterval(timer);
    }
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  runAnalysisWorker().catch((error: unknown) => {
    console.error(error);
    process.exit(1);
  });
}
