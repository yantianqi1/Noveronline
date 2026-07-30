import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const paperUrl = new URL(
  "../app/projects/[projectId]/writer/manuscript-paper.tsx",
  import.meta.url,
);
const workspaceUrl = new URL(
  "../app/projects/[projectId]/writer/writer-workspace.tsx",
  import.meta.url,
);

test("manuscript paper surfaces a selection and offers rewrite/continue actions", async () => {
  const paper = await readFile(paperUrl, "utf8");

  // Each editable segment reports its highlight up to the paper.
  assert.match(paper, /onMouseUp=\{reportSelection\}/);
  assert.match(paper, /measureSelectionRect/);
  // The floating bar carries the four co-writer verbs.
  assert.match(paper, /kind: "rewrite", label: "改写"/);
  assert.match(paper, /kind: "continue", label: "续写"/);
  assert.match(paper, /kind: "polish", label: "润色"/);
  assert.match(paper, /kind: "expand", label: "扩写"/);
  assert.match(paper, /role="toolbar"/);
  assert.match(paper, /aria-label="选中文字操作"/);
  // The bar hands the picked action back to the workspace.
  assert.match(paper, /onSelectionAction\(kind, selection\)/);
});

test("workspace turns a selection action into a draft-run instruction", async () => {
  const workspace = await readFile(workspaceUrl, "utf8");

  assert.match(workspace, /onSelectionAction=\{handleSelectionAction\}/);
  assert.match(workspace, /buildSelectionInstruction\(kind, sel\.text\)/);
  // 续写 continues from the passage; the others transform it in place.
  assert.match(workspace, /请接着下面这段文字续写下去/);
  assert.match(workspace, /请\$\{verb\}下面这段文字/);
});
