#!/usr/bin/env node

import { createServer } from "node:http";

const port = Number(process.env.MIROFISH_WORLDLINE_CHARACTER_PROVIDER_PORT || "43119");
let characterRound = 0;

const server = createServer(async (request, response) => {
  if (request.method === "GET" && request.url === "/healthz") {
    response.writeHead(200, { "Content-Type": "application/json" }).end('{"status":"ok"}');
    return;
  }
  if (request.method === "GET" && request.url === "/v1/models") {
    const models = ["journey-worldline-prepare", "journey-worldline-director", "journey-character-dialogue", "journey-writer-orchestrator", "journey-writer-composer"];
    response.writeHead(200, { "Content-Type": "application/json" }).end(JSON.stringify({ data: models.map((id) => ({ id, owned_by: "local" })) }));
    return;
  }
  if (request.method !== "POST") {
    response.writeHead(404).end();
    return;
  }
  const chunks = [];
  for await (const chunk of request) chunks.push(Buffer.from(chunk));
  const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
  const moduleKey = request.headers["x-mirofish-module-key"] || moduleFromModel(body.model);
  if (moduleKey === "writer_orchestrator" || moduleKey === "writer_composer") {
    respondWriter(response, body);
    return;
  }
  const content = moduleKey === "worldline_agent_prepare"
    ? preparation(body)
    : moduleKey === "character_dialogue"
      ? character()
      : worldline();
  const payload = JSON.stringify({
    choices: [{ message: { content: JSON.stringify(content) } }],
    usage: { prompt_tokens: 12, completion_tokens: 18, total_tokens: 30 },
  });
  response.writeHead(200, { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(payload) }).end(payload);
});

server.listen(port, "0.0.0.0", () => process.stdout.write(`worldline-character local provider ready on ${port}\n`));

function preparation(body) {
  const refs = Array.from(new Set(JSON.stringify(body).match(/(?:asset|entity):[0-9a-f-]{12,}/gi) || []));
  return {
    prepared_agents: refs.map((sourceRef, index) => ({
      source_ref: sourceRef,
      display_name: `Prepared character ${index + 1}`,
      role: "protagonist",
      public_profile: { summary: "Prepared from the selected persisted source for the current-world journey." },
    })),
  };
}

function worldline() {
  return {
    candidate_events: [{
      title: `Current-world pressure ${Date.now()}`,
      summary: "The council delays the handoff and raises the cost of the next choice.",
      kind: "political_turn",
      confidence: 0.82,
      involved_agent_ids: [],
      state_change_summary: "Pressure rises without automatic canon adoption.",
    }],
  };
}

function character() {
  characterRound += 1;
  return {
    reply_summary: `The character names the hidden cost of the pact in round ${characterRound}.`,
    speaker_type: "agent",
    speaker_id: "prepared-agent",
    memory_candidates: [{ summary: `The rain-night pact carried a hidden debt in round ${characterRound}.` }],
    relation_candidates: [{ summary: "The negotiators now distrust each other's silence.", source_entity_name: "Negotiator", target_entity_name: "Witness", relationship_type: "distrusts" }],
    world_state_candidates: [{ summary: "The inner gate remains sealed.", state_changes: { inner_gate: "sealed" } }],
  };
}

function respondWriter(response, body) {
  response.writeHead(200, { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" });
  const text = Array.isArray(body.tools)
    ? "The selected interaction becomes a chapter and scene candidate while manuscript adoption remains explicit."
    : "Plan the candidate from the selected interaction metadata.";
  response.write(`data: ${JSON.stringify(chunk({ role: "assistant", content: text.slice(0, 45) }, null))}\n\n`);
  response.write(`data: ${JSON.stringify(chunk({ content: text.slice(45) }, "stop", { prompt_tokens: 11, completion_tokens: 15, total_tokens: 26 }))}\n\n`);
  response.end("data: [DONE]\n\n");
}

function chunk(delta, finishReason, usage) {
  return { id: "journey-live", object: "chat.completion.chunk", created: 1, model: "journey-live", choices: [{ index: 0, delta, finish_reason: finishReason }], ...(usage ? { usage } : {}) };
}

function moduleFromModel(model) {
  if (String(model).includes("prepare")) return "worldline_agent_prepare";
  if (String(model).includes("character")) return "character_dialogue";
  if (String(model).includes("orchestrator")) return "writer_orchestrator";
  if (String(model).includes("composer")) return "writer_composer";
  return "worldline_director";
}

for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => server.close(() => process.exit(0)));
