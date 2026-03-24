import test from "node:test";
import assert from "node:assert/strict";

import {
  getWorldlineAgentMemory,
  getWorldlineAgentMemoryContext,
  startWorldlineAutoEvolve,
} from "../src/api/worldline.js";

test("startWorldlineAutoEvolve posts to the session auto evolve endpoint", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return {
      status: 202,
      async json() {
        return { success: true, data: { tasks: [] } };
      },
    };
  };

  try {
    await startWorldlineAutoEvolve({
      session_id: "ws_demo",
      mode: "continuous",
      branch_ids: ["branch_1"],
      goal_text: "主角公开真相",
      max_steps: 6,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls.length, 1);
  assert.match(String(calls[0].url), /\/api\/worldline\/session\/ws_demo\/auto-evolve$/);
  assert.equal(calls[0].options.method, "POST");
  assert.match(String(calls[0].options.body), /"mode":"continuous"/);
  assert.doesNotMatch(String(calls[0].options.body), /"branch_ids":/);
});

test("worldline memory APIs build the expected query paths", async () => {
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
    await getWorldlineAgentMemory("ws_demo", { agent_id: "agent_1", limit: 8 });
    await getWorldlineAgentMemoryContext("ws_demo", {
      agent_id: "agent_1",
      message: "现在该怎么办？",
      limit: 5,
    });
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls.length, 2);
  assert.match(
    String(calls[0].url),
    /\/api\/worldline\/session\/ws_demo\/agent-memory\?agent_id=agent_1&limit=8$/,
  );
  assert.match(
    String(calls[1].url),
    /\/api\/worldline\/session\/ws_demo\/agent-memory-context\?agent_id=agent_1&limit=5&message=/,
  );
  assert.equal(calls[0].options.method, "GET");
  assert.equal(calls[1].options.method, "GET");
});
