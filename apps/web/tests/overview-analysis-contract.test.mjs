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

test("overview analysis failure surfaces actionable binding recovery", async () => {
  const activity = await fileText("lib/overview-analysis-activity.ts");
  const shell = await fileText("components/overview-seed-shell.tsx");
  const wall = await fileText("components/overview-seed-progress-wall.tsx");
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/overview/page.tsx");

  assert.match(activity, /分析所需模型尚未绑定|Analysis modules are unbound/);
  assert.match(shell, /分析模型未就绪|Analysis model not ready/);
  assert.match(shell, /failureRecoveryHref/);
  assert.match(shell, /overview-action-status/);
  assert.match(wall, /overview-status-failure-banner/);
  assert.match(wall, /立即重试|Retry now/);
  assert.match(wall, /打开模型设置|Open model settings/);
  assert.match(page, /startAnalysisRun/);
  assert.match(page, /ANALYSIS_RETRY_SOURCE_MISSING/);
});

test("overview surfaces analysis results with tool_ progress lines", async () => {
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
  assert.match(activity, /analysis\.tool\.started/);
  assert.match(activity, /analysis\.tool\.completed/);
  assert.match(activity, /message: `tool_\$\{toolName\}`/);
  assert.doesNotMatch(
    activity.slice(
      activity.indexOf('if (event.event_type === "analysis.tool.started"'),
      activity.indexOf("if (event.event_type === \"analysis.file.written\")"),
    ),
    /return null;/,
  );
  assert.match(activity, /path\.startsWith\("20-notes\/"\)/);
  assert.match(live, /关键进度|Key progress/);
  assert.match(live, /lines\.slice\(0, 24\)/);
  assert.doesNotMatch(live, /完整工具轨迹不向作者展示|full tool traces are hidden/);
  assert.match(candidates, /拆解结果（已自动入库）|Analysis results \(auto-imported\)/);
  assert.match(candidates, /自动写入素材库|auto-imported into the library/);
  assert.match(candidates, /<details className="overview-details overview-analysis-candidates"/);
  assert.doesNotMatch(candidates, /overview-analysis-candidates"[^>]*\sopen/);
  assert.match(candidates, /overview-details-chevron/);
  const workspace = await fileText("components/overview-analysis-workspace-panel.tsx");
  assert.match(workspace, /<details className="overview-details overview-analysis-workspace"/);
  assert.doesNotMatch(
    workspace.replace(/error-box" open/g, 'error-box"'),
    /overview-analysis-workspace"[^>]*\sopen/,
  );
  assert.match(workspace, /overview-details-chevron/);
  assert.match(wall, /拆解完成，已自动入库|Analysis complete/);
  assert.match(wall, /#analysis-candidates-heading/);
  assert.match(activity, /analysis\.assets\.imported/);
  assert.match(activity, /已自动入库|Auto-imported/);
  assert.match(shell, /overview-completed-board|OverviewCompletedBoard/);
  assert.match(shell, /overview-completed-import/);
  assert.match(shell, /presentation="body"/);
  assert.match(shell, /embedResults=\{false\}/);
  assert.match(shell, /data-overview-state=\{overviewState\}/);
  assert.doesNotMatch(shell, /overview-upload-collapsed/);
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
