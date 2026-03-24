import test from "node:test";
import assert from "node:assert/strict";

async function loadModule() {
  try {
    return await import("../src/views/worldline/worldlineDirectorPanelViewModel.js");
  } catch (error) {
    assert.fail(`worldlineDirectorPanelViewModel.js 缺失: ${error.message}`);
  }
}

test("buildWorldlineCurrentWorldSummary merges task progress into the current world snapshot", async () => {
  const { buildWorldlineCurrentWorldSummary } = await loadModule();

  const summary = buildWorldlineCurrentWorldSummary({
    currentWorld: {
      branch_id: "main",
      title: "当前世界",
      current_step: 3,
      status: "running",
      pending_variables: 1,
      pending_actions: 2,
    },
    taskSnapshot: {
      branch_id: "main",
      task_id: "task_main",
      status: "processing",
      progress: 58,
      latest_event: {
        title: "沈夜潜入藏书阁",
        summary: "他提前截获长老调令。",
        driving_entities: ["沈夜", "秦昭"],
      },
    },
  });

  assert.equal(summary.worldId, "main");
  assert.equal(summary.progress, 58);
  assert.equal(summary.status, "processing");
  assert.equal(summary.latestEventTitle, "沈夜潜入藏书阁");
  assert.equal(summary.pendingCount, 3);
  assert.deepEqual(summary.drivers, ["沈夜", "秦昭"]);
});

test("buildWorldlineFocusNarrative prefers the current world snapshot and auto task latest event", async () => {
  const { buildWorldlineFocusNarrative } = await loadModule();

  const narrative = buildWorldlineFocusNarrative({
    currentWorld: {
      branch_id: "main",
      title: "当前世界",
      current_step: 4,
      status: "running",
      core_change: "主角选择暗线取证。",
      pending_variables: 1,
      pending_actions: 1,
      actor_states: {
        沈夜: { status: "active", drive: "保住证人", role: "protagonist" },
        秦昭: { status: "adjusting", drive: "试探立场", role: "major" },
      },
      organization_states: {
        玄霄宗: { status: "engaged", role: "sect" },
      },
      relationship_states: [
        { source: "沈夜", target: "玄霄宗", change: "tension_up", note: "双方戒备升级" },
      ],
    },
    taskSnapshot: {
      latest_event: {
        title: "证人转移",
        summary: "证人被秘密送离城区。",
        driving_entities: ["沈夜", "秦昭"],
      },
    },
    timeline: [
      {
        event_id: "evt_seed",
        step: 0,
        title: "当前世界 初始化",
        summary: "分支建立。",
        driving_entities: ["沈夜"],
        relation_changes: [],
        state_changes: [],
        variable_effects: [],
      },
      {
        event_id: "evt_4",
        step: 4,
        title: "证人转移",
        summary: "沈夜将证人转移出城。",
        driving_entities: ["沈夜", "秦昭"],
        relation_changes: [{ source: "沈夜", target: "玄霄宗", change: "tension_up" }],
        state_changes: [],
        variable_effects: [],
      },
    ],
  });

  assert.equal(narrative.worldId, "main");
  assert.equal(narrative.latestEvent.title, "证人转移");
  assert.deepEqual(narrative.latestEvent.drivers, ["沈夜", "秦昭"]);
  assert.equal(narrative.dispatchActors[0].name, "沈夜");
  assert.equal(narrative.dispatchActors[0].isDriver, true);
  assert.equal(narrative.pending.actionCount, 1);
  assert.equal(narrative.pending.variableCount, 1);
  assert.equal(narrative.latestEvent.digest, "证人被秘密送离城区。");
});

test("buildWorldlineWorldShiftFeed exposes variables, relations, and state changes per event", async () => {
  const { buildWorldlineWorldShiftFeed } = await loadModule();

  const feed = buildWorldlineWorldShiftFeed([
    {
      event_id: "evt_2",
      step: 2,
      title: "密信外泄",
      summary: "情报提前泄露引发各方异动。",
      driving_entities: ["沈夜", "乌云"],
      variable_effects: [
        { variable_id: "var_1", name: "密信提前泄露", description: "主角先得知宗门布局" },
      ],
      relation_changes: [
        { source: "沈夜", target: "玄霄宗", change: "tension_up", note: "双方正面对峙" },
      ],
      state_changes: [
        { entity_name: "乌云", status: "engaged", reason: "manual_action", action: "布置眼线", influence: 0.8 },
      ],
    },
  ]);

  assert.equal(feed.emptyMessage, "");
  assert.equal(feed.items.length, 1);
  assert.deepEqual(feed.items[0].drivers, ["沈夜", "乌云"]);
  assert.equal(feed.items[0].variableEffects[0].name, "密信提前泄露");
  assert.equal(feed.items[0].relationChanges[0].label, "张力上升");
  assert.equal(feed.items[0].stateChanges[0].entityName, "乌云");
});

test("buildWorldlineWorldShiftFeed can recover action and variable structure from legacy summary text", async () => {
  const { buildWorldlineWorldShiftFeed } = await loadModule();

  const feed = buildWorldlineWorldShiftFeed([
    {
      event_id: "evt_legacy",
      step: 1,
      title: "平行世界 1 · 第1步演化",
      summary: "变量触发 天策军在太原打赢了:天策军在太原打赢了；主动行动 世子 × 陈迹执行“世子在太原大捷后秘密召见陈迹。”；本轮围绕“问题”持续收敛。",
      driving_entities: [],
      variable_effects: [],
      relation_changes: [],
      state_changes: [],
    },
  ]);

  assert.equal(feed.items[0].summary, "变量 1 条已触发，agent 动作 1 条已落地");
  assert.equal(feed.items[0].variableEffects[0].name, "天策军在太原打赢了");
  assert.equal(feed.items[0].actionEffects[0].actor, "世子 × 陈迹");
});

test("buildWorldlineWorldShiftFeed returns an explicit empty state when timeline is unavailable", async () => {
  const { buildWorldlineWorldShiftFeed } = await loadModule();

  assert.deepEqual(
    buildWorldlineWorldShiftFeed([]),
    {
      emptyMessage: "当前世界还没有新的世界变化，推进后会在这里连续记录局势改写。",
      items: [],
    },
  );
});
