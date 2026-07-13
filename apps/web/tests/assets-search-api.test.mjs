import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";

test("asset search capabilities client calls project capabilities route", async () => {
  const requests = [];
  const server = http.createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    requests.push({
      method: request.method,
      url: request.url,
      headers: request.headers,
    });
    response.setHeader("Content-Type", "application/json");
    response.end(JSON.stringify({
      keyword: true,
      vector: false,
      hybrid: false,
      reason: "asset_search_embedding module is not bound",
      config_href: "/projects/project-1/llm-facility?module=asset_search_embedding",
    }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const previousBaseUrl = process.env.MIROFISH_API_BASE_URL;
  process.env.MIROFISH_API_BASE_URL = `http://127.0.0.1:${address.port}`;

  try {
    const api = await import(`../lib/api.ts?assetSearchCapabilitiesApi=${Date.now()}`);
    const result = await api.getAssetSearchCapabilities({
      tenantId: "tenant-1",
      projectId: "project-1",
      sessionCookie: "session-secret",
      csrfToken: "csrf-secret",
    });
    assert.equal(result.ok, true);
    assert.equal(result.keyword, true);
    assert.equal(result.vector, false);
    assert.equal(result.hybrid, false);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].method, "GET");
    assert.equal(requests[0].url, "/v1/projects/project-1/assets/search-capabilities");
    assert.equal(requests[0].headers.cookie, "mirofish_session=session-secret");
  } finally {
    if (previousBaseUrl === undefined) delete process.env.MIROFISH_API_BASE_URL;
    else process.env.MIROFISH_API_BASE_URL = previousBaseUrl;
    await new Promise((resolve) => server.close(resolve));
  }
});

test("asset search forwards cookie CSRF and filters without client embeddings", async () => {
  const requests = [];
  const server = http.createServer(async (request, response) => {
    const chunks = [];
    for await (const chunk of request) chunks.push(chunk);
    requests.push({
      method: request.method,
      url: request.url,
      headers: request.headers,
      body: JSON.parse(Buffer.concat(chunks).toString("utf8")),
    });
    response.setHeader("Content-Type", "application/json");
    response.end(JSON.stringify({ items: [{
      search_document_id: "doc-1",
      source: "asset",
      source_ref: "asset-1",
      project_id: "project-1",
      entity_type: "world_rule",
      title: "Moon rule",
      tags: ["moon"],
      payload: {},
      version: { count: 1, latest_version: 1, latest_version_id: "version-1" },
      collections: [],
      ranking: {
        mode: "hybrid",
        keyword_score: 0.5,
        vector_score: 0.9,
        keyword_weight: 0.45,
        vector_weight: 0.55,
        keyword_contribution: 0.225,
        vector_contribution: 0.495,
        recency_boost: 0.04,
        lifecycle_boost: 0.08,
        pinned_boost: 0.05,
        final_score: 0.89,
        rank: 1,
        embedding_model: "embedding-model-1",
        explanation: "45% keyword relevance and 55% vector similarity",
      },
      created_at: "2026-07-10T00:00:00Z",
      updated_at: "2026-07-10T00:00:00Z",
    }] }));
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  assert.ok(address && typeof address === "object");
  const previousBaseUrl = process.env.MIROFISH_API_BASE_URL;
  process.env.MIROFISH_API_BASE_URL = `http://127.0.0.1:${address.port}`;

  try {
    const api = await import(`../lib/api.ts?assetsSearchApi=${Date.now()}`);
    const result = await api.searchAssets({
      tenantId: "tenant-1",
      projectId: "project-1",
      sessionCookie: "session-secret",
      csrfToken: "csrf-secret",
      query: "Moon",
      mode: "hybrid",
      filters: {
        asset_types: ["world_rule"],
        categories: ["world"],
        lifecycles: ["canon"],
        sources: ["manual"],
        tags: ["moon"],
        pinned: true,
      },
    });
    assert.equal(result.ok, true);
    assert.equal(result.items[0].ranking.keyword_weight, 0.45);
    assert.equal(result.items[0].ranking.vector_contribution, 0.495);
    assert.equal(requests.length, 1);
    assert.equal(requests[0].method, "POST");
    assert.equal(requests[0].url, "/v1/assets/search");
    assert.equal(requests[0].headers.cookie, "mirofish_session=session-secret");
    assert.equal(requests[0].headers["x-csrf-token"], "csrf-secret");
    assert.deepEqual(requests[0].body, {
      project_id: "project-1",
      query: "Moon",
      mode: "hybrid",
      filters: {
        asset_types: ["world_rule"],
        categories: ["world"],
        lifecycles: ["canon"],
        sources: ["manual"],
        tags: ["moon"],
        pinned: true,
      },
    });
    const rawBody = JSON.stringify(requests[0].body);
    assert.doesNotMatch(rawBody, /embedding|model_id|channel_id|api_key|credential/i);
  } finally {
    if (previousBaseUrl === undefined) delete process.env.MIROFISH_API_BASE_URL;
    else process.env.MIROFISH_API_BASE_URL = previousBaseUrl;
    await new Promise((resolve) => server.close(resolve));
  }
});
