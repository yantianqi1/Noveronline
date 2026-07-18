import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const webRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = path.resolve(webRoot, "../..");

async function source(relativePath) {
  return readFile(path.join(webRoot, relativePath), "utf8");
}

async function repositorySource(relativePath) {
  return readFile(path.join(repoRoot, relativePath), "utf8");
}

test("worldline goal-start is the primary start path", async () => {
  const page = await source("app/(app)/[tenantSlug]/projects/[projectId]/worldline/page.tsx");
  const shell = await source("components/worldline-shell.tsx");
  const client = await source("lib/api.ts");
  const registry = await repositorySource("apps/api/internal/llm/registry.go");
  const migration = await repositorySource("infra/postgres/migrations/0022_worldline_goal_starts.sql");
  const worker = await repositorySource("apps/pi-agent-runtime/src/worldline-cast-worker.ts");

  assert.match(page, /createWorldlineGoalStartAction/);
  assert.match(page, /createWorldlineGoalStart/);
  assert.match(page, /getWorldlineGoalStart/);
  assert.match(shell, /createWorldlineGoalStartAction/);
  assert.match(shell, /GoalStartProgress|worldline-goal-start-progress/);
  assert.match(shell, /高级：手动选角|Advanced: manual cast/);
  assert.match(client, /export async function createWorldlineGoalStart/);
  assert.match(client, /worldline-goal-starts/);
  assert.match(registry, /worldline_cast_planner/);
  assert.match(migration, /worldline_goal_starts/);
  assert.match(worker, /worldline-cast-worker|WORLDLINE_CAST_TASK_QUEUE|runPiWorldlineGoalStartActivity/);
});
