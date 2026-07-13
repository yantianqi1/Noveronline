import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");

async function source(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

test("Asset Library uses one compact search surface and one advanced filter disclosure", async () => {
  const shell = await source("components/asset-library-shell.tsx");
  const formStart = shell.indexOf('<form action={searchAction}');
  const formEnd = shell.indexOf("</form>", formStart);
  const searchForm = shell.slice(formStart, formEnd);

  assert.match(searchForm, /CompactFilterBar/);
  assert.match(searchForm, /asset-search-primary-field/);
  assert.match(searchForm, /<details className="overview-details asset-filter-disclosure">/);
  assert.equal((searchForm.match(/asset-filter-disclosure/g) ?? []).length, 1);
  for (const name of ["mode", "assetType", "category", "lifecycle", "source", "tag", "pinned"]) {
    assert.match(searchForm, new RegExp(`name=["']${name}["']`));
  }
  assert.match(shell, /appliedAssetFilters/);
  assert.match(shell, /assetSearchHref/);
  assert.match(shell, /InspectorPanel/);
  assert.doesNotMatch(shell, /data-search-document-id|data-search-mode|formatScore|searchRanking/);
  assert.doesNotMatch(shell, /<span className="form-hint">\{asset\.asset_id\}<\/span>/);
  assert.match(shell, /asset-title-link/);
  assert.match(shell, /assetDetailHref/);
  assert.doesNotMatch(shell.slice(shell.indexOf('id="asset-search-query"'), shell.indexOf('id="asset-search-query"') + 280), /\brequired\b/);
});

test("Overview prioritizes the current next step and folds secondary activity", async () => {
  const shell = await source("components/overview-seed-shell.tsx");
  const nextPanelIndex = shell.indexOf("overview-next-panel");
  const metricsPanelIndex = shell.indexOf('aria-labelledby="project-health-heading"');

  assert.ok(nextPanelIndex >= 0 && nextPanelIndex < metricsPanelIndex);
  assert.match(shell, /<OverviewNextStep/);
  assert.match(shell, /Files and analysis history/);
  assert.match(shell, /Progress and activity/);
  assert.match(shell, /overview-upload-disclosure/);
  assert.doesNotMatch(shell, /<dd>\{selectedSeedRun\.run_id\}<\/dd>/);
  assert.doesNotMatch(shell, /<dd>\{projectReadiness\.run_id\}<\/dd>/);
  assert.doesNotMatch(shell, /<dd>\{projectReadiness\.project_readiness_snapshot_id\}<\/dd>/);
  assert.doesNotMatch(shell, /<strong>\{status\.code\}<\/strong>/);
  assert.doesNotMatch(shell, /<strong>\{(?:projectOverview|projectReadiness|selectedSeedRun|seedEvents|sourceFiles|seedRuns)\.code\}<\/strong>/);
});

test("Overview empty project exposes dual idea-first and upload entries", async () => {
  const [shell, page] = await Promise.all([
    source("components/overview-seed-shell.tsx"),
    source("app/(app)/[tenantSlug]/projects/[projectId]/overview/page.tsx"),
  ]);

  assert.match(shell, /EmptyProjectDualEntry|data-empty-project-entry/);
  assert.match(shell, /从一个想法开始|Start from an idea/);
  assert.match(shell, /上传已有文本|Upload existing text/);
  assert.match(shell, /bootstrapIdeaAction/);
  assert.match(shell, /从一个想法开始|Start from an idea|创建最小书籍计划|Create a minimal book plan/i);
  assert.doesNotMatch(shell, /必须先上传|must upload before writing/i);
  assert.match(page, /bootstrapIdeaAction/);
  assert.match(page, /createBookPlan/);
  assert.match(page, /createChapter/);
  assert.match(page, /createScene/);
  assert.match(page, /IDEA_BOOTSTRAP_READY|writer\?/);
});

test("Overview gates Seed analysis behind creation readiness without blocking idea-first", async () => {
  const [shell, readiness] = await Promise.all([
    source("components/overview-seed-shell.tsx"),
    source("lib/llm-creation-readiness.ts"),
  ]);

  assert.match(readiness, /evaluateCreationReadiness/);
  assert.match(readiness, /llm_has_quota_policy/);
  assert.match(readiness, /llm_enabled_channel_count/);
  assert.match(readiness, /Complete model & budget setup/);
  assert.match(shell, /evaluateCreationReadiness/);
  assert.match(shell, /overview-readiness-panel/);
  assert.match(shell, /CreationReadinessPanel/);
  assert.match(shell, /PublicErrorNotice/);
  assert.match(shell, /LLM_QUOTA_POLICY_UNAVAILABLE/);
  assert.match(shell, /LLM_MODULE_UNBOUND/);
  assert.match(shell, /llmFacilityProjectHref|llmFacilityHref/);
  assert.match(shell, /idea-first structure bootstrap does not depend|从想法开始的结构创建不依赖/);

  const nextStepStart = shell.indexOf("function OverviewNextStep");
  const preparedFileIndex = shell.indexOf('parse_status === "uploaded"', nextStepStart);
  const seedReadinessGateIndex = shell.indexOf("!creationReadiness.ready", preparedFileIndex);
  assert.ok(preparedFileIndex >= 0, "prepared file branch missing");
  assert.ok(seedReadinessGateIndex > preparedFileIndex, "Seed readiness gate must stay on the upload/analysis path");
  assert.match(shell, /EmptyProjectDualEntry/);
});

test("Asset Library gates vector and hybrid search modes by capabilities", async () => {
  const [shell, page] = await Promise.all([
    source("components/asset-library-shell.tsx"),
    source("app/(app)/[tenantSlug]/projects/[projectId]/assets/page.tsx"),
  ]);

  assert.match(page, /getAssetSearchCapabilities/);
  assert.match(page, /searchCapabilities=\{searchCapabilities\}/);
  assert.match(shell, /searchCapabilities/);
  assert.match(shell, /SearchModeSelect/);
  assert.match(shell, /disabled=\{!vectorEnabled\}/);
  assert.match(shell, /disabled=\{!hybridEnabled\}/);
  assert.match(shell, /Configure search embedding module/);
});
