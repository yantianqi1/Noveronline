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
    ev("writer.tool.failed", { tool_call_id: "a" }),
  ]);
  assert.equal(state.steps.length, 1);
  assert.match(state.steps[0].label, /查阅故事资料/);
  assert.equal(state.steps[0].status, "error");
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
