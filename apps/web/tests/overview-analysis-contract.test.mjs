import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

async function fileText(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

test("overview header does not show project status / active analysis pills", async () => {
  const shell = await fileText("components/overview-seed-shell.tsx");
  const live = await fileText("components/overview-activity-log-live.tsx");
  assert.doesNotMatch(shell, /zh="项目状态"/);
  assert.doesNotMatch(shell, /zh="当前分析"/);
  assert.match(shell, /OverviewActivityLogLive/);
  assert.match(shell, /streamKind=\{isAnalysisRun \? "analysis" : "static"\}/);
  assert.match(live, /connectAnalysisEventStream/);
  assert.match(live, /实时 SSE|Live SSE/);
});

test("overview primary path starts Pi analysis runs instead of seed_pipeline", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/overview/page.tsx");
  const form = await fileText("components/overview-seed-upload-form.tsx");
  const shell = await fileText("components/overview-seed-shell.tsx");

  assert.match(page, /startAnalysisRun/);
  assert.match(page, /getProjectAnalysisRuns/);
  assert.match(page, /listAnalysisWorkspaceFiles/);
  assert.match(page, /listAnalysisCandidates/);
  assert.doesNotMatch(page, /startSeedRun\(/);
  assert.doesNotMatch(page, /getProjectSeedRuns/);
  assert.match(form, /analysis-hints/);
  assert.match(form, /上传并开始分析|Upload and start analysis/);
  assert.doesNotMatch(form, /支持 TXT、Markdown 和 PDF/);
  assert.match(shell, /OverviewAnalysisWorkspacePanel/);
  assert.match(shell, /OverviewAnalysisCandidatesPanel/);
  assert.match(shell, /analysis_run/);
});

test("overview surfaces analysis results on the main path and hides tool spam", async () => {
  const shell = await fileText("components/overview-seed-shell.tsx");
  const activity = await fileText("lib/overview-analysis-activity.ts");
  const live = await fileText("components/overview-activity-log-live.tsx");
  const candidates = await fileText("components/overview-analysis-candidates-panel.tsx");
  const wall = await fileText("components/overview-seed-progress-wall.tsx");

  assert.match(shell, /overview-analysis-results/);
  assert.match(shell, /showResults && isAnalysisRun/);
  assert.match(shell, /项目诊断（可选）|Project diagnostics \(optional\)/);
  assert.doesNotMatch(shell, /function SeedEvents/);
  assert.doesNotMatch(shell, /Progress and activity/);
  assert.match(activity, /Author-facing log keeps stage milestones only/);
  assert.match(activity, /analysis\.tool\.started/);
  assert.match(activity, /analysis\.tool\.completed/);
  assert.ok(
    activity.includes('if (event.event_type === "analysis.tool.started" || event.event_type === "analysis.tool.completed")')
      && activity.includes("return null;"),
    "tool events must be dropped from author activity lines",
  );
  assert.match(activity, /20-notes\//);
  assert.match(activity, /return null;/);
  assert.match(live, /关键进度|Key progress/);
  assert.match(live, /lines\.slice\(0, 12\)/);
  assert.match(candidates, /拆解结果（分析候选）|Analysis results \(candidates\)/);
  assert.match(wall, /查看拆解结果|View analysis results/);
  assert.match(wall, /#analysis-candidates-heading/);
});

test("analysis API client exposes workspace and candidates endpoints", async () => {
  const client = await fileText("lib/api.ts");
  assert.match(client, /export async function startAnalysisRun/);
  assert.match(client, /export async function listAnalysisWorkspaceFiles/);
  assert.match(client, /export async function listAnalysisCandidates/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/analysis-runs`/);
  assert.match(client, /\/v1\/analysis-runs\/\$\{input\.runId\}\/workspace\/files/);
  assert.match(client, /\/v1\/analysis-runs\/\$\{input\.runId\}\/candidates/);
});
