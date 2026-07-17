import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

const root = path.resolve(import.meta.dirname, "..");

async function source(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

test("design tokens keep the retired blue admin palette out of the active app", async () => {
  const css = await source("app/globals.css");

  assert.match(css, /--surface-app:\s*#f3eee4/);
  assert.match(css, /--surface-panel:\s*#f7f2e9/);
  assert.match(css, /--ink:\s*#171a1b/);
  assert.match(css, /--accent-primary:\s*#8f211b/);
  assert.match(css, /--accent-gold:\s*#a9854f/);
  assert.match(css, /--primary:\s*var\(--accent-primary\)/);
  assert.match(css, /--focus:\s*var\(--accent-primary\)/);
  assert.match(css, /--font-serif:/);
  assert.match(css, /Songti SC/);
  assert.doesNotMatch(css, /--primary:\s*#0f6cbd/);
  assert.doesNotMatch(css, /--focus:\s*#0f6cbd/);
});

test("global app shell uses paper navigation and compact context bar", async () => {
  const css = await source("app/globals.css");
  const layout = await source("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");

  assert.match(css, /\.app-frame\s*\{[^}]*grid-template-columns:\s*minmax\(232px,\s*248px\)/s);
  assert.match(css, /\.workspace-header\s*\{/);
  assert.match(css, /\.compact-filter-bar\s*\{/);
  assert.match(css, /\.inspector-panel\s*\{/);
  assert.match(css, /\.workflow-progress\s*\{/);
  assert.match(css, /\.submit-button\s*\{/);
  assert.match(css, /\.confirm-dialog\s*\{/);
  assert.match(css, /\.overflow-menu\s*\{/);
  assert.match(css, /\.public-error-notice\s*\{/);
  assert.match(css, /@media\s*\(max-width:\s*860px\)/);
  assert.match(css, /min-height:\s*44px/);

  assert.match(layout, /WorkspaceContextBar|app-command-bar project-context-bar/);
  assert.match(layout, /id="workspace-main"/);
  assert.match(layout, /className="skip-link"/);
});

test("Assets put counts in command bar; Overview uses foundation metrics bar", async () => {
  const assets = await source("components/asset-library-shell.tsx");
  const contextBar = await source("components/workspace-context-bar.tsx");
  const overview = await source("components/overview-seed-shell.tsx");

  assert.doesNotMatch(assets, /WorkspaceHeader/);
  assert.doesNotMatch(assets, /from "\.\/workspace-header"/);
  assert.doesNotMatch(assets, /asset-browse-heading|浏览与检索创作资料|WorkspaceHeader/);
  assert.match(assets, /WorkspaceCommandMeta/);
  assert.match(assets, /asset-command-stats|项资产|Showing/);
  assert.match(contextBar, /data-workspace-command-meta/);
  assert.match(overview, /overview-foundation-bar/);
  assert.match(overview, /data-layout="foundation-bar"/);
  assert.doesNotMatch(overview, /WorkspaceHeader/);
  assert.doesNotMatch(overview, /from "\.\/workspace-header"/);
});

test("SubmitButton disables while pending and exposes busy state", async () => {
  const button = await source("components/submit-button.tsx");
  assert.match(button, /useFormStatus/);
  assert.match(button, /aria-busy=\{busy\}/);
  assert.match(button, /disabled=\{disabled \|\| busy\}/);
  assert.match(button, /data-tone/);
});

test("ConfirmDialog restores focus and uses modal semantics", async () => {
  const dialog = await source("components/confirm-dialog.tsx");
  assert.match(dialog, /showModal\(/);
  assert.match(dialog, /previousFocusRef/);
  assert.match(dialog, /aria-labelledby/);
  assert.match(dialog, /aria-describedby/);
});
