import assert from "node:assert/strict";
import http from "node:http";
import { test } from "node:test";

test("Worldline client preserves preparation compatibility and starts metadata-only auto-evolution", async () => {
  const requests = [];
  const server = http.createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    requests.push({
      method: request.method,
      path: request.url,
      headers: request.headers,
      body: JSON.parse(Buffer.concat(chunks).toString("utf8")),
    });

    response.statusCode = 202;
    response.setHeader("Content-Type", "application/json");
    if (request.url?.endsWith("/auto-evolutions")) {
      response.end(JSON.stringify({
        run_id: "run-auto-1",
        project_id: "project-1",
        session_id: "session-1",
        workflow_type: "worldline_auto_evolution",
        status: "queued",
        max_steps: 4,
        trace_id: "private-trace",
        options: { prompt: "private-prompt" },
        provider_response: "private-response",
      }));
      return;
    }
    response.end(JSON.stringify({
      prepare_id: "prepare-1",
      run_id: "run-prepare-1",
      project_id: "project-1",
      workflow_type: "worldline_preparation",
      status: "queued",
      lifecycle: "preparing",
      goal_summary: "Prepare the current world",
      anchor_path_id: "",
      created_by: "user-1",
      created_at: "2026-07-10T00:00:00Z",
      updated_at: "2026-07-10T00:00:00Z",
    }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const previousBaseUrl = process.env.MIROFISH_API_BASE_URL;
  process.env.MIROFISH_API_BASE_URL = `http://127.0.0.1:${address.port}`;

  try {
    const api = await import(`../lib/api.ts?worldlineApiContract=${Date.now()}`);
    const context = {
      tenantId: "tenant-1",
      actorUserId: "user-1",
      sessionCookie: "session-token",
      csrfToken: "csrf-token",
    };

    const compatiblePreparation = await api.createWorldlinePreparation({
      ...context,
      projectId: "project-1",
      goal: "Prepare the current world",
    });
    assert.equal(compatiblePreparation.ok, true);

    const selectedPreparation = await api.createWorldlinePreparation({
      ...context,
      projectId: "project-1",
      goal: "Prepare selected agents",
      anchorPathId: "path-1",
      agentRefs: [
        { source_kind: "asset", source_id: "agent-asset-1" },
        { source_kind: "entity", source_id: "agent-entity-1" },
      ],
      sourceRefs: [
        { source_kind: "saved_path", source_id: "saved-path-1" },
        { source_kind: "worldline_event", source_id: "worldline-event-1" },
      ],
      options: { pacing: "measured" },
    });
    assert.equal(selectedPreparation.ok, true);

    const autoEvolution = await api.startWorldlineAutoEvolution({
      ...context,
      sessionId: "session-1",
      maxSteps: 4,
      branchId: "legacy-branch",
      comparison: { against: "legacy-world" },
      apiKey: "top-level-secret",
      options: {
        director_mode: "paced",
        branch: "legacy-branch",
        comparison: { against: "legacy-world" },
        world_scope: "parallel-world",
        api_key: "private-key",
        credentialRef: "private-credential",
        nested: {
          safe: true,
          prompt: "private-prompt",
          manuscript: "private-manuscript",
        },
        list: [
          { keep: "yes", branch_id: "legacy-branch", provider: "local" },
          "literal",
        ],
      },
    });
    assert.deepEqual(autoEvolution, {
      ok: true,
      run_id: "run-auto-1",
      project_id: "project-1",
      session_id: "session-1",
      workflow_type: "worldline_auto_evolution",
      status: "queued",
      max_steps: 4,
    });
  } finally {
    if (previousBaseUrl === undefined) delete process.env.MIROFISH_API_BASE_URL;
    else process.env.MIROFISH_API_BASE_URL = previousBaseUrl;
    await new Promise((resolve) => server.close(resolve));
  }

  assert.deepEqual(
    requests.map((request) => [request.method, request.path]),
    [
      ["POST", "/v1/projects/project-1/worldlines/preparations"],
      ["POST", "/v1/projects/project-1/worldlines/preparations"],
      ["POST", "/v1/worldline-sessions/session-1/auto-evolutions"],
    ],
  );
  for (const request of requests) {
    assert.equal(request.headers["x-tenant-id"], "tenant-1");
    assert.equal(request.headers["x-user-id"], undefined);
    assert.equal(request.headers["x-csrf-token"], "csrf-token");
    assert.equal(request.headers.cookie, "mirofish_session=session-token");
  }
  assert.deepEqual(requests[0].body, {
    goal: "Prepare the current world",
    anchor_path_id: "",
    options: {},
  });
  assert.equal("agent_refs" in requests[0].body, false);
  assert.equal("source_refs" in requests[0].body, false);
  assert.deepEqual(requests[1].body, {
    goal: "Prepare selected agents",
    anchor_path_id: "path-1",
    agent_refs: [
      { source_kind: "asset", source_id: "agent-asset-1" },
      { source_kind: "entity", source_id: "agent-entity-1" },
    ],
    source_refs: [
      { source_kind: "saved_path", source_id: "saved-path-1" },
      { source_kind: "worldline_event", source_id: "worldline-event-1" },
    ],
    options: { pacing: "measured" },
  });
  assert.deepEqual(requests[2].body, {
    max_steps: 4,
    options: {
      director_mode: "paced",
      nested: { safe: true },
      list: [{ keep: "yes", provider: "local" }, "literal"],
    },
  });
  assert.doesNotMatch(
    JSON.stringify(requests[2].body),
    /branch|comparison|world_scope|api_key|credential|prompt|manuscript|top-level-secret|private-/i,
  );
});

test("Worldline auto-evolution client rejects incomplete success metadata", async () => {
  const server = http.createServer((_request, response) => {
    response.statusCode = 202;
    response.setHeader("Content-Type", "application/json");
    response.end(JSON.stringify({
      run_id: "run-auto-1",
      project_id: "project-1",
      session_id: "session-1",
      workflow_type: "worldline_auto_evolution",
      status: "queued",
      max_steps: 0,
    }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const previousBaseUrl = process.env.MIROFISH_API_BASE_URL;
  process.env.MIROFISH_API_BASE_URL = `http://127.0.0.1:${address.port}`;

  try {
    const api = await import(`../lib/api.ts?worldlineInvalidContract=${Date.now()}`);
    const result = await api.startWorldlineAutoEvolution({
      tenantId: "tenant-1",
      sessionId: "session-1",
      maxSteps: 4,
    });
    assert.deepEqual(result, {
      ok: false,
      code: "INVALID_API_RESPONSE",
      message: "worldline auto-evolution response missing required fields",
      request_id: "",
    });
  } finally {
    if (previousBaseUrl === undefined) delete process.env.MIROFISH_API_BASE_URL;
    else process.env.MIROFISH_API_BASE_URL = previousBaseUrl;
    await new Promise((resolve) => server.close(resolve));
  }
});
