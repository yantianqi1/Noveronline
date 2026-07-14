import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";

const root = path.resolve(import.meta.dirname, "..");

async function fileText(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

test("mobile chrome stylesheet and root import are present", async () => {
  const css = await fileText("app/mobile-chrome.css");
  const layoutRoot = await fileText("app/layout.tsx");

  assert.match(layoutRoot, /mobile-chrome\.css/);
  assert.match(layoutRoot, /viewportFit:\s*"cover"/);
  assert.match(css, /--mobile-tabbar-height/);
  assert.match(css, /--mobile-safe-bottom/);
  assert.match(css, /\.mobile-tabbar/);
  assert.match(css, /\.mobile-topbar/);
  assert.match(css, /\.mobile-paper-stack/);
  assert.match(css, /data-mobile-scroll="elevated"/);
  assert.match(css, /mobile-layer-rise/);
  assert.match(css, /@media \(max-width:\s*860px\)/);
  assert.match(css, /data-mobile-immersive="true"/);
  assert.match(css, /prefers-reduced-motion:\s*reduce/);
  // Writer must keep the global bottom tab dock visible (no hide-on-immersive).
  assert.doesNotMatch(
    css,
    /\.app-frame\.app-frame-unified\[data-mobile-immersive="true"\]\s*\.mobile-tabbar\s*\{[^}]*visibility:\s*hidden/s,
  );
});

test("project layout mounts mobile top bar and tab bar alongside desktop nav", async () => {
  const layout = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");

  assert.match(layout, /MobileTopBar/);
  assert.match(layout, /MobileTabBar/);
  assert.match(layout, /MobileScrollChrome/);
  assert.match(layout, /ProjectNav/);
  assert.match(layout, /app-frame app-frame-unified/);
  assert.match(layout, /id="workspace-main"/);
});

test("mobile tab bar uses hybrid IA 总览/资料/创作/我的", async () => {
  const tabBar = await fileText("components/mobile-tab-bar.tsx");

  assert.match(tabBar, /总览/);
  assert.match(tabBar, /资料/);
  assert.match(tabBar, /创作/);
  assert.match(tabBar, /我的/);
  assert.match(tabBar, /path:\s*"\/overview"/);
  assert.match(tabBar, /path:\s*"\/materials"/);
  assert.match(tabBar, /path:\s*"\/writer"/);
  assert.match(tabBar, /path:\s*"\/me"/);
  assert.match(tabBar, /matchPaths:.*"\/assets"/s);
  assert.match(tabBar, /matchPaths:.*"\/graph"/s);
  assert.match(tabBar, /matchPaths:.*"\/worldline"/s);
  assert.match(tabBar, /matchPaths:.*"\/character-console"/s);
});

test("materials and me hub routes exist", async () => {
  const materialsPage = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/materials/page.tsx");
  const mePage = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/me/page.tsx");
  const materialsHub = await fileText("components/materials-hub.tsx");
  const meHub = await fileText("components/me-hub.tsx");

  assert.match(materialsPage, /MaterialsHub/);
  assert.match(mePage, /MeHub/);
  assert.match(materialsHub, /资产库/);
  assert.match(materialsHub, /故事图谱/);
  assert.match(materialsHub, /世界线/);
  assert.match(materialsHub, /角色控制台/);
  assert.match(materialsHub, /mobile-paper-stack/);
  assert.match(meHub, /模型设置/);
  assert.match(meHub, /退出登录/);
  assert.match(meHub, /mobile-paper-stack/);
  assert.match(meHub, /mobile-profile-avatar/);
});

test("writer mobile defaults to agent conversation surface", async () => {
  const switchSource = await fileText("components/writer-mobile-switch.tsx");
  const shell = await fileText("components/writer-workbench-shell.tsx");
  const keyboard = await fileText("components/writer-composer-keyboard.tsx");

  assert.match(switchSource, /return "agent"/);
  assert.match(switchSource, /useState<WriterMobileView>\("agent"\)/);
  assert.match(shell, /data-mobile-view="agent"/);
  assert.match(shell, /WriterComposerKeyboard/);
  assert.match(keyboard, /visualViewport/);
  assert.match(keyboard, /--writer-keyboard-inset/);
});

test("workspace route aliases include materials and me", async () => {
  const route = await fileText("lib/workspace-route.ts");
  assert.match(route, /materials:\s*"materials"/);
  assert.match(route, /me:\s*"me"/);
});

test("quota reservation failures stay humanized for authors", async () => {
  const copy = await fileText("lib/user-facing-copy.ts");
  assert.match(copy, /LLM_QUOTA_RESERVATION_UNAVAILABLE/);
  assert.match(copy, /模型额度暂时不可用/);
  assert.match(copy, /WORLDLINE_SESSION_NOT_SELECTED/);
});

test("overview mid-band keeps dual-column structure under desktop chrome", async () => {
  const polish = await fileText("app/workbench-polish.css");
  const globals = await fileText("app/globals.css");

  // Phone stack only at ≤860; do not force single-column for all <1280.
  assert.doesNotMatch(
    polish,
    /@media \(max-width:\s*1279px\)\s*\{[^}]*overview-root[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s*!important/s,
  );
  assert.match(
    polish,
    /@media \(min-width:\s*861px\)\s*\{[\s\S]*?overview-root[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1\.2fr\)\s+minmax\(240px,\s*0\.8fr\)/s,
  );
  assert.match(
    polish,
    /@media \(max-width:\s*1199px\)\s+and\s+\(min-width:\s*861px\)\s*\{[\s\S]*?overview-root[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1\.35fr\)\s+minmax\(220px,\s*0\.72fr\)/s,
  );
  assert.match(
    polish,
    /@media \(max-width:\s*860px\)\s*\{[\s\S]*?overview-root[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)\s*!important/s,
  );

  // globals route skin must not reintroduce mid-band single-column waterfall.
  assert.match(
    globals,
    /@media \(max-width:\s*1199px\)\s+and\s+\(min-width:\s*861px\)\s*\{[\s\S]*?\.overview-root\s+\.workbench-grid\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1\.35fr\)\s+minmax\(220px,\s*0\.72fr\)/s,
  );
  assert.doesNotMatch(
    globals,
    /@media \(max-width:\s*1279px\)\s+and\s+\(min-width:\s*861px\)\s*\{[\s\S]*?\.overview-root\s+\.workbench-grid\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)\s*;/s,
  );
});

test("workbench mid-band rails collapse near 960 not 980-1100 scatter", async () => {
  const polish = await fileText("app/workbench-polish.css");
  const globals = await fileText("app/globals.css");

  assert.match(polish, /@media \(max-width:\s*960px\)\s+and\s+\(min-width:\s*861px\)/);
  assert.match(globals, /@media \(max-width:\s*960px\)\s*\{[\s\S]*?\.worldline-workbench/s);
  assert.match(globals, /@media \(max-width:\s*960px\)\s*\{[\s\S]*?\.character-console-workbench/s);
  assert.match(globals, /@media \(max-width:\s*960px\)\s*\{[\s\S]*?llm-facility-workbench/s);
});

test("materials and me hubs use 2x2 grid on tablet widths", async () => {
  const polish = await fileText("app/workbench-polish.css");
  assert.match(
    polish,
    /@media \(min-width:\s*861px\)\s*\{[\s\S]*?\.mobile-hub\s+\.mobile-paper-stack\s*\{[\s\S]*?grid-template-columns:\s*repeat\(2,\s*minmax\(0,\s*1fr\)\)/s,
  );
  assert.match(
    polish,
    /@media \(max-width:\s*860px\)\s*\{[\s\S]*?\.mobile-hub\s+\.mobile-paper-stack\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1fr\)/s,
  );
});
