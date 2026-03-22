import test from "node:test";
import assert from "node:assert/strict";

import {
  buildLlmChannelPath,
  buildLlmChannelSyncModelsPath,
  buildLlmModuleBindingPath,
  deleteLlmModuleBinding,
} from "../src/api/llm.js";

test("llm facility api path builders generate expected endpoints", () => {
  assert.equal(buildLlmChannelPath(), "/api/llm/channels");
  assert.equal(buildLlmChannelPath("channel_123"), "/api/llm/channels/channel_123");
  assert.equal(buildLlmChannelSyncModelsPath("channel_123"), "/api/llm/channels/channel_123/sync-models");
  assert.equal(buildLlmModuleBindingPath("story_ontology"), "/api/llm/module-bindings/story_ontology");
});

test("deleteLlmModuleBinding sends a DELETE request to the binding endpoint", async () => {
  const calls = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options });
    return {
      status: 200,
      async json() {
        return { success: true, data: { module_key: "story_ontology", deleted: true } };
      },
    };
  };

  try {
    await deleteLlmModuleBinding("story_ontology");
  } finally {
    globalThis.fetch = originalFetch;
  }

  assert.equal(calls.length, 1);
  assert.match(String(calls[0].url), /\/api\/llm\/module-bindings\/story_ontology$/);
  assert.equal(calls[0].options.method, "DELETE");
});
