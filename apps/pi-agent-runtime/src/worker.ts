import { pathToFileURL, fileURLToPath } from "node:url";

import { NativeConnection, Worker } from "@temporalio/worker";

import * as activities from "./activities/pi-writer-activities.js";
import { createPiWriterRunActivity, type ComposeDraftResult, type ComposeDraftRequest } from "./activities/pi-writer-activities.js";
import { createPiAIComposeDraft } from "./llm/pi-ai-compose.js";
import {
  createAesGcmCredentialDecryptor,
  createPgPoolQueryExecutor,
  createPostgresPiWriterDeps,
  type ClosableQueryExecutor
} from "./runtime/postgres-pi-writer-deps.js";
import { WRITER_TASK_QUEUE } from "./worker-spec.js";

export interface WorkerActivityBundle {
  activities: typeof activities;
  close(): Promise<void>;
}

export interface WorkerActivityBundleOptions {
  env?: Record<string, string | undefined>;
  createDb?(databaseUrl: string): Promise<ClosableQueryExecutor> | ClosableQueryExecutor;
  composeDraft?(request: ComposeDraftRequest): Promise<ComposeDraftResult>;
}

export async function createWorkerActivityBundle(options: WorkerActivityBundleOptions = {}): Promise<WorkerActivityBundle> {
  const env = options.env ?? process.env;
  const databaseUrl = env.DATABASE_URL?.trim();
  const credentialKey = env.LLM_CREDENTIAL_ENCRYPTION_KEY?.trim();
  if (!databaseUrl) {
    return {
      activities,
      close: async () => undefined
    };
  }

  const db = await (options.createDb ? options.createDb(databaseUrl) : createPgPoolQueryExecutor(databaseUrl));
  const decryptCredential = credentialKey
    ? createAesGcmCredentialDecryptor(credentialKey)
    : async () => {
      throw new Error("LLM_CREDENTIAL_KEY_UNCONFIGURED: LLM_CREDENTIAL_ENCRYPTION_KEY is required to decrypt LLM Facility credentials");
    };
  const deps = createPostgresPiWriterDeps({
    db,
    decryptCredential,
    composeDraft: options.composeDraft ?? createPiAIComposeDraft()
  });
  return {
    activities: {
      ...activities,
      runPiWriterRunActivity: createPiWriterRunActivity(deps)
    },
    close: async () => {
      await db.close();
    }
  };
}

export async function runWorker(): Promise<void> {
  const temporalAddress = process.env.TEMPORAL_ADDRESS ?? "127.0.0.1:7233";
  const namespace = process.env.TEMPORAL_NAMESPACE ?? "default";
  const taskQueue = process.env.WRITER_TASK_QUEUE ?? WRITER_TASK_QUEUE;
  const activityBundle = await createWorkerActivityBundle();
  const connection = await NativeConnection.connect({ address: temporalAddress });
  try {
    const worker = await Worker.create({
      connection,
      namespace,
      taskQueue,
      workflowsPath: fileURLToPath(new URL("./workflows/pi-writer-workflow.js", import.meta.url)),
      activities: activityBundle.activities
    });
    await worker.run();
  } finally {
    await activityBundle.close();
    await connection.close();
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  runWorker().catch((error: unknown) => {
    console.error(error);
    process.exit(1);
  });
}
