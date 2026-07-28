import { test } from "node:test";
import assert from "node:assert/strict";

import { buildConversationTurns } from "../app/projects/[projectId]/writer/writer-turns.ts";

let seq = 0;
function msg(role, body, run_id) {
  seq += 1;
  return {
    message_id: `m${seq}`,
    thread_id: "t1",
    role,
    body,
    run_id,
    sequence: seq,
    created_at: "2026-07-26T00:00:00Z",
  };
}

test("empty history yields no turns", () => {
  assert.deepEqual(buildConversationTurns([]), []);
});

test("a user message with a run_id anchors one task turn right after it", () => {
  const turns = buildConversationTurns([msg("user", "开始第一章", "run-1")]);
  assert.deepEqual(
    turns.map((t) => t.kind),
    ["user", "task"],
  );
  assert.equal(turns[0].body, "开始第一章");
  assert.equal(turns[1].runId, "run-1");
});

test("the run's agent status line collapses into the task card (no echo)", () => {
  const turns = buildConversationTurns([
    msg("user", "开始第一章", "run-1"),
    msg("agent", "候选稿已写好（3510 字），见左侧画布。", "run-1"),
  ]);
  assert.deepEqual(
    turns.map((t) => t.kind),
    ["user", "task"],
  );
});

test("repeated runs across turns each get their own task card, in order", () => {
  const turns = buildConversationTurns([
    msg("user", "开始第一章", "run-1"),
    msg("agent", "候选稿已写好", "run-1"),
    msg("user", "开始第一章", "run-2"),
    msg("agent", "候选稿已写好", "run-2"),
  ]);
  assert.deepEqual(
    turns.map((t) => t.kind),
    ["user", "task", "user", "task"],
  );
  assert.equal(turns[1].runId, "run-1");
  assert.equal(turns[3].runId, "run-2");
});

test("a user message with no run still renders, without a task card", () => {
  const turns = buildConversationTurns([msg("user", "随便聊聊", undefined)]);
  assert.deepEqual(
    turns.map((t) => t.kind),
    ["user"],
  );
});

test("an agent message whose run was never seen keeps its own line", () => {
  const turns = buildConversationTurns([
    msg("user", "开始第一章", "run-1"),
    msg("agent", "（历史外的状态行）", "run-9"),
  ]);
  assert.deepEqual(
    turns.map((t) => t.kind),
    ["user", "task", "agent", "task"],
  );
});

test("an orphan run message (no user echo for it) still anchors one card", () => {
  // Old threads may hold an agent line for a run whose user message was never
  // persisted — the run must still surface, once, as a task card.
  const turns = buildConversationTurns([
    msg("user", "开始第一章", "run-1"),
    msg("agent", "候选稿已写好", "run-1"),
    msg("agent", "候选稿已写好", "run-2"),
  ]);
  assert.deepEqual(
    turns.map((t) => t.kind),
    ["user", "task", "agent", "task"],
  );
  assert.equal(turns[3].runId, "run-2");
});

test("system and approval messages are not thread content", () => {
  const turns = buildConversationTurns([
    msg("user", "开始第一章", "run-1"),
    msg("system", "run completed", "run-1"),
    msg("approval", "approved", "run-1"),
  ]);
  assert.deepEqual(
    turns.map((t) => t.kind),
    ["user", "task"],
  );
});

test("turns carry the message's created_at so the rail can group by day", () => {
  const turns = buildConversationTurns([msg("user", "开始第一章", "run-1")]);
  assert.equal(turns[0].createdAt, "2026-07-26T00:00:00Z");
  assert.equal(turns[1].createdAt, "2026-07-26T00:00:00Z");
});
