import assert from "node:assert/strict";
import { test } from "node:test";

import {
  authorRunStatusLabel,
  authorTaskStatusLine,
  authorToolLabel,
} from "../lib/author-copy.ts";
import { summarizeWriterTaskStatus } from "../lib/writer-task-status.ts";

function event(overrides) {
  return {
    event_id: "evt-0",
    run_id: "run-1",
    project_id: "proj-1",
    sequence: 0,
    event_type: "writer.token",
    payload: {},
    created_at: "2026-07-14T00:00:00Z",
    ...overrides,
  };
}

test("authorToolLabel maps known tools and falls back safely", () => {
  assert.equal(authorToolLabel("zh-CN", "query_assets"), "查找人物与设定");
  assert.equal(authorToolLabel("en", "query_graph_neighbors"), "Checking relationships");
  assert.equal(authorToolLabel("zh-CN", "mystery_tool_xyz"), "处理写作请求");
  assert.doesNotMatch(authorToolLabel("zh-CN", "mystery_tool_xyz"), /mystery_tool/);
});

test("authorRunStatusLabel never echoes raw enums for unknown values", () => {
  assert.equal(authorRunStatusLabel("zh-CN", "completed"), "已完成");
  assert.equal(authorRunStatusLabel("zh-CN", "weird_status"), "正在处理");
  assert.doesNotMatch(authorRunStatusLabel("en", "weird_status"), /weird_status/);
});

test("authorTaskStatusLine collapses retrieve and draft phases with counts", () => {
  assert.equal(authorTaskStatusLine("zh-CN", "understanding"), "正在分析需求");
  assert.match(authorTaskStatusLine("zh-CN", "retrieving", { toolCompletedCount: 3 }), /已完成 3 项/);
  assert.match(authorTaskStatusLine("zh-CN", "drafting", { draftCharCount: 812 }), /812 字/);
  assert.match(authorTaskStatusLine("zh-CN", "completed", { draftCharCount: 1204 }), /1204 字/);
});

test("summarizeWriterTaskStatus: started → understanding", () => {
  const summary = summarizeWriterTaskStatus("zh-CN", [
    event({ event_id: "1", sequence: 1, event_type: "writer.run.started" }),
  ]);
  assert.equal(summary.phase, "understanding");
  assert.equal(summary.line, "正在分析需求");
});

test("summarizeWriterTaskStatus: tools → retrieving with author steps", () => {
  const summary = summarizeWriterTaskStatus("zh-CN", [
    event({ event_id: "1", sequence: 1, event_type: "writer.run.started" }),
    event({
      event_id: "2",
      sequence: 2,
      event_type: "writer.tool.started",
      payload: { tool_name: "query_assets" },
    }),
    event({
      event_id: "3",
      sequence: 3,
      event_type: "writer.tool.completed",
      payload: { tool_name: "query_assets" },
    }),
    event({
      event_id: "4",
      sequence: 4,
      event_type: "writer.tool.started",
      payload: { tool_name: "query_graph_neighbors" },
    }),
  ]);
  assert.equal(summary.phase, "retrieving");
  assert.match(summary.line, /正在查阅资料/);
  assert.match(summary.line, /已完成 1 项/);
  assert.equal(summary.steps.length, 2);
  assert.equal(summary.steps[0].label, "查找人物与设定");
  assert.equal(summary.steps[0].status, "completed");
  assert.equal(summary.steps[1].label, "核对人物关系");
  assert.equal(summary.steps[1].status, "running");
  for (const step of summary.steps) {
    assert.doesNotMatch(step.label, /query_/);
  }
});

test("summarizeWriterTaskStatus: tokens → drafting with character count", () => {
  const summary = summarizeWriterTaskStatus("zh-CN", [
    event({ event_id: "1", sequence: 1, event_type: "writer.run.started" }),
    event({ event_id: "2", sequence: 2, event_type: "writer.token", payload: { token: "雨点" } }),
    event({ event_id: "3", sequence: 3, event_type: "writer.token", payload: { token: "砸在屋檐" } }),
  ]);
  assert.equal(summary.phase, "drafting");
  assert.match(summary.line, /正在起草正文/);
  assert.equal(summary.draftCharCount, 6);
  assert.match(summary.line, /6 字/);
});

test("summarizeWriterTaskStatus: completed candidate", () => {
  const summary = summarizeWriterTaskStatus("zh-CN", [
    event({ event_id: "1", sequence: 1, event_type: "writer.run.started" }),
    event({ event_id: "2", sequence: 2, event_type: "writer.token", payload: { token: "开场" } }),
    event({
      event_id: "3",
      sequence: 3,
      event_type: "writer.draft.saved",
      payload: { draft_id: "draft-1" },
    }),
    event({ event_id: "4", sequence: 4, event_type: "writer.run.completed" }),
  ]);
  assert.equal(summary.phase, "completed");
  assert.equal(summary.terminal, true);
  assert.match(summary.line, /已完成/);
  assert.match(summary.line, /2 字/);
});

test("summarizeWriterTaskStatus: connection override while in flight", () => {
  const events = [
    event({ event_id: "1", sequence: 1, event_type: "writer.run.started" }),
    event({
      event_id: "2",
      sequence: 2,
      event_type: "writer.tool.started",
      payload: { tool_name: "query_manuscript_context" },
    }),
  ];
  assert.equal(summarizeWriterTaskStatus("zh-CN", events, "reconnecting").phase, "reconnecting");
  assert.match(summarizeWriterTaskStatus("zh-CN", events, "reconnecting").line, /重连/);
  assert.equal(summarizeWriterTaskStatus("zh-CN", events, "interrupted").phase, "interrupted");
});

test("summarizeWriterTaskStatus: failed uses authorized failure detail", () => {
  const summary = summarizeWriterTaskStatus("zh-CN", [
    event({ event_id: "1", sequence: 1, event_type: "writer.run.started" }),
    event({
      event_id: "2",
      sequence: 2,
      event_type: "writer.run.failed",
      payload: { error_code: "LLM_MODEL_TOOLS_UNSUPPORTED", message: "tools required" },
    }),
  ]);
  assert.equal(summary.phase, "failed");
  assert.match(summary.line, /未完成/);
  assert.doesNotMatch(summary.line, /LLM_MODEL_TOOLS_UNSUPPORTED/);
});

test("summarizeWriterTaskStatus: awaiting approval beats completed tools", () => {
  const summary = summarizeWriterTaskStatus("zh-CN", [
    event({ event_id: "1", sequence: 1, event_type: "writer.run.started" }),
    event({
      event_id: "2",
      sequence: 2,
      event_type: "writer.approval.required",
      payload: { approval_id: "ap-1", summary: "Apply revision" },
    }),
  ]);
  assert.equal(summary.phase, "awaiting_approval");
  assert.equal(summary.line, "等待你的确认");
});
