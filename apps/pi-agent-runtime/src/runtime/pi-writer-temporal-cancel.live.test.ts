import { createServer } from "node:http";
import { once } from "node:events";
import { fileURLToPath } from "node:url";

import { Context } from "@temporalio/activity";
import { Client, Connection } from "@temporalio/client";
import { NativeConnection, Worker, bundleWorkflowCode } from "@temporalio/worker";
import { afterAll, describe, expect, it } from "vitest";

import { createPiWriterRunActivity, type PiWriterRunActivityDeps } from "../activities/pi-writer-activities.js";
import { createPiWriterExecution } from "./pi-writer-agent.js";
import { withTemporalCancellation } from "../worker.js";

const describeLive = process.env.MIROFISH_PI_WRITER_TEMPORAL_LIVE === "1" ? describe : describe.skip;

describeLive("Pi writer real Temporal cancellation", () => {
  const servers: ReturnType<typeof createServer>[] = [];
  afterAll(async () => {
    await Promise.all(servers.map((server) => new Promise<void>((resolve) => server.close(() => resolve()))));
  });

  it("aborts the provider and releases quota plus concurrency resources", async () => {
    let providerStarted!: () => void;
    const started = new Promise<void>((resolve) => { providerStarted = resolve; });
    let providerClosed = false;
    const provider = createServer(async (request, response) => {
      for await (const _chunk of request) { /* drain request */ }
      response.writeHead(200, { "Content-Type": "text/event-stream" });
      providerStarted();
      await new Promise<void>((resolve) => {
        response.on("close", () => { providerClosed = true; resolve(); });
      });
    });
    servers.push(provider);
    provider.listen(0, "127.0.0.1");
    await once(provider, "listening");
    const address = provider.address();
    if (!address || typeof address === "string") throw new Error("cancel provider did not bind");

    const reservations: string[] = [];
    const releasedReservations: string[] = [];
    const releasedLeases: string[] = [];
    const execution = createPiWriterExecution();
    const deps: PiWriterRunActivityDeps = {
      cancellationSignal: () => Context.current().cancellationSignal,
      resolveModuleBinding: async ({ module_key }) => ({
        module_key,
        channel_id: `${module_key}-channel`,
        model_id: `${module_key}-model`,
        provider: "openai-compatible",
        base_url: `http://127.0.0.1:${address.port}/v1`,
        credential_ref: `${module_key}-credential`,
        supports_tools: module_key === "writer_orchestrator",
        supports_json: true,
        settings: { quota_reserved_tokens: 1000 }
      }),
      resolveCredential: async () => ({ apiKey: "cancel-test-key" }),
      reserveLLMQuota: async (request) => {
        reservations.push(request.provider_call_id);
        return {
          reservation_id: `reservation-${reservations.length}`,
          provider_call_id: request.provider_call_id,
          status: "reserved",
          expires_at: new Date(Date.now() + 60_000).toISOString()
        };
      },
      finalizeLLMQuota: async () => { throw new Error("provider must not finalize after cancellation"); },
      releaseLLMQuota: async (request) => { releasedReservations.push(request.provider_call_id); },
      acquireLLMLease: async (request) => ({
        lease_id: `lease-${request.module_key}`,
        channel_id: request.channel_id,
        lock_mode: "slot:0"
      }),
      releaseLLMLease: async (request) => { releasedLeases.push(request.lease_id); },
      executeWriterTool: async () => ({}),
      orchestrateWritingBrief: execution.orchestrateWritingBrief,
      composeDraft: execution.composeDraft,
      saveDraftRevision: async () => { throw new Error("cancelled run must not save a candidate"); },
      recordLLMActivity: async () => undefined,
      recordUsageEvent: async () => undefined,
      recordAgentTraceEvent: async () => undefined,
      recordWorkflowEvent: async () => undefined,
      updateWriterRunStatus: async () => undefined
    };
    const activity = withTemporalCancellation(createPiWriterRunActivity(deps));
    const taskQueue = `pi-writer-cancel-${Date.now()}`;
    const workflowBundle = await bundleWorkflowCode({
      workflowsPath: fileURLToPath(new URL("../workflows/pi-writer-workflow.ts", import.meta.url))
    });
    const nativeConnection = await NativeConnection.connect({ address: "127.0.0.1:7233" });
    const worker = await Worker.create({
      connection: nativeConnection,
      namespace: "default",
      taskQueue,
      workflowBundle,
      activities: { runPiWriterRunActivity: activity }
    });
    const workerRun = worker.run();
    const clientConnection = await Connection.connect({ address: "127.0.0.1:7233" });
    const client = new Client({ connection: clientConnection, namespace: "default" });
    try {
      const handle = await client.workflow.start("PiWriterRunWorkflow", {
        taskQueue,
        workflowId: `pi-writer-cancel-${Date.now()}`,
        args: [{
          tenant_id: "tenant-cancel",
          project_id: "project-cancel",
          run_id: "run-cancel",
          trace_id: "trace-cancel",
          requested_by: "user-cancel",
          mode: "draft",
          instruction: "wait for cancellation",
          selected_asset_ids: [],
          graph_node_ids: [],
          worldline_path_ids: [],
          options: { module_key: "writer_composer" }
        }]
      });
      await started;
      await handle.cancel();
      await expect(handle.result()).rejects.toThrow();
      await eventually(() => providerClosed && releasedReservations.length === 1 && releasedLeases.length === 1);
      expect(releasedReservations).toEqual(reservations);
      expect(releasedLeases).toEqual(["lease-writer_orchestrator"]);
    } finally {
      worker.shutdown();
      await workerRun;
      await clientConnection.close();
      await nativeConnection.close();
    }
  }, 60_000);
});

async function eventually(predicate: () => boolean): Promise<void> {
  const deadline = Date.now() + 10_000;
  while (!predicate()) {
    if (Date.now() >= deadline) throw new Error("Temporal cancellation cleanup did not complete");
    await new Promise((resolve) => setTimeout(resolve, 50));
  }
}
