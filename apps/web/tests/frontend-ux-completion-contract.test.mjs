import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");
const repositoryRoot = path.resolve(root, "../..");

async function source(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

async function repositorySource(relativePath) {
  return readFile(path.join(repositoryRoot, relativePath), "utf8");
}

test("retired root frontend and blue Writer evidence stay removed", async () => {
  await assert.rejects(access(path.join(repositoryRoot, "frontend")), { code: "ENOENT" });

  const guidance = (
    await Promise.all([
      "AGENTS.md",
      "CLAUDE.md",
      "CONTRIBUTING.md",
      "README.md",
      "docs/refactor-saas/25-release-retirement-and-compatibility.md",
    ].map(repositorySource))
  ).join("\n");
  assert.doesNotMatch(guidance, /cd\s+frontend\b|frontend\/src\//);
  assert.match(guidance, /apps\/web[^\n]*(?:only|\u552f\u4e00)|\u552f\u4e00[^\n]*apps\/web/i);

  const currentEvidence = (
    await Promise.all([
      "docs/refactor-saas/18-legacy-coverage-matrix.md",
      "docs/refactor-saas/24-current-development-progress.md",
    ].map(repositorySource))
  ).join("\n");
  assert.doesNotMatch(currentEvidence, /\/tmp\/p6-writer-planning-certification/);
  assert.match(currentEvidence, /Agent-first/);

  const localSkill = await repositorySource(".agents/skills/build-novel-agent-ui/SKILL.md");
  assert.match(localSkill, /Agent-first/);
  assert.doesNotMatch(localSkill, /manuscript is primary|contextual agent rail/i);

  const activeGraph = await source("components/story-graph-shell.tsx");
  assert.doesNotMatch(activeGraph, /#0f6cbd/i);
});

test("Wave 3: Assets use CompactFilterBar and InspectorPanel", async () => {
  const shell = await source("components/asset-library-shell.tsx");
  assert.match(shell, /CompactFilterBar/);
  assert.match(shell, /InspectorPanel/);
  assert.match(shell, /asset-filter-disclosure/);
  assert.match(shell, /WorkspaceHeader/);
});

test("Wave 3: Overview wires shared WorkflowProgress and SubmitButton", async () => {
  const shell = await source("components/overview-seed-shell.tsx");
  const wall = await source("components/overview-seed-progress-wall.tsx");
  assert.match(shell, /OverviewSeedProgressWall/);
  assert.match(wall, /from "\.\/workflow-progress"/);
  assert.match(wall, /<WorkflowProgress/);
  assert.match(shell, /SubmitButton/);
  assert.match(shell, /overview-next-panel/);
});

test("Overview seed progress wall collapses idle stages and densifies failed cards", async () => {
  const shell = await source("components/overview-seed-shell.tsx");
  const wall = await source("components/overview-seed-progress-wall.tsx");
  const css = await source("app/globals.css");
  const beijing = await source("lib/beijing-time.ts");

  assert.match(shell, /OverviewSeedProgressWall/);
  assert.match(shell, /formatBeijingTimeLabel|formatBeijingTime/);
  assert.match(wall, /data-wall="seed-progress"/);
  assert.match(wall, /shouldAutoExpand/);
  assert.match(wall, /previewStages|stageStates\.slice\(0,\s*2\)/);
  assert.match(wall, /overview-status-wall-ellipsis/);
  assert.match(wall, /data-density=\{isFailed \|\| interrupted \? "compact"/);
  assert.match(wall, /aria-expanded=\{expanded\}/);
  assert.match(shell, /seedActivityLog|overview-activity-log/);
  assert.match(shell, /seed\.sequential_reading\.progress/);
  assert.match(css, /\.overview-status-card\[data-density="compact"\]/);
  assert.match(css, /min-height:\s*0/);
  assert.match(css, /overview-wall-pop/);
  assert.match(css, /\.overview-activity-log/);
  assert.match(css, /overview-progress-thin|height:\s*4px/);
  assert.match(css, /prefers-reduced-motion/);
  assert.match(beijing, /Asia\/Shanghai/);
  assert.match(beijing, /export function formatBeijingTime/);
});

test("Wave 4: Graph exclusive Explore/Build/Curate/Compose modes", async () => {
  const shell = await source("components/story-graph-shell.tsx");
  assert.match(shell, /"explore" \| "build" \| "curate" \| "compose"/);
  assert.match(shell, /workspaceMode === "explore"/);
  assert.match(shell, /workspaceMode === "build"/);
  assert.match(shell, /workspaceMode === "curate"/);
  assert.match(shell, /workspaceMode === "compose"/);
  assert.match(shell, /InspectorPanel/);
});

test("Wave 4: Worldline exclusive mode switcher", async () => {
  const shell = await source("components/worldline-shell.tsx");
  assert.match(shell, /WorkspaceModeSwitcher/);
  assert.match(shell, /id: "start"/);
  assert.match(shell, /id: "simulate"/);
  assert.match(shell, /id: "records"/);
  assert.match(shell, /SubmitButton/);
  assert.doesNotMatch(shell, /<strong>\{[^}]*\.code\}<\/strong>/);
});

test("Wave 4: Character exclusive mode switcher and inspector", async () => {
  const shell = await source("components/character-console-shell.tsx");
  assert.match(shell, /WorkspaceModeSwitcher/);
  assert.match(shell, /id: "setup"/);
  assert.match(shell, /id: "play"/);
  assert.match(shell, /id: "review"/);
  assert.match(shell, /InspectorPanel/);
  assert.doesNotMatch(shell, /<code>\{runtimeStatus\.runId\}<\/code>/);
});

test("Wave 5: Writer privacy and diagnostics drawer", async () => {
  const shell = await source("components/writer-workbench-shell.tsx");
  const product = await source("components/writer-product-workspace.tsx");
  assert.match(shell, /TechnicalDetailsDrawer/);
  assert.match(shell, /SubmitButton/);
  assert.match(shell, /Recovered stream/);
  assert.match(shell, /name="after_event_id"/);
  assert.doesNotMatch(shell, /<Bi zh="任务" en="Run" \/> <strong>\{runSummary\.run_id\}<\/strong>/);
  assert.doesNotMatch(shell, /<strong>\{status\.code\}<\/strong>/);
  assert.doesNotMatch(product, /<strong>\{review\.review_id\}<\/strong>/);
  assert.doesNotMatch(product, /command_run_id\}<\/span>/);
  assert.doesNotMatch(product, /error_code \? <small>\{[^}]*error_code\}<\/small>/);
  assert.doesNotMatch(product, /<strong>\{record\.export_id\}<\/strong>/);
  assert.match(product, /ConfirmSubmitButton/);
  assert.match(product, /SubmitButton/);
});

test("Wave 6: LLM author surface gated by canManageAdmin", async () => {
  const shell = await source("components/llm-facility-shell.tsx");
  const page = await source("app/(app)/[tenantSlug]/projects/[projectId]/llm-facility/page.tsx");
  assert.match(shell, /canManageAdmin/);
  assert.match(shell, /data-surface="author"/);
  assert.match(shell, /data-surface="admin"/);
  assert.match(shell, /canManageAdmin \? \(/);
  assert.match(page, /canManageAdmin=\{canManageAdmin\}/);
  assert.match(page, /tenantRole === "owner" \|\| tenantRole === "admin"/);
});

test("shared controls provide pending submit and confirm focus semantics", async () => {
  const submit = await source("components/submit-button.tsx");
  const confirm = await source("components/confirm-dialog.tsx");
  const drawer = await source("components/technical-details-drawer.tsx");
  const mode = await source("components/workspace-mode-switcher.tsx");
  assert.match(submit, /useFormStatus/);
  assert.match(submit, /aria-busy=\{busy\}/);
  assert.match(confirm, /showModal\(/);
  assert.match(confirm, /previousFocusRef/);
  assert.match(drawer, /showModal\(/);
  assert.match(drawer, /triggerRef\.current\?\.focus/);
  assert.match(mode, /role="tablist"/);
  assert.match(mode, /role="tabpanel"/);
});

test("paper-ink tokens and responsive shell remain complete", async () => {
  const css = await source("app/globals.css");
  assert.match(css, /--surface-app:\s*#f3eee4/);
  assert.match(css, /--accent-primary:\s*#8f211b/);
  assert.match(css, /--ink:\s*#171a1b/);
  assert.match(css, /\.workspace-header\s*\{/);
  assert.match(css, /\.compact-filter-bar\s*\{/);
  assert.match(css, /\.inspector-panel\s*\{/);
  assert.match(css, /\.workflow-progress\s*\{/);
  assert.match(css, /\.technical-details-dialog\s*\{/);
  assert.match(css, /\.workspace-mode-switcher\s*\{/);
  assert.match(css, /clip-path:\s*polygon\(/);
  assert.match(css, /@media\s*\(max-width:\s*860px\)/);
  assert.match(css, /min-height:\s*44px/);
  assert.doesNotMatch(css, /--primary:\s*#0f6cbd/);
});

test("content boundary covers product workspace id dumps", async () => {
  const product = await source("components/writer-product-workspace.tsx");
  assert.doesNotMatch(product, /<strong>\{[^}]*\.(review_id|export_id|command_run_id)\}<\/strong>/);
  assert.doesNotMatch(product, /error_code \? <small>/);
});

test("Wave A polish: Assets rows link to detail and search is optional", async () => {
  const shell = await source("components/asset-library-shell.tsx");
  const ops = await source("components/asset-operation-workspace.tsx");
  const queryInput = shell.slice(shell.indexOf('id="asset-search-query"'), shell.indexOf('id="asset-search-query"') + 320);
  assert.match(shell, /assetDetailHref/);
  assert.match(shell, /asset-title-link/);
  assert.match(shell, /\/assets\/\$\{encodeURIComponent\(assetId\)\}/);
  assert.doesNotMatch(queryInput, /\brequired\b/);
  assert.match(ops, /primaryId/);
  assert.match(ops, /moreLabel|asset-command-more/);
});

test("Wave A polish: author LLM bindings panel hides infrastructure fields", async () => {
  const shell = await source("components/llm-facility-shell.tsx");
  const panel = await source("components/llm-module-bindings-panel.tsx");
  assert.match(shell, /LLMModuleBindingsPanel/);
  assert.match(shell, /data-layout="single"/);
  assert.match(shell, /workspace-header-actions|actions=\{diagnosticsDrawer\}/);
  assert.doesNotMatch(shell, /llm-observability-rail/);
  assert.doesNotMatch(shell, /配置项目模型|Configure project models/);
  assert.match(panel, /llm-bindings-panel/);
  assert.match(panel, /batchBindModuleAction/);
  assert.match(panel, /llm-bindings-group-chips/);
  assert.match(panel, /llm-bindings-group-chip/);
  assert.match(panel, /应用到所选|Apply to selected/);
  assert.doesNotMatch(panel, /一张表管理全部模块绑定/);
  assert.doesNotMatch(panel, /base_url/);
  assert.doesNotMatch(panel, /supports_tools/);
  assert.doesNotMatch(panel, /effective\?\.channel_id/);
  assert.doesNotMatch(panel, /max_tokens=/);
  assert.doesNotMatch(panel, />module_key</);
});

test("Wave A polish: writer draft panel hides raw draft id", async () => {
  const shell = await source("components/writer-workbench-shell.tsx");
  assert.doesNotMatch(shell, /<Bi zh="草稿" en="Draft" \/> <strong>\{draftId\}<\/strong>/);
  assert.match(shell, /候选草稿|Candidate draft/);
});

test("Wave A polish: product errors avoid raw error codes", async () => {
  const detail = await source("components/asset-detail-shell.tsx");
  const members = await source("components/members-workspace.tsx");
  const security = await source("app/(app)/[tenantSlug]/projects/[projectId]/security/page.tsx");
  const css = await source("app/globals.css");
  assert.match(detail, /PublicErrorNotice/);
  assert.doesNotMatch(detail, /props\.failure\?\.code/);
  assert.doesNotMatch(detail, /Operation failed: \{props\.errorCode\}/);
  assert.match(members, /PublicErrorNotice/);
  assert.doesNotMatch(members, /\{error\}<\/p>/);
  assert.match(security, /PublicErrorNotice/);
  assert.doesNotMatch(security, /<strong>\{errorCode\}<\/strong>/);
  assert.doesNotMatch(css, /15,\s*108,\s*189/);
});

test("Writer is manuscript-primary with a persistent Agent dock", async () => {
  const product = await source("components/writer-product-workspace.tsx");
  const shell = await source("components/writer-workbench-shell.tsx");
  const polish = await source("app/workbench-polish.css");
  assert.match(product, /WriterArtifactTabs/);
  assert.match(product, /manuscript={/);
  assert.match(product, /structure={/);
  assert.match(product, /review={/);
  assert.match(product, /studio={/);
  assert.match(shell, /writer-agent-layout/);
  assert.match(shell, /data-layout="manuscript-primary"/);
  assert.match(shell, /writer-artifact-canvas/);
  assert.match(shell, /writer-agent-dock/);
  assert.match(shell, /writer-structure-rail/);
  assert.match(shell, /structureNav/);
  assert.match(shell, /data-has-structure/);
  assert.match(shell, /WriterAgentThread/);
  assert.match(shell, /writer-agent-composer/);
  assert.match(shell, /WriterLiveDraft/);
  const liveDraft = await source("components/writer-live-draft.tsx");
  assert.match(liveDraft, /writerDraftText|connectWriterEventStream/);
  assert.match(liveDraft, /connectWriterEventStream|mergeWriterEvents/);
  assert.match(liveDraft, /after_event_id|connectWriterEventStream/);
  // Persistent left-rail structure navigator (true three-region), progressive-enhancement GET forms.
  const structureNav = await source("components/writer-structure-nav.tsx");
  assert.match(structureNav, /WriterStructureNav/);
  assert.match(structureNav, /writer-structure-nav/);
  assert.match(structureNav, /method="get"/);
  // ⌘K command palette drives the canvas tabs via shared workbench context.
  assert.match(shell, /WriterCommandPalette/);
  assert.match(shell, /WriterWorkbenchProvider/);
  const palette = await source("components/writer-command-palette.tsx");
  assert.match(palette, /writer-command-palette/);
  assert.match(palette, /role="dialog"/);
  const workbenchContext = await source("components/writer-workbench-context.tsx");
  assert.match(workbenchContext, /metaKey|ctrlKey/);
  const artifactTabs = await source("components/writer-artifact-tabs.tsx");
  assert.match(artifactTabs, /useWriterWorkbench/);
  // Top bar: breadcrumb + run-state chip + sync indicator.
  assert.match(shell, /writer-breadcrumb/);
  assert.match(shell, /WriterRunStateChip/);
  assert.match(shell, /writer-sync-chip/);
  const headerStart = shell.indexOf("<WorkspaceHeader");
  const headerEnd = shell.indexOf("\n      />", headerStart);
  const header = shell.slice(headerStart, headerEnd);
  const actionsIndex = header.indexOf("actions={");
  const runStateIndex = header.indexOf("<WriterRunStateChip");
  const syncIndex = header.indexOf("writer-sync-chip");
  assert.ok(actionsIndex >= 0 && runStateIndex > actionsIndex && syncIndex > runStateIndex);
  assert.doesNotMatch(header, /meta=\{<WriterRunStateChip/);
  assert.match(polish, /\.app-frame\.app-frame-unified:has\(\.writer-root\)\s*\{\s*--workspace-header-height:\s*96px;/s);
  // Manuscript canvas is the dominant primary; the Agent dock is persistent but secondary.
  const productIndex = shell.indexOf("{productWorkspace}");
  const threadIndex = shell.indexOf("<WriterAgentThread");
  assert.ok(productIndex >= 0 && threadIndex > productIndex);
  for (const retiredClass of ["writer-studio-grid", "writer-workbench-prose-first", "writer-composer-disclosure", "writer-agent-rail"]) {
    assert.doesNotMatch(`${product}\n${shell}`, new RegExp(retiredClass));
  }
});

test("Wave B: Worldline simulate elevates timeline", async () => {
  const shell = await source("components/worldline-shell.tsx");
  assert.match(shell, /worldline-timeline-primary/);
  assert.match(shell, /worldline-simulate-toolbar/);
  const timelineIndex = shell.indexOf("worldline-timeline-primary");
  const toolbarIndex = shell.indexOf("worldline-simulate-toolbar");
  assert.ok(timelineIndex >= 0 && toolbarIndex > timelineIndex);
});

test("Wave B: Graph inspector is selection-first", async () => {
  const shell = await source("components/story-graph-shell.tsx");
  assert.match(shell, /selectedNodeId/);
  assert.match(shell, /onSelectNodeId/);
  assert.match(shell, /graph-selected-heading/);
  assert.match(shell, /story-graph-stats-disclosure/);
});

test("Wave B/C: compact header, list row, polish CSS, context bar", async () => {
  const header = await source("components/workspace-header.tsx");
  const listRow = await source("components/list-row.tsx");
  const polish = await source("app/workbench-polish.css");
  const layout = await source("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");
  const root = await source("app/layout.tsx");
  const overview = await source("components/overview-seed-shell.tsx");
  assert.match(header, /workspace-header-compact/);
  assert.match(listRow, /list-row-title-link/);
  assert.match(polish, /\.writer-agent-layout/);
  assert.match(polish, /\.writer-artifact-tabs/);
  assert.doesNotMatch(polish, /\.writer-studio-grid|\.writer-agent-rail/);
  assert.match(polish, /\.list-row/);
  assert.match(layout, /WorkspaceContextBar/);
  assert.match(root, /workbench-polish\.css/);
  assert.doesNotMatch(overview, /PROJECT OVERVIEW \/ 07/);
  assert.match(overview, /overview-readiness-inline|overview-next-blocked/);
});
