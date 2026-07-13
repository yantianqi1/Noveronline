import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import { once } from "node:events";

import { afterEach, describe, expect, it } from "vitest";

import { createPiWriterExecution } from "./pi-writer-agent.js";

describe("Pi writer local OpenAI-compatible provider E2E", () => {
  const servers: ReturnType<typeof createServer>[] = [];
  afterEach(async () => {
    await Promise.all(servers.splice(0).map((server) => new Promise<void>((resolve) => server.close(() => resolve()))));
  });

  it("executes a real Pi tool round trip then streams composer prose", async () => {
    const requests: Array<Record<string, unknown>> = [];
    const requestHeaders: Array<Record<string, string | string[] | undefined>> = [];
    const server = createServer(async (request, response) => {
      const body = JSON.parse(await readBody(request)) as Record<string, unknown>;
      requests.push(body);
      requestHeaders.push(request.headers);
      const messages = body.messages as Array<{ role?: string }>;
      const lastRole = messages.at(-1)?.role;
      if (Array.isArray(body.tools) && lastRole !== "tool") {
        streamToolCall(response);
      } else if (Array.isArray(body.tools)) {
        streamText(response, "Authoritative rain-scene writing brief.");
      } else {
        streamText(response, "Rain pressed against the negotiation room windows.");
      }
    });
    servers.push(server);
    server.listen(0, "127.0.0.1");
    await once(server, "listening");
    const address = server.address();
    if (!address || typeof address === "string") throw new Error("local provider did not expose a TCP port");
    const base = {
      tenant_id: "ten-local", project_id: "proj-local", run_id: "run-local",
      channel_id: "channel-local", model_id: "model-local", provider: "openai-compatible",
      base_url: `http://127.0.0.1:${address.port}/v1`, instruction: "Write the rain negotiation scene.",
      apiKey: "local-test-key", settings: { max_tokens: 200 }, thinking_level: "off" as const
    };
    const toolCalls: string[] = [];
    const tokens: string[] = [];
    const execution = createPiWriterExecution();

    const brief = await execution.orchestrateWritingBrief({
      ...base,
      module_key: "writer_orchestrator",
      provider_call_id: "pi-writer:v1:writer_orchestrator:orchestrator:0:stable",
      mode: "draft",
      selected_asset_ids: [], graph_node_ids: [], worldline_path_ids: [], tool_names: ["query_project_context"],
      runtime_context: {
        tenant_id: "ten-local",
        project_id: "proj-local",
        run_id: "run-local",
        trace_id: "trace-local",
        requested_by: "user-local",
        permissions: { tools: ["query_project_context"], can_write_draft: false }
      },
      executeTool: async (name) => {
        toolCalls.push(name);
        return { project: { title: "Local Provider Novel", language: "en" } };
      }
    });
    const draft = await execution.composeDraft({
      ...base,
      module_key: "writer_composer",
      provider_call_id: "pi-writer:v1:writer_composer:composer:0:stable",
      writing_brief: brief.writing_brief,
      onToken: async (token) => { tokens.push(token); }
    });

    expect(toolCalls).toEqual(["query_project_context"]);
    expect(brief.writing_brief).toBe("Authoritative rain-scene writing brief.");
    expect(brief.usage).toEqual({ prompt_tokens: 9, completion_tokens: 9, cost_estimate: 0 });
    expect(draft.content).toBe("Rain pressed against the negotiation room windows.");
    expect(tokens.join("")).toBe(draft.content);
    expect(requests).toHaveLength(3);
    expect(requests.every((request) => request.stream === true)).toBe(true);
    expect(requestHeaders.slice(0, 2).map((headers) => headers["idempotency-key"])).toEqual([
      "pi-writer:v1:writer_orchestrator:orchestrator:0:stable:turn:0",
      "pi-writer:v1:writer_orchestrator:orchestrator:0:stable:turn:1"
    ]);
    expect(requestHeaders[2]?.["idempotency-key"]).toBe("pi-writer:v1:writer_composer:composer:0:stable:turn:0");
    for (const [index, headers] of requestHeaders.entries()) {
      expect(headers["x-mirofish-tenant-id"]).toBe("ten-local");
      expect(headers["x-mirofish-project-id"]).toBe("proj-local");
      expect(headers["x-mirofish-run-id"]).toBe("run-local");
      expect(headers["x-mirofish-module-key"]).toBe(index < 2 ? "writer_orchestrator" : "writer_composer");
      expect(headers["x-mirofish-provider-call-parent"]).toBe(index < 2
        ? "pi-writer:v1:writer_orchestrator:orchestrator:0:stable"
        : "pi-writer:v1:writer_composer:composer:0:stable");
      const accountingHeaders = {
        idempotency: headers["idempotency-key"],
        tenant: headers["x-mirofish-tenant-id"],
        project: headers["x-mirofish-project-id"],
        run: headers["x-mirofish-run-id"],
        module: headers["x-mirofish-module-key"]
      };
      expect(JSON.stringify(accountingHeaders)).not.toContain("local-test-key");
      expect(JSON.stringify(accountingHeaders)).not.toContain("Write the rain negotiation scene");
    }
    expect(JSON.stringify(requests)).not.toContain("local-test-key");
  }, 15_000);

  it("preflights tool allowlist and runtime ownership before calling the DB tool executor", async () => {
    const server = createServer(async (request, response) => {
      const body = JSON.parse(await readBody(request)) as Record<string, unknown>;
      const messages = body.messages as Array<{ role?: string }>;
      if (Array.isArray(body.tools) && messages.at(-1)?.role !== "tool") {
        streamToolCall(response);
      } else {
        streamText(response, "This response must not be reached.");
      }
    });
    servers.push(server);
    server.listen(0, "127.0.0.1");
    await once(server, "listening");
    const address = server.address();
    if (!address || typeof address === "string") throw new Error("permission provider did not expose a TCP port");
    let executeCalls = 0;
    const execution = createPiWriterExecution();
    const request = {
      tenant_id: "ten-runtime",
      project_id: "proj-runtime",
      run_id: "run-runtime",
      channel_id: "channel-runtime",
      model_id: "model-runtime",
      provider: "openai-compatible",
      base_url: `http://127.0.0.1:${address.port}/v1`,
      instruction: "Use project context.",
      apiKey: "permission-test-key",
      settings: { max_tokens: 100 },
      module_key: "writer_orchestrator" as const,
      provider_call_id: "pi-writer:v1:writer_orchestrator:permission:0:stable",
      mode: "draft" as const,
      selected_asset_ids: [],
      graph_node_ids: [],
      worldline_path_ids: [],
      tool_names: ["query_project_context" as const],
      executeTool: async () => {
        executeCalls += 1;
        return { unreachable: true };
      }
    };

    await expect(execution.orchestrateWritingBrief({
      ...request,
      runtime_context: {
        tenant_id: request.tenant_id,
        project_id: request.project_id,
        run_id: request.run_id,
        trace_id: "trace-runtime",
        requested_by: "user-runtime",
        permissions: { tools: [], can_write_draft: false }
      }
    })).rejects.toThrow("tool is not allowed");
    expect(executeCalls).toBe(0);

    const mismatchedContexts = [
      { field: "tenant_id", tenant_id: "different-tenant", project_id: request.project_id, run_id: request.run_id },
      { field: "project_id", tenant_id: request.tenant_id, project_id: "different-project", run_id: request.run_id },
      { field: "run_id", tenant_id: request.tenant_id, project_id: request.project_id, run_id: "different-run" }
    ];
    for (const [index, mismatch] of mismatchedContexts.entries()) {
      await expect(execution.orchestrateWritingBrief({
        ...request,
        provider_call_id: `pi-writer:v1:writer_orchestrator:ownership:${index}:stable`,
        runtime_context: {
          tenant_id: mismatch.tenant_id,
          project_id: mismatch.project_id,
          run_id: mismatch.run_id,
          trace_id: "trace-runtime",
          requested_by: "user-runtime",
          permissions: { tools: ["query_project_context"], can_write_draft: false }
        }
      })).rejects.toThrow(`${mismatch.field} does not match runtime context`);
    }
    expect(executeCalls).toBe(0);
  }, 15_000);
});

async function readBody(request: IncomingMessage): Promise<string> {
  const chunks: Buffer[] = [];
  for await (const chunk of request) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks).toString("utf8");
}

function streamToolCall(response: ServerResponse): void {
  startStream(response);
  send(response, chunk({ role: "assistant", tool_calls: [{ index: 0, id: "call-project", type: "function", function: { name: "query_project_context", arguments: "{}" } }] }, null));
  send(response, chunk({}, "tool_calls", { prompt_tokens: 4, completion_tokens: 2, total_tokens: 6 }));
  finish(response);
}

function streamText(response: ServerResponse, text: string): void {
  startStream(response);
  send(response, chunk({ role: "assistant" }, null));
  for (const part of [text.slice(0, Math.ceil(text.length / 2)), text.slice(Math.ceil(text.length / 2))]) {
    send(response, chunk({ content: part }, null));
  }
  send(response, chunk({}, "stop", { prompt_tokens: 5, completion_tokens: 7, total_tokens: 12 }));
  finish(response);
}

function startStream(response: ServerResponse): void {
  response.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
}

function send(response: ServerResponse, payload: unknown): void {
  response.write(`data: ${JSON.stringify(payload)}\n\n`);
}

function finish(response: ServerResponse): void {
  response.end("data: [DONE]\n\n");
}

function chunk(delta: Record<string, unknown>, finishReason: string | null, usage?: Record<string, number>): Record<string, unknown> {
  return {
    id: "chatcmpl-local", object: "chat.completion.chunk", created: 1, model: "model-local",
    choices: [{ index: 0, delta, finish_reason: finishReason }],
    ...(usage ? { usage } : {})
  };
}
