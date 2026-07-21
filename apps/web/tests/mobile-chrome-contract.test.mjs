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
  // Idle fold hides chrome; immersive alone must not permanently kill the tab dock.
  assert.match(css, /data-mobile-chrome="folded"/);
  assert.doesNotMatch(
    css,
    /\.app-frame\.app-frame-unified\[data-mobile-immersive="true"\]\s*\.mobile-tabbar\s*\{[^}]*visibility:\s*hidden/s,
  );
});

test("mobile scroll chrome folds idle top/tab and re-shows on scroll", async () => {
  const scroll = await fileText("components/mobile-scroll-chrome.tsx");
  const css = await fileText("app/mobile-chrome.css");

  assert.match(scroll, /data-mobile-chrome/);
  assert.match(scroll, /folded|shown/);
  assert.match(scroll, /writer-thread-scroll/);
  assert.match(scroll, /IDLE_FOLD_MS|1500/);
  assert.match(css, /\[data-mobile-chrome="folded"\]\s*\.mobile-topbar/);
  assert.match(css, /\[data-mobile-chrome="folded"\]\s*\.mobile-tabbar/);
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

test("writer mobile defaults to conversation surface (two-pane)", async () => {
  const switchSource = await fileText("components/writer-mobile-switch.tsx");
  const shell = await fileText("components/writer-workbench-shell.tsx");
  const keyboard = await fileText("components/writer-composer-keyboard.tsx");
  const context = await fileText("components/writer-workbench-context.tsx");

  assert.match(switchSource, /conversation/);
  assert.match(switchSource, /artifact/);
  assert.match(switchSource, /touchstart|touchend/);
  assert.match(switchSource, /writer-mobile-switch-badge/);
  assert.match(context, /revealArtifact/);
  assert.match(context, /setMobileView/);
  assert.match(shell, /data-mobile-view="conversation"/);
  assert.match(shell, /WriterComposerKeyboard/);
  assert.match(keyboard, /visualViewport/);
  assert.match(keyboard, /--writer-keyboard-inset/);
});

test("writer mobile hides status header and reclaims writing canvas height", async () => {
  const polish = await fileText("app/workbench-polish.css");
  const chrome = await fileText("app/mobile-chrome.css");
  const shell = await fileText("components/writer-workbench-shell.tsx");
  const agentThreadSource = await fileText("components/writer-agent-thread.tsx");
  const composerInput = await fileText("components/writer-composer-input.tsx");
  const toast = await fileText("components/writer-transient-toast.tsx");
  const mode = await fileText("components/writer-mode-picker.tsx");
  const taskStatus = await fileText("lib/writer-task-status.ts");
  const statusLine = await fileText("components/writer-task-status-line.tsx");

  // Phone must not show the desktop tools rail (命令 / 技术详情).
  assert.match(
    polish,
    /@media \(max-width:\s*640px\)\s*\{[\s\S]*?\.writer-canvas-tools\s*\{[\s\S]*?display:\s*none\s*!important/s,
  );
  assert.match(
    chrome,
    /\[data-mobile-immersive="true"\]\s*\.writer-canvas-tools\s*\{[\s\S]*?display:\s*none\s*!important/s,
  );
  // Identity strip + marketing empty state must not steal conversation height.
  assert.match(
    polish,
    /@media \(max-width:\s*640px\)\s*\{[\s\S]*?\.writer-agent-toolbar\s+\.writer-agent-identity\s*\{[\s\S]*?display:\s*none/s,
  );
  assert.match(
    polish,
    /@media \(max-width:\s*640px\)\s*\{[\s\S]*?\.writer-agent-empty\s*\{[\s\S]*?display:\s*none\s*!important/s,
  );
  assert.match(
    chrome,
    /\[data-mobile-immersive="true"\]\s*\.writer-agent-empty\s*\{[\s\S]*?display:\s*none\s*!important/s,
  );
  // Fill remaining viewport via flex — no short fixed-height calc that left a blank band.
  assert.match(
    chrome,
    /\[data-mobile-immersive="true"\]\s*\.writer-root\s*\{[\s\S]*?flex:\s*1\s+1\s+auto/s,
  );
  assert.match(
    chrome,
    /\[data-mobile-immersive="true"\]\s*\.writer-agent-layout[\s\S]*?height:\s*auto\s*!important/s,
  );
  assert.doesNotMatch(
    chrome,
    /\[data-mobile-immersive="true"\]\s*\.writer-agent-layout[\s\S]*?-\s*132px/s,
  );

  // Folded immersive must reclaim topbar + tabbar padding so content pins under safe area.
  assert.match(
    chrome,
    /\[data-mobile-immersive="true"\]\[data-mobile-chrome="folded"\]\s*\.app-main\s*\{[\s\S]*?padding-top:\s*calc\(6px\s*\+\s*var\(--mobile-safe-top\)\)/s,
  );
  assert.match(
    chrome,
    /\[data-mobile-immersive="true"\]\[data-mobile-chrome="folded"\]\s*\{[\s\S]*?--mobile-main-pad-bottom:\s*calc\(12px\s*\+\s*var\(--mobile-safe-bottom\)\)/s,
  );

  // Admission feedback is a light toast, not a permanent form-status strip.
  // Soft history clean only — no second Next.js navigation flash.
  assert.match(agentThreadSource, /WriterTransientToast/);
  assert.match(toast, /HOLD_MS|3200/);
  assert.match(toast, /history\.replaceState/);
  assert.doesNotMatch(toast, /import \{[^}]*useRouter/);
  assert.match(toast, /writerRunStatus/);
  assert.doesNotMatch(agentThreadSource, /writer-composer-dock[\s\S]*StatusLine status=\{writerRunStatus\}/s);

  // Mode is a compact chip inside the input row (not a full-width 4-tab bar).
  assert.match(agentThreadSource, /WriterAgentComposer|WriterComposerInput/);
  assert.match(composerInput, /WriterModePicker/);
  assert.match(mode, /writer-mode-chip/);
  assert.match(mode, /draft.*continue.*outline.*revise/s);
  // Div menu avoids UA list markers bloating the composer (no ul/li bullets).
  assert.match(mode, /className="writer-mode-menu"/);
  assert.doesNotMatch(mode, /<ul[\s\S]*writer-mode-menu/);
  assert.match(polish, /\.writer-mode-chip/);
  assert.match(polish, /\.writer-mode-menu\s*\{[\s\S]*position:\s*absolute\s*!important/s);
  assert.match(polish, /Div menu \(not ul\)/);

  // Compact single-row composer + gray send that fades in when text is present.
  assert.match(composerInput, /rows=\{1\}/);
  assert.match(composerInput, /写一段要发生什么/);
  assert.match(composerInput, /data-can-send/);
  assert.match(composerInput, /disabled=\{!canSend \|\| blocked\}|disabled=\{!canSend \|\| forcePending\}|disabled=\{!canSend\}/);
  assert.match(composerInput, /sendLocked/);
  assert.match(composerInput, /writer-composer-lock-hint|lockHint/);
  assert.match(polish, /\.writer-send-button\s*\{[\s\S]*?opacity:\s*0\.28/s);
  assert.match(
    polish,
    /\[data-can-send="true"\]\s*\.writer-send-button|writer-send-button\[data-can-send="true"\]/,
  );
  assert.match(polish, /opacity:\s*1/);
  assert.doesNotMatch(composerInput, /rows=\{3\}/);

  // Run lifecycle is summarized by the live task status line (retired activity timeline).
  assert.match(taskStatus, /summarizeWriterTaskStatus/);
  assert.match(statusLine, /writer-task-status/);
  assert.match(taskStatus, /failed|completed|error_code|message/);
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

test("character console workbench aligns flush under command bar without hero header", async () => {
  const globals = await fileText("app/globals.css");
  const polish = await fileText("app/workbench-polish.css");
  const shell = await fileText("components/character-console-shell.tsx");

  // Headerless: content card is the page frame, flush to the top chrome.
  assert.doesNotMatch(shell, /WorkspaceHeader|character-console-header|与角色互动|次互动|次推演/);
  assert.match(
    globals,
    /\.app-frame:has\(\.character-console-root\)\s+\.app-main\s*\{[\s\S]*?max-width:\s*none/s,
  );
  assert.match(
    globals,
    /@media \(min-width:\s*861px\)\s*\{[\s\S]*?\.app-frame:has\(\.character-console-root\)\s+\.app-main\s*\{[\s\S]*?max-width:\s*none/s,
  );
  assert.match(
    globals,
    /\.character-console-workbench\s*\{[\s\S]*?border-top:\s*0/s,
  );
  assert.match(
    globals,
    /\.character-console-workbench\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1\.28fr\)\s+minmax\(220px,\s*0\.78fr\)/s,
  );
  assert.match(
    polish,
    /\.character-console-workbench\s*\{[\s\S]*?grid-template-columns:\s*minmax\(0,\s*1\.2fr\)\s+minmax\(200px,\s*0\.72fr\)/s,
  );
  assert.match(
    polish,
    /\.app-frame\.app-frame-unified:has\(\.character-console-root\)\s+\.character-console-workbench\s*\{[\s\S]*?border-top:\s*0/s,
  );
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

test("phone density: compact materials headers, short artifact tabs, no aside clamp", async () => {
  const chrome = await fileText("app/mobile-chrome.css");
  const polish = await fileText("app/workbench-polish.css");

  // Hub bottom reserve is tight (+14), not a loose +28 band.
  assert.match(
    chrome,
    /--mobile-main-pad-bottom:\s*calc\(var\(--mobile-tabbar-height\)\s*\+\s*var\(--mobile-safe-bottom\)\s*\+\s*14px\)/,
  );

  // Materials deep pages shrink WorkspaceHeader under the mobile topbar.
  assert.match(
    chrome,
    /\.asset-library-header,\s*\n\s*\.story-graph-header,\s*\n\s*\.worldline-header[\s\S]*?min-height:\s*0\s*!important/s,
  );

  // Graph/worldline mode switcher becomes a short segmented bar on phone.
  assert.match(
    chrome,
    /\.story-graph-root\s+\.workspace-mode-switcher[\s\S]*?--mode-facet-h:\s*36px/s,
  );

  // Expanded seed wall must not keep a preview retry control.
  assert.match(
    chrome,
    /\.overview-status-stage\[data-expanded="true"\]\s+\.overview-status-wall-preview-action\s*\{[\s\S]*?display:\s*none/s,
  );

  // Asset ops must not clamp to 52dvh on phone (avoids dual-scroll sandwich).
  assert.match(
    chrome,
    /\.asset-library-root \.asset-search-ops[\s\S]*?max-height:\s*none\s*!important/s,
  );

  // Writer bottom handlebar stays reachable on phone; retired artifact tabs stay gone.
  assert.match(await fileText("app/writer-redesign.css"), /\.writer-handlebar/);
  assert.doesNotMatch(polish, /\.writer-artifact-tab\b/);

  // Writer home fills flex parent instead of a second 100dvh calc.
  assert.match(
    polish,
    /\.writer-root\[data-home="true"\]\s*\{[\s\S]*?flex:\s*1\s+1\s+auto/s,
  );
  assert.doesNotMatch(
    polish,
    /\.writer-root\[data-home="true"\]\s*\{[^}]*100dvh/,
  );

  // Character console: desktop-only !important pad; phone inherits mobile-chrome.
  assert.match(
    polish,
    /@media \(min-width:\s*861px\)\s*\{[\s\S]*?\.app-frame\.app-frame-unified:has\(\.character-console-root\)\s+\.app-main\s*\{[\s\S]*?padding:\s*0\s+0\s+28px\s*!important/s,
  );
  assert.match(
    polish,
    /\.app-frame\.app-frame-unified:has\(\.character-console-root\)\s+\.app-main\s*\{\s*width:\s*100%;\s*max-width:\s*none;\s*margin:\s*0;\s*padding:\s*0\s+0\s+28px;\s*\}/s,
  );

  // Character + graph inspectors must not clamp to 52dvh on phone.
  assert.match(
    chrome,
    /\.character-console-root\s+\.inspector-panel\s*\{[\s\S]*?max-height:\s*none/s,
  );
});
