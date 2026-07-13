import assert from "node:assert/strict";
import test from "node:test";

import {
  acceptAllHunks,
  applyHunkDecisions,
  computeRevisionHunks,
  rejectAllHunks,
} from "../lib/writer-diff.ts";

test("computeRevisionHunks detects insert and delete line changes", () => {
  const hunks = computeRevisionHunks("第一行\n第二行\n", "第一行\n新行\n第二行\n");
  assert.ok(hunks.length >= 1);
  assert.ok(hunks.some((hunk) => hunk.op === "insert" && hunk.proposedText.includes("新行")));
});

test("acceptAllHunks yields proposed text for pure replacement", () => {
  const base = "旧文";
  const proposed = "新文";
  assert.equal(acceptAllHunks(base, proposed), proposed);
});

test("rejectAllHunks keeps base text", () => {
  assert.equal(rejectAllHunks("原文", "改文"), "原文");
});

test("applyHunkDecisions accepts only chosen hunks", () => {
  const base = "A\nB\nC\n";
  const proposed = "A\nX\nC\n";
  const hunks = computeRevisionHunks(base, proposed);
  assert.ok(hunks.length > 0);
  const decisions = Object.fromEntries(hunks.map((hunk) => [hunk.id, "accept"]));
  assert.equal(applyHunkDecisions(base, hunks, decisions), proposed);
  const reject = Object.fromEntries(hunks.map((hunk) => [hunk.id, "reject"]));
  assert.equal(applyHunkDecisions(base, hunks, reject), base);
});

test("identical texts produce no hunks", () => {
  assert.deepEqual(computeRevisionHunks("same", "same"), []);
});
