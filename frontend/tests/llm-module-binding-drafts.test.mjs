import test from "node:test";
import assert from "node:assert/strict";

import {
  createBindingDraft,
  draftMatchesBinding,
  syncBindingDrafts,
  updateBindingDraft,
} from "../src/views/llm-facility/llmModuleBindingDrafts.js";

test("createBindingDraft mirrors current binding", () => {
  assert.deepEqual(
    createBindingDraft({
      binding: {
        channel_key: "channel_demo",
        model_id: "gpt-5.4",
      },
    }),
    {
      channelKey: "channel_demo",
      modelId: "gpt-5.4",
    },
  );
});

test("draftMatchesBinding compares draft against module binding", () => {
  assert.equal(
    draftMatchesBinding(
      { channelKey: "channel_demo", modelId: "gpt-5.4" },
      { channel_key: "channel_demo", model_id: "gpt-5.4" },
    ),
    true,
  );
  assert.equal(
    draftMatchesBinding(
      { channelKey: "channel_demo", modelId: "gpt-5.3" },
      { channel_key: "channel_demo", model_id: "gpt-5.4" },
    ),
    false,
  );
});

test("syncBindingDrafts preserves dirty local edits during polling refresh", () => {
  const result = syncBindingDrafts({
    modules: [
      {
        module_key: "worldline_goal_evaluator",
        binding: {
          channel_key: "channel_demo",
          model_id: "gemini-3-flash-preview-minimal",
        },
      },
    ],
    drafts: {
      worldline_goal_evaluator: {
        channelKey: "channel_demo",
        modelId: "gpt-5.4",
      },
    },
    dirtyKeys: new Set(["worldline_goal_evaluator"]),
  });

  assert.deepEqual(result.drafts.worldline_goal_evaluator, {
    channelKey: "channel_demo",
    modelId: "gpt-5.4",
  });
  assert.equal(result.dirtyKeys.has("worldline_goal_evaluator"), true);
});

test("syncBindingDrafts clears dirty flag after server catches up", () => {
  const result = syncBindingDrafts({
    modules: [
      {
        module_key: "worldline_goal_evaluator",
        binding: {
          channel_key: "channel_demo",
          model_id: "gpt-5.4",
        },
      },
    ],
    drafts: {
      worldline_goal_evaluator: {
        channelKey: "channel_demo",
        modelId: "gpt-5.4",
      },
    },
    dirtyKeys: new Set(["worldline_goal_evaluator"]),
  });

  assert.equal(result.dirtyKeys.has("worldline_goal_evaluator"), false);
  assert.deepEqual(result.drafts.worldline_goal_evaluator, {
    channelKey: "channel_demo",
    modelId: "gpt-5.4",
  });
});

test("updateBindingDraft marks module as dirty and applies patch", () => {
  const result = updateBindingDraft({
    drafts: {
      worldline_goal_evaluator: {
        channelKey: "channel_demo",
        modelId: "gemini-3-flash-preview-minimal",
      },
    },
    dirtyKeys: new Set(),
    moduleKey: "worldline_goal_evaluator",
    patch: {
      modelId: "gpt-5.4",
    },
  });

  assert.deepEqual(result.drafts.worldline_goal_evaluator, {
    channelKey: "channel_demo",
    modelId: "gpt-5.4",
  });
  assert.equal(result.dirtyKeys.has("worldline_goal_evaluator"), true);
});
