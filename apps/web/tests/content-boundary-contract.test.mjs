import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");

/** All author-facing creative shells after full UX optimization waves. */
const AUTHOR_SHELLS = [
  "components/overview-seed-shell.tsx",
  "components/asset-library-shell.tsx",
  "components/asset-detail-shell.tsx",
  "components/story-graph-shell.tsx",
  "components/worldline-shell.tsx",
  "components/character-console-shell.tsx",
  "components/writer-workbench-shell.tsx",
  "components/writer-product-workspace.tsx",
  "components/llm-facility-shell.tsx",
  "components/project-nav.tsx",
  "components/public-error-notice.tsx",
  "components/workspace-header.tsx",
  "components/compact-filter-bar.tsx",
  "components/inspector-panel.tsx",
  "components/workflow-progress.tsx",
  "components/submit-button.tsx",
  "components/confirm-dialog.tsx",
  "components/confirm-submit-button.tsx",
  "components/technical-details-drawer.tsx",
  "components/workspace-mode-switcher.tsx",
  "app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx",
  "app/(app)/[tenantSlug]/projects/[projectId]/overview/page.tsx",
  "app/(app)/[tenantSlug]/projects/[projectId]/assets/page.tsx",
];

const FORBIDDEN_AUTHOR_COPY = [
  /docs\/refactor-saas/i,
  /\bAGENTS\.md\b/,
  /\bCLAUDE\.md\b/,
  /\bDEVELOPMENT_PLAN\.md\b/,
  /24-current-development-progress/i,
  /system[_\s-]?prompt/i,
  /provider[_\s-]?body/i,
  /request[_\s-]?body/i,
  /response[_\s-]?body/i,
  /encrypted[_\s-]?api/i,
  /ranking\.(?:final_score|keyword_score|vector_score|embedding_model)/i,
  /formatScore|searchRanking|raw relevance/i,
];

const FORBIDDEN_VISIBLE_ID_DUMPS = [
  /<dd>\{\s*[a-zA-Z0-9_.]*(?:run_id|request_id|project_readiness_snapshot_id)\s*\}<\/dd>/,
  /<span className="form-hint">\{\s*[a-zA-Z0-9_.]*asset_id\s*\}<\/span>/,
  /<strong>\{\s*(?:status|error)\.code\s*\}<\/strong>/,
];

async function source(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

test("content boundary helper defines author-surface deny lists", async () => {
  const helper = await source("lib/content-boundary.ts");
  assert.match(helper, /AUTHOR_FORBIDDEN_PATH_MARKERS/);
  assert.match(helper, /AUTHOR_FORBIDDEN_TECHNICAL_MARKERS/);
  assert.match(helper, /AUTHOR_FORBIDDEN_WRITER_SURFACE_PATTERNS/);
  assert.match(helper, /scanAuthorSurfaceText/);
  assert.match(helper, /assertAuthorSurfaceClean/);
  assert.match(helper, /docs\/refactor-saas/);
  assert.match(helper, /system_prompt/);
  assert.match(helper, /provider_body/);
  assert.match(helper, /placeholder=\["']chapter_id\["']/);
  assert.match(helper, /option\\s\+value=\["']complete_outline\["']/);
  assert.match(helper, /name=\["']orderedIds\["']/);
});

test("public error mapping keeps recovery copy free of internal codes", async () => {
  const errors = await source("lib/public-errors.ts");
  assert.match(errors, /mapPublicError/);
  assert.match(errors, /sanitizeAuthorErrorMessage/);
  assert.match(errors, /recoveryHint/);
  assert.doesNotMatch(errors, /INTERNAL_SERVER_ERROR|provider body|system prompt/i);
});

const FORBIDDEN_WRITER_SURFACE = [
  /placeholder=["']chapter_id["']/,
  /placeholder=["']scene_id["']/,
  /placeholder=["']block_id["']/,
  /option\s+value=["']complete_outline["']/,
  /option\s+value=["']scan_lexicon["']/,
  /<input[^>]*name=["']orderedIds["'][^>]*defaultValue=\{[^}]*\.join\(["'],["']\)/,
  /<a[^>]*href=\{`\$\{[^}]+\}\?commandId=/,
  /<a[^>]*href=\{`\$\{[^}]+\}\?planningRunId=/,
  /<strong>\{[^}]*\.command_type\}<\/strong>/,
  /<strong>\{[^}]*\.workflow_type\}<\/strong>/,
];

test("author creative shells stay within content boundary", async () => {
  for (const relativePath of AUTHOR_SHELLS) {
    const text = await source(relativePath);
    for (const pattern of FORBIDDEN_AUTHOR_COPY) {
      assert.doesNotMatch(text, pattern, `${relativePath} contains forbidden author copy: ${pattern}`);
    }
    for (const pattern of FORBIDDEN_VISIBLE_ID_DUMPS) {
      assert.doesNotMatch(text, pattern, `${relativePath} dumps technical ids into author UI: ${pattern}`);
    }
    if (relativePath === "components/writer-product-workspace.tsx") {
      for (const pattern of FORBIDDEN_WRITER_SURFACE) {
        assert.doesNotMatch(text, pattern, `${relativePath} exposes internal writer workspace markers: ${pattern}`);
      }
      assert.match(text, /MANUSCRIPT_COMMAND_CHOICES/);
      assert.match(text, /commandChoice/);
      assert.match(text, /刷新进度|Refresh progress/);
    }
  }
});

test("author shells do not render raw error codes as primary copy", async () => {
  const shells = await Promise.all(
    AUTHOR_SHELLS.filter((entry) => entry.startsWith("components/")).map(async (relativePath) => ({
      relativePath,
      text: await source(relativePath),
    })),
  );

  for (const { relativePath, text } of shells) {
    assert.doesNotMatch(
      text,
      /<strong>\{\s*[a-zA-Z0-9_.]+\.code\s*\}<\/strong>/,
      `${relativePath} renders internal error codes as primary copy`,
    );
    assert.doesNotMatch(
      text,
      /<dd>\{\s*[a-zA-Z0-9_.]*\.run_id\s*\}<\/dd>/,
      `${relativePath} exposes run ids in definition lists`,
    );
  }
});

test("shared foundation components exist for progressive disclosure", async () => {
  const required = [
    "components/workspace-header.tsx",
    "components/compact-filter-bar.tsx",
    "components/inspector-panel.tsx",
    "components/workflow-progress.tsx",
    "components/public-error-notice.tsx",
    "components/submit-button.tsx",
    "components/confirm-dialog.tsx",
    "components/technical-details-drawer.tsx",
  ];

  for (const relativePath of required) {
    const text = await source(relativePath);
    assert.ok(text.length > 0, `${relativePath} must exist`);
  }
});

test("content-boundary scans exclude development docs from default author projections", async () => {
  const appEntries = await readdir(path.join(root, "app"), { withFileTypes: true });
  assert.ok(appEntries.length > 0);
  const layout = await source("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");
  assert.doesNotMatch(layout, /docs\/refactor-saas|DEVELOPMENT_PLAN|AGENTS\.md/);
});
