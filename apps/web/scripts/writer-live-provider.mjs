#!/usr/bin/env node

import { createServer } from "node:http";

const port = Number(process.env.MIROFISH_WRITER_PROVIDER_PORT || "43117");
if (!Number.isSafeInteger(port) || port < 1024 || port > 65535) {
  throw new Error("writer live provider port must be an unprivileged TCP port");
}
const cancellationBoundaryTimeoutMs = Number(process.env.MIROFISH_WRITER_CANCEL_BOUNDARY_TIMEOUT_MS || "120000");
if (!Number.isSafeInteger(cancellationBoundaryTimeoutMs) || cancellationBoundaryTimeoutMs <= 0) {
  throw new Error("writer live provider cancellation boundary timeout must be a positive integer");
}

const server = createServer(async (request, response) => {
  if (request.method === "GET" && request.url === "/healthz") {
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end('{"status":"ok"}');
    return;
  }
  if (request.method !== "POST") {
    response.writeHead(404).end();
    return;
  }

  const chunks = [];
  for await (const chunk of request) chunks.push(Buffer.from(chunk));
  const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  process.stdout.write(`writer live provider request: ${String(body.model || "unknown")}\n`);
  if (body.model === "writer-live-reviewer") {
    const content = JSON.stringify({ issues: [{
      severity: "medium",
      category: "pov_drift",
      summary: "The focal perspective shifts without a clear transition.",
      suggestion: "Keep the scene anchored to Mara's observable experience.",
    }] });
    response.writeHead(200, { "Content-Type": "application/json" });
    response.end(JSON.stringify({
      id: "writer-review-live",
      object: "chat.completion",
      choices: [{ index: 0, message: { role: "assistant", content }, finish_reason: "stop" }],
      usage: { prompt_tokens: 23, completion_tokens: 27, total_tokens: 50 },
    }));
    return;
  }
  if (body.model === "writer-live-dedup") {
    sendJSON(response, { patterns: [{
      pattern_text: "Repeated threshold gesture",
      pattern_kind: "description",
      occurrence_count: 2,
    }] }, "writer-dedup-live");
    return;
  }
  if (body.model === "writer-live-book-planner") {
    sendJSON(response, {
      premise: "A city must choose between memory and safety.",
      acts: [{ title: "Signal", summary: "The hidden cost of passage appears.", chapter_start: 1, chapter_end: 6 }],
    }, "writer-book-planner-live");
    return;
  }
  if (JSON.stringify(body).includes("CANCEL_BOUNDARY")) {
    await waitForCancellationBoundary(response, cancellationBoundaryTimeoutMs);
    if (response.destroyed) return;
  }

  response.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
  const lastRole = body.messages?.at(-1)?.role;
  if (Array.isArray(body.tools) && lastRole !== "tool") {
    send(response, chunk({ role: "assistant", tool_calls: [
      toolCall(0, "writer-assets", "query_assets"),
      toolCall(1, "writer-graph", "query_graph_neighbors"),
      toolCall(2, "writer-worldline", "query_worldline_paths"),
    ] }, null));
    send(response, chunk({}, "tool_calls"));
  } else {
    const text = Array.isArray(body.tools)
      ? "Use the selected asset, graph relationship, and saved worldline path as explicit references."
      : "Rain tightened across the gate as Mara named the price of passage and waited for the answer.";
    send(response, chunk({ role: "assistant" }, null));
    send(response, chunk({ content: text.slice(0, 38) }, null));
    send(response, chunk({ content: text.slice(38) }, null));
    send(response, chunk({}, "stop", { prompt_tokens: 17, completion_tokens: 19, total_tokens: 36 }));
  }
  response.end("data: [DONE]\n\n");
});

server.listen(port, "0.0.0.0", () => process.stdout.write(`writer live provider ready on ${port}\n`));

function toolCall(index, id, name) {
  return { index, id, type: "function", function: { name, arguments: "{}" } };
}

function chunk(delta, finish_reason, usage) {
  return {
    id: "writer-live", object: "chat.completion.chunk", created: 1, model: "writer-live",
    choices: [{ index: 0, delta, finish_reason }], ...(usage ? { usage } : {}),
  };
}

function send(response, value) {
  response.write(`data: ${JSON.stringify(value)}\n\n`);
}

function sendJSON(response, content, id) {
  response.writeHead(200, { "Content-Type": "application/json" });
  response.end(JSON.stringify({
    id,
    object: "chat.completion",
    choices: [{ index: 0, message: { role: "assistant", content: JSON.stringify(content) }, finish_reason: "stop" }],
    usage: { prompt_tokens: 20, completion_tokens: 10, total_tokens: 30 },
  }));
}

function waitForCancellationBoundary(response, timeoutMs) {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, timeoutMs);
    response.once("close", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => server.close(() => process.exit(0)));
}
