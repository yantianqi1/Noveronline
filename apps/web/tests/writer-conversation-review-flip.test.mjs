import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

const workspaceUrl = new URL(
  "../app/projects/[projectId]/writer/writer-workspace.tsx",
  import.meta.url,
);
const flipUrl = new URL(
  "../app/projects/[projectId]/writer/composer-review-flip.tsx",
  import.meta.url,
);

test("writer switches the complete conversation dock between 对话/待审资产 tabs", async () => {
  const [workspace, flip] = await Promise.all([
    readFile(workspaceUrl, "utf8"),
    readFile(flipUrl, "utf8"),
  ]);

  assert.match(workspace, /<ConversationReviewFlip/);
  assert.match(workspace, /conversation=\{\(\) =>/);
  assert.match(workspace, /<WriterRail/);
  // The dock-head tabs own switching, so the rail's own header stays hidden.
  assert.match(workspace, /hideHeader/);
  assert.match(workspace, /<WriterComposer/);
  assert.doesNotMatch(workspace, /<ComposerReviewFlip/);

  // The 3D flip is gone: a dock-head owns 对话/待审资产 tabs (ink underline,
  // neutral count chip, hasNew dot, ⌘J hint) and both faces crossfade in
  // place while staying mounted.
  assert.doesNotMatch(flip, /rotateY/);
  assert.match(flip, /role="tablist"/);
  assert.match(flip, /aria-label="合著者对话"/);
  assert.match(flip, /aria-label="待审资产审核台"/);
  assert.match(flip, /aria-selected=\{active\}/);
  assert.match(flip, /rounded-full bg-paper-deep px-1\.5 font-mono text-micro/);
  assert.match(flip, /size-1\.5 rounded-full bg-accent/);
  assert.match(flip, /<kbd className="kbd ml-auto">⌘J<\/kbd>/);
  assert.match(flip, /transition-opacity/);
  assert.match(flip, /conversation\(null\)/);
  assert.match(flip, /review\(handleCountChange\)/);
  assert.doesNotMatch(flip, /返回合著者/);
  assert.doesNotMatch(flip, /bg-candidate/);
  assert.equal(flip.match(/onClick=\{\(\) => setFlipped\(false\)\}/g)?.length, 1);
});
