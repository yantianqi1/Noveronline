import test from "node:test";
import assert from "node:assert/strict";
import { existsSync } from "node:fs";

const stateModuleUrl = new URL("../src/views/overview/overviewWorkbenchState.js", import.meta.url);

test("overview workbench state module exists for focus-card helpers", () => {
  assert.equal(existsSync(stateModuleUrl), true);
});

test("buildPipelineRailWindow folds distant stages into summary pills", async () => {
  assert.equal(existsSync(stateModuleUrl), true);
  if (!existsSync(stateModuleUrl)) {
    return;
  }

  const { buildPipelineRailWindow } = await import(stateModuleUrl);
  const rail = buildPipelineRailWindow({
    uploadPhase: "processing",
    taskStatus: "processing",
    activeStage: { key: "contextual_block_analysis", label: "分析剧情块" },
  });

  assert.equal(rail.items.some((item) => item.kind === "summary" && item.state === "done"), true);
  assert.equal(rail.items.some((item) => item.kind === "node" && item.state === "active"), true);
  assert.equal(rail.items.some((item) => item.kind === "summary" && item.state === "pending"), true);
});

test("buildPipelineRailWindow preserves a failed stage in the visible window", async () => {
  assert.equal(existsSync(stateModuleUrl), true);
  if (!existsSync(stateModuleUrl)) {
    return;
  }

  const { buildPipelineRailWindow } = await import(stateModuleUrl);
  const rail = buildPipelineRailWindow({
    uploadPhase: "error",
    taskStatus: "failed",
    activeStage: { key: "entity_resolution", label: "实体消歧" },
  });

  assert.equal(rail.items.some((item) => item.kind === "node" && item.state === "failed"), true);
});

test("buildOverviewNextActions prioritizes worldline and writer after graph is ready", async () => {
  assert.equal(existsSync(stateModuleUrl), true);
  if (!existsSync(stateModuleUrl)) {
    return;
  }

  const { buildOverviewNextActions } = await import(stateModuleUrl);
  const actions = buildOverviewNextActions({
    project_id: "proj_001",
    name: "天穹秘约",
    status: "completed",
    graph_id: "graph_001",
  });

  assert.deepEqual(
    actions.map((item) => item.label),
    ["世界线工作台", "写作台", "档案库", "故事图谱"],
  );
});

test("buildOverviewNextActions falls back to onboarding actions when no project exists", async () => {
  assert.equal(existsSync(stateModuleUrl), true);
  if (!existsSync(stateModuleUrl)) {
    return;
  }

  const { buildOverviewNextActions } = await import(stateModuleUrl);
  const actions = buildOverviewNextActions(null);

  assert.equal(actions[0].label, "启动新任务");
  assert.equal(actions.some((item) => item.label === "帮助指南"), true);
});
