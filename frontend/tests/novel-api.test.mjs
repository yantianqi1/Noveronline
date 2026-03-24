import test from "node:test";
import assert from "node:assert/strict";

import {
  buildChapterContext,
  generateArchiveCandidates,
  generateArchives,
  getChapterContextOptions,
} from "../src/api/novel.js";

test("generateArchiveCandidates posts to the candidates endpoint", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return {
      status: 200,
      async json() {
        return { success: true, data: { candidates: [] } };
      },
    };
  };

  try {
    await generateArchiveCandidates({ projectId: "proj_demo", graphId: "graph_demo" });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls.length, 1);
  assert.match(String(calls[0].url), /\/api\/novel\/archives\/candidates$/);
  assert.equal(calls[0].options.method, "POST");
  assert.match(String(calls[0].options.body), /"project_id":"proj_demo"/);
});

test("generateArchives forwards tier overrides and candidate snapshot", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return {
      status: 200,
      async json() {
        return { success: true, data: { archives: [] } };
      },
    };
  };

  try {
    await generateArchives({
      projectId: "proj_demo",
      graphId: "graph_demo",
      tierOverrides: [{ entity_uuid: "seed_character_沈夜", importance_tier: "major" }],
      candidateSnapshot: [{ entity_uuid: "seed_character_沈夜", selected_importance_tier: "major" }],
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls.length, 1);
  assert.match(String(calls[0].url), /\/api\/novel\/archives\/generate$/);
  assert.match(String(calls[0].options.body), /"tier_overrides":/);
  assert.match(String(calls[0].options.body), /"candidate_snapshot":/);
});

test("chapter context APIs use the expected endpoints", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return {
      status: 200,
      async json() {
        return { success: true, data: {} };
      },
    };
  };

  try {
    await getChapterContextOptions("proj_demo");
    await buildChapterContext({
      scope_type: "project_chapter",
      project_id: "proj_demo",
      chapter_order: 2,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls.length, 2);
  assert.match(String(calls[0].url), /\/api\/novel\/chapter-context\/options\?project_id=proj_demo$/);
  assert.match(String(calls[1].url), /\/api\/novel\/chapter-context$/);
  assert.equal(calls[0].options.method, "GET");
  assert.equal(calls[1].options.method, "POST");
});
