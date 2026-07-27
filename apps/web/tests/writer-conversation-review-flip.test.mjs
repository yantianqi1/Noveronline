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

test("writer flips the complete conversation dock to a complete review face", async () => {
  const [workspace, flip] = await Promise.all([
    readFile(workspaceUrl, "utf8"),
    readFile(flipUrl, "utf8"),
  ]);

  assert.match(workspace, /<ConversationReviewFlip/);
  assert.match(workspace, /conversation=\{/);
  assert.match(workspace, /<WriterRail/);
  assert.match(workspace, /<WriterComposer/);
  assert.doesNotMatch(workspace, /<ComposerReviewFlip/);

  assert.match(flip, /\[transform:rotateY\(180deg\)\]/);
  assert.match(flip, /aria-label="合著者对话"/);
  assert.match(flip, /aria-label="待审资产审核台"/);
  assert.match(flip, /翻转到待审资产/);
  assert.match(flip, /返回合著者对话/);
});
