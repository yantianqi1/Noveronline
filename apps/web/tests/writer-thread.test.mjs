import assert from "node:assert/strict";
import test from "node:test";

import {
  latestThreadMessage,
  mergeThreadMessages,
  sortThreadMessages,
} from "../lib/writer-thread.ts";

test("sortThreadMessages orders by sequence then created_at", () => {
  const sorted = sortThreadMessages([
    { message_id: "b", thread_id: "t", role: "agent", body: "2", sequence: 2, created_at: "2026-07-13T00:00:02Z" },
    { message_id: "a", thread_id: "t", role: "user", body: "1", sequence: 1, created_at: "2026-07-13T00:00:01Z" },
    { message_id: "c", thread_id: "t", role: "agent", body: "3", sequence: 3, created_at: "2026-07-13T00:00:03Z" },
  ]);
  assert.deepEqual(sorted.map((item) => item.message_id), ["a", "b", "c"]);
});

test("mergeThreadMessages dedupes by message_id and keeps order", () => {
  const merged = mergeThreadMessages(
    [
      { message_id: "a", thread_id: "t", role: "user", body: "old", sequence: 1, created_at: "2026-07-13T00:00:01Z" },
    ],
    [
      { message_id: "a", thread_id: "t", role: "user", body: "new", sequence: 1, created_at: "2026-07-13T00:00:01Z" },
      { message_id: "b", thread_id: "t", role: "agent", body: "reply", sequence: 2, created_at: "2026-07-13T00:00:02Z" },
    ],
  );
  assert.equal(merged.length, 2);
  assert.equal(merged[0].body, "new");
  assert.equal(merged[1].message_id, "b");
});

test("latestThreadMessage returns highest sequence", () => {
  const latest = latestThreadMessage([
    { message_id: "a", thread_id: "t", role: "user", body: "1", sequence: 1, created_at: "2026-07-13T00:00:01Z" },
    { message_id: "b", thread_id: "t", role: "agent", body: "2", sequence: 2, created_at: "2026-07-13T00:00:02Z" },
  ]);
  assert.equal(latest?.message_id, "b");
  assert.equal(latestThreadMessage([]), null);
});
