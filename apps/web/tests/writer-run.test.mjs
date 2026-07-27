import { test } from "node:test";
import assert from "node:assert/strict";

import { reduceWriterRun } from "../lib/api/writer-run.ts";

let seq = 0;
function ev(event_type, payload = {}) {
  seq += 1;
  return { event_id: `e${seq}`, sequence: seq, event_type, payload };
}

test("queued run with no events is not terminal", () => {
  const state = reduceWriterRun([]);
  assert.equal(state.phase, "queued");
  assert.equal(state.isTerminal, false);
  assert.equal(state.candidateText, "");
  assert.equal(state.draftId, null);
});

test("orchestrating phase counts tool calls and reports retrieval progress", () => {
  const state = reduceWriterRun([
    ev("workflow.queued"),
    ev("writer.run.started"),
    ev("writer.tool.started", { tool_call_id: "a" }),
    ev("writer.tool.started", { tool_call_id: "b" }),
    ev("writer.tool.completed", { tool_call_id: "a" }),
  ]);
  assert.equal(state.phase, "orchestrating");
  assert.equal(state.toolCount, 2);
  assert.match(state.statusLine, /查阅故事资料/);
  assert.match(state.statusLine, /2 项/);
  assert.equal(state.isTerminal, false);
});

test("token events accumulate candidate prose and flip to composing", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.token", { token: "雨敲在" }),
    ev("writer.token", { token: "书房的青瓦上。" }),
  ]);
  assert.equal(state.phase, "composing");
  assert.equal(state.candidateText, "雨敲在书房的青瓦上。");
  assert.match(state.statusLine, /正在起草正文/);
});

test("draft.saved captures draft_id; completed is terminal", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.token", { token: "正文。" }),
    ev("writer.draft.saved", { draft_id: "draft-1" }),
    ev("writer.run.completed"),
  ]);
  assert.equal(state.phase, "completed");
  assert.equal(state.draftId, "draft-1");
  assert.equal(state.isTerminal, true);
  assert.match(state.statusLine, /候选稿/);
});

test("failed run surfaces an author-facing reason without raw codes", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.run.failed", { message: "LLM_QUOTA_EXCEEDED 模型额度不足 07c8c057-a2b5-492f-afdc-c2be8b49f5da" }),
  ]);
  assert.equal(state.phase, "failed");
  assert.equal(state.isTerminal, true);
  assert.match(state.statusLine, /未完成/);
  assert.ok(!/QUOTA|EXCEEDED|[0-9a-f]{8}-/.test(state.statusLine), "no raw codes/uuids");
});

test("events are ordered by sequence even if delivered out of order", () => {
  const a = ev("writer.token", { token: "一" });
  const b = ev("writer.token", { token: "二" });
  const c = ev("writer.token", { token: "三" });
  // deliver reversed
  const state = reduceWriterRun([c, a, b]);
  assert.equal(state.candidateText, "一二三");
});

test("tool calls become legible steps that settle from running to completed", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.tool.started", { tool_call_id: "a", tool_name: "query_project_context" }),
    ev("writer.tool.started", { tool_call_id: "b", tool_name: "query_character_profile" }),
    ev("writer.tool.completed", { tool_call_id: "a" }),
  ]);
  assert.equal(state.steps.length, 2);
  assert.equal(state.steps[0].label, "查阅全书设定");
  assert.equal(state.steps[0].status, "completed");
  assert.equal(state.steps[1].label, "查阅角色档案");
  assert.equal(state.steps[1].status, "running");
});

test("a tool step with no name falls back to a calm retrieval label", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.tool.started", { tool_call_id: "a" }),
    ev("writer.tool.completed", { tool_call_id: "a", is_error: true, status: "failed" }),
  ]);
  assert.equal(state.steps.length, 1);
  assert.match(state.steps[0].label, /查阅故事资料/);
  assert.equal(state.steps[0].status, "error");
});

test("a failed tool completion (is_error) marks the step as error, not completed", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.tool.started", { tool_call_id: "s1", tool_name: "search_assets" }),
    ev("writer.tool.completed", {
      tool_call_id: "s1",
      tool_name: "search_assets",
      status: "failed",
      is_error: true,
      result: { items: [{ asset_id: "bad", title: "不应收录" }] },
    }),
  ]);
  assert.equal(state.steps[0].status, "error");
  // A failed retrieval never contributes citations.
  assert.equal(state.citations.length, 0);
});

test("search_assets completions collect deduped citations and the degraded flag", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.tool.started", { tool_call_id: "s1", tool_name: "search_assets" }),
    ev("writer.tool.completed", {
      tool_call_id: "s1",
      tool_name: "search_assets",
      result: {
        mode_used: "hybrid",
        degraded: false,
        items: [
          { asset_id: "a1", title: "师门戒律", lifecycle: "canon", channel: "search_assets" },
          { asset_id: "a2", title: "师父关系", lifecycle: "seed", channel: "search_assets" },
          { asset_id: "a1", title: "师门戒律(重复)", lifecycle: "canon", channel: "search_assets" },
        ],
      },
    }),
  ]);
  assert.equal(state.steps[0].label, "语义召回设定");
  assert.equal(state.citations.length, 2);
  assert.deepEqual(state.citations.map((c) => c.assetId), ["a1", "a2"]);
  assert.equal(state.citations[0].title, "师门戒律");
  assert.equal(state.citationsDegraded, false);
});

test("search_assets keyword fallback marks citationsDegraded", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.tool.started", { tool_call_id: "s1", tool_name: "search_assets" }),
    ev("writer.tool.completed", {
      tool_call_id: "s1",
      tool_name: "search_assets",
      result: { mode_used: "keyword", degraded: true, items: [{ asset_id: "a9", title: "旧事件", lifecycle: "material", channel: "search_assets" }] },
    }),
  ]);
  assert.equal(state.citationsDegraded, true);
  assert.equal(state.citations.length, 1);
});

test("fuse_recall always_on items surface as 常驻 citations, deduped against recall", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.tool.completed", {
      tool_call_id: "s1",
      tool_name: "search_assets",
      result: { mode_used: "hybrid", degraded: false, items: [{ asset_id: "a2", title: "师父", lifecycle: "canon", channel: "search_assets" }] },
    }),
    ev("writer.tool.completed", {
      tool_call_id: "f1",
      tool_name: "fuse_recall",
      result: {
        items: [
          { asset_id: "law-1", title: "世界铁律", channel: "always_on" },
          { asset_id: "a2", title: "师父", channel: "fuse_recall" }, // duplicate of recall, not always_on
        ],
      },
    }),
  ]);
  // a2 already cited via search_assets; only the always_on law-1 is added, marked 常驻.
  assert.equal(state.citations.length, 2);
  const alwaysOn = state.citations.find((c) => c.channel === "always_on");
  assert.equal(alwaysOn.assetId, "law-1");
  assert.equal(alwaysOn.lifecycle, "常驻");
});

test("writer.always_on.injected surfaces 常驻 citations without any fuse_recall call", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.always_on.injected", {
      count: 2,
      items: [
        { asset_id: "law-1", title: "世界铁律", asset_type: "world_rule" },
        { asset_id: "ban-1", title: "禁词表", asset_type: "style" },
      ],
    }),
    ev("writer.tool.completed", {
      tool_call_id: "f1",
      tool_name: "fuse_recall",
      result: { items: [{ asset_id: "law-1", title: "世界铁律", channel: "always_on" }] },
    }),
  ]);
  // Both constant assets cited once each; the later fuse_recall echo dedupes.
  assert.equal(state.citations.length, 2);
  assert.deepEqual(state.citations.map((c) => c.assetId), ["law-1", "ban-1"]);
  assert.ok(state.citations.every((c) => c.channel === "always_on" && c.lifecycle === "常驻"));
});

test("query_asset_relationships completions surface related assets as citations", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.tool.started", { tool_call_id: "r1", tool_name: "query_asset_relationships" }),
    ev("writer.tool.completed", {
      tool_call_id: "r1",
      tool_name: "query_asset_relationships",
      result: {
        asset_id: "a1",
        items: [
          { asset_id: "w1", title: "青冥剑", lifecycle: "canon", relation_type: "持有", direction: "outgoing" },
          { asset_id: "s1", title: "玄天宗", lifecycle: "canon", relation_type: "宗门", direction: "outgoing" },
        ],
      },
    }),
  ]);
  assert.equal(state.steps[0].label, "带出关联资产");
  assert.equal(state.citations.length, 2);
  assert.deepEqual(state.citations.map((c) => c.assetId), ["w1", "s1"]);
  assert.ok(state.citations.every((c) => c.channel === "关联带出"));
});

test("consistency violation events are collected for the author notice", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.token", { token: "沈翠花一剑斩了师父。" }),
    ev("writer.consistency.violations", {
      count: 2,
      major_count: 1,
      violations: [
        { canon_label: "师父不可杀", conflict: "草稿写沈翠花斩了师父", severity: "major" },
        { canon_label: "云峰已断臂", conflict: "草稿写云峰挥剑", severity: "minor" },
      ],
    }),
    ev("writer.draft.saved", { draft_id: "d1" }),
    ev("writer.run.completed"),
  ]);
  assert.equal(state.phase, "completed");
  assert.equal(state.consistencyViolations.length, 2);
  assert.equal(state.consistencyViolations[0].canonLabel, "师父不可杀");
  assert.equal(state.consistencyViolations[0].severity, "major");
  assert.equal(state.consistencyViolations[1].severity, "minor");
});

test("a clean run has no consistency violations", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.consistency.clean", { canon_count: 5 }),
    ev("writer.run.completed"),
  ]);
  assert.equal(state.consistencyViolations.length, 0);
});

test("search_manuscript results become 前文 citations with scores kept", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.tool.started", { tool_call_id: "m", tool_name: "search_manuscript" }),
    ev("writer.tool.completed", {
      tool_call_id: "m",
      tool_name: "search_manuscript",
      result: {
        mode_used: "vector",
        degraded: false,
        items: [{ block_id: "block-9", chapter_id: "c1", block_order: 3, score: 0.88, channel: "search_manuscript" }],
      },
    }),
  ]);
  assert.equal(state.citations.length, 1);
  assert.equal(state.citations[0].channel, "search_manuscript");
  assert.equal(state.citations[0].score, 0.88);
  assert.match(state.citations[0].title, /前文呼应/);
});

test("search_assets citations keep their relevance score", () => {
  const state = reduceWriterRun([
    ev("writer.tool.completed", {
      tool_call_id: "s",
      tool_name: "search_assets",
      result: {
        degraded: false,
        items: [{ asset_id: "a1", title: "世界规则", lifecycle: "canon", score: 0.76, channel: "search_assets" }],
      },
    }),
  ]);
  assert.equal(state.citations[0].score, 0.76);
});

test("retrieval plan and budget-trim events no longer fall through", () => {
  const state = reduceWriterRun([
    ev("writer.run.started"),
    ev("writer.retrieval_plan.completed", {
      intent: "payoff_foreshadow",
      queries: [{ channel: "keyed", text: "许七安" }, { channel: "hybrid", text: "税银案" }],
    }),
    ev("writer.context_budget.trimmed", { dropped_items: 3, budget_tokens: 24000 }),
  ]);
  assert.deepEqual(state.retrievalPlan, { status: "completed", intent: "payoff_foreshadow", queryCount: 2 });
  assert.equal(state.contextTrimmedItems, 3);
});

test("degraded and skipped retrieval plans surface distinctly", () => {
  const degraded = reduceWriterRun([ev("writer.retrieval_plan.degraded", { reason: "planner_call_failed" })]);
  assert.deepEqual(degraded.retrievalPlan, { status: "degraded" });
  const skipped = reduceWriterRun([ev("writer.retrieval_plan.skipped", { reason: "no_planner_binding" })]);
  assert.deepEqual(skipped.retrievalPlan, { status: "skipped" });
});
