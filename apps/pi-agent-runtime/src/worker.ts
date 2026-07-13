import { pathToFileURL, fileURLToPath } from "node:url";

import { NativeConnection, Worker } from "@temporalio/worker";
import { CancelledFailure, Context } from "@temporalio/activity";

import * as activities from "./activities/pi-writer-activities.js";
import { createPiWriterRunActivity, type ComposeDraftResult, type ComposeDraftRequest, type ProviderStageCheckpoint } from "./activities/pi-writer-activities.js";
import { createPiWriterExecution } from "./runtime/pi-writer-agent.js";
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
  cancellationSignal?(): AbortSignal | undefined;
  loadProviderStageCheckpoint?(providerCallID: string): Promise<ProviderStageCheckpoint | undefined>;
  saveProviderStageCheckpoint?(checkpoint: ProviderStageCheckpoint): Promise<void>;
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
  const writerExecution = createPiWriterExecution();
  const deps = createPostgresPiWriterDeps({
    db,
    decryptCredential,
    composeDraft: options.composeDraft ?? writerExecution.composeDraft
  });
  deps.cancellationSignal = options.cancellationSignal;
  deps.loadProviderStageCheckpoint = options.loadProviderStageCheckpoint;
  deps.saveProviderStageCheckpoint = options.saveProviderStageCheckpoint;
  if (!options.composeDraft) {
    deps.orchestrateWritingBrief = writerExecution.orchestrateWritingBrief;
    deps.composeDraft = writerExecution.composeDraft;
  }
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
  const activityBundle = await createWorkerActivityBundle({
    cancellationSignal: () => Context.current().cancellationSignal,
    loadProviderStageCheckpoint: loadTemporalStageCheckpoint,
    saveProviderStageCheckpoint: saveTemporalStageCheckpoint
  });
  const connection = await NativeConnection.connect({ address: temporalAddress });
  try {
    const worker = await Worker.create({
      connection,
      namespace,
      taskQueue,
      workflowsPath: fileURLToPath(new URL("./workflows/pi-writer-workflow.js", import.meta.url)),
      activities: {
        ...activityBundle.activities,
        runPiWriterRunActivity: withTemporalCancellation(activityBundle.activities.runPiWriterRunActivity)
      }
    });
    await worker.run();
  } finally {
    await activityBundle.close();
    await connection.close();
  }
}

export function withTemporalCancellation(
  activity: typeof activities.runPiWriterRunActivity
): typeof activities.runPiWriterRunActivity {
  return async (payload: unknown) => {
    const context = Context.current();
    initializeTemporalCheckpointState(context);
    context.heartbeat(temporalHeartbeatDetails(context, "started"));
    const timer = setInterval(() => context.heartbeat(temporalHeartbeatDetails(context, "running")), 500);
    try {
      const result = await activity(payload);
      if (context.cancellationSignal.aborted) {
        throw new CancelledFailure("Pi writer activity cancelled after cleanup");
      }
      return result;
    } catch (error) {
      if (context.cancellationSignal.aborted) {
        throw new CancelledFailure("Pi writer activity cancelled after cleanup");
      }
      throw error;
    } finally {
      clearInterval(timer);
      temporalCheckpointState.delete(context);
    }
  };
}

interface TemporalHeartbeatDetails {
  stage: string;
  provider_stages: ProviderStageCheckpoint[];
}

const temporalCheckpointState = new WeakMap<Context, ProviderStageCheckpoint[]>();

function initializeTemporalCheckpointState(context: Context): void {
  const details = context.info.heartbeatDetails as Partial<TemporalHeartbeatDetails> | undefined;
  const checkpoints = Array.isArray(details?.provider_stages) ? details.provider_stages : [];
  temporalCheckpointState.set(context, checkpoints);
}

function temporalHeartbeatDetails(context: Context, stage: string): TemporalHeartbeatDetails {
  return { stage, provider_stages: temporalCheckpointState.get(context) ?? [] };
}

async function loadTemporalStageCheckpoint(providerCallID: string): Promise<ProviderStageCheckpoint | undefined> {
  return temporalCheckpointState.get(Context.current())?.find((checkpoint) => checkpoint.provider_call_id === providerCallID);
}

async function saveTemporalStageCheckpoint(checkpoint: ProviderStageCheckpoint): Promise<void> {
  const context = Context.current();
  const checkpoints = temporalCheckpointState.get(context) ?? [];
  const next = [...checkpoints.filter((item) => item.provider_call_id !== checkpoint.provider_call_id), checkpoint];
  temporalCheckpointState.set(context, next);
  context.heartbeat(temporalHeartbeatDetails(context, "provider_completed"));
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  runWorker().catch((error: unknown) => {
    console.error(error);
    process.exit(1);
  });
}
