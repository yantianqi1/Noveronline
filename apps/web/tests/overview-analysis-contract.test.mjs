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

test("author-facing UI copy never names the Pi runtime vendor", async () => {
  const files = [
    "lib/user-facing-copy.ts",
    "lib/overview-analysis-activity.ts",
    "lib/author-copy.ts",
    "components/overview-analysis-workspace-panel.tsx",
    "components/overview-seed-shell.tsx",
    "components/materials-hub.tsx",
    "components/writer-agent-thread.tsx",
    "components/writer-home-state.tsx",
  ];
  for (const relative of files) {
    let text = await fileText(relative);
    // Scrub helper may mention vendor tokens in regex patterns; those are not UI copy.
    text = text.replace(/export function scrubInternalRuntimeBranding[\s\S]*?\n\}/, "");
    text = text.replace(/function inferFailureCodeFromMessage[\s\S]*?\n\}/, "");
    assert.doesNotMatch(
      text,
      /["'`][^"'`]{0,80}\bPi\s+(Writer|agent|analysis|planner|worker|智能体|分析|拆解|规划|执行)/i,
      `${relative} must not expose Pi vendor branding in UI strings`,
    );
  }
  const copy = await fileText("lib/user-facing-copy.ts");
  assert.match(copy, /scrubInternalRuntimeBranding/);
  assert.match(copy, /写作助手暂时不可用/);
  assert.doesNotMatch(copy, /PI_WRITER_UNAVAILABLE:\s*\[["']Pi /);
});

test("overview primary path starts analysis runs instead of seed_pipeline", async () => {
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
  assert.match(candidates, /拆解结果（已自动入库）|Analysis results \(auto-imported\)/);
  assert.match(candidates, /自动写入素材库|auto-imported into the library/);
  assert.match(candidates, /<details className="overview-details overview-analysis-candidates"/);
  assert.match(candidates, /overview-details-chevron/);
  const workspace = await fileText("components/overview-analysis-workspace-panel.tsx");
  assert.match(workspace, /<details className="overview-details overview-analysis-workspace"/);
  assert.match(workspace, /overview-details-chevron/);
  assert.match(wall, /拆解完成，已自动入库|Analysis complete/);
  assert.match(wall, /#analysis-candidates-heading/);
  assert.match(activity, /analysis\.assets\.imported/);
  assert.match(activity, /已自动入库|Auto-imported/);
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
