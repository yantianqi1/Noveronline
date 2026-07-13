import assert from "node:assert/strict";
import { test } from "node:test";

import {
  latestDraftId,
  latestWriterCursor,
  mergeWriterEvents,
  writerDraftText,
  writerProgressStage,
  writerStreamReachedTerminal,
  writerToolCompletedCount,
} from "../lib/writer-event-store.ts";

function event(overrides) {
  return {
    event_id: "evt-0",
    run_id: "run-1",
    project_id: "proj-1",
    sequence: 0,
    event_type: "writer.token",
    payload: {},
    created_at: "2026-07-13T00:00:00Z",
    ...overrides,
  };
}

test("mergeWriterEvents dedupes by event_id and orders by sequence", () => {
  const merged = mergeWriterEvents(
    [event({ event_id: "b", sequence: 2 })],
    [event({ event_id: "a", sequence: 1 }), event({ event_id: "c", sequence: 3 })],
  );
  assert.deepEqual(merged.map((item) => item.event_id), ["a", "b", "c"]);
});

test("mergeWriterEvents tolerates out-of-order delivery", () => {
  const merged = mergeWriterEvents(
    [],
    [event({ event_id: "c", sequence: 3 }), event({ event_id: "a", sequence: 1 }), event({ event_id: "b", sequence: 2 })],
  );
  assert.deepEqual(merged.map((item) => item.sequence), [1, 2, 3]);
});

test("mergeWriterEvents is idempotent — re-merging the same events yields an equal set", () => {
  const first = mergeWriterEvents([], [event({ event_id: "a", sequence: 1 })]);
  const second = mergeWriterEvents(first, [event({ event_id: "a", sequence: 1 })]);
  assert.equal(second.length, 1);
  assert.deepEqual(second.map((item) => item.event_id), ["a"]);
});

test("mergeWriterEvents lets a later duplicate event_id replace the earlier payload", () => {
  const merged = mergeWriterEvents(
    [event({ event_id: "a", sequence: 1, payload: { token: "old" } })],
    [event({ event_id: "a", sequence: 1, payload: { token: "new" } })],
  );
  assert.equal(merged.length, 1);
  assert.equal(merged[0].payload.token, "new");
});

test("latestWriterCursor returns the highest-sequence event id, empty when none", () => {
  assert.equal(latestWriterCursor([]), "");
  assert.equal(
    latestWriterCursor([event({ event_id: "a", sequence: 1 }), event({ event_id: "b", sequence: 5 }), event({ event_id: "c", sequence: 2 })]),
    "b",
  );
});

test("writerDraftText joins token events in sequence order regardless of input order", () => {
  const text = writerDraftText([
    event({ event_id: "t2", sequence: 2, payload: { token: " world" } }),
    event({ event_id: "t1", sequence: 1, payload: { token: "hello" } }),
    event({ event_id: "x", sequence: 3, event_type: "writer.tool.completed", payload: { tool_name: "query_assets" } }),
  ]);
  assert.equal(text, "hello world");
});

test("writerProgressStage advances understand -> retrieve -> draft -> save", () => {
  assert.equal(writerProgressStage([]), 0);
  assert.equal(writerProgressStage([event({ event_type: "writer.tool.started" })]), 1);
  assert.equal(writerProgressStage([event({ event_type: "writer.tool.completed" })]), 1);
  assert.equal(writerProgressStage([event({ event_type: "writer.token" })]), 2);
  assert.equal(writerProgressStage([event({ event_type: "writer.draft.saved" })]), 3);
  assert.equal(writerProgressStage([event({ event_type: "writer.run.completed" })]), 3);
});

test("writerToolCompletedCount counts only completed tool events", () => {
  assert.equal(
    writerToolCompletedCount([
      event({ event_type: "writer.tool.completed" }),
      event({ event_type: "writer.tool.started" }),
      event({ event_type: "writer.tool.completed" }),
    ]),
    2,
  );
});

test("writerStreamReachedTerminal is true only after a terminal run event", () => {
  assert.equal(writerStreamReachedTerminal([event({ event_type: "writer.token" })]), false);
  assert.equal(writerStreamReachedTerminal([event({ event_type: "writer.run.completed" })]), true);
  assert.equal(writerStreamReachedTerminal([event({ event_type: "writer.run.failed" })]), true);
  assert.equal(writerStreamReachedTerminal([event({ event_type: "writer.run.cancelled" })]), true);
});

test("latestDraftId recovers the most recent saved draft id", () => {
  assert.equal(latestDraftId([]), "");
  assert.equal(
    latestDraftId([
      event({ event_id: "a", sequence: 1, event_type: "writer.draft.saved", payload: { draft_id: "draft-old" } }),
      event({ event_id: "b", sequence: 2, event_type: "writer.run.completed", payload: { draft_id: "draft-new" } }),
    ]),
    "draft-new",
  );
});
