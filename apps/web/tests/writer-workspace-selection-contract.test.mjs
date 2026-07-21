import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");

async function source(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

test("writer workspace BFF proxies chapter/scene/block reads with session cookie", async () => {
  const route = await source("app/api/writer-workspace/[tenantId]/[projectId]/route.ts");
  const client = await source("components/writer-workspace-client.ts");
  assert.match(route, /resource=chapters \| scenes \| blocks \| block \| versions/);
  assert.match(route, /mirofish_session/);
  assert.match(route, /X-Tenant-Id/);
  assert.match(route, /UNAUTHENTICATED/);
  assert.match(route, /VALIDATION_FAILED/);
  assert.match(route, /manuscript-workspace/);
  assert.match(route, /\/blocks\/\$\{encodeURIComponent\(blockId\)\}/);
  assert.match(route, /\/versions/);
  assert.doesNotMatch(route, /MIROFISH_API_KEY|Authorization:\s*Bearer/);
  assert.match(client, /fetchBlocks|fetchScenes|fetchPrivateBlock|fetchBlockVersions/);
  assert.match(client, /credentials:\s*["']same-origin["']/);
});

test("writer selection mirrors focus into workbench for agent admission", async () => {
  const selection = await source("components/writer-selection.tsx");
  const workbench = await source("components/writer-workbench-context.tsx");
  const thread = await source("components/writer-agent-thread.tsx");
  const switcher = await source("components/writer-chapter-switcher.tsx");
  assert.match(workbench, /focus:\s*WriterFocus|setFocus/);
  assert.match(selection, /setFocus\?\.\(\{ chapterId, sceneId, blockId \}\)/);
  assert.match(selection, /setScenes\(\[\]\)/);
  assert.match(thread, /workbench\?\.focus\.chapterId/);
  assert.match(switcher, /liveScenes|selection\?\.scenes/);
  assert.match(switcher, /currentChapterId/);
});
