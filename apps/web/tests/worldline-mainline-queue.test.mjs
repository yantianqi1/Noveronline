import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

// worldline-model.ts is pure derivation logic with only type-only imports, so
// Node's native TS support can import and exercise the real functions (no mocks).
const {
  stepNumeral,
  worldlineChipState,
  WORLDLINE_CHIP_LABELS,
  partitionWorldlineEvents,
  formatWorldlineCounts,
  pendingStepFor,
  goalStartStageIndex,
  GOAL_START_STAGES,
  stateChangeView,
  involvedNamesForEvent,
  isRejectionTimelineRow,
  timelineEventToWorldlineEvent,
  timelineEventsToWorldlineEvents,
} = await import("../app/projects/[projectId]/worldline/worldline-model.ts");

const root = path.resolve(import.meta.dirname, "..");

async function source(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

function event(overrides) {
  return {
    event_id: "e1",
    session_id: "s1",
    project_id: "p1",
    step: 1,
    title: "",
    summary: "",
    kind: "",
    status: "candidate",
    lifecycle: "candidate",
    confidence: "",
    involved_agent_ids: [],
    state_changes: {},
    source_run_id: "r1",
    created_by: "",
    created_at: "",
    updated_at: "",
    ...overrides,
  };
}

// ── 状态芯片三态 ────────────────────────────────────────────────────────────

test("状态芯片三态:有候选即待裁决,queued/running 为推演中,否则待推进", () => {
  // 待裁决优先 — candidates must be settled before the world moves on.
  assert.equal(worldlineChipState({ sessionStatus: "paused", candidateCount: 2 }), "judging");
  assert.equal(worldlineChipState({ sessionStatus: "running", candidateCount: 1 }), "judging");
  // 推演中:session queued/running,或本地轮询仍未收官。
  assert.equal(worldlineChipState({ sessionStatus: "running", candidateCount: 0 }), "running");
  assert.equal(worldlineChipState({ sessionStatus: "queued", candidateCount: 0 }), "running");
  assert.equal(worldlineChipState({ sessionStatus: "paused", candidateCount: 0, evolving: true }), "running");
  // 待推进:paused 且无候选。
  assert.equal(worldlineChipState({ sessionStatus: "paused", candidateCount: 0 }), "idle");
  assert.equal(worldlineChipState({ sessionStatus: "ready", candidateCount: 0 }), "idle");
  assert.deepEqual(WORLDLINE_CHIP_LABELS, { idle: "待推进", running: "推演中", judging: "待裁决" });
});

// ── 候选 / 正史分区 ─────────────────────────────────────────────────────────

test("候选/正史分区:rejected 持久化退场,两条泳道都不复现", () => {
  const lanes = partitionWorldlineEvents([
    event({ event_id: "c1", status: "candidate" }),
    event({ event_id: "k1", status: "canon" }),
    event({ event_id: "r1", status: "rejected" }),
    event({ event_id: "c2", status: "candidate" }),
  ]);
  assert.deepEqual(lanes.candidates.map((e) => e.event_id), ["c1", "c2"]);
  assert.deepEqual(lanes.canon.map((e) => e.event_id), ["k1"]);
  assert.deepEqual(partitionWorldlineEvents([]), { candidates: [], canon: [] });
});

// ── 计数与待定夺步号 ────────────────────────────────────────────────────────

test("计数派生与待定夺步号", () => {
  assert.equal(formatWorldlineCounts(6, 3), "6 段正史 · 3 条待定夺");
  assert.equal(formatWorldlineCounts(0, 0), "0 段正史 · 0 条待定夺");
  assert.equal(pendingStepFor(6), 7);
  assert.equal(pendingStepFor(0), 1);
});

test("步骤印章用汉字数字,编排标记不落假步号", () => {
  assert.equal(stepNumeral(1), "壹");
  assert.equal(stepNumeral(6), "陆");
  assert.equal(stepNumeral(10), "拾");
  assert.equal(stepNumeral(11), "11");
  assert.equal(stepNumeral(0), "·");
});

// ── 整备阶梯 ────────────────────────────────────────────────────────────────

test("整备阶梯映射 queued→casting→preparing→starting→ready", () => {
  assert.equal(goalStartStageIndex("queued"), 0);
  assert.equal(goalStartStageIndex("casting"), 0);
  assert.equal(goalStartStageIndex("preparing"), 1);
  assert.equal(goalStartStageIndex("starting"), 2);
  assert.equal(goalStartStageIndex("ready"), GOAL_START_STAGES.length);
  assert.equal(goalStartStageIndex("failed"), 0);
});

// ── 状态变化视图 ────────────────────────────────────────────────────────────

test("状态变化视图:提取 summary,过滤编排簿记键,余者字符串化", () => {
  const view = stateChangeView({
    summary: " 医馆结界破损 ",
    mode: "director",
    model_id: "m",
    source_step_index: 3,
    source_workflow_type: "w",
    tension: "上升",
    casualties: 0,
  });
  assert.equal(view.summary, "医馆结界破损");
  assert.deepEqual(view.entries, [
    { key: "tension", value: "上升" },
    { key: "casualties", value: "0" },
  ]);
  assert.deepEqual(stateChangeView(undefined), { summary: "", entries: [] });
  assert.deepEqual(stateChangeView({ summary: 42 }), { summary: "", entries: [] });
});

// ── 涉及角色名解析 ──────────────────────────────────────────────────────────

test("涉及角色:先按名册解析 id/名,解析不出回退到正文点名,绝不回显原始 slug", () => {
  const roster = [
    { id: "uuid-1", name: "顾临渊" },
    { id: "uuid-2", name: "谢无衍" },
  ];
  assert.deepEqual(
    involvedNamesForEvent({ title: "", summary: "", involved_agent_ids: ["uuid-1", "uuid-2", "uuid-1"] }, roster),
    ["顾临渊", "谢无衍"],
  );
  assert.deepEqual(
    involvedNamesForEvent({ title: "", summary: "", involved_agent_ids: ["顾临渊"] }, roster),
    ["顾临渊"],
  );
  // 导演给的 slug 映射不回名册 → 回退到事件文本里点名的角色。
  assert.deepEqual(
    involvedNamesForEvent({ title: "雪夜渡劫", summary: "被谢无衍所救", involved_agent_ids: ["xie_wu_yan"] }, roster),
    ["谢无衍"],
  );
  // 什么都对不上时为空,而不是把 slug 原样端给作者。
  assert.deepEqual(involvedNamesForEvent({ title: "t", summary: "s", involved_agent_ids: ["nobody"] }, roster), []);
});

// ── 时间线行 → 正史卡片事件 ─────────────────────────────────────────────────

function timelineRow(overrides) {
  return {
    event_id: "tl-9",
    session_id: "s1",
    run_id: "r9",
    project_id: "p1",
    event_type: "worldline.event_adopted",
    sequence: 9,
    status: "canon",
    lifecycle: "canon_reference",
    kind: "event_adoption",
    title: "Worldline event adopted",
    summary: "",
    created_at: "t",
    ...overrides,
  };
}

test("采纳行解析为被采纳的正史事件:标题/正文/kind/把握/涉及/状态变化/领域步", () => {
  const canon = event({
    event_id: "canon-1",
    status: "canon",
    lifecycle: "canon",
    step: 6,
    title: "雨夜对峙",
    summary: "一人一剑挡住三名魔修。",
    kind: "冲突",
    confidence: "高",
    involved_agent_ids: ["uuid-2"],
    state_changes: { summary: "结界破损" },
  });
  const mapped = timelineEventToWorldlineEvent(
    timelineRow({ event_ref_id: "canon-1" }),
    "p1",
    new Map([["canon-1", canon]]),
  );
  assert.equal(mapped.event_id, "canon-1");
  assert.equal(mapped.step, 6); // 领域步,不是编排 sequence 9
  assert.equal(mapped.title, "雨夜对峙");
  assert.equal(mapped.summary, "一人一剑挡住三名魔修。");
  assert.equal(mapped.kind, "冲突");
  assert.equal(mapped.confidence, "高");
  assert.deepEqual(mapped.involved_agent_ids, ["uuid-2"]);
  assert.deepEqual(mapped.state_changes, { summary: "结界破损" });
});

test("正史表缺行时退回后端 join 的 adopted_title/summary,普通行原样通过", () => {
  const fallback = timelineEventToWorldlineEvent(
    timelineRow({ event_ref_id: "gone", adopted_title: "旧标题", adopted_summary: "旧正文" }),
    "p1",
    new Map(),
  );
  assert.equal(fallback.title, "旧标题");
  assert.equal(fallback.summary, "旧正文");
  assert.equal(fallback.step, 0);

  const plain = timelineEventToWorldlineEvent(
    timelineRow({ kind: "session_seed", title: "雪夜渡劫", summary: "渡劫失败。", event_ref_id: "" }),
    "p1",
    new Map(),
  );
  assert.equal(plain.event_id, "tl-9");
  assert.equal(plain.title, "雪夜渡劫");
  assert.equal(plain.kind, "session_seed");
});

test("isRejectionTimelineRow:kind 与 event_type 任一命中即剔除,采纳/普通行不误伤", () => {
  assert.equal(isRejectionTimelineRow({ kind: "event_rejection", event_type: "" }), true);
  assert.equal(isRejectionTimelineRow({ kind: "", event_type: "worldline.event.rejected" }), true);
  assert.equal(isRejectionTimelineRow({ kind: "event_adoption", event_type: "worldline.event.adopted" }), false);
  assert.equal(isRejectionTimelineRow({ kind: "session_seed", event_type: "worldline.session.started" }), false);
});

test("拒绝台账行不进正史阅读列,正史普通行与采纳落位行保留", () => {
  const canon = event({
    event_id: "canon-1",
    status: "canon",
    lifecycle: "canon",
    step: 6,
    title: "雨夜对峙",
  });
  const rows = [
    timelineRow({
      event_id: "tl-3",
      kind: "session_seed",
      title: "雪夜渡劫",
      summary: "渡劫失败。",
      event_ref_id: "",
      event_type: "worldline.session.started",
    }),
    // 采纳落位行
    timelineRow({ event_id: "tl-9", event_ref_id: "canon-1", event_type: "worldline.event.adopted" }),
    // 拒绝台账行:被否候选的标题经 event_ref_id join 镜像在行上,也不得渲染
    timelineRow({
      event_id: "tl-10",
      kind: "event_rejection",
      event_type: "worldline.event.rejected",
      event_ref_id: "rejected-1",
      adopted_title: "被否的走向",
      adopted_summary: "这条候选没被采纳。",
    }),
  ];
  const mapped = timelineEventsToWorldlineEvents(rows, "p1", [canon]);
  assert.deepEqual(mapped.map((e) => e.event_id), ["tl-3", "canon-1"]);
  assert.equal(mapped[1].title, "雨夜对峙");
  assert.ok(!mapped.some((e) => e.title === "被否的走向"), "rejected candidate title must never reach the reading column");
});

test("时间线映射先剔除拒绝台账行再映射(源码契约)", async () => {
  const model = await source("app/projects/[projectId]/worldline/worldline-model.ts");
  const filterAt = model.indexOf(".filter((t) => !isRejectionTimelineRow(t))");
  const mapAt = model.indexOf(".map((t) => timelineEventToWorldlineEvent(t, projectId, canonById))");
  assert.ok(filterAt >= 0 && mapAt > filterAt, "rejection ledger rows are filtered before the card mapping");
});

// ── 暂不采纳持久化链路(源码契约) ─────────────────────────────────────────────

test("client 的 rejectWorldlineEvent 走与 adoptions 相同的 POST + CSRF/幂等纪律", async () => {
  const client = await source("lib/api/worldline-client.ts");
  const fnStart = client.indexOf("export function rejectWorldlineEvent");
  assert.ok(fnStart >= 0, "client must export rejectWorldlineEvent");
  const fn = client.slice(fnStart, client.indexOf("\n}", fnStart));
  assert.match(fn, /sendJson<WorldlineEvent>\(\s*"POST",/);
  assert.match(fn, /worldline-events\/\$\{encodeURIComponent\(eventId\)\}\/rejections/);
  assert.match(fn, /\{ note: note \?\? "" \}/);
});

test("BFF 放行 worldline-events 的 rejections,并与 adoptions 同一转发形状", async () => {
  const route = await source("app/api/projects/[projectId]/[...path]/route.ts");
  assert.match(route, /\^worldline-events\\\/\(\[\^\/\]\+\)\(\\\/adoptions\|\\\/rejections\)\?\$/);
  assert.match(route, /\/v1\/worldline-events\/\$\{encodeURIComponent\(m\[1\]\)\}/);
});

test("暂不采纳先在后端持久化再移出队列,禁止本地假移除", async () => {
  const workspace = await source("app/projects/[projectId]/worldline/worldline-workspace.tsx");
  const slice = workspace.slice(
    workspace.indexOf("const handleRejectCandidate"),
    workspace.indexOf("// ── Render"),
  );
  const callAt = slice.indexOf("await rejectWorldlineEvent");
  const dropAt = slice.indexOf("setCandidates((prev) => prev.filter");
  assert.ok(callAt >= 0, "rejection must call the persisted endpoint");
  assert.ok(dropAt > callAt, "the card leaves the queue only after the rejection landed");
  assert.match(slice, /暂不采纳失败/); // honest error, no silent swallow
  // 旧的纯前端移除(刷新即复现)已退役。
  assert.doesNotMatch(workspace, /A rejected candidate simply leaves the queue/);
});

test("采纳后整量 refetch,同步候选因后端自动 rejected 而消失", async () => {
  const workspace = await source("app/projects/[projectId]/worldline/worldline-workspace.tsx");
  const slice = workspace.slice(
    workspace.indexOf("const handleAdoptCandidate"),
    workspace.indexOf("const handleEditCandidate"),
  );
  const adoptAt = slice.indexOf("await adoptWorldlineEvent");
  const refetchAt = slice.indexOf("await loadSessionData");
  assert.ok(adoptAt >= 0 && refetchAt > adoptAt, "adoption persists, then the session reloads");
  // 事件一次拉取、按 status 分区,候选与正史分道。
  assert.match(workspace, /partitionWorldlineEvents\(evs\)/);
});

test("方案A布局接线:状态行芯片三态、待定夺右栏、底栏推进计数", async () => {
  const workspace = await source("app/projects/[projectId]/worldline/worldline-workspace.tsx");
  assert.match(workspace, /worldlineChipState\(\{/);
  assert.match(workspace, /pendingStepFor\(currentStep\)/);
  assert.match(workspace, /pendingCount=\{candidates\.length\}/);
  assert.match(workspace, /formatWorldlineCounts\(canonEvents\.length, candidates\.length\)/);

  const statusRow = await source("app/projects/[projectId]/worldline/worldline-status-row.tsx");
  assert.match(statusRow, /WORLDLINE_CHIP_LABELS\[chip\]/);
  assert.match(statusRow, /第 \$\{currentStep\} 步/);

  const candidateCard = await source("app/projects/[projectId]/worldline/worldline-candidate-card.tsx");
  for (const label of ["采纳", "改一改", "暂不采纳", "把握", "状态变化"]) {
    assert.ok(candidateCard.includes(label), `candidate card must carry 「${label}」`);
  }

  const rail = await source("app/projects/[projectId]/worldline/worldline-candidate-rail.tsx");
  for (const label of ["待定夺", "锁定变量", "演员名册", "onToggleVariableLock"]) {
    assert.ok(rail.includes(label), `rail must carry 「${label}」`);
  }
});

test("正史卡片就地展开涉及角色/状态变化/kind,最新一步印章填朱标记此刻", async () => {
  const card = await source("app/projects/[projectId]/worldline/worldline-event-card.tsx");
  assert.match(card, /stateChangeView\(event\.state_changes\)/);
  assert.match(card, /involvedNames\.join/);
  assert.match(card, /此刻/);
  assert.match(card, /aria-expanded=\{open\}/);

  const timeline = await source("app/projects/[projectId]/worldline/worldline-timeline.tsx");
  // 单开手风琴:展开一张即收起其余。
  assert.match(timeline, /setOpenId\(\(current\) => \(current === e\.event_id \? null : e\.event_id\)\)/);
});
