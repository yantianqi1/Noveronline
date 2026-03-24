import test from "node:test";
import assert from "node:assert/strict";

import {
  buildWriterRequestPayload,
  deriveWriterDefaults,
  findContextItem,
  resolveWriterPovOptions,
} from "../src/views/writer/writerWorkbenchState.js";

test("deriveWriterDefaults picks the first chapter and pov from options", () => {
  const defaults = deriveWriterDefaults({
    chapters: [
      { chapter_id: "chapter_0001", order: 1, title: "起疑" },
      { chapter_id: "chapter_0002", order: 2, title: "废塔" },
    ],
    pov_characters: ["沈夜", "秦昭"],
  });

  assert.equal(defaults.chapterOrder, 1);
  assert.equal(defaults.chapterId, "chapter_0001");
  assert.equal(defaults.povCharacter, "沈夜");
});

test("buildWriterRequestPayload shapes project scope requests", () => {
  const payload = buildWriterRequestPayload({
    scopeType: "project_chapter",
    projectId: "proj_demo",
    chapterOrder: 2,
    povCharacter: "沈夜",
    writingGoal: "生成场景卡",
    sceneFocus: "废塔残响",
    includeCandidates: false,
  });

  assert.deepEqual(payload, {
    scope_type: "project_chapter",
    project_id: "proj_demo",
    chapter_order: 2,
    pov_character: "沈夜",
    writing_goal: "生成场景卡",
    scene_focus: "废塔残响",
    include_candidates: false,
  });
});

test("buildWriterRequestPayload shapes worldline scope requests", () => {
  const payload = buildWriterRequestPayload({
    scopeType: "worldline_branch",
    projectId: "proj_demo",
    sessionId: "ws_demo",
    branchId: "main",
    povCharacter: "沈夜",
    writingGoal: "生成分支场景卡",
    sceneFocus: "顾行舟现身",
    includeCandidates: true,
  });

  assert.equal(payload.scope_type, "worldline_branch");
  assert.equal(payload.session_id, "ws_demo");
  assert.equal(payload.branch_id, "main");
  assert.equal(payload.include_candidates, true);
  assert.equal(payload.chapter_order, undefined);
});

test("resolveWriterPovOptions prefers agent roster in worldline mode", () => {
  const items = resolveWriterPovOptions(
    "worldline_branch",
    ["沈夜", "秦昭"],
    [{ agent_id: "a1", display_name: "沈夜", agent_kind: "character" }, { agent_id: "rel_1", display_name: "沈夜 × 秦昭", agent_kind: "relationship" }],
  );

  assert.deepEqual(items, ["沈夜"]);
});

test("findContextItem restores the matching item after pack refresh", () => {
  const selectedItem = { item_id: "ctx_runtime_1", summary: "旧 candidate" };
  const match = findContextItem(
    {
      must_know: [{ item_id: "ctx_runtime_1", summary: "已转为 canon" }],
      should_know: [],
      warnings: [],
    },
    selectedItem,
  );

  assert.deepEqual(match, { item_id: "ctx_runtime_1", summary: "已转为 canon" });
  assert.equal(findContextItem({ must_know: [], should_know: [], warnings: [] }, selectedItem), null);
});
