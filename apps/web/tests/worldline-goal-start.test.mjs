import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");

async function source(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

test("世界线整备按钮触发真正的 goal-start 编排，而不是裸会话排队", async () => {
  const workspace = await source("app/projects/[projectId]/worldline/worldline-workspace.tsx");
  // The start action admits a worldline_goal_start run (Pi cast planner)…
  assert.match(workspace, /startWorldlineGoalStart/);
  // …and no longer admits a bare worldline_session row with no consumer.
  assert.doesNotMatch(workspace, /startWorldlineSession/);
  // The run is tracked until the orchestration attaches a session.
  assert.match(workspace, /fetchWorldlineGoalStart/);
  assert.match(workspace, /gs\.status === "ready" && gs\.session_id/);
  assert.match(workspace, /gs\.status === "failed"/);
  // The roster is loaded from the preparation the orchestration completed.
  assert.match(workspace, /fetchWorldlinePreparedAgents/);
});

test("goal-start 客户端走真实后端路由并携带幂等与 CSRF 纪律", async () => {
  const client = await source("lib/api/worldline-client.ts");
  // BFF paths the Go API actually serves (see internal/httpapi goal-start handlers).
  assert.match(client, /\/api\/projects\/\$\{projectId\}\/worldline-goal-starts`/);
  assert.match(client, /worldline-goal-starts\/\$\{encodeURIComponent\(runId\)\}/);
  // Mutations keep the X-Request-Id idempotency discipline via sendJson.
  assert.match(client, /X-Request-Id/);
  assert.match(client, /X-CSRF-Token/);
});

test("BFF 代理只放行真实存在的 goal-start 路由", async () => {
  const route = await source("app/api/projects/[projectId]/[...path]/route.ts");
  // POST /api/projects/{id}/worldline-goal-starts → /v1/projects/{id}/worldline-goal-starts
  assert.match(route, /\^worldline-goal-starts\$/);
  // GET /api/projects/{id}/worldline-goal-starts/{runId} → /v1/worldline-goal-starts/{runId}
  assert.match(route, /\^worldline-goal-starts\\\/\(\[\^\/\]\+\)\$/);
  assert.match(route, /\/v1\/worldline-goal-starts\//);
});

test("整备态展示真实编排阶段与演员落位，不伪造数据", async () => {
  const workspace = await source("app/projects/[projectId]/worldline/worldline-workspace.tsx");
  // The 整备态 ladder mirrors the backend status machine (casting/preparing/starting).
  assert.match(workspace, /casting/);
  assert.match(workspace, /preparing/);
  assert.match(workspace, /starting/);
  // Failed runs surface a resume path (续传) keyed to the failed run.
  assert.match(workspace, /续传整备/);
  assert.match(workspace, /resume_of/);
  // No fabricated sessions/events: nothing seeds local timeline or candidate data.
  assert.doesNotMatch(workspace, /setTimeline\(\[(?!tl)/);
  assert.doesNotMatch(workspace, /mock|fixture|demo/i);
});

test("时间线把采纳行解析为真实领域事件，而不是编排占位符", async () => {
  const workspace = await source("app/projects/[projectId]/worldline/worldline-workspace.tsx");
  // Adoption rows map to the referenced canon event (title/summary + full detail).
  assert.match(workspace, /event_ref_id/);
  assert.match(workspace, /adopted_title/);
  assert.match(workspace, /resolveInspectEvent/);
  assert.match(workspace, /WORLDLINE_CANON/);
  // The inspector surfaces agents/confidence/state-change summary for the canon event.
  assert.match(workspace, /involved_agent_ids/);
  assert.match(workspace, /涉及角色/);
  assert.match(workspace, /置信度/);
  // And the placeholder string is gone from the frontend mapping.
  assert.doesNotMatch(workspace, /Worldline event adopted/);
});

test("时间线卡片把编排标记渲染为静态节点，不给空检查器", async () => {
  const card = await source("app/projects/[projectId]/worldline/worldline-event-card.tsx");
  // workflow.* markers (queued/admitted) render as a static node, not a button.
  assert.match(card, /workflow\./);
  assert.match(card, /isMarker/);
  // Canon detection includes the adoption lifecycle.
  assert.match(card, /canon_reference/);
});
