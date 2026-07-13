import http from "node:http";

if (process.env.MIROFISH_ASSETS_LOCAL_PROVIDER !== "1") {
  throw new Error("set MIROFISH_ASSETS_LOCAL_PROVIDER=1 to run the local-only asset embedding provider");
}

const port = Number(process.env.PORT || 18082);
const expectedKey = process.env.MIROFISH_ASSETS_LOCAL_PROVIDER_KEY?.trim() || "";
if (!Number.isSafeInteger(port) || port <= 0) throw new Error("PORT must be a positive integer");
if (!expectedKey) throw new Error("MIROFISH_ASSETS_LOCAL_PROVIDER_KEY is required");

const server = http.createServer(async (request, response) => {
  if (request.method !== "POST" || request.url !== "/v1/embeddings") {
    response.writeHead(404).end();
    return;
  }
  if (request.headers.authorization !== `Bearer ${expectedKey}`) {
    response.writeHead(401, { "Content-Type": "application/json" }).end(JSON.stringify({ error: "unauthorized" }));
    return;
  }
  try {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    const payload = JSON.parse(Buffer.concat(chunks).toString("utf8"));
    const inputs = Array.isArray(payload.input) ? payload.input : [];
    if (inputs.length === 0 || inputs.some((value) => typeof value !== "string")) {
      response.writeHead(400, { "Content-Type": "application/json" }).end(JSON.stringify({ error: "input is required" }));
      return;
    }
    const data = inputs.map((input, index) => ({ index, embedding: embeddingFor(input) }));
    response.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify({ data }));
  } catch {
    response.writeHead(400, { "Content-Type": "application/json" }).end(JSON.stringify({ error: "invalid request" }));
  }
});

server.listen(port, "0.0.0.0", () => {
  process.stdout.write(`local-only asset embedding provider listening on ${port}\n`);
});

function embeddingFor(input) {
  const normalized = input.toLowerCase();
  if (normalized.includes("moon")) return [1, 0, 0];
  if (normalized.includes("fire")) return [0, 1, 0];
  return [0.8, 0.2, 0];
}
