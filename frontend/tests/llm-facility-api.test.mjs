import test from "node:test";
import assert from "node:assert/strict";

import {
  buildLlmChannelPath,
  buildLlmChannelSyncModelsPath,
  buildLlmModuleBindingPath,
} from "../src/api/llm.js";

test("llm facility api path builders generate expected endpoints", () => {
  assert.equal(buildLlmChannelPath(), "/api/llm/channels");
  assert.equal(buildLlmChannelPath("channel_123"), "/api/llm/channels/channel_123");
  assert.equal(buildLlmChannelSyncModelsPath("channel_123"), "/api/llm/channels/channel_123/sync-models");
  assert.equal(buildLlmModuleBindingPath("story_ontology"), "/api/llm/module-bindings/story_ontology");
});
