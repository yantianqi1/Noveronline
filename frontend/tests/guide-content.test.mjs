import test from "node:test";
import assert from "node:assert/strict";

import { GUIDE_CONCEPT_ITEMS } from "../src/views/guide/guideContent.js";
import { WORKFLOW_STEPS } from "../src/views/guide/workflowGuideState.js";

test("guide content exposes four workflow steps", () => {
  assert.equal(WORKFLOW_STEPS.length, 4);
  assert.deepEqual(
    WORKFLOW_STEPS.map((item) => item.label),
    ["上传小说文本", "种子分析", "建立档案", "世界线推演"],
  );
});

test("guide content exposes the required concept terms", () => {
  assert.equal(GUIDE_CONCEPT_ITEMS.length, 6);
  assert.deepEqual(
    GUIDE_CONCEPT_ITEMS.map((item) => item.label),
    ["种子分析", "骨架时间线", "档案", "世界线", "变量注入", "Agent"],
  );
  for (const item of GUIDE_CONCEPT_ITEMS) {
    assert.ok(item.description);
  }
});
