import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");

async function source(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

test("变量锁定走 PATCH 回写并持久化，不再是纯前端内存", async () => {
  const workspace = await source("app/projects/[projectId]/worldline/worldline-workspace.tsx");
  // Lock toggle calls the persisted PATCH endpoint with the next locked value…
  assert.match(workspace, /setWorldlineVariableLocked/);
  assert.match(workspace, /const nextLocked = !variable\.locked/);
  // …optimistically flips local state…
  assert.match(workspace, /\{ \.\.\.v, locked: nextLocked \}/);
  // …rolls back on failure with an honest error…
  assert.match(workspace, /锁定变量失败/);
  // …and reconciles with the server-returned record on success.
  assert.match(workspace, /v\.variable_id === saved\.variable_id \? saved : v/);

  const client = await source("lib/api/worldline-client.ts");
  assert.match(client, /"PATCH",\s*\n?\s*`\/api\/projects\/\$\{projectId\}\/worldline-sessions\/\$\{encodeURIComponent\(sessionId\)\}\/variables\/\$\{encodeURIComponent\(variableId\)\}`/);
  assert.match(client, /\{ locked \}/);
});

test("会话装载时经 GET 水合变量，替换空数组初值", async () => {
  const workspace = await source("app/projects/[projectId]/worldline/worldline-workspace.tsx");
  assert.match(workspace, /fetchWorldlineVariables\(sel\.project_id, sel\.tenant_id, sessionId\)/);
  assert.match(workspace, /pendingVariableLocksRef\.current\.has\(variable\.variable_id\)/);
  assert.match(workspace, /setVariables\(\(current\) =>/);

  const client = await source("lib/api/worldline-client.ts");
  assert.match(client, /export async function fetchWorldlineVariables/);
  assert.match(client, /worldline-sessions\/\$\{encodeURIComponent\(sessionId\)\}\/variables`/);
});

test("BFF 放行变量 GET 与嵌套 PATCH，且变量 id 被重新编码", async () => {
  const route = await source("app/api/projects/[projectId]/[...path]/route.ts");
  // worldline-sessions/{id}/variables[/{variableId}] is in the top-level allowlist…
  assert.match(route, /\\\/variables\(\\\/\[\^\/\]\+\)\?/);
  // …and the nested variable id is URI-encoded before hitting the Go route.
  assert.match(route, /`\/v1\/worldline-sessions\/\$\{encodeURIComponent\(m\[1\]\)\}\$\{suffix\}\$\{query\}`/);
});

test("banner 步号用领域步 current_step，不再读编排 sequence", async () => {
  const workspace = await source("app/projects/[projectId]/worldline/worldline-workspace.tsx");
  // The banner reads the session's domain step…
  assert.match(workspace, /session\?\.current_step \?\? 0/);
  // …and nothing in the workspace still derives step from timeline sequence.
  assert.doesNotMatch(workspace, /Math\.max\(\.\.\.timeline\.map\(\(e\) => e\.sequence\)\)/);

  const types = await source("lib/api/worldline-types.ts");
  assert.match(types, /current_step: number/);
});

test("时间线卡片步号统一为领域步：采纳卡读正史事件的 step，编排标记不显式步号", async () => {
  const workspace = await source("app/projects/[projectId]/worldline/worldline-workspace.tsx");
  // Adoption rows resolve the step from the adopted canon event, not t.sequence…
  assert.match(workspace, /step: adopted\?\.step \?\? 0/);
  // …and the mapping no longer reads the orchestration sequence at all.
  const mapping = workspace.slice(workspace.indexOf("function timelineEventToWorldlineEvent"));
  assert.doesNotMatch(mapping.slice(0, mapping.indexOf("function resolveInspectEvent")), /t\.sequence/);

  const card = await source("app/projects/[projectId]/worldline/worldline-event-card.tsx");
  // Orchestration markers show 整备 instead of a fabricated step number.
  assert.match(card, /整备/);
  // Domain steps render as 第 N 步 only when N > 0.
  assert.match(card, /event\.step > 0 \? `第 \$\{event\.step\} 步`/);

  const timeline = await source("app/projects/[projectId]/worldline/worldline-timeline.tsx");
  assert.match(timeline, /stepRangeLabel/);
});

test("inspector 的步号也用领域 step，不回读编排 sequence", async () => {
  const workspace = await source("app/projects/[projectId]/worldline/worldline-workspace.tsx");
  assert.match(workspace, /\{ \.\.\.canonById, event_type: row\?\.event_type \?\? event\.event_type \}/);
  const inspector = workspace.slice(workspace.indexOf("function EventInspector"));
  assert.doesNotMatch(inspector, /row\.sequence/);
});
