import assert from "node:assert/strict";
import { test } from "node:test";

import {
  canonicalLLMFacilitySearch,
  llmChannelAnchorId,
  llmChannelKey,
  llmModuleKeyFromSegment,
  llmModuleKeyFromPathSegment,
  llmModulePathSegment,
  llmModuleSegment,
  resolveLLMChannelKey,
} from "../lib/llm-facility-route.ts";

test("LLM facility query names are concise and empty state is removed", () => {
  const channelId = "b16c0012-e98c-4c8f-898e-803380e1991d";
  const result = canonicalLLMFacilitySearch(new URLSearchParams({
    channelId,
    moduleKey: "novel_chapter_summarizer",
    runId: "",
  }));

  assert.equal(result.get("channel"), llmChannelKey(channelId));
  assert.equal(result.get("module"), "novel-chapter-summarizer");
  assert.equal(result.has("run"), false);
  assert.equal(result.has("channelId"), false);
  assert.equal(result.has("moduleKey"), false);
  assert.equal(result.has("runId"), false);
});

test("LLM module and channel URL keys resolve back to internal identifiers", () => {
  const channelIds = [
    "b16c0012-e98c-4c8f-898e-803380e1991d",
    "f707bf0b-565b-458d-8af8-e6e671b3272d",
  ];
  assert.equal(llmModuleKeyFromSegment(llmModuleSegment("writer_composer")), "writer_composer");
  assert.equal(
    resolveLLMChannelKey(channelIds, llmChannelKey(channelIds[1])),
    channelIds[1],
  );
  assert.equal(resolveLLMChannelKey(channelIds, channelIds[0]), channelIds[0]);
  assert.equal(resolveLLMChannelKey(channelIds, "unknown"), undefined);
});

test("LLM modules use short product aliases in the visible path", () => {
  assert.equal(llmModulePathSegment("novel_chapter_summarizer"), "summary");
  assert.equal(llmModuleKeyFromPathSegment("summary"), "novel_chapter_summarizer");
  assert.equal(llmModulePathSegment("writer_reviewer"), "review");
  assert.equal(llmModuleKeyFromPathSegment("review"), "writer_reviewer");
  assert.equal(llmModulePathSegment("custom_module"), "custom-module");
  assert.equal(llmModuleKeyFromPathSegment("custom-module"), "custom_module");
});

test("LLM channel management cards use stable hash-safe anchors", () => {
  const channelId = "b16c0012-e98c-4c8f-898e-803380e1991d";
  assert.equal(llmChannelAnchorId(channelId), `channel-${llmChannelKey(channelId)}`);
  assert.equal(llmChannelAnchorId(""), "");
  assert.equal(llmChannelAnchorId("  "), "");
});
