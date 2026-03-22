import test from "node:test";
import assert from "node:assert/strict";

import {
  APP_BRAND_NAME,
  APP_SUBTITLE,
  buildStepLabel,
  formatAgentKind,
  formatAgentStatus,
  formatBranchStatus,
  formatProjectStatus,
  formatRelationChange,
  formatTaskStageStatus,
} from "../src/utils/chineseDisplay.js";

test("exports Chinese-first brand copy", () => {
  assert.equal(APP_BRAND_NAME, "Novelfish 小说工作台");
  assert.match(APP_SUBTITLE, /中文|小说|工作台/);
});

test("formats agent kinds into Chinese labels", () => {
  assert.equal(formatAgentKind("character"), "角色");
  assert.equal(formatAgentKind("organization"), "组织");
  assert.equal(formatAgentKind("relationship"), "关系");
  assert.equal(formatAgentKind("unknown"), "未知类型");
});

test("formats statuses into Chinese labels", () => {
  assert.equal(formatAgentStatus("active"), "活跃");
  assert.equal(formatAgentStatus("engaged"), "已介入");
  assert.equal(formatAgentStatus("adjusting"), "调整中");
  assert.equal(formatBranchStatus("running"), "推演中");
  assert.equal(formatProjectStatus("completed"), "已完成");
  assert.equal(formatTaskStageStatus("processing"), "进行中");
});

test("formats relation changes and steps into Chinese labels", () => {
  assert.equal(formatRelationChange("stable"), "稳定");
  assert.equal(formatRelationChange("tension_up"), "张力上升");
  assert.equal(formatRelationChange("relationship_shift"), "关系转变");
  assert.equal(buildStepLabel(3), "第 3 步");
});
