import assert from "node:assert/strict";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";
import {
  addLiveSeedSessionCookie,
  assertDisposableLiveSeedConfig,
  assertLocalHttpUrl,
  assertNoForbiddenPublicMarkers,
  BROWSER_LIVE_SEED_PREFIX,
  LIVE_SEED_PREFIX,
  loadLiveSeedConfig,
  overviewUrl,
  publicFailure,
  redactSensitiveText,
  waitForSeedWorkerStageEvents,
} from "./live-seed-harness.mjs";

const root = path.resolve(import.meta.dirname, "..");

async function fileText(relativePath) {
  return readFile(path.join(root, relativePath), "utf8");
}

async function sourceFiles(relativeDirectory) {
  const directory = path.join(root, relativeDirectory);
  const entries = await readdir(directory, { withFileTypes: true });
  const nestedFiles = await Promise.all(
    entries.map(async (entry) => {
      const relativePath = path.join(relativeDirectory, entry.name);
      if (entry.isDirectory()) {
        return sourceFiles(relativePath);
      }
      if (!entry.isFile() || !entry.name.endsWith(".tsx")) {
        return [];
      }
      return [{ relativePath, source: await fileText(relativePath) }];
    }),
  );
  return nestedFiles.flat();
}

function sourceSlice(source, startMarker, endMarker) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start);
  assert.notEqual(start, -1, `missing source slice start marker: ${startMarker}`);
  assert.notEqual(end, -1, `missing source slice end marker: ${endMarker}`);
  return source.slice(start, end);
}

test("Next app shell declares tenant/project writer route", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /getWriterRunSummary/);
  assert.match(page, /WriterWorkbenchShell/);
});

test("writer API client exposes metadata-only manuscript endpoints with tenant headers", async () => {
  const client = await fileText("lib/api.ts");
  const manuscriptClient = [
    sourceSlice(client, "export type ManuscriptBlockMetadata", "export type WorkflowRunSummary"),
    sourceSlice(client, "export async function getProjectManuscript", "export async function downloadProjectManuscriptArtifact"),
    sourceSlice(client, "async function decodeProjectManuscriptResponse", "async function decodeWorkflowRunResponse"),
    sourceSlice(client, "function decodeManuscriptBlockMetadata", "function decodeWorkflowRunEvent"),
  ].join("\n");

  assert.match(manuscriptClient, /ManuscriptBlockMetadata/);
  assert.match(manuscriptClient, /ProjectManuscriptSummary/);
  assert.match(manuscriptClient, /ManuscriptExportManifestBlock/);
  assert.match(manuscriptClient, /ProjectManuscriptExportManifestSummary/);
  assert.match(manuscriptClient, /getProjectManuscript/);
  assert.match(manuscriptClient, /getProjectManuscriptExportManifest/);
  assert.match(manuscriptClient, /\/v1\/projects\/\$\{input\.projectId\}\/manuscript`/);
  assert.match(manuscriptClient, /\/v1\/projects\/\$\{input\.projectId\}\/manuscript\/export`/);
  assert.match(manuscriptClient, /headers:\s*contextHeaders\(input\)/);
  assert.equal((manuscriptClient.match(/headers:\s*contextHeaders\(input\)/g) ?? []).length, 2);
  assert.match(manuscriptClient, /block_id/);
  assert.match(manuscriptClient, /chapter_id/);
  assert.match(manuscriptClient, /source_draft_id/);
  assert.match(manuscriptClient, /block_order/);
  assert.match(manuscriptClient, /word_count/);
  assert.match(manuscriptClient, /generated_at/);
  assert.doesNotMatch(manuscriptClient, /block_ids/);
  assert.doesNotMatch(manuscriptClient, /content_text:\s*string/);
  assert.doesNotMatch(manuscriptClient, /draft_text:\s*string/);
  assert.doesNotMatch(manuscriptClient, /manuscript_text:\s*string/);
  assert.doesNotMatch(manuscriptClient, /raw_body:\s*string/);
  assert.doesNotMatch(manuscriptClient, /exported_at:\s*string/);
  assert.doesNotMatch(manuscriptClient, /credential_ref:\s*string/);
  assert.doesNotMatch(manuscriptClient, /encrypted_api_key:\s*string/);
  assert.doesNotMatch(manuscriptClient, /api_key:\s*string/);
});

test("writer page loads manuscript summaries alongside picker data", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx");

  assert.match(page, /getProjectManuscript/);
  assert.match(page, /getProjectManuscriptExportManifest/);
  assert.match(page, /listWriterThreads/);
  assert.match(page, /listWriterThreadMessages/);
  assert.match(
    page,
    /const\s*\[\s*assets,\s*graphView,\s*worldlineSavedPaths,\s*manuscript,\s*manuscriptExportManifest,\s*writerThreads\s*\]\s*=\s*await\s+Promise\.all/,
  );
  assert.match(page, /planningRun,\s*proposals,\s*distillationSettings\s*\]\s*=\s*await\s+Promise\.all/);
  assert.match(page, /<Suspense\s+fallback=\{<WriterProductWorkspaceLoading\s*\/>\}>/);
  assert.match(page, /getProjectManuscript\(\{\s*\.\.\.apiContext,\s*projectId,\s*\}\)/s);
  assert.match(page, /getProjectManuscriptExportManifest\(\{\s*\.\.\.apiContext,\s*projectId,\s*\}\)/s);
  assert.match(page, /manuscript=\{manuscript\}/);
  assert.match(page, /manuscriptExportManifest=\{manuscriptExportManifest\}/);
  assert.match(page, /threadMessages=\{threadMessages\}/);
});

test("Writer shell renders metadata-only manuscript and export panels", async () => {
  const shell = await fileText("components/writer-workbench-shell.tsx");

  assert.match(shell, /ProjectManuscriptSummary/);
  assert.match(shell, /ProjectManuscriptExportManifestSummary/);
  assert.match(shell, /manuscript\.ok/);
  assert.match(shell, /manuscriptExportManifest\.ok/);
  assert.match(shell, /Manuscript metadata/);
  assert.match(shell, /Export manuscript/);
  assert.match(shell, /MANUSCRIPT_BACKEND_UNCONFIGURED/);
  assert.match(shell, /MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED/);
  assert.match(shell, /block\.block_id/);
  assert.match(shell, /data-chapter-id=\{block\.chapter_id/);
  assert.match(shell, /data-source-draft-id=\{block\.source_draft_id/);
  assert.match(shell, /block\.word_count/);
  assert.match(shell, /manifestBlock\.block_id/);
  assert.match(shell, /manifestBlock\.word_count/);
  assert.match(shell, /generated_at/);
  assert.doesNotMatch(shell, /block_ids/);
  assert.doesNotMatch(shell, /content_text/);
  assert.doesNotMatch(shell, /draft_text/);
  assert.doesNotMatch(shell, /manuscript_text/);
  assert.doesNotMatch(shell, /raw_body/);
  assert.doesNotMatch(shell, /exported_at/);
  assert.doesNotMatch(shell, /credential_ref|encrypted_api_key|api_key/i);
  assert.doesNotMatch(shell, /PDF|DOCX|TXT/);
});

test("project navigation includes writer and LLM Facility routes with active path state", async () => {
  const layout = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");
  const nav = await fileText("components/project-nav.tsx");
  const workspaceRoute = await fileText("lib/workspace-route.ts");
  const transition = await fileText("components/workspace-route-transition.tsx");
  const css = await fileText("app/globals.css");

  assert.match(layout, /ProjectNav/);
  assert.match(nav, /usePathname/);
  assert.match(nav, /useRouter/);
  assert.match(nav, /useTransition/);
  assert.match(nav, /router\.prefetch\(href\)/);
  assert.match(nav, /\/overview/);
  assert.match(nav, /\/writer/);
  assert.match(nav, /\/llm-facility/);
  assert.match(nav, /Overview/);
  assert.match(nav, /Model settings/);
  assert.match(nav, /aria-current/);
  assert.doesNotMatch(nav, /navigationBasePath/);
  assert.match(nav, /const activeTenants = currentUser\.ok \? currentUser\.active_tenants : \[\]/);
  assert.match(nav, /const href = workspacePathForProject\(activeTenants, currentProject, item\.path\)/);
  assert.match(nav, /matchesWorkspaceNavigationPath/);
  assert.match(nav, /matchesWorkspaceNavigationPath\(\s*pathname,\s*workspacePathForProject\(activeTenants, currentProject, item\.path\),\s*item\.path,\s*\)/s);
  assert.match(workspaceRoute, /export function matchesWorkspaceNavigationPath/);
  assert.match(workspaceRoute, /pathname\.startsWith\(`\$\{href\}\/`\)/);
  assert.match(nav, /const activeHref = optimisticHref \?\? pathname/);
  assert.match(nav, /const active = matchesWorkspaceNavigationPath\(activeHref, href, item\.path\)/);
  assert.match(nav, /data-active=\{active \? "true" : undefined\}/);
  assert.match(nav, /onNavigate=\{navigateWorkspace\}/);
  assert.match(nav, /onNavigate=\{\(event\) => onNavigate\(event, href\)\}/);
  assert.match(nav, /onFocus=\{prefetchRoute\}/);
  assert.match(nav, /onFocus=\{\(\) => onFocus\(href\)\}/);
  assert.match(nav, /onMouseEnter=\{\(\) => onFocus\(href\)\}/);
  assert.doesNotMatch(nav, /prefetch=\{false\}/);
  assert.match(nav, /event\.preventDefault\(\)/);
  assert.match(nav, /startNavigationTransition\(\(\) => router\.push\(href\)\)/);
  assert.doesNotMatch(nav, /pendingHref|LoaderCircle|nav-link-spinner|aria-busy/);
  assert.match(layout, /WorkspaceRouteTransition/);
  assert.match(layout, /<WorkspaceRouteTransition>\s*\{children\}\s*<\/WorkspaceRouteTransition>/s);
  assert.match(nav, /signalWorkspaceNavigationStart\(\)/);
  assert.match(transition, /usePathname/);
  assert.match(transition, /WORKSPACE_NAVIGATION_START_EVENT/);
  assert.match(transition, /WORKSPACE_NAVIGATION_COMPLETE_EVENT/);
  assert.match(transition, /window\.addEventListener\(WORKSPACE_NAVIGATION_START_EVENT/);
  assert.match(transition, /window\.addEventListener\(WORKSPACE_NAVIGATION_COMPLETE_EVENT/);
  assert.match(transition, /window\.setTimeout/);
  assert.match(transition, /data-pending=\{pending \? "true" : "false"\}/);
  assert.match(transition, /className="workspace-route-content" key=\{pathname\}/);
  assert.match(css, /\.workspace-route-content\s*\{[^}]*animation:\s*workspace-route-enter var\(--motion-fast\) var\(--ease-natural\)/s);
  assert.match(css, /@keyframes workspace-route-enter\s*\{[\s\S]*opacity:[\s\S]*transform:\s*translateY\(4px\)/);
  assert.match(css, /\.workspace-route-progress\[data-visible="true"\]/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.workspace-route-content[\s\S]*animation:\s*none/s);
  await assert.rejects(
    fileText("app/(app)/[tenantSlug]/projects/[projectId]/loading.tsx"),
    { code: "ENOENT" },
  );
});

test("project chrome is content-sized and keeps route identifiers out of display copy", async () => {
  const css = await fileText("app/globals.css");
  const layout = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");
  const nav = await fileText("components/project-nav.tsx");
  const shells = await Promise.all([
    "components/asset-library-shell.tsx",
    "components/story-graph-shell.tsx",
    "components/llm-facility-shell.tsx",
    "components/writer-workbench-shell.tsx",
  ].map((path) => fileText(path)));

  assert.match(css, /\.app-sidebar\s*\{[^}]*height:\s*fit-content/s);
  assert.match(css, /\.app-sidebar\s*\{[^}]*max-height:\s*100dvh/s);
  assert.match(css, /\.sidebar-stack\s*\{[^}]*min-height:\s*0/s);
  // Narrow viewports stack chrome in one column: sidebar must not pin to 100dvh
  // or the main workbench is pushed below the fold and looks missing.
  const polish = await fileText("app/workbench-polish.css");
  assert.match(
    polish,
    /@media \(min-width:\s*861px\)\s*\{[\s\S]*?\.app-frame\.app-frame-unified \.app-sidebar[\s\S]*?height:\s*100dvh/,
  );
  assert.match(
    polish,
    /@media \(max-width:\s*860px\)\s*\{[\s\S]*?\.app-frame\.app-frame-unified \.app-sidebar[\s\S]*?height:\s*auto/,
  );
  // Collapsed desktop rail must stay icon-only; the old hide-drawer rule was
  // overridden by `.sidebar-drawer { display: flex }` and crushed labels.
  assert.match(
    polish,
    /html\[data-sidebar-collapsed="true"\] \.app-frame\.app-frame-unified \.sidebar-drawer\s*\{[\s\S]*?display:\s*flex\s*!important/,
  );
  assert.match(
    polish,
    /html\[data-sidebar-collapsed="true"\] \.sidebar-drawer > \.sidebar-section \.nav-link-label/,
  );
  assert.match(nav, /className="nav-link-label"/);
  assert.match(nav, /title=\{label\}/);
  assert.match(layout, /const\s+currentProject\s*=\s*currentUser\.ok/);
  assert.match(layout, /currentProject\?\.name/);
  assert.doesNotMatch(layout, /<span>\{tenantSlug\}<\/span>/);
  assert.doesNotMatch(layout, /<strong>\{projectId\}<\/strong>/);
  assert.doesNotMatch(nav, /currentProject\?\.name \|\| projectId/);
  assert.doesNotMatch(nav, /currentTenant\?\.name \|\| tenantSlug/);
  for (const shell of shells) {
    assert.doesNotMatch(shell, /<Bi zh="租户" en="Tenant" \/>\s*<strong>\{tenantSlug\}<\/strong>/);
    assert.doesNotMatch(shell, /<Bi zh="项目" en="Project" \/>\s*<strong>\{projectId\}<\/strong>/);
  }
  assert.doesNotMatch(shells[1], /<Bi zh="节点 ID" en="Node ID" \/>/);
  assert.doesNotMatch(shells[1], /node\.title \|\| node\.node_id/);
});

test("Current user API client can fetch public membership summary with browser session cookie", async () => {
  const client = await fileText("lib/api.ts");
  const currentUserTypes = sourceSlice(client, "export type TenantMembershipSummary", "export type WriterRunSummary");
  const apiFetchHelper = sourceSlice(client, "function apiFetch", "export async function getCurrentUser");
  const currentUserClient = sourceSlice(client, "export async function getCurrentUser", "export async function startWriterRun");
  const currentUserDecoder = sourceSlice(client, "async function decodeCurrentUserResponse", "async function decodeWriterRunResponse");

  assert.match(apiFetchHelper, /hasCookieHeader/);
  assert.match(apiFetchHelper, /return fetch\(input,\s*init\)/);
  assert.match(apiFetchHelper, /nodeHttpFetch/);
  assert.doesNotMatch(apiFetchHelper, /MIROFISH_WEB_TEST_ALLOW_COOKIE_FETCH_MOCK/);
  assert.match(client, /import http from "node:http"/);
  assert.match(client, /import https from "node:https"/);
  assert.match(apiFetchHelper, /url\.protocol === "https:" \? https : http/);
  assert.match(apiFetchHelper, /new Response\(responseStatusHasNoBody\(status\) \? null : Buffer\.concat\(chunks\)/);
  assert.match(apiFetchHelper, /status === 204 \|\| status === 205 \|\| status === 304/);
  assert.doesNotMatch(client, /await fetch\(/);
  assert.match(currentUserTypes, /CurrentUserRecord/);
  assert.match(currentUserTypes, /TenantMembershipSummary/);
  assert.match(currentUserTypes, /ProjectMembershipSummary/);
  assert.match(currentUserTypes, /CurrentUserSummary/);
  assert.match(currentUserTypes, /user_id:\s*string/);
  assert.match(currentUserTypes, /email:\s*string/);
  assert.match(currentUserTypes, /display_name:\s*string/);
  assert.match(currentUserTypes, /avatar_url:\s*string/);
  assert.match(currentUserTypes, /active_tenants:\s*TenantMembershipSummary\[\]/);
  assert.match(currentUserTypes, /active_projects:\s*ProjectMembershipSummary\[\]/);
  assert.match(currentUserTypes, /tenant_id:\s*string/);
  assert.match(currentUserTypes, /project_id:\s*string/);
  assert.match(currentUserTypes, /role:\s*string/);
  assert.match(currentUserTypes, /status:\s*string/);
  assert.match(currentUserTypes, /\|\s*ApiFailure/);

  assert.match(currentUserClient, /\/v1\/me/);
  assert.match(currentUserClient, /actorUserId\?:\s*string/);
  assert.match(currentUserClient, /sessionCookie\?:\s*string/);
  assert.match(currentUserClient, /const response = await apiFetch/);
  assert.match(currentUserClient, /headers:\s*currentUserHeaders\(input\)/);
  assert.match(client, /function currentUserHeaders\(input:\s*\{\s*actorUserId\?:\s*string;\s*sessionCookie\?:\s*string;?\s*\}\)/);
  assert.match(client, /headers\.Cookie\s*=\s*`mirofish_session=\$\{sessionCookie\}`/);
  assert.match(client, /else if\s*\(actorUserId\)\s*\{\s*headers\["X-User-Id"\]\s*=\s*actorUserId;\s*\}/s);
  assert.match(currentUserClient, /decodeCurrentUserResponse/);
  assert.match(currentUserClient, /networkFailure\(error,\s*"CURRENT_USER_QUERY_FAILED"\)/);
  assert.doesNotMatch(currentUserClient, /X-Tenant-Id/);
  assert.doesNotMatch(currentUserClient, /contextHeaders/);

  assert.match(currentUserDecoder, /decodeError\(payload,\s*response\.status,\s*"CURRENT_USER_QUERY_FAILED"\)/);
  assert.match(currentUserDecoder, /recordFromUnknown\(payload\.user\)/);
  assert.match(currentUserDecoder, /requiredArray\(payload,\s*"active_tenants"\)/);
  assert.match(currentUserDecoder, /requiredArray\(payload,\s*"active_projects"\)/);
  assert.match(currentUserDecoder, /activeTenants\s*===\s*null/);
  assert.match(currentUserDecoder, /tenantSummaries\s*===\s*null/);
  assert.match(currentUserDecoder, /projectSummaries\s*===\s*null/);
  assert.match(currentUserDecoder, /decodeTenantMembershipSummaries/);
  assert.match(currentUserDecoder, /decodeProjectMembershipSummaries/);
  assert.match(client, /const tenantName = requiredString\(value,\s*"name"\)/);
  assert.match(client, /const projectName = requiredString\(value,\s*"name"\)/);
  assert.match(client, /!tenantName/);
  assert.match(client, /!projectName/);
  assert.doesNotMatch(currentUserDecoder, /credential_ref|encrypted_api_key|api_key|prompt|provider|raw_body|body|content|draft|manuscript|object_key/i);
});

test("tenant picker project layout loads current user and passes memberships into ProjectNav", async () => {
  const layout = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");
  const requestSession = await fileText("lib/request-session.ts");
  const devAccess = await fileText("lib/dev-access.ts");
  const workspaceRoute = await fileText("lib/workspace-route.ts");
  const middleware = await fileText("middleware.ts");

  assert.match(layout, /getCurrentUser/);
  assert.match(layout, /currentRequestSessionCookie/);
  assert.match(layout, /required:\s*!isDevLoginBypassEnabled\(\)/);
  assert.doesNotMatch(layout, /from\s*"next\/headers"|cookies\(\)|headers\(\)|cookieStore\.get\("mirofish_session"\)/);
  assert.match(requestSession, /workUnitAsyncStorage/);
  assert.match(requestSession, /CURRENT_REQUEST_SESSION_CONTEXT_UNAVAILABLE/);
  assert.match(requestSession, /store\.type !== "request"/);
  assert.match(requestSession, /CURRENT_REQUEST_SESSION_STORE_UNAVAILABLE/);
  assert.match(requestSession, /store\.headers\.get\("cookie"\)/);
  assert.doesNotMatch(requestSession, /from\s*"next\/headers"|cookies\(\)|headers\(\)/);
  assert.match(devAccess, /export function isDevLoginBypassEnabled/);
  assert.match(
    devAccess,
    /if \(flag === "1"[^}]+return true;\s*}\s*return false;/s,
    "development login bypass must require explicit opt-in",
  );
  assert.doesNotMatch(
    devAccess,
    /Enabled outside production by default/,
    "normal local entry must use the real login page",
  );
  assert.match(devAccess, /export function devActorUserId/);
  assert.match(workspaceRoute, /workspacePathForProject/);
  assert.match(workspaceRoute, /projectPublicKey/);
  assert.match(workspaceRoute, /resolveProjectPublicKey/);
  assert.match(workspaceRoute, /workspaceKeyFromIds/);
  assert.match(workspaceRoute, /workspaceIdsFromKey/);
  assert.match(workspaceRoute, /publicWorkspaceSection/);
  assert.match(middleware, /NextResponse\.rewrite/);
  assert.match(middleware, /NextResponse\.redirect/);
  assert.match(middleware, /workspaceIdFromPublicSegment/);
  assert.match(middleware, /workspaceIdsFromKey/);
  assert.match(middleware, /resolveProjectPublicKey/);
  assert.match(middleware, /projectPublicKey/);
  assert.match(middleware, /canonicalLLMFacilitySearch/);
  assert.match(middleware, /llmModulePathSegment/);
  assert.match(middleware, /sessionCookieFromHeader/);
  assert.match(middleware, /decodeURIComponent\(value\)/);
  assert.match(middleware, /route\.kind === "project"/);
  assert.match(middleware, /route\.kind === "workspace-key"/);
  assert.match(middleware, /matcher:\s*\["\/p\/:path\*",\s*"\/w\/:path\*"/);
  assert.match(middleware, /canonical\.pathname = `\/p\/\$\{publicKey\}/);
  assert.match(middleware, /INTERNAL_WORKSPACE_REWRITE_HEADER/);
  assert.match(middleware, /request\.headers\.get\(INTERNAL_WORKSPACE_REWRITE_HEADER\) === "1"/);
  assert.match(middleware, /request:\s*\{\s*headers:\s*internalHeaders\s*\}/);
  assert.match(layout, /devActorUserId\(\)/);
  assert.match(layout, /sessionCookie\s*\|\|\s*actorUserId/);
  assert.doesNotMatch(layout, /getCurrentUserSessions|currentUserSessions/);
  assert.match(layout, /getCurrentUser\(\{\s*actorUserId:\s*sessionCookie\s*\?\s*undefined\s*:\s*actorUserId,\s*sessionCookie,\s*\}\)/s);
  assert.match(layout, /CURRENT_USER_CONTEXT_UNCONFIGURED/);
  assert.doesNotMatch(layout, /\?\?\s*"web-shell"/);
  assert.match(layout, /currentUser=\{currentUser\}/);
  assert.match(layout, /tenantSlug=\{tenantSlug\}/);
  assert.match(layout, /projectId=\{projectId\}/);
});

test("marketing landing is the product homepage and CTAs enter login", async () => {
  const home = await fileText("app/page.tsx");
  const shell = await fileText("components/landing-shell.tsx");
  const bodyHtml = await fileText("lib/landing-body-html.ts");
  const publicMain = await fileText("public/landing/main.js");
  const publicBody = await fileText("public/landing/body.html");
  const landingCss = await fileText("public/landing/styles.css");
  const authCss = await fileText("app/auth-marketing.css");
  const dockerfile = await fileText("../../infra/docker/web.Dockerfile");

  assert.match(home, /LandingShell/);
  assert.doesNotMatch(home, /devEntryRedirectPath/);
  assert.match(shell, /LANDING_BODY_HTML/);
  assert.match(shell, /landing-active/);
  assert.match(shell, /\/landing\/styles\.css/);
  assert.match(shell, /\/landing\/main\.js/);
  assert.match(bodyHtml, /LANDING_BODY_HTML/);
  assert.match(bodyHtml, /href=\\"\/login\\"/);
  assert.match(publicBody, /href="\/login"/);
  assert.match(publicBody, /\/landing\/assets\//);
  assert.match(publicMain, /\/landing\/assets\//);
  assert.match(publicMain, /__MIROFISH_LANDING_BOOTED__/);
  assert.match(
    publicMain,
    /previousBootScreen === bootScreen && bootScreen\?\.isConnected/,
    "landing boot guard must be scoped to the connected DOM instance so remounts can initialize",
  );
  assert.doesNotMatch(
    publicMain,
    /if \(window\.__MIROFISH_LANDING_BOOTED__\) return/,
    "a session-wide boot guard leaves the remounted landing page stuck on its preload screen",
  );
  assert.doesNotMatch(publicMain, /href="#workbench"/);
  assert.match(publicMain, /visualViewport/);
  assert.match(landingCss, /--landing-topbar-h/);
  assert.match(landingCss, /--landing-bottom-chrome-h/);
  assert.match(landingCss, /--landing-rail-h/);
  assert.match(landingCss, /--landing-content-pad-x/);
  assert.match(
    landingCss,
    /@media \(max-width:\s*768px\)[\s\S]*\.scene\s*\{[\s\S]*var\(--landing-topbar-h\)[\s\S]*var\(--landing-bottom-chrome-h\)/s,
    "mobile scenes must pad with reserved chrome so content is not under topbar/rail",
  );
  assert.match(
    landingCss,
    /@media \(max-width:\s*768px\)[\s\S]*\.scene-rail\s*\{[\s\S]*var\(--landing-rail-gap\)[\s\S]*var\(--landing-rail-h\)/s,
  );
  assert.match(
    landingCss,
    /@media \(max-width:\s*768px\)[\s\S]*\.scene-counter\s*\{[\s\S]*var\(--landing-rail-h\)/s,
    "scene counter must share the bottom rail baseline on mobile",
  );
  assert.match(authCss, /auth-shell/);
  assert.match(authCss, /#9b2c2c/);
  assert.match(authCss, /--login-topbar-h/);
  assert.match(
    authCss,
    /@media \(max-width:\s*960px\)[\s\S]*\.login-page \.auth-topbar\s*\{[\s\S]*position:\s*sticky/s,
  );
  assert.match(
    authCss,
    /@media \(max-width:\s*960px\)[\s\S]*\.login-input-wrap input\s*\{[\s\S]*font-size:\s*16px/s,
  );
  assert.match(dockerfile, /COPY --from=build \/app\/public \.\/public/);
});

test("password login page issues browser session server-side without exposing token material", async () => {
  const client = await fileText("lib/api.ts");
  const page = await fileText("app/login/page.tsx");
  const form = await fileText("components/login-form.tsx");
  const home = await fileText("app/page.tsx");
  const loginClient = sourceSlice(client, "export async function loginWithPassword", "export async function revokeCurrentSession");
  const loginAction = sourceSlice(page, "async function loginAction", "return (");

  assert.match(client, /export type PasswordLoginSummary/);
  assert.match(client, /export async function loginWithPassword\(input:\s*\{\s*email:\s*string;\s*password:\s*string;\s*clientProof\?:\s*string;?\s*\}\)/);
  assert.match(loginClient, /\/v1\/auth\/login/);
  assert.match(loginClient, /method:\s*"POST"/);
  assert.match(loginClient, /"Content-Type":\s*"application\/json"/);
  assert.match(loginClient, /"X-Mirofish-Recovery-Client":\s*input\.clientProof\.trim\(\)/);
  assert.match(loginClient, /body:\s*JSON\.stringify\(\{\s*email:\s*input\.email,\s*password:\s*input\.password,\s*\}\)/s);
  assert.match(loginClient, /parseSessionCookieSetCookie\(response\.headers\.get\("set-cookie"\)\)/);
  assert.match(loginClient, /decodeCurrentUserResponse\(response\)/);
  assert.match(loginClient, /session_cookie:\s*sessionCookie/);
  assert.match(loginClient, /networkFailure\(error,\s*"PASSWORD_LOGIN_FAILED"\)/);
  assert.doesNotMatch(loginClient, /X-User-Id|X-Tenant-Id|headers\.Cookie|Cookie:\s*|contextHeaders|actorUserId|csrfToken/);

  assert.match(page, /import\s*\{\s*cookies,\s*headers\s*\}\s*from\s*"next\/headers"/);
  assert.match(page, /import\s*\{\s*createRecoveryClientProof\s*\}\s*from\s*"\.\.\/\.\.\/lib\/auth-recovery-server"/);
  assert.match(page, /import\s*\{\s*redirect\s*\}\s*from\s*"next\/navigation"/);
  assert.match(page, /isDevLoginBypassEnabled\(\)/);
  assert.match(page, /devWorkspacePath\("overview"\)/);
  assert.match(home, /LandingShell/);
  assert.match(home, /长篇小说多智能体创作平台|Long-form fiction/);
  assert.match(page, /loginWithPassword/);
  assert.match(loginAction, /"use server"/);
  assert.match(loginAction, /const\s+email\s*=\s*stringFromFormData\(formData,\s*"email"\)/);
  assert.match(loginAction, /const\s+password\s*=\s*rawStringFromFormData\(formData,\s*"password"\)/);
  assert.match(loginAction, /const\s+clientProof\s*=\s*createRecoveryClientProof\(await\s+headers\(\)\)/);
  assert.match(loginAction, /await\s+loginWithPassword\(\{\s*email,\s*password,\s*clientProof\s*\}\)/s);
  assert.match(loginAction, /const\s+cookieStore\s*=\s*await\s+cookies\(\)/);
  assert.match(loginAction, /cookieStore\.set\("mirofish_session",\s*result\.session_cookie\.value,/);
  assert.match(loginAction, /httpOnly:\s*result\.session_cookie\.http_only/);
  assert.match(loginAction, /sameSite:\s*result\.session_cookie\.same_site/);
  assert.match(loginAction, /const\s+project\s*=\s*result\.active_projects\[0\]/);
  assert.match(loginAction, /cookieStore\.set\("mirofish_session"[\s\S]*const\s+project\s*=\s*result\.active_projects\[0\][\s\S]*if\s*\(!project\)\s*\{\s*redirect\("\/invitations\/accept"\)/);
  assert.match(loginAction, /redirect\(workspacePathForProject\(result\.active_tenants,\s*project,\s*"overview"\)\)/);
  assert.doesNotMatch(loginAction, /console\.|MIROFISH_WEB_DEV_ACTOR_USER_ID|X-User-Id|X-Tenant-Id|getCurrentUser|session_cookie\.value\}/);

  assert.match(page, /<LoginForm action=\{loginAction\} \/>/);
  assert.match(page, /欢迎回来/);
  assert.match(form, /<form action=\{action\}/);
  assert.match(form, /htmlFor="login-email"/);
  assert.match(form, /type="email"/);
  assert.match(form, /htmlFor="login-password"/);
  assert.match(form, /type=\{passwordVisible \? "text" : "password"\}/);
  assert.match(form, /autoComplete="email"/);
  assert.match(form, /autoComplete="current-password"/);
  assert.match(form, /useFormStatus/);
  assert.match(form, /正在登录/);
  assert.match(form, /进入创作工作台/);
  assert.doesNotMatch(page, /<LanguageSwitcher \/>/);
  assert.doesNotMatch(page, /token_hash|credential_ref|encrypted_api_key|api_key|object_key|draft|manuscript|prompt|provider|raw_body|content_text/i);
});

test("live Seed harness loads strict opt-in configs for isolated prefixes", () => {
  assert.deepEqual(loadLiveSeedConfig({ env: {}, prefix: LIVE_SEED_PREFIX }), {
    enabled: false,
    prefix: LIVE_SEED_PREFIX,
  });
  assert.deepEqual(loadLiveSeedConfig({ env: {}, prefix: BROWSER_LIVE_SEED_PREFIX, browser: true }), {
    enabled: false,
    prefix: BROWSER_LIVE_SEED_PREFIX,
  });

  const liveConfig = loadLiveSeedConfig({
    env: {
      MIROFISH_WEB_LIVE_SEED_API_BASE_URL: " http://127.0.0.1:3888 ",
      MIROFISH_WEB_LIVE_SEED_TENANT_ID: "tenant-live",
      MIROFISH_WEB_LIVE_SEED_PROJECT_ID: "project-live",
      MIROFISH_WEB_LIVE_SEED_SESSION_COOKIE: "session-live",
      MIROFISH_WEB_LIVE_SEED_ALLOW_MUTATION: "1",
      MIROFISH_WEB_LIVE_SEED_THROWAWAY_PROJECT: "1",
      MIROFISH_WEB_LIVE_SEED_DISPOSABLE_PROJECT_MARKER: "throwaway",
      MIROFISH_WEB_BROWSER_LIVE_SEED_API_BASE_URL: "http://127.0.0.1:4999",
    },
    prefix: LIVE_SEED_PREFIX,
  });
  assert.equal(liveConfig.enabled, true);
  assert.equal(liveConfig.apiBaseUrl, "http://127.0.0.1:3888");
  assert.equal(liveConfig.tenantId, "tenant-live");
  assert.equal(liveConfig.projectId, "project-live");
  assert.equal(liveConfig.sessionCookie, "session-live");
  assert.equal(liveConfig.allowMutation, true);
  assert.equal(liveConfig.throwawayProject, true);
  assert.equal(liveConfig.disposableProjectMarker, "throwaway");
  assert.equal("appBaseUrl" in liveConfig, false);
  assertDisposableLiveSeedConfig(liveConfig);

  const browserConfig = loadLiveSeedConfig({
    env: {
      MIROFISH_WEB_BROWSER_LIVE_SEED_APP_BASE_URL: "http://localhost:3999",
      MIROFISH_WEB_BROWSER_LIVE_SEED_API_BASE_URL: "http://localhost:3888",
      MIROFISH_WEB_BROWSER_LIVE_SEED_TENANT_ID: "tenant-browser",
      MIROFISH_WEB_BROWSER_LIVE_SEED_PROJECT_ID: "project-browser",
      MIROFISH_WEB_BROWSER_LIVE_SEED_SESSION_COOKIE: "session-browser",
      MIROFISH_WEB_BROWSER_LIVE_SEED_ALLOW_MUTATION: "1",
      MIROFISH_WEB_BROWSER_LIVE_SEED_THROWAWAY_PROJECT: "1",
      MIROFISH_WEB_BROWSER_LIVE_SEED_DISPOSABLE_PROJECT_MARKER: "throwaway",
      MIROFISH_WEB_BROWSER_LIVE_SEED_REQUIRE_WORKER_RETRY: "1",
      MIROFISH_WEB_BROWSER_LIVE_SEED_WORKER_RETRY_TIMEOUT_MS: "120000",
    },
    prefix: BROWSER_LIVE_SEED_PREFIX,
    browser: true,
  });
  assert.equal(browserConfig.enabled, true);
  assert.equal(browserConfig.appBaseUrl, "http://localhost:3999");
  assert.equal(browserConfig.apiBaseUrl, "http://localhost:3888");
  assert.equal(browserConfig.consumeRetryRun, false);
  assert.equal(browserConfig.retryRunId, "");
  assert.equal(browserConfig.requireWorkerRetry, true);
  assert.equal(browserConfig.workerRetryTimeoutMs, 120000);
  assertDisposableLiveSeedConfig(browserConfig);
});

test("live Seed harness rejects worker-retry mode with external retry-run fallback", () => {
  assert.throws(
    () => loadLiveSeedConfig({
      env: {
        MIROFISH_WEB_BROWSER_LIVE_SEED_APP_BASE_URL: "http://localhost:3999",
        MIROFISH_WEB_BROWSER_LIVE_SEED_API_BASE_URL: "http://localhost:3888",
        MIROFISH_WEB_BROWSER_LIVE_SEED_TENANT_ID: "tenant-browser",
        MIROFISH_WEB_BROWSER_LIVE_SEED_PROJECT_ID: "project-browser",
        MIROFISH_WEB_BROWSER_LIVE_SEED_SESSION_COOKIE: "session-browser",
        MIROFISH_WEB_BROWSER_LIVE_SEED_ALLOW_MUTATION: "1",
        MIROFISH_WEB_BROWSER_LIVE_SEED_THROWAWAY_PROJECT: "1",
        MIROFISH_WEB_BROWSER_LIVE_SEED_DISPOSABLE_PROJECT_MARKER: "throwaway",
        MIROFISH_WEB_BROWSER_LIVE_SEED_REQUIRE_WORKER_RETRY: "1",
        MIROFISH_WEB_BROWSER_LIVE_SEED_CONSUME_RETRY_RUN: "1",
        MIROFISH_WEB_BROWSER_LIVE_SEED_RETRY_RUN_ID: "run-retry-secret",
      },
      prefix: BROWSER_LIVE_SEED_PREFIX,
      browser: true,
    }),
    (error) => {
      assert.match(error.message, /worker retry mode must retry the browser-uploaded run/);
      assert.doesNotMatch(error.message, /run-retry-secret|session-browser|tenant-browser|project-browser/);
      return true;
    },
  );
});

test("live Seed harness keeps completed browser mode separate from retry modes", () => {
  const baseEnv = {
    MIROFISH_WEB_BROWSER_LIVE_SEED_APP_BASE_URL: "http://localhost:3999",
    MIROFISH_WEB_BROWSER_LIVE_SEED_API_BASE_URL: "http://localhost:3888",
    MIROFISH_WEB_BROWSER_LIVE_SEED_TENANT_ID: "tenant-browser",
    MIROFISH_WEB_BROWSER_LIVE_SEED_PROJECT_ID: "project-browser",
    MIROFISH_WEB_BROWSER_LIVE_SEED_SESSION_COOKIE: "session-browser",
    MIROFISH_WEB_BROWSER_LIVE_SEED_ALLOW_MUTATION: "1",
    MIROFISH_WEB_BROWSER_LIVE_SEED_THROWAWAY_PROJECT: "1",
    MIROFISH_WEB_BROWSER_LIVE_SEED_DISPOSABLE_PROJECT_MARKER: "throwaway",
    MIROFISH_WEB_BROWSER_LIVE_SEED_EXPECT_COMPLETED: "1",
  };
  const completed = loadLiveSeedConfig({
    env: baseEnv,
    prefix: BROWSER_LIVE_SEED_PREFIX,
    browser: true,
  });
  assert.equal(completed.expectCompleted, true);
  assert.equal(completed.requireWorkerRetry, false);

  assert.throws(
    () => loadLiveSeedConfig({
      env: {
        ...baseEnv,
        MIROFISH_WEB_BROWSER_LIVE_SEED_REQUIRE_WORKER_RETRY: "1",
      },
      prefix: BROWSER_LIVE_SEED_PREFIX,
      browser: true,
    }),
    /completed mode cannot enable retry-run options/,
  );
});

test("live Seed harness waits for worker parse segment and terminal events without leaking public material", async () => {
  const calls = [];
  const api = {
    async getSeedRunEvents(input) {
      calls.push(input);
      const base = { ok: true, run_id: input.runId, items: [] };
      if (calls.length === 1) {
        return base;
      }
      if (calls.length === 2) {
        return {
          ...base,
          items: [
            { event_id: "evt-1", run_id: input.runId, sequence: 2, event_type: "seed.stage.completed", payload: { stage: "parse_file" } },
            { event_id: "evt-2", run_id: input.runId, sequence: 3, event_type: "seed.stage.completed", payload: { stage: "segment_text" } },
          ],
        };
      }
      return {
        ...base,
        items: [
          { event_id: "evt-1", run_id: input.runId, sequence: 2, event_type: "seed.stage.completed", payload: { stage: "parse_file" } },
          { event_id: "evt-2", run_id: input.runId, sequence: 3, event_type: "seed.stage.completed", payload: { stage: "segment_text" } },
          { event_id: "evt-3", run_id: input.runId, sequence: 4, event_type: "seed.stage.failed", payload: { stage: "story_ontology", error_code: "LLM_MODULE_UNBOUND" } },
        ],
      };
    },
  };
  const result = await waitForSeedWorkerStageEvents(api, {
    tenantId: "tenant-live",
    sessionCookie: "session-live",
  }, "run-live", {
    afterSequence: 1,
    timeoutMs: 1000,
    pollMs: 1,
  });

  assert.equal(calls.length, 3);
  assert.equal(result.parseEvent.payload.stage, "parse_file");
  assert.equal(result.segmentEvent.payload.stage, "segment_text");
  assert.equal(result.terminalEvent.payload.stage, "story_ontology");
});

test("live Seed worker event wait rejects public event payload leaks", async () => {
  const api = {
    async getSeedRunEvents(input) {
      return {
        ok: true,
        run_id: input.runId,
        items: [
          {
            event_id: "evt-leak",
            run_id: input.runId,
            sequence: 2,
            event_type: "seed.stage.completed",
            payload: { stage: "parse_file", provider: "openai", content: "source private text" },
          },
        ],
      };
    },
  };

  await assert.rejects(
    () => waitForSeedWorkerStageEvents(api, {
      tenantId: "tenant-live",
      sessionCookie: "session-live",
    }, "run-live", {
      afterSequence: 1,
      timeoutMs: 1000,
      pollMs: 1,
    }),
    /live Seed public payload contained forbidden material/,
  );
});

test("live Seed harness fails loudly on partial config without echoing env values", () => {
  assert.throws(
    () => loadLiveSeedConfig({
      env: {
        MIROFISH_WEB_LIVE_SEED_API_BASE_URL: "http://127.0.0.1:3888",
        MIROFISH_WEB_LIVE_SEED_SESSION_COOKIE: "secret-session-cookie",
      },
      prefix: LIVE_SEED_PREFIX,
    }),
    (error) => {
      assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_TENANT_ID/);
      assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_PROJECT_ID/);
      assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_ALLOW_MUTATION/);
      assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_THROWAWAY_PROJECT/);
      assert.match(error.message, /MIROFISH_WEB_LIVE_SEED_DISPOSABLE_PROJECT_MARKER/);
      assert.doesNotMatch(error.message, /secret-session-cookie|127\.0\.0\.1:3888/);
      return true;
    },
  );

  assert.throws(
    () => loadLiveSeedConfig({
      env: {
        MIROFISH_WEB_BROWSER_LIVE_SEED_API_BASE_URL: "http://127.0.0.1:3888",
        MIROFISH_WEB_BROWSER_LIVE_SEED_TENANT_ID: "tenant-browser",
        MIROFISH_WEB_BROWSER_LIVE_SEED_PROJECT_ID: "project-browser",
        MIROFISH_WEB_BROWSER_LIVE_SEED_SESSION_COOKIE: "browser-secret-session",
        MIROFISH_WEB_BROWSER_LIVE_SEED_ALLOW_MUTATION: "1",
        MIROFISH_WEB_BROWSER_LIVE_SEED_THROWAWAY_PROJECT: "1",
        MIROFISH_WEB_BROWSER_LIVE_SEED_DISPOSABLE_PROJECT_MARKER: "throwaway",
      },
      prefix: BROWSER_LIVE_SEED_PREFIX,
      browser: true,
    }),
    (error) => {
      assert.match(error.message, /MIROFISH_WEB_BROWSER_LIVE_SEED_APP_BASE_URL/);
      assert.doesNotMatch(error.message, /browser-secret-session|tenant-browser|project-browser/);
      return true;
    },
  );
});

test("live Seed harness URL guard only accepts local http URLs", () => {
  for (const value of [
    "http://localhost:3888",
    "http://127.0.0.1:3888/api",
    "http://[::1]:3888",
  ]) {
    assert.equal(assertLocalHttpUrl(value, "test URL").protocol, "http:");
  }

  for (const value of [
    "https://localhost:3888",
    "http://example.com:3888",
    "http://user:pass@localhost:3888",
    "//localhost:3888",
    "/v1/me",
    "localhost:3888",
  ]) {
    assert.throws(
      () => assertLocalHttpUrl(value, "test URL"),
      (error) => {
        assert.match(error.message, /test URL must be a local http URL/);
        assert.doesNotMatch(error.message, /example\.com|user|pass|localhost:3888|\/v1\/me/);
        return true;
      },
    );
  }
});

test("live Seed harness privacy helpers redact tokens and keep assertion messages public", () => {
  const jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.signature";
  const sensitive = {
    cookie: "mirofish_session=secret-cookie; theme=light",
    auth: `Bearer ${jwt}`,
    nested: { token: jwt },
  };
  const redacted = redactSensitiveText(sensitive, { sessionCookie: "secret-cookie" });
  assert.doesNotMatch(redacted, /secret-cookie|Bearer eyJ|eyJhbGciOiJIUzI1NiJ9/);
  assert.match(redacted, /\[redacted/);
  assert.doesNotMatch(
    redactSensitiveText("token v2:user-1:secret-token-material"),
    /v2:user-1:secret-token-material/,
  );
  assert.doesNotMatch(
    redactSensitiveText("access_token=secret-access refreshToken:secret-refresh csrf_token=secret-csrf"),
    /secret-access|secret-refresh|secret-csrf/,
  );
  assert.doesNotMatch(
    redactSensitiveText({
      access_token: "secret-access",
      accessToken: "secret-access-camel",
      csrfToken: "secret-csrf",
      sessionToken: "secret-session",
      token: "secret-token",
    }),
    /secret-access|secret-access-camel|secret-csrf|secret-session|secret-token/,
  );
  assert.doesNotMatch(
    publicFailure({ ok: false, code: "LIVE_FAILED", message: "source text: private chapter body" }),
    /source text|private chapter body/i,
  );

  const sourceText = "uploaded \"chapter\"\nbody <private> should stay private";
  for (const value of [
    { prompt: "private prompt" },
    { provider_response: "provider raw response" },
    { source_text: sourceText },
    { raw_content: "private raw content" },
    { api_key: "sk-live-secret" },
    { encryptedCredential: "encrypted-secret" },
    { credential_ref: "credential-secret" },
    { object_key: "object-secret" },
    { access_token: "access-secret" },
    { csrf_token: "csrf-secret" },
    { refreshToken: "refresh-secret" },
    { draft_note: "draft marker" },
    { manuscript_title: "manuscript marker" },
  ]) {
    assert.throws(
      () => assertNoForbiddenPublicMarkers(value, {
        sourceText,
        sessionCookie: "secret-cookie",
      }),
      (error) => {
        assert.match(error.message, /live Seed public payload contained forbidden material/);
        assert.doesNotMatch(
          error.message,
          /uploaded chapter|private prompt|provider raw response|raw content|api_key|encryptedCredential|credential_ref|object_key|draft|manuscript|access-secret|csrf-secret|refresh-secret|secret-cookie|sk-live-secret|encrypted-secret|credential-secret|object-secret/i,
        );
        return true;
      },
    );
  }

  assert.throws(
    () => assertNoForbiddenPublicMarkers({ text: JSON.stringify(sourceText).slice(1, -1) }, { sourceText }),
    /live Seed public payload contained forbidden material/,
  );
  assert.throws(
    () => assertNoForbiddenPublicMarkers(
      { text: "uploaded &quot;chapter&quot;\nbody &lt;private&gt; should stay private" },
      { sourceText },
    ),
    /live Seed public payload contained forbidden material/,
  );
  assert.throws(
    () => assertNoForbiddenPublicMarkers(
      { text: "uploaded \"chapter\" body <private> should stay private" },
      { sourceText },
    ),
    /live Seed public payload contained forbidden material/,
  );
  assert.throws(
    () => assertNoForbiddenPublicMarkers(
      { text: "uploaded &quot;chapter&quot; body &lt;private&gt; should stay private" },
      { sourceText },
    ),
    /live Seed public payload contained forbidden material/,
  );
  for (const rawText of [
    '{"draft_note":"private"}',
    '{"manuscript_title":"private"}',
    '{"token":"private"}',
    '{"sessionCookie":"private"}',
    '{"access_token":"private"}',
  ]) {
    assert.throws(
      () => assertNoForbiddenPublicMarkers(rawText),
      /live Seed public payload contained forbidden material/,
    );
  }

  assertNoForbiddenPublicMarkers({
    title: "Manuscript metadata",
    note: "The run completed promptly.",
    status: "draft status",
    usage: { total_tokens: 42 },
  });
});

test("live Seed harness public failures redact sensitive result material", () => {
  const message = publicFailure({
    ok: false,
    code: "LIVE_FAILED",
    message: "Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ1c2VyIn0.signature mirofish_session=secret-cookie raw content",
  }, { sessionCookie: "secret-cookie" });

  assert.match(message, /LIVE_FAILED/);
  assert.doesNotMatch(message, /secret-cookie|Bearer eyJ|eyJhbGciOiJIUzI1NiJ9|raw content/i);
});

test("live Seed harness overview URL encodes route segments", () => {
  const url = new URL(overviewUrl({
    appBaseUrl: "http://localhost:3999",
    tenantId: "tenant/with space",
    projectId: "project?with#chars",
  }));
  assert.equal(url.origin, "http://localhost:3999");
  assert.equal(url.pathname, "/tenant%2Fwith%20space/projects/project%3Fwith%23chars/overview");
  assert.equal(url.search, "");
});

test("live Seed harness adds browser session cookies without changing public error text", async () => {
  const calls = [];
  await addLiveSeedSessionCookie(
    {
      addCookies: async (cookies) => {
        calls.push(cookies);
      },
    },
    {
      appBaseUrl: "http://127.0.0.1:3999",
      sessionCookie: "secret-session-cookie",
    },
  );

  assert.deepEqual(calls, [[{
    name: "mirofish_session",
    value: "secret-session-cookie",
    url: "http://127.0.0.1:3999",
    httpOnly: true,
    sameSite: "Lax",
  }]]);

  await assert.rejects(
    () => addLiveSeedSessionCookie(
      { addCookies: async () => {} },
      {
        appBaseUrl: "https://127.0.0.1:3999",
        sessionCookie: "secret-session-cookie",
      },
    ),
    (error) => {
      assert.match(error.message, /live Seed app base URL must be a local http URL/);
      assert.doesNotMatch(error.message, /secret-session-cookie|https:\/\/127\.0\.0\.1/);
      return true;
    },
  );
});

test("project shell exposes current-session logout without leaking the session token", async () => {
  const client = await fileText("lib/api.ts");
  const layout = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");
  const actions = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/session-actions.ts");
  const nav = await fileText("components/project-nav.tsx");
  const logoutClient = sourceSlice(client, "export async function revokeCurrentSession", "export async function changePassword");
  const logoutAction = sourceSlice(actions, "export async function logoutAction", "export async function rotateSessionAction");

  assert.match(client, /export async function getSessionCSRFToken\(input:\s*\{\s*sessionCookie\?:\s*string;?\s*\}\)/);
  assert.match(client, /\/v1\/auth\/csrf-token/);
  assert.match(client, /networkFailure\(error,\s*"SESSION_CSRF_TOKEN_FAILED"\)/);
  assert.match(logoutClient, /sessionCookie\?:\s*string/);
  assert.match(logoutClient, /csrfToken\?:\s*string/);
  assert.match(logoutClient, /\/v1\/auth\/session/);
  assert.match(logoutClient, /method:\s*"DELETE"/);
  assert.match(logoutClient, /headers:\s*sessionCookieHeaders\(input\)/);
  assert.match(logoutClient, /networkFailure\(error,\s*"SESSION_REVOKE_FAILED"\)/);
  assert.match(client, /function sessionCookieHeaders\(input:\s*\{\s*sessionCookie\?:\s*string;\s*csrfToken\?:\s*string;?\s*\}\)/);
  assert.match(client, /headers\.Cookie\s*=\s*`mirofish_session=\$\{sessionCookie\}`/);
  assert.match(client, /headers\["X-CSRF-Token"\]\s*=\s*csrfToken/);
  assert.doesNotMatch(logoutClient, /X-User-Id|contextHeaders|actorUserId|body|JSON\.stringify/);

  assert.match(layout, /import\s*\{[\s\S]*logoutAction[\s\S]*\}\s*from\s*"\.\/session-actions"/);
  assert.doesNotMatch(layout, /async function logoutAction|async function rotateSessionAction|async function revokeAllSessionsAction|async function revokeTenantSessionsAction/);
  assert.match(actions, /^"use server";/);
  assert.match(actions, /getSessionCSRFToken/);
  assert.match(actions, /revokeCurrentSession/);
  assert.match(actions, /async function readActionSessionCookie/);
  assert.match(actions, /const\s+actionCookieStore\s*=\s*await\s+cookies\(\)/);
  assert.match(actions, /actionCookieStore\.get\("mirofish_session"\)\?\.value\?\.trim\(\)/);
  assert.match(logoutAction, /"use server"/);
  assert.match(logoutAction, /readActionSessionCookie\(\)/);
  assert.match(logoutAction, /if\s*\(!actionSessionCookie\)\s*\{\s*redirect\("\/login"\);\s*\}/s);
  assert.match(actions, /async function requireActionCSRFToken/);
  assert.match(actions, /throw new Error\("SESSION_CSRF_TOKEN_UNAVAILABLE"\)/);
  assert.match(logoutAction, /const\s+csrfResult\s*=\s*await\s+requireActionCSRFToken\(actionSessionCookie\)/s);
  assert.match(logoutAction, /await\s+revokeCurrentSession\(\{\s*sessionCookie:\s*actionSessionCookie,\s*csrfToken:\s*csrfResult\.csrf_token\s*\}\)/s);
  assert.match(logoutAction, /throw new Error\("SESSION_REVOKE_FAILED"\)/);
  assert.match(logoutAction, /actionCookieStore\.delete\("mirofish_session"\)/);
  assert.match(logoutAction, /actionCookieStore\.delete\("mirofish_session"\);\s*redirect\("\/login"\)/s);
  assert.doesNotMatch(logoutAction, /MIROFISH_WEB_DEV_ACTOR_USER_ID|X-User-Id|console\.|sessionCookie\s*\}/);
  assert.match(layout, /logoutAction=\{logoutAction\}/);

  assert.match(nav, /logoutAction:\s*\(\)\s*=>\s*Promise<void>/);
  assert.match(nav, /logoutAction/);
  assert.match(nav, /<form\s+action=\{logoutAction\}/);
  assert.match(nav, /type="submit"/);
  assert.match(nav, /Sign out/);
  assert.doesNotMatch(nav, /mirofish_session|sessionCookie|api_key|credential_ref|draft|manuscript|prompt|provider/i);
});

test("project shell exposes current-session rotation without leaking the session token", async () => {
  const client = await fileText("lib/api.ts");
  const layout = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");
  const actions = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/session-actions.ts");
  const nav = await fileText("components/project-nav.tsx");
  const rotationClient = sourceSlice(client, "export async function rotateCurrentSession", "export async function getSessionCSRFToken");
  const rotateAction = sourceSlice(actions, "export async function rotateSessionAction", "export async function revokeAllSessionsAction");

  assert.match(client, /export type RotatedSessionCookie/);
  assert.match(client, /export async function rotateCurrentSession\(input:\s*\{\s*sessionCookie\?:\s*string;\s*csrfToken\?:\s*string;?\s*\}\)/);
  assert.match(rotationClient, /\/v1\/auth\/session\/rotation/);
  assert.match(rotationClient, /method:\s*"POST"/);
  assert.match(rotationClient, /headers:\s*sessionCookieHeaders\(input\)/);
  assert.match(rotationClient, /response\.headers\.get\("set-cookie"\)/);
  assert.match(rotationClient, /parseSessionCookieSetCookie/);
  assert.match(rotationClient, /networkFailure\(error,\s*"SESSION_ROTATION_FAILED"\)/);
  assert.doesNotMatch(rotationClient, /X-User-Id|contextHeaders|actorUserId|body|JSON\.stringify/);

  assert.match(layout, /import\s*\{[\s\S]*rotateSessionAction[\s\S]*\}\s*from\s*"\.\/session-actions"/);
  assert.doesNotMatch(layout, /async function rotateSessionAction/);
  assert.match(actions, /rotateCurrentSession/);
  assert.match(rotateAction, /"use server"/);
  assert.match(rotateAction, /readActionSessionCookie\(\)/);
  assert.match(rotateAction, /const\s+csrfResult\s*=\s*await\s+requireActionCSRFToken\(actionSessionCookie\)/s);
  assert.match(rotateAction, /const\s+rotationResult\s*=\s*await\s+rotateCurrentSession\(\{[\s\S]*sessionCookie:\s*actionSessionCookie,[\s\S]*csrfToken:\s*csrfResult\.csrf_token,[\s\S]*\}\)/);
  assert.match(rotateAction, /throw new Error\("SESSION_ROTATION_FAILED"\)/);
  assert.match(rotateAction, /actionCookieStore\.set\("mirofish_session",\s*rotationResult\.session_cookie\.value,/);
  assert.doesNotMatch(rotateAction, /MIROFISH_WEB_DEV_ACTOR_USER_ID|X-User-Id|console\.|JSON\.stringify/);
  assert.match(layout, /rotateSessionAction=\{rotateSessionAction\}/);

  assert.match(nav, /rotateSessionAction:\s*\(\)\s*=>\s*Promise<void>/);
  assert.match(nav, /<form\s+action=\{rotateSessionAction\}/);
  assert.match(nav, /Refresh session/);
  assert.doesNotMatch(nav, /mirofish_session|sessionCookie|api_key|credential_ref|draft|manuscript|prompt|provider/i);
});

test("project shell exposes session management metadata without leaking token material", async () => {
  const client = await fileText("lib/api.ts");
  const layout = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");
  const actions = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/session-actions.ts");
  const nav = await fileText("components/project-nav.tsx");
  const sessionsRoute = await fileText("app/api/auth/sessions/route.ts");
  const listClient = sourceSlice(client, "export async function getCurrentUserSessions", "export async function revokeAllCurrentUserSessions");
  const revokeAllClient = sourceSlice(client, "export async function revokeAllCurrentUserSessions", "export async function startWriterRun");
  const revokeAllAction = sourceSlice(actions, "export async function revokeAllSessionsAction", "export async function revokeTenantSessionsAction");

  assert.match(client, /export type CurrentUserSessionRecord/);
  assert.match(client, /export type CurrentUserSessionsSummary/);
  assert.match(client, /export async function getCurrentUserSessions\(input:\s*\{\s*sessionCookie\?:\s*string;?\s*\}\)/);
  assert.match(listClient, /\/v1\/auth\/sessions/);
  assert.match(listClient, /method:\s*"GET"/);
  assert.match(listClient, /headers:\s*sessionCookieHeaders\(input\)/);
  assert.match(listClient, /requiredString\(session,\s*"session_id"\)/);
  assert.match(listClient, /requiredString\(session,\s*"expires_at"\)/);
  assert.match(listClient, /requiredBoolean\(session,\s*"current"\)/);
  assert.match(listClient, /networkFailure\(error,\s*"SESSION_LIST_FAILED"\)/);
  assert.doesNotMatch(listClient, /X-User-Id|actorUserId|body|JSON\.stringify|csrfToken/);

  assert.match(client, /export async function revokeAllCurrentUserSessions\(input:\s*\{\s*sessionCookie\?:\s*string;\s*csrfToken\?:\s*string;?\s*\}\)/);
  assert.match(revokeAllClient, /\/v1\/auth\/sessions/);
  assert.match(revokeAllClient, /method:\s*"DELETE"/);
  assert.match(revokeAllClient, /headers:\s*sessionCookieHeaders\(input\)/);
  assert.match(revokeAllClient, /networkFailure\(error,\s*"SESSION_REVOKE_ALL_FAILED"\)/);
  assert.doesNotMatch(revokeAllClient, /X-User-Id|actorUserId|body|JSON\.stringify/);

  assert.doesNotMatch(layout, /getCurrentUserSessions|currentUserSessions/);
  assert.match(actions, /revokeAllCurrentUserSessions/);
  assert.match(revokeAllAction, /"use server"/);
  assert.match(revokeAllAction, /readActionSessionCookie\(\)/);
  assert.match(revokeAllAction, /const\s+csrfResult\s*=\s*await\s+requireActionCSRFToken\(actionSessionCookie\)/s);
  assert.match(revokeAllAction, /await\s+revokeAllCurrentUserSessions\(\{\s*sessionCookie:\s*actionSessionCookie,\s*csrfToken:\s*csrfResult\.csrf_token\s*\}\)/s);
  assert.match(revokeAllAction, /throw new Error\("SESSION_REVOKE_FAILED"\)/);
  assert.match(layout, /revokeAllSessionsAction=\{revokeAllSessionsAction\}/);
  assert.doesNotMatch(revokeAllAction, /MIROFISH_WEB_DEV_ACTOR_USER_ID|X-User-Id|console\.|JSON\.stringify|sessionCookie\s*\}/);

  assert.match(nav, /useState<CurrentUserSessionsSummary/);
  assert.match(nav, /onToggle=\{loadSessionsWhenOpened\}/);
  assert.match(nav, /fetch\("\/api\/auth\/sessions"/);
  assert.match(nav, /if \(!event\.currentTarget\.open/);
  assert.match(nav, /revokeAllSessionsAction:\s*\(\)\s*=>\s*Promise<void>/);
  assert.match(nav, /aria-label="会话 \/ Sessions"/);
  assert.match(nav, /Active sessions/);
  assert.match(nav, /currentUserSessions\.sessions\.map/);
  assert.match(nav, /session\.current/);
  assert.match(nav, /expires_at/);
  assert.match(nav, /last_seen_at/);
  assert.match(nav, /<form\s+action=\{revokeAllSessionsAction\}/);
  assert.match(nav, /Sign out everywhere/);
  assert.doesNotMatch(nav, /mirofish_session|sessionCookie|token_hash|api_key|credential_ref|draft|manuscript|prompt|provider/i);
  assert.match(sessionsRoute, /export async function GET/);
  assert.match(sessionsRoute, /getCurrentUserSessions\(\{\s*sessionCookie\s*\}\)/);
  assert.match(sessionsRoute, /cache-control",\s*"private, no-store"/i);
});

test("project shell exposes tenant-wide session revocation for tenant admins without leaking token material", async () => {
  const client = await fileText("lib/api.ts");
  const layout = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");
  const actions = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/session-actions.ts");
  const nav = await fileText("components/project-nav.tsx");
  const revokeTenantClient = sourceSlice(client, "export async function revokeTenantSessions", "export async function startWriterRun");
  const revokeTenantAction = sourceSlice(actions, "export async function revokeTenantSessionsAction", "async function readActionSessionCookie");

  assert.match(client, /export async function revokeTenantSessions\(input:\s*\{\s*tenantId:\s*string;\s*sessionCookie\?:\s*string;\s*csrfToken\?:\s*string;?\s*\}\)/);
  assert.match(revokeTenantClient, /\/v1\/tenants\/\$\{encodeURIComponent\(input\.tenantId\)\}\/sessions/);
  assert.match(revokeTenantClient, /method:\s*"DELETE"/);
  assert.match(revokeTenantClient, /headers:\s*sessionCookieHeaders\(input\)/);
  assert.match(revokeTenantClient, /networkFailure\(error,\s*"TENANT_SESSION_REVOKE_FAILED"\)/);
  assert.doesNotMatch(revokeTenantClient, /X-User-Id|actorUserId|body|JSON\.stringify|password|token_hash/);

  assert.match(actions, /revokeTenantSessions/);
  assert.match(revokeTenantAction, /"use server"/);
  assert.match(revokeTenantAction, /readActionSessionCookie\(\)/);
  assert.match(revokeTenantAction, /requireActionCSRFToken\(actionSessionCookie\)/s);
  assert.match(revokeTenantAction, /revokeTenantSessions\(\{\s*tenantId,\s*sessionCookie:\s*actionSessionCookie,\s*csrfToken:\s*csrfResult\.csrf_token\s*\}\)/s);
  assert.match(revokeTenantAction, /throw new Error\("TENANT_SESSION_REVOKE_FAILED"\)/);
  assert.match(revokeTenantAction, /actionCookieStore\.delete\("mirofish_session"\)/);
  assert.match(layout, /revokeTenantSessionsAction=\{revokeTenantSessionsAction\.bind\(null,\s*tenantSlug\)\}/);
  assert.doesNotMatch(revokeTenantAction, /MIROFISH_WEB_DEV_ACTOR_USER_ID|X-User-Id|console\.|JSON\.stringify|token_hash|api_key|credential_ref|draft|manuscript|prompt|provider/i);

  assert.match(nav, /revokeTenantSessionsAction:\s*\(\)\s*=>\s*Promise<void>/);
  assert.match(nav, /const\s+currentTenant\s*=\s*currentUser\.ok\s*\?\s*currentUser\.active_tenants\.find\(\(tenant\)\s*=>\s*tenant\.tenant_id\s*===\s*tenantSlug\)\s*:\s*undefined/s);
  assert.match(nav, /const\s+canManageTenantSessions\s*=\s*currentTenant\s*\?\s*\["owner",\s*"admin"\]\.includes\(currentTenant\.role\)\s*:\s*false/s);
  assert.match(nav, /<form\s+action=\{revokeTenantSessionsAction\}/);
  assert.match(nav, /Revoke workspace sessions/);
  assert.doesNotMatch(nav, /mirofish_session|sessionCookie|csrf|token_hash|api_key|credential_ref|draft|manuscript|prompt|provider/i);
});

test("project shell triggers automatic session refresh without exposing the session token", async () => {
  const layout = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");
  const trigger = await fileText("components/session-auto-refresh.tsx");
  const route = await fileText("app/api/auth/session/refresh/route.ts");

  assert.match(layout, /SessionAutoRefresh/);
  assert.match(layout, /<SessionAutoRefresh\s+enabled=\{Boolean\(sessionCookie\)\}\s*\/>/);
  assert.doesNotMatch(layout, /<SessionAutoRefresh[^>]*sessionCookie=\{/i);

  assert.match(trigger, /"use client"/);
  assert.match(trigger, /export function SessionAutoRefresh\(input:\s*\{\s*enabled:\s*boolean;?\s*\}\)/);
  assert.match(trigger, /useEffect/);
  assert.match(trigger, /sessionStorage/);
  assert.match(trigger, /SESSION_REFRESH_COOLDOWN_MS/);
  assert.match(trigger, /SESSION_REFRESH_THRESHOLD_MS/);
  assert.match(trigger, /fetch\("\/api\/auth\/sessions"/);
  assert.match(trigger, /session\.current/);
  assert.match(trigger, /Date\.parse\(currentSession\?\.expires_at\s*\?\?\s*""\)/);
  assert.match(trigger, /expiresAt\s*-\s*now\s*>\s*SESSION_REFRESH_THRESHOLD_MS/);
  assert.match(trigger, /\[input\.enabled\]/);
  assert.match(trigger, /fetch\("\/api\/auth\/session\/refresh"/);
  assert.match(trigger, /method:\s*"POST"/);
  assert.match(trigger, /credentials:\s*"same-origin"/);
  assert.match(trigger, /cache:\s*"no-store"/);
  assert.doesNotMatch(trigger, /mirofish_session|sessionCookie|X-User-Id|X-CSRF-Token|Cookie|body|JSON\.stringify|console\.|api_key|credential_ref|draft|manuscript|prompt|provider/i);

  assert.match(route, /export async function POST/);
  assert.match(route, /cookies\(\)/);
  assert.match(route, /cookieStore\.get\("mirofish_session"\)\?\.value\?\.trim\(\)/);
  assert.match(route, /getSessionCSRFToken\(\{\s*sessionCookie\s*\}\)/);
  assert.match(route, /rotateCurrentSession\(\{\s*sessionCookie,\s*csrfToken:\s*csrfResult\.csrf_token\s*\}\)/);
  assert.match(route, /response\.cookies\.set\("mirofish_session",\s*rotationResult\.session_cookie\.value,/);
  assert.match(route, /httpOnly:\s*rotationResult\.session_cookie\.http_only/);
  assert.match(route, /maxAge:\s*rotationResult\.session_cookie\.max_age/);
  assert.doesNotMatch(route, /MIROFISH_WEB_DEV_ACTOR_USER_ID|X-User-Id|actorUserId|request\.json|JSON\.stringify|console\.|api_key|credential_ref|draft|manuscript|prompt|provider/i);
});

test("project pages resolve API context from browser session cookie instead of hardcoded actor", async () => {
  const helper = await fileText("lib/server-auth.ts");
  const projectPages = [
    "app/(app)/[tenantSlug]/projects/[projectId]/assets/page.tsx",
    "app/(app)/[tenantSlug]/projects/[projectId]/character-console/page.tsx",
    "app/(app)/[tenantSlug]/projects/[projectId]/graph/page.tsx",
    "app/(app)/[tenantSlug]/projects/[projectId]/llm-facility/page.tsx",
    "app/(app)/[tenantSlug]/projects/[projectId]/overview/page.tsx",
    "app/(app)/[tenantSlug]/projects/[projectId]/worldline/page.tsx",
    "app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx",
  ];
  const pageSources = (await Promise.all(projectPages.map((page) => fileText(page)))).join("\n");
  const client = await fileText("lib/api.ts");

  assert.match(helper, /export\s+async\s+function\s+webApiContext/);
  assert.match(helper, /currentRequestSessionCookie/);
  assert.match(helper, /required:\s*!isDevLoginBypassEnabled\(\)/);
  assert.doesNotMatch(helper, /from\s*"next\/headers"|cookies\(\)|headers\(\)|cookieStore\.get\("mirofish_session"\)/);
  assert.match(helper, /devActorUserId\(\)/);
  assert.match(helper, /getSessionCSRFToken/);
  assert.match(helper, /const\s+csrfResult\s*=\s*sessionCookie\s*\?\s*await\s+getSessionCSRFToken\(\{\s*sessionCookie\s*\}\)\s*:\s*undefined/s);
  assert.match(helper, /throw new Error\("WEB_CSRF_TOKEN_UNAVAILABLE"\)/);
  assert.match(helper, /actorUserId:\s*sessionCookie\s*\?\s*undefined\s*:\s*actorUserId/);
  assert.match(helper, /csrfToken:\s*csrfResult\?\.ok\s*\?\s*csrfResult\.csrf_token\s*:\s*undefined/);
  assert.match(client, /sessionCookie\?:\s*string/);
  assert.match(client, /csrfToken\?:\s*string/);
  assert.match(client, /headers\.Cookie\s*=\s*`mirofish_session=\$\{sessionCookie\}`/);
  assert.match(client, /headers\["X-CSRF-Token"\]\s*=\s*csrfToken/);
  assert.match(client, /else if\s*\(actorUserId\)\s*\{\s*headers\["X-User-Id"\]\s*=\s*actorUserId;\s*\}/s);
  assert.match(client, /function contextHeaders\(input:\s*ApiContext\)/);
  assert.match(client, /headers\.Cookie\s*=\s*`mirofish_session=\$\{sessionCookie\}`/);
  assert.match(pageSources, /webApiContext/);
  assert.match(pageSources, /await\s+webApiContext/);
  assert.doesNotMatch(pageSources, /actorUserId:\s*"web-shell"/);
  assert.doesNotMatch(pageSources, /actorUserId:\s*'web-shell'/);
});

test("ProjectNav renders workspace and project picker links from public memberships", async () => {
  const nav = await fileText("components/project-nav.tsx");

  assert.match(nav, /CurrentUserSummary/);
  assert.match(nav, /currentUser\.ok/);
  assert.match(nav, /active_tenants/);
  assert.match(nav, /active_projects/);
  assert.match(nav, /currentProject/);
  assert.match(nav, /Project access unavailable/);
  assert.match(nav, /const hasMultipleWorkspaces = activeTenants\.length > 1/);
  assert.match(nav, /currentSectionPath/);
  assert.match(nav, /workspacePathForProject\(activeTenants,\s*project,\s*currentSectionPath\)/);
  assert.match(nav, /workspacePathForProject\(\[tenant\],\s*project,\s*currentSectionPath\)/);
  assert.match(nav, /tenant\.tenant_id/);
  assert.match(nav, /tenant\.name/);
  assert.match(nav, /project\.project_id/);
  assert.match(nav, /project\.name/);
  assert.doesNotMatch(nav, /function hrefForProject/);
  assert.match(nav, /currentProject\s*\?\s*\(/s);
  assert.match(nav, /<FailureText \/>/);
  assert.match(nav, /Membership unavailable/);
  assert.match(nav, /User/);
  assert.match(nav, /Workspaces/);
  assert.match(nav, /Projects/);
  assert.doesNotMatch(nav, /tenant\.name\s*\|\|\s*tenant\.tenant_id/);
  assert.doesNotMatch(nav, /project\.name\s*\|\|\s*project\.project_id/);
  assert.doesNotMatch(nav, /credential_ref|encrypted_api_key|api_key|prompt|provider|raw_body|body|content|draft|manuscript|object_key/i);
});

test("Next app shell declares tenant/project Overview route for source files and Seed runs", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/overview/page.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /afterEventId\?:\s*string/);
  assert.match(page, /after_event_id\?:\s*string/);
  assert.match(page, /afterEventId:\s*query\.after_event_id\s*\?\?\s*query\.afterEventId\s*\?\?\s*""/);
  assert.match(page, /getProjectOverview/);
  assert.match(page, /getProjectSourceFiles/);
  assert.match(page, /getProjectReadinessSnapshot/);
  assert.match(page, /createSourceFileUpload/);
  assert.match(page, /uploadSourceFileObject/);
  assert.match(page, /completeSourceFileUpload/);
  assert.match(page, /startAnalysisRun/);
  assert.match(page, /getProjectAnalysisRuns/);
  assert.match(page, /getAnalysisRunSummary/);
  assert.match(page, /getAnalysisRunEvents/);
  assert.match(page, /cancelAnalysisRun/);
  assert.match(page, /listAnalysisWorkspaceFiles/);
  assert.match(page, /listAnalysisCandidates/);
  assert.match(page, /uploadAndStartSeedAction/);
  assert.match(page, /completeUploadAction/);
  assert.match(page, /startSeedRunAction/);
  assert.doesNotMatch(page, /admitSourceFileAction|uploadSourceObjectAction/);
  assert.match(page, /cancelSeedRunAction/);
  assert.match(page, /retrySeedRunAction/);
  assert.doesNotMatch(page, /startSeedRun\(/);
  assert.doesNotMatch(page, /getProjectSeedRuns/);
  assert.match(page, /OverviewSeedShell/);
  assert.match(page, /projectOverview=\{projectOverview\}/);
  assert.match(page, /projectReadiness=\{projectReadiness\}/);
  assert.match(page, /workspaceFiles=\{workspaceFiles\}/);
  assert.match(page, /analysisCandidates=\{analysisCandidates\}/);
});

test("source file, Seed, readiness, and overview API client uses sanitized Go endpoints and tenant context headers", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /ProjectOverviewRecord/);
  assert.match(client, /ProjectOverviewSummary/);
  assert.match(client, /SourceFileRecord/);
  assert.match(client, /SourceFilesSummary/);
  assert.match(client, /ProjectReadinessSnapshot/);
  assert.match(client, /ProjectReadinessSummary/);
  assert.match(client, /SeedRunStartSummary/);
  assert.match(client, /getProjectOverview/);
  assert.match(client, /getProjectSourceFiles/);
  assert.match(client, /getProjectReadinessSnapshot/);
  assert.match(client, /createSourceFileUpload/);
  assert.match(client, /UploadSourceFileObjectInput/);
  assert.match(client, /SourceFileObjectUploadSummary/);
  assert.match(client, /uploadSourceFileObject/);
  assert.match(client, /completeSourceFileUpload/);
  assert.match(client, /startSeedRun/);
  assert.match(client, /startAnalysisRun/);
  assert.match(client, /cancelSeedRun/);
  assert.match(client, /cancelAnalysisRun/);
  assert.match(client, /retrySeedRun/);
  assert.match(client, /getProjectSeedRuns/);
  assert.match(client, /getProjectAnalysisRuns/);
  assert.match(client, /getSeedRunSummary/);
  assert.match(client, /getAnalysisRunSummary/);
  assert.match(client, /getSeedRunEvents/);
  assert.match(client, /getAnalysisRunEvents/);
  assert.match(client, /listAnalysisWorkspaceFiles/);
  assert.match(client, /listAnalysisCandidates/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/uploads`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/overview`/);
  assert.match(client, /\/v1\/uploads\/\$\{input\.uploadId\}\/object`/);
  assert.match(client, /method:\s*"PUT"/);
  assert.match(client, /body:\s*input\.file/);
  assert.match(client, /\/v1\/uploads\/\$\{input\.uploadId\}\/complete`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/source-files`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/readiness`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/seed-runs`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/analysis-runs`/);
  assert.match(client, /\/v1\/seed-runs\/\$\{input\.runId\}`/);
  assert.match(client, /\/v1\/analysis-runs\/\$\{input\.runId\}`/);
  assert.match(client, /\/v1\/seed-runs\/\$\{input\.runId\}\/events/);
  assert.match(client, /\/v1\/analysis-runs\/\$\{input\.runId\}\/events/);
  assert.match(client, /\/v1\/seed-runs\/\$\{input\.runId\}\/cancel`/);
  assert.match(client, /\/v1\/analysis-runs\/\$\{input\.runId\}\/cancel`/);
  assert.match(client, /\/v1\/analysis-runs\/\$\{input\.runId\}\/workspace\/files/);
  assert.match(client, /\/v1\/analysis-runs\/\$\{input\.runId\}\/candidates/);
  assert.match(client, /\/v1\/seed-runs\/\$\{input\.runId\}\/retry`/);
  assert.match(client, /X-Tenant-Id/);
  assert.match(client, /X-User-Id/);
  assert.match(client, /upload_id/);
  assert.match(client, /source_file_count/);
  assert.match(client, /seed_run_count/);
  assert.match(client, /active_workflow_run_id/);
  assert.match(client, /active_workflow_type/);
  assert.match(client, /active_workflow_status/);
  assert.match(client, /asset_count/);
  assert.match(client, /graph_node_count/);
  assert.match(client, /graph_edge_count/);
  assert.match(client, /worldline_session_count/);
  assert.match(client, /worldline_event_count/);
  assert.match(client, /character_interaction_count/);
  assert.match(client, /writer_run_count/);
  assert.match(client, /llm_activity_count/);
  assert.match(client, /llm_token_count/);
  assert.match(client, /llm_enabled_channel_count/);
  assert.match(client, /llm_bound_module_count/);
  assert.match(client, /llm_missing_core_module_count/);
  assert.match(client, /llm_sync_ok_channel_count/);
  assert.match(client, /llm_sync_failed_channel_count/);
  assert.match(client, /llm_sync_pending_channel_count/);
  assert.match(client, /llm_latest_sync_at/);
  assert.match(client, /latest_failed_workflow_run_id/);
  assert.match(client, /latest_failed_workflow_type/);
  assert.match(client, /latest_failed_workflow_error_code/);
  assert.match(client, /latest_failed_workflow_updated_at/);
  assert.match(client, /readiness_snapshot_id/);
  assert.match(client, /readiness_run_id/);
  assert.match(client, /project_readiness_snapshot_id/);
  assert.match(client, /ready_asset_count/);
  assert.match(client, /ready_entity_count/);
  assert.match(client, /ready_relationship_count/);
  assert.match(client, /ready_world_rule_count/);
  assert.match(client, /parse_status/);
  assert.doesNotMatch(client, /object_key:\s*string/);
  assert.doesNotMatch(client, /source_object_key:\s*string/);
  assert.doesNotMatch(client, /presigned/i);
  assert.doesNotMatch(client, /raw_text:\s*string/);
  assert.doesNotMatch(client, /parsed_text:\s*string/);
  assert.doesNotMatch(client, /readiness_report_body:\s*string/);
  assert.doesNotMatch(client, /prompt:\s*string/);
  assert.doesNotMatch(client, /response:\s*string/);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
  assert.doesNotMatch(client, /encrypted_api_key:\s*string/);
  assert.doesNotMatch(client, /latest_failed_workflow_error_message/);
});

test("Overview page exposes one-step upload and Seed start server action", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/overview/page.tsx");
  const action = sourceSlice(page, "async function uploadAndStartSeedAction", "async function cancelSeedRunAction");
  const nextConfig = await fileText("next.config.ts");
  const webDockerfile = await fileText("../../infra/docker/web.Dockerfile");

  assert.match(action, /"use server"/);
  assert.match(action, /fileFromFormData\(formData,\s*"file"\)/);
  assert.match(action, /await\s+file\.arrayBuffer\(\)/);
  assert.match(action, /createHash\("sha256"\)/);
  assert.match(action, /sizeBytes:\s*file\.size/);
  assert.match(action, /filename:\s*fileNameFromUpload\(file\)/);
  assert.match(action, /const\s+mimeType\s*=\s*supportedSourceMimeType\(file\)/);
  assert.match(page, /function\s+supportedSourceMimeType/);
  assert.match(page, /filename\.endsWith\("\.md"\)/);
  assert.match(page, /filename\.endsWith\("\.pdf"\)/);
  assert.match(page, /SOURCE_FILE_TYPE_UNSUPPORTED/);
  assert.match(action, /mimeType,?/);
  assert.doesNotMatch(action, /application\/octet-stream/);
  assert.match(action, /createSourceFileUpload\(/);
  assert.match(action, /uploadSourceFileObject\(/);
  assert.match(action, /completeSourceFileUpload\(/);
  assert.match(action, /startAnalysisRun\(/);
  assert.match(action, /uploadId:\s*admitted\.upload_id/);
  assert.match(action, /mode:\s*stringFromFormData\(formData,\s*"mode"\)\s*\|\|\s*"full"/);
  assert.match(action, /hintsText|hints:/);
  assert.match(action, /if\s*\(!admitted\.ok\)[\s\S]*return\s+redirect\(/);
  assert.match(action, /if\s*\(!uploaded\.ok\)[\s\S]*return\s+redirect\(/);
  assert.match(action, /if\s*\(!completed\.ok\)[\s\S]*return\s+redirect\(/);
  assert.match(action, /return\s+redirect\(overviewRoute/);
  assert.match(page, /function\s+overviewRoute\([\s\S]*workspacePathForProject\(/);
  assert.doesNotMatch(page, /function\s+overviewRoute\([\s\S]*`\/\$\{input\.tenantSlug\}\/projects\/\$\{input\.projectId\}\/overview/);
  assert.doesNotMatch(action, /mock|fake|MIROFISH_.*LLM|OPENAI_API_KEY|api_key|credential_ref|encrypted_api_key/i);
  assert.match(nextConfig, /serverActions:\s*\{/);
  assert.match(nextConfig, /bodySizeLimit:\s*SOURCE_UPLOAD_BODY_LIMIT|bodySizeLimit:\s*"64mb"/);
  assert.match(nextConfig, /SOURCE_UPLOAD_BODY_LIMIT\s*=\s*"64mb"/);
  assert.match(nextConfig, /middlewareClientMaxBodySize:\s*SOURCE_UPLOAD_BODY_LIMIT|middlewareClientMaxBodySize:\s*"64mb"/);
  assert.match(nextConfig, /distDir:\s*process\.env\.NODE_ENV\s*===\s*"development"\s*\?\s*"\.next-dev"\s*:\s*"\.next"/);
  assert.match(webDockerfile, /COPY --from=build \/app\/next\.config\.ts \.\/next\.config\.ts/);
});

test("Overview Seed upload live harness is opt-in and privacy bounded", async () => {
  const liveTest = await fileText("tests/seed-upload-live.test.mjs");

  assert.match(liveTest, /MIROFISH_WEB_LIVE_SEED_API_BASE_URL/);
  assert.match(liveTest, /MIROFISH_WEB_LIVE_SEED_TENANT_ID/);
  assert.match(liveTest, /MIROFISH_WEB_LIVE_SEED_PROJECT_ID/);
  assert.match(liveTest, /MIROFISH_WEB_LIVE_SEED_SESSION_COOKIE/);
  assert.match(liveTest, /MIROFISH_WEB_LIVE_SEED_ALLOW_MUTATION/);
  assert.match(liveTest, /MIROFISH_WEB_LIVE_SEED_THROWAWAY_PROJECT/);
  assert.match(liveTest, /MIROFISH_WEB_LIVE_SEED_DISPOSABLE_PROJECT_MARKER/);
  assert.match(liveTest, /allowMutation/);
  assert.match(liveTest, /throwawayProject/);
  assert.match(liveTest, /disposableProjectMarker/);
  assert.match(liveTest, /assertSafeApiBaseUrl/);
  assert.match(liveTest, /assertDisposableProject/);
  assert.match(liveTest, /getCurrentUser/);
  assert.doesNotMatch(liveTest, /actorUserId/);
  assert.match(liveTest, /test\.skip/);
  assert.match(liveTest, /createSourceFileUpload/);
  assert.match(liveTest, /uploadSourceFileObject/);
  assert.match(liveTest, /completeSourceFileUpload/);
  assert.match(liveTest, /startSeedRun/);
  assert.match(liveTest, /mimeType:\s*admitted\.mime_type/);
  assert.match(liveTest, /assertNoForbiddenPublicMarkers/);
  assert.match(liveTest, /"pro"\s*\+\s*"vider"/);
  assert.match(liveTest, /"ra"\s*\+\s*"w"/);
  assert.match(liveTest, /"con"\s*\+\s*"tent"/);
  assert.match(liveTest, /"creden"\s*\+\s*"tial"/);
  assert.match(liveTest, /"raw"\s*\+\s*"Body"/);
  assert.match(liveTest, /"source"\s*\+\s*"Text"/);
  assert.doesNotMatch(liveTest, /OPENAI_API_KEY|api_key|encrypted_api_key|credential_ref|object_key|draft|manuscript|prompt|provider_response|raw_body|content_text/i);
});

test("Overview Seed browser live harness is opt-in and privacy bounded", async () => {
  const browserLiveTest = await fileText("tests/seed-upload-browser-live.test.mjs");

  assert.match(browserLiveTest, /MIROFISH_WEB_BROWSER_LIVE_SEED_APP_BASE_URL/);
  assert.match(browserLiveTest, /MIROFISH_WEB_BROWSER_LIVE_SEED_API_BASE_URL/);
  assert.match(browserLiveTest, /MIROFISH_WEB_BROWSER_LIVE_SEED_TENANT_ID/);
  assert.match(browserLiveTest, /MIROFISH_WEB_BROWSER_LIVE_SEED_PROJECT_ID/);
  assert.match(browserLiveTest, /MIROFISH_WEB_BROWSER_LIVE_SEED_SESSION_COOKIE/);
  assert.match(browserLiveTest, /MIROFISH_WEB_BROWSER_LIVE_SEED_ALLOW_MUTATION/);
  assert.match(browserLiveTest, /MIROFISH_WEB_BROWSER_LIVE_SEED_THROWAWAY_PROJECT/);
  assert.match(browserLiveTest, /MIROFISH_WEB_BROWSER_LIVE_SEED_DISPOSABLE_PROJECT_MARKER/);
  assert.match(browserLiveTest, /MIROFISH_WEB_BROWSER_LIVE_SEED_RETRY_RUN_ID/);
  assert.match(browserLiveTest, /MIROFISH_WEB_BROWSER_LIVE_SEED_CONSUME_RETRY_RUN/);
  assert.match(browserLiveTest, /MIROFISH_WEB_BROWSER_LIVE_SEED_REQUIRE_WORKER_RETRY/);
  assert.match(browserLiveTest, /MIROFISH_WEB_BROWSER_LIVE_SEED_APP_DEV_BYPASS/);
  assert.match(browserLiveTest, /waitForSeedWorkerStageEvents/);
  assert.match(browserLiveTest, /browser Seed worker-retry mode cannot consume an external retry run/);
  assert.match(browserLiveTest, /test\.skip/);
  assert.match(browserLiveTest, /hasAnyBrowserLiveConfig/);
  assert.match(browserLiveTest, /assertBrowserLiveConfigComplete/);
  assert.match(browserLiveTest, /browser Seed upload live config is incomplete/);
  assert.match(browserLiveTest, /import\("@playwright\/test"\)/);
  assert.match(browserLiveTest, /chromium\.launch/);
  assert.match(browserLiveTest, /addCookies/);
  assert.match(browserLiveTest, /mirofish_session/);
  assert.match(browserLiveTest, /getCurrentUser/);
  assert.match(browserLiveTest, /assertDisposableProject/);
  assert.match(browserLiveTest, /assertSafeLocalUrl/);
  assert.match(browserLiveTest, /setInputFiles/);
  assert.match(browserLiveTest, /getByRole\("button",\s*\{\s*name:\s*\/Upload and start analysis\/i\s*\}\)/);
  assert.match(browserLiveTest, /getSeedRunSummary/);
  assert.match(browserLiveTest, /getSeedRunEvents/);
  assert.match(browserLiveTest, /fetchBrowserLivePublicJsonWithRawScan/);
  assert.match(browserLiveTest, /new URL\(path,\s*config\.apiBaseUrl\)/);
  assert.match(browserLiveTest, /assertSafeLocalUrl\(config\.apiBaseUrl,\s*"Go API"\)/);
  assert.match(browserLiveTest, /path\.startsWith\("\/"\)/);
  assert.match(browserLiveTest, /path\.startsWith\("\/\/"\)/);
  assert.match(browserLiveTest, /const\s+apiBase\s*=\s*new URL\(config\.apiBaseUrl\)/);
  assert.match(browserLiveTest, /url\.origin,\s*apiBase\.origin/);
  assert.match(browserLiveTest, /headers:\s*\{\s*"X-Tenant-Id":\s*config\.tenantId,\s*Cookie:\s*`mirofish_session=\$\{config\.sessionCookie\}`,\s*\}/s);
  assert.match(browserLiveTest, /const\s+rawText\s*=\s*await\s+response\.text\(\)/);
  assert.match(browserLiveTest, /assertNoForbiddenPublicMarkers\(rawText,\s*\{\s*sourceText,\s*sessionCookie:\s*config\.sessionCookie,\s*\}\)/s);
  assert.match(browserLiveTest, /JSON\.parse\(rawText\)/);
  assert.match(browserLiveTest, /fetchBrowserLivePublicJsonWithRawScan\(\s*config,\s*"\/v1\/me"/);
  assert.match(browserLiveTest, /fetchBrowserLivePublicJsonWithRawScan\(\s*config,\s*`\/v1\/seed-runs\/\$\{runId\}`/);
  assert.match(browserLiveTest, /fetchBrowserLivePublicJsonWithRawScan\(\s*config,\s*`\/v1\/seed-runs\/\$\{runId\}\/events`/);
  assert.match(browserLiveTest, /fetchBrowserLivePublicJsonWithRawScan\(\s*config,\s*`\/v1\/seed-runs\/\$\{runId\}\/events\?after_event_id=\$\{encodeURIComponent\(queuedEvent\.event_id\)\}`/);
  assert.match(browserLiveTest, /workflow\.queued/);
  assert.match(browserLiveTest, /workflow\.retry_requested/);
  assert.match(browserLiveTest, /Recent analysis/);
  assert.match(browserLiveTest, /Seed events/);
  assert.match(browserLiveTest, /assertRunControlIdentity/);
  assert.match(browserLiveTest, /openOperationalDetails/);
  assert.match(browserLiveTest, /Cancel analysis/);
  assert.match(browserLiveTest, /Retry analysis/);
  assert.match(browserLiveTest, /seq 1/);
  assert.match(browserLiveTest, /afterEventId:\s*queuedEvent\.event_id/);
  assert.match(browserLiveTest, /assertSeedRunBrowserControlsReflectStatus/);
  assert.match(browserLiveTest, /assertConsumableRetryableSeedRun/);
  assert.match(browserLiveTest, /preparedRetryRun\.status === "completed" && config\.consumeRetryRun/);
  assert.match(browserLiveTest, /afterEventId:\s*retryCursorEvent\.event_id/);
  assert.match(browserLiveTest, /Seed cursor replay rendered the cursor event/);
  assert.match(browserLiveTest, /retry_requested/);
  assert.match(browserLiveTest, /after_event_id/);
  assert.match(browserLiveTest, /maxRetryableSequence/);
  assert.match(browserLiveTest, /assertNoForbiddenPublicMarkers/);
  assert.doesNotMatch(browserLiveTest, /"ra"\s*\+\s*"w"/);
  assert.match(browserLiveTest, /forbiddenKeys[\s\S]*"body"/);
  assert.match(browserLiveTest, /forbiddenKeys[\s\S]*"source"/);
  assert.match(browserLiveTest, /forbiddenKeys[\s\S]*"token"/);
  assert.match(browserLiveTest, /forbiddenKeys[\s\S]*"sessioncookie"/);
  assert.match(browserLiveTest, /forbiddenKeys[\s\S]*"privatecontent"/);
  assert.match(browserLiveTest, /sessionCookie:\s*config\.sessionCookie/);
  assert.match(browserLiveTest, /markers\.push\(\[options\.sessionCookie,\s*"session cookie value"\]\)/);
  assert.match(browserLiveTest, /"private"\s*\+\s*"Content"/);
  assert.match(browserLiveTest, /redactAssertionMessage/);
  assert.match(browserLiveTest, /"api"\s*\+\s*"\s+"\s*\+\s*"key"/);
  assert.match(browserLiveTest, /"encrypted"\s*\+\s*"\s+"\s*\+\s*"credential"/);
  assert.match(browserLiveTest, /"\\\\\\""\s*\+\s*"ob"\s*\+\s*"ject"\s*\+\s*"\\\\\\""/);
  assert.match(browserLiveTest, /"object"\s*\+\s*"\s+"\s*\+\s*"key"/);
  assert.doesNotMatch(browserLiveTest, /actorUserId|MIROFISH_WEB_BROWSER_LIVE_SEED_ACTOR|X-User-Id|OPENAI_API_KEY|api_key|encrypted_api_key|credential_ref|object_key|draft|manuscript|prompt|provider_response|raw_body|content_text/i);
});

test("Overview Seed shell renders explicit source file and Seed run states", async () => {
  const shell = await fileText("components/overview-seed-shell.tsx");
  const wall = await fileText("components/overview-seed-progress-wall.tsx");
  const overviewSurface = `${shell}\n${wall}`;

  assert.match(shell, /Source files/);
  assert.match(shell, /Project health/);
  assert.match(shell, /projectOverview\.ok/);
  assert.match(shell, /source_file_count/);
  assert.match(shell, /seed_run_count/);
  assert.match(shell, /active_workflow_run_id/);
  assert.match(shell, /active_workflow_type/);
  assert.match(shell, /active_workflow_status/);
  assert.match(shell, /OverviewActivityLogLive/);
  assert.doesNotMatch(shell, /zh="项目状态"/);
  assert.doesNotMatch(shell, /zh="当前分析"/);
  assert.match(shell, /Asset records/);
  assert.match(shell, /Graph nodes/);
  assert.match(shell, /Graph edges/);
  assert.match(shell, /Worldline sessions/);
  assert.match(shell, /Worldline events/);
  assert.match(shell, /Character interactions/);
  assert.match(shell, /Writer runs/);
  assert.match(shell, /Latest interruption/);
  assert.match(shell, /Interruption updated/);
  assert.match(shell, /asset_count/);
  assert.match(shell, /graph_node_count/);
  assert.match(shell, /graph_edge_count/);
  assert.match(shell, /worldline_session_count/);
  assert.match(shell, /worldline_event_count/);
  assert.match(shell, /character_interaction_count/);
  assert.match(shell, /writer_run_count/);
  assert.match(shell, /latest_failed_workflow_run_id/);
  assert.match(shell, /latest_failed_workflow_type/);
  assert.match(shell, /latest_failed_workflow_error_code/);
  assert.match(shell, /latest_failed_workflow_updated_at/);
  assert.match(shell, /readiness_snapshot_id/);
  assert.match(shell, /readiness_run_id/);
  assert.match(shell, /projectOverview\.code/);
  assert.match(shell, /Project readiness/);
  assert.match(shell, /projectReadiness\.ok/);
  assert.match(shell, /ready_asset_count/);
  assert.match(shell, /ready_entity_count/);
  assert.match(shell, /ready_relationship_count/);
  assert.match(shell, /ready_world_rule_count/);
  assert.match(shell, /Import manuscript/);
  assert.match(shell, /uploadAndStartSeedAction/);
  assert.match(shell, /OverviewSeedUploadForm/);
  assert.match(shell, /OverviewSeedProgressWall/);
  const uploadForm = await fileText("components/overview-seed-upload-form.tsx");
  assert.match(uploadForm, /type="file"/);
  assert.match(uploadForm, /name="file"/);
  assert.match(uploadForm, /name="mode"/);
  assert.match(uploadForm, /SOURCE_UPLOAD_MAX_BYTES\s*=\s*64\s*\*\s*1024\s*\*\s*1024/);
  assert.match(shell, /Complete upload/);
  assert.match(shell, /Start analysis/);
  assert.match(shell, /completeUploadAction/);
  assert.match(shell, /startSeedRunAction/);
  assert.match(shell, /type="hidden"\s+name="uploadId"\s+value=\{file\.upload_id\}/);
  assert.match(shell, /file\.parse_status !== "pending"/);
  assert.match(shell, /file\.parse_status !== "uploaded"/);
  assert.doesNotMatch(shell, /Admit source file|Upload object|Complete this upload|uploadSourceObjectAction|<label htmlFor=".*upload-id"|placeholder=".*upload/i);
  assert.match(shell, /Analysis history/);
  assert.match(shell, /Inspect/);
  assert.match(overviewSurface, /name="runId"/);
  // Authors see progress/results on the main path; raw event dumps stay out of the secondary rail.
  assert.match(shell, /Project diagnostics \(optional\)|项目诊断（可选）/);
  assert.match(shell, /Analysis progress|分析进度/);
  assert.match(shell, /cancelSeedRunAction/);
  assert.match(shell, /retrySeedRunAction/);
  assert.match(wall, /Cancel analysis/);
  assert.match(wall, /Retry analysis/);
  assert.match(shell, /formatBeijingTimeLabel|formatBeijingTime/);
  assert.match(shell, /projectReadiness\.code/);
  assert.match(shell, /sourceFiles\.ok/);
  assert.match(shell, /seedRuns\.ok/);
  assert.match(shell, /selectedSeedRun\.ok/);
  assert.match(shell, /seedEvents\?\.ok|seedEvents\.ok/);
  assert.match(shell, /sourceFiles\.code/);
  assert.match(shell, /seedActivityLog/);
  assert.match(shell, /seed\.sequential_reading\.progress/);
  assert.match(shell, /OverviewActivityLogLive/);
  const activityLive = await fileText("components/overview-activity-log-live.tsx");
  assert.match(activityLive, /overview-activity-log/);
  assert.match(activityLive, /关键进度|Key progress/);
  assert.match(activityLive, /实时 SSE|Live SSE/);
  assert.match(activityLive, /connectAnalysisEventStream/);
  assert.match(shell, /overview-progress-thin/);
  assert.match(shell, /<FailureText \/>/);
  assert.doesNotMatch(shell, /object key/i);
  assert.doesNotMatch(shell, /presigned/i);
  assert.doesNotMatch(shell, /raw text|prompt|credential|draft_text|manuscript_text/i);
  assert.doesNotMatch(shell, /readiness report body/i);
  assert.doesNotMatch(shell, /mock/i);
});

test("Overview Seed controls are status-gated and retry resets successful event cursor", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/overview/page.tsx");
  const shell = await fileText("components/overview-seed-shell.tsx");
  const wall = await fileText("components/overview-seed-progress-wall.tsx");
  const controls = await import(`../components/overview-seed-run-controls.ts?seedControls=${Date.now()}`);
  const cancelAction = sourceSlice(page, "async function cancelSeedRunAction", "async function retrySeedRunAction");
  const retryAction = sourceSlice(page, "async function retrySeedRunAction", "return (");

  const statusCases = [
    { status: "queued", cancel: true, retry: false },
    { status: "running", cancel: true, retry: false },
    { status: "completed", cancel: false, retry: false },
    { status: "failed", cancel: false, retry: true },
    { status: "cancelled", cancel: false, retry: true },
    { status: " FAILED ", cancel: false, retry: true },
  ];
  for (const statusCase of statusCases) {
    const run = { ok: true, status: statusCase.status };
    assert.equal(controls.canCancelSeedRun(run), statusCase.cancel, `cancel gate for ${statusCase.status}`);
    assert.equal(controls.canRetrySeedRun(run), statusCase.retry, `retry gate for ${statusCase.status}`);
  }
  assert.equal(controls.canCancelSeedRun(null), false);
  assert.equal(controls.canRetrySeedRun(null), false);
  assert.equal(controls.canCancelSeedRun({ ok: false, status: "running" }), false);
  assert.equal(controls.canRetrySeedRun({ ok: false, status: "failed" }), false);

  assert.match(shell, /const\s+cancelSeedRunEnabled\s*=\s*canCancelSeedRun\(selectedSeedRun\)/);
  assert.match(shell, /const\s+retrySeedRunEnabled\s*=\s*canRetrySeedRun\(selectedSeedRun\)/);
  assert.match(wall, /disabled=\{!cancelSeedRunEnabled\}/);
  assert.match(wall, /disabled=\{!retrySeedRunEnabled\}/);
  assert.doesNotMatch(shell, /const\s+hasSelectedRun\s*=/);
  assert.doesNotMatch(`${shell}\n${wall}`, /disabled=\{!hasSelectedRun\}/);

  assert.match(cancelAction, /afterEventId:\s*query\.after_event_id\s*\?\?\s*query\.afterEventId\s*\?\?\s*""/);
  assert.match(cancelAction, /cancelAnalysisRun/);
  assert.match(retryAction, /ANALYSIS_RETRY_USE_NEW_RUN/);
  assert.match(retryAction, /afterEventId:\s*query\.after_event_id\s*\?\?\s*query\.afterEventId\s*\?\?\s*""/);
  assert.doesNotMatch(retryAction, /retrySeedRun\(/);
  assert.doesNotMatch(`${shell}\n${wall}\n${retryAction}\n${cancelAction}`, /raw_body|content_text|draft_text|manuscript_text|provider_response|credential_ref|encrypted_api_key|api_key|object_key/i);
});

test("Next app shell declares tenant/project LLM Facility route", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/llm-facility/page.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /upsertLLMModuleBinding/);
  assert.match(page, /createLLMChannel/);
  assert.match(page, /updateLLMChannel/);
  assert.match(page, /deleteLLMChannel/);
  assert.match(page, /syncLLMChannelModels/);
  assert.match(page, /getLLMSettings/);
  assert.match(page, /deleteLLMModuleBinding/);
  assert.match(page, /optionalPositiveNumberFromFormData\(formData,\s*"moduleMaxConcurrency"\)/);
  assert.match(page, /settings\.max_concurrency\s*=\s*maxConcurrency/);
  assert.match(page, /bindModuleAction/);
  assert.match(page, /batchBindModuleAction/);
  assert.match(page, /loadChannelModels/);
  assert.match(page, /clearBindingAction/);
  assert.match(page, /createChannelAction/);
  assert.match(page, /updateChannelAction/);
  assert.match(page, /deleteChannelAction/);
  assert.match(page, /syncChannelAction/);
  assert.match(page, /testModelAction/);
  assert.match(page, /checkProviderHealth/);
  assert.match(page, /healthStatus/);
  assert.match(page, /llmChannelAnchorId/);
  assert.match(page, /focusChannelId/);
  assert.match(page, /channel: channelQueryValue\(selectedChannelId\)/);
  assert.match(page, /getLLMChannels/);
  assert.match(page, /getLLMChannelModels/);
  assert.match(page, /getLLMModules/);
  assert.match(page, /getLLMModuleBindings/);
  assert.match(page, /resolveLLMModuleBinding/);
  assert.match(page, /getLLMActivity/);
  assert.match(page, /getLLMUsage/);
  assert.match(page, /query\.module\?\.trim\(\) \|\| query\.moduleKey\?\.trim\(\)/);
  assert.match(page, /query\.channel\?\.trim\(\) \|\| query\.channelId\?\.trim\(\)/);
  assert.match(page, /query\.run\?\.trim\(\) \|\| query\.runId\?\.trim\(\)/);
  assert.match(page, /hasDefaultChannelQuery/);
  assert.match(page, /canonicalSearch\.delete\("channel"\)/);
  assert.match(page, /workspacePathForProject/);
  assert.doesNotMatch(page, /redirect\(`\/\$\{tenantSlug\}\/projects\/\$\{projectId\}\/llm-facility/);
  assert.match(page, /LLMFacilityShell/);
});

test("Next app shell declares tenant/project Asset Library route", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/assets/page.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /getProjectAssets/);
  assert.match(page, /getAssetFacets/);
  assert.match(page, /getArchiveAssetMemories/);
  assert.match(page, /getArchiveAssetMemoryEvents/);
  assert.match(page, /adoptArchiveMemory/);
  assert.match(page, /rejectArchiveMemory/);
  assert.match(page, /searchAssets/);
  assert.match(page, /createAsset/);
  assert.match(page, /updateAsset/);
  assert.match(page, /deleteAsset/);
  assert.match(page, /adoptAsset/);
  assert.match(page, /bulkActionAssets/);
  assert.match(page, /startAssetIngestion/);
  assert.match(page, /startAssetReindex/);
  assert.match(page, /memoryAssetId/);
  assert.match(page, /memoryAssetAction/);
  assert.match(page, /adoptArchiveMemoryAction/);
  assert.match(page, /rejectArchiveMemoryAction/);
  assert.match(page, /createAssetAction/);
  assert.match(page, /updateAssetAction/);
  assert.match(page, /deleteAssetAction/);
  assert.match(page, /adoptAssetAction/);
  assert.match(page, /bulkAssetAction/);
  assert.match(page, /ingestAssetAction/);
  assert.match(page, /reindexAssetsAction/);
  assert.match(page, /AssetLibraryShell/);
});

test("legacy Asset Library entry routes redirect through shared entry path", async () => {
  const archiveRoute = await fileText("app/archive-library/page.tsx");
  const assetRoute = await fileText("app/asset-library/page.tsx");
  const devAccess = await fileText("lib/dev-access.ts");

  for (const route of [archiveRoute, assetRoute]) {
    assert.match(route, /redirect/);
    assert.match(route, /devEntryRedirectPath\(\)/);
    assert.doesNotMatch(route, /mock/i);
    assert.doesNotMatch(route, /api_key|encrypted_api_key|credential_ref/i);
  }
  assert.match(devAccess, /export function devEntryRedirectPath/);
  assert.match(devAccess, /isDevLoginBypassEnabled\(\)\s*\?\s*devWorkspacePath\("overview"\)\s*:\s*"\/login"/);
});

test("Next app shell declares tenant/project Worldline route with saved-path read side", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/worldline/page.tsx");
  const shell = await fileText("components/worldline-shell.tsx");
  const client = await fileText("lib/api.ts");
  const legacyRoute = await fileText("app/worldline/page.tsx");
  const nav = await fileText("components/project-nav.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /getWorldlineSavedPaths/);
  assert.match(page, /getWorldlineSessions/);
  assert.match(page, /getWorldlineTimeline/);
  assert.match(page, /getWorldlineEvents/);
  assert.match(page, /getWorldlinePreparation/);
  assert.match(page, /getWorldlinePreparedAgents/);
  assert.match(page, /startWorldlineSession/);
  assert.match(page, /createWorldlinePreparation/);
  assert.match(page, /injectWorldlineVariable/);
  assert.match(page, /createWorldlineSavedPath/);
  assert.match(page, /adoptWorldlineEvent/);
  assert.match(page, /updateWorldlineEvent/);
  assert.match(page, /startWorldlineStep/);
  assert.match(page, /startWorldlineSessionAction/);
  assert.match(page, /startWorldlineStepAction/);
  assert.match(page, /createWorldlinePreparationAction/);
  assert.match(page, /injectWorldlineVariableAction/);
  assert.match(page, /createWorldlineSavedPathAction/);
  assert.match(page, /adoptWorldlineEventAction/);
  assert.match(page, /updateWorldlineEventAction/);
  assert.match(page, /worldlineSessionStatus/);
  assert.match(page, /worldlinePreparationStatus/);
  assert.match(page, /worldlineVariableStatus/);
  assert.match(page, /worldlineSavedPathStatus/);
  assert.match(page, /worldlineEventAdoptionStatus/);
  assert.match(page, /worldlineEventMutationStatus/);
  assert.match(page, /worldlineStepStatus/);
  assert.match(page, /WorldlineShell/);
  assert.match(shell, /savedPaths\.ok/);
  assert.match(shell, /sessions\.ok/);
  assert.match(shell, /timeline\.ok/);
  assert.match(shell, /events\.ok/);
  assert.match(shell, /preparation/);
  assert.match(shell, /preparedAgents/);
  assert.match(shell, /Start session/);
  assert.match(shell, /Step once|Step session|推进一步/);
  assert.match(shell, /Inject variable|Variable injection|注入变量/);
  assert.match(shell, /Save path/);
  assert.match(shell, /Prepare agents/);
  assert.match(shell, /Prepared agents/);
  assert.match(shell, /Session history/);
  assert.match(shell, /Timeline/);
  assert.match(shell, /Candidate events/);
  assert.match(shell, /Edit event/);
  assert.match(shell, /Adopt event/);
  assert.match(shell, /worldline-timeline-primary|worldline-simulate-toolbar/);
  assert.match(shell, /timeline\.ok/);
  assert.match(shell, /events\.ok/);
  assert.match(shell, /startWorldlineSessionAction/);
  assert.match(shell, /startWorldlineStepAction/);
  assert.match(shell, /createWorldlinePreparationAction/);
  assert.match(shell, /injectWorldlineVariableAction/);
  assert.match(shell, /createWorldlineSavedPathAction/);
  assert.match(shell, /adoptWorldlineEventAction/);
  assert.match(shell, /updateWorldlineEventAction/);
  assert.match(shell, /name="goal"/);
  assert.match(shell, /name="stepMode"/);
  assert.match(shell, /name="variableName"/);
  assert.match(shell, /name="impactAxis"/);
  assert.match(shell, /name="savedPathTitle"/);
  assert.match(shell, /name="selectedEventIds"/);
  assert.match(shell, /name="eventTitle"/);
  assert.match(shell, /name="eventSummary"/);
  assert.match(shell, /name="eventKind"/);
  assert.match(shell, /name="preparationGoal"/);
  assert.match(shell, /name="anchorPathId"/);
  assert.match(shell, /worldlineSessionStatus/);
  assert.match(shell, /worldlinePreparationStatus/);
  assert.match(shell, /worldlineSavedPathStatus/);
  assert.match(shell, /worldlineEventAdoptionStatus/);
  assert.match(shell, /worldlineEventMutationStatus/);
  assert.match(shell, /worldlineStepStatus/);
  assert.match(shell, /!preparation\.ok/);
  assert.match(shell, /!preparedAgents\.ok/);
  assert.match(shell, /sessions\.ok/);
  assert.match(shell, /savedPaths\.ok/);
  assert.match(shell, /<FailureText \/>/);
  assert.match(shell, /path\.path_id/);
  assert.match(client, /CreateWorldlineSavedPathInput/);
  assert.match(client, /createWorldlineSavedPath/);
  assert.match(client, /adoptWorldlineEvent/);
  assert.match(client, /UpdateWorldlineEventInput/);
  assert.match(client, /updateWorldlineEvent/);
  assert.match(client, /StartWorldlineStepInput/);
  assert.match(client, /startWorldlineStep/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}\/saved-paths`/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}\/steps`/);
  assert.match(client, /\/v1\/worldline-events\/\$\{input\.eventId\}\/adoptions`/);
  assert.match(client, /\/v1\/worldline-events\/\$\{input\.eventId\}`/);
  assert.match(client, /selected_event_ids/);
  assert.doesNotMatch(shell, /api_key|encrypted_api_key|credential_ref/i);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
  assert.match(legacyRoute, /redirect/);
  assert.match(legacyRoute, /devEntryRedirectPath\(\)/);
  assert.doesNotMatch(legacyRoute, /mock/i);
  assert.match(nav, /\/worldline/);
  assert.match(nav, /Worldline/);
});

test("worldline API client exposes preparation endpoints without credential fields", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /WorldlineEventRecord/);
  assert.match(client, /WorldlineEventsSummary/);
  assert.match(client, /WorldlinePreparationRecord/);
  assert.match(client, /WorldlinePreparedAgentRecord/);
  assert.match(client, /getWorldlineEvents/);
  assert.match(client, /createWorldlinePreparation/);
  assert.match(client, /getWorldlinePreparation/);
  assert.match(client, /getWorldlinePreparedAgents/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}\/events/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/worldlines\/preparations`/);
  assert.match(client, /\/v1\/worldline-preparations\/\$\{input\.prepareId\}`/);
  assert.match(client, /\/v1\/worldline-preparations\/\$\{input\.prepareId\}\/agents`/);
  assert.match(client, /X-Tenant-Id/);
  assert.match(client, /X-User-Id/);
  assert.doesNotMatch(client, /body_text:\s*string/);
  assert.doesNotMatch(client, /content_text:\s*string/);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
  assert.doesNotMatch(client, /encrypted_api_key:\s*string/);
});

test("worldline API client exposes metadata-only variable injection", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /WorldlineVariableRecord/);
  assert.match(client, /WorldlineVariableSummary/);
  assert.match(client, /injectWorldlineVariable/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}\/variables`/);
  assert.match(client, /impact_axis/);
  assert.match(client, /locked/);
  assert.match(client, /X-Tenant-Id/);
  assert.match(client, /X-User-Id/);
  assert.doesNotMatch(client, /body_text:\s*string/);
  assert.doesNotMatch(client, /content_text:\s*string/);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
  assert.doesNotMatch(client, /encrypted_api_key:\s*string/);
});

test("Next app shell declares tenant/project Character Console route", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/character-console/page.tsx");
  const shell = await fileText("components/character-console-shell.tsx");
  const legacyRoute = await fileText("app/character-console/page.tsx");
  const nav = await fileText("components/project-nav.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /CharacterConsoleShell/);
  assert.match(page, /listCharacterInteractions/);
  assert.match(page, /interactions=/);
  assert.match(shell, /worldlineSessions\.ok/);
  assert.match(shell, /<FailureText \/>/);
  assert.match(shell, /CharacterInteractionsSummary/);
  assert.match(shell, /interactions\.ok/);
  assert.match(shell, /Convert to chapter draft/);
  assert.doesNotMatch(shell, /mock/i);
  assert.doesNotMatch(shell, /api_key|encrypted_api_key|credential_ref/i);
  assert.match(legacyRoute, /redirect/);
  assert.match(legacyRoute, /devEntryRedirectPath\(\)/);
  assert.doesNotMatch(legacyRoute, /mock/i);
  assert.match(nav, /\/character-console/);
  assert.match(nav, /Characters/);
});

test("Character Console route exposes create interaction metadata form and action", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/character-console/page.tsx");
  const shell = await fileText("components/character-console-shell.tsx");

  assert.match(page, /createCharacterInteractionAction/);
  assert.match(page, /createCharacterInteraction/);
  assert.match(page, /appendCharacterInteractionTurnAction/);
  assert.match(page, /appendCharacterInteractionTurn/);
  assert.match(page, /updateCharacterInteractionStatusAction/);
  assert.match(page, /updateCharacterInteractionStatus/);
  assert.match(page, /getCharacterInteraction/);
  assert.match(page, /listCharacterInteractionTurns/);
  assert.match(page, /getCharacterInteractionEvents/);
  assert.match(page, /getCharacterProposals/);
  assert.match(page, /adoptCharacterProposal/);
  assert.match(page, /convertCharacterInteractionToChapterDraft/);
  assert.match(page, /getWorldlineEvents/);
  assert.match(page, /getWorldlinePreparedAgents/);
  assert.match(page, /getWorldlineSavedPaths/);
  assert.match(page, /getWorldlineSessions/);
  assert.match(page, /getStoryGraphView/);
  assert.match(page, /viewId:\s*"current"/);
  assert.match(page, /types:\s*\[\s*"character",\s*"organization",\s*"location",\s*"plot_thread"\s*\]/);
  assert.match(page, /includeEdges:\s*false/);
  assert.match(page, /inspectWorldlineEventAnchorsAction/);
  assert.match(page, /inspectWorldlinePreparationAgentsAction/);
  assert.match(page, /inspectCharacterInteractionAction/);
  assert.match(page, /inspectCharacterInteractionTurnsAction/);
  assert.match(page, /inspectCharacterInteractionEventsAction/);
  assert.match(page, /convertCharacterInteractionToChapterDraftAction/);
  assert.match(page, /adoptCharacterProposalAction/);
  assert.match(page, /searchParams/);
  assert.match(page, /anchor_session_id/);
  assert.match(page, /characterConsoleStatusRoute/);
  assert.match(page, /prepare_id/);
  assert.match(page, /selected_interaction_id/);
  assert.match(page, /turns_interaction_id/);
  assert.match(page, /runtime_status/);
  assert.match(page, /runtime_code/);
  assert.match(page, /runtime_message/);
  assert.match(page, /interaction_status/);
  assert.match(page, /interaction_code/);
  assert.match(page, /interaction_message/);
  assert.match(page, /CHARACTER_INTERACTION_WRITER_RUN_QUEUED/);
  assert.match(page, /Writer run \$\{result\.run_id\} queued/);
  assert.match(page, /turn_status/);
  assert.match(page, /turn_code/);
  assert.match(page, /turn_message/);
  assert.match(page, /optionalJsonObjectFromFormData/);
  assert.match(page, /redirect/);

  assert.match(shell, /createCharacterInteractionAction/);
  assert.match(shell, /appendCharacterInteractionTurnAction/);
  assert.match(shell, /updateCharacterInteractionStatusAction/);
  assert.match(shell, /inspectCharacterInteractionAction/);
  assert.match(shell, /inspectCharacterInteractionTurnsAction/);
  assert.match(shell, /inspectCharacterInteractionEventsAction/);
  assert.match(shell, /convertCharacterInteractionToChapterDraftAction/);
  assert.match(shell, /adoptCharacterProposalAction/);
  assert.match(shell, /CharacterProposalReview/);
  assert.match(shell, /proposal\.proposal_type/);
  assert.match(shell, /proposal\.lifecycle === "candidate"/);
  assert.match(shell, /name="proposalInteractionId"/);
  assert.match(shell, /name="proposalAssetId"/);
  assert.match(shell, /inspectWorldlineEventAnchorsAction/);
  assert.match(shell, /anchorSessionId/);
  assert.match(shell, /interactionStatus/);
  assert.match(shell, /preparedAgents/);
  assert.match(shell, /prepareId/);
  assert.match(shell, /graphView/);
  assert.match(shell, /runtimeStatus/);
  assert.match(shell, /selectedInteraction/);
  assert.match(shell, /selectedTurns/);
  assert.match(shell, /savedPaths/);
  assert.match(shell, /worldlineEvents/);
  assert.match(shell, /worldlineSessions/);
  assert.match(shell, /CharacterInteractionDetailSummary/);
  assert.match(shell, /CharacterInteractionTurnsSummary/);
  assert.match(shell, /StoryGraphViewSummary/);
  assert.match(shell, /WorldlineSavedPathsSummary/);
  assert.match(shell, /WorldlineEventsSummary/);
  assert.match(shell, /WorldlinePreparedAgentsSummary/);
  assert.match(shell, /graphView\.ok/);
  assert.match(shell, /graphView\.nodes/);
  assert.match(shell, /savedPaths\.ok/);
  assert.match(shell, /savedPaths\.items/);
  assert.match(shell, /worldlineEvents\.ok/);
  assert.match(shell, /worldlineEvents\.items/);
  assert.match(shell, /preparedAgents\.ok/);
  assert.match(shell, /preparedAgents\.items/);
  assert.match(shell, /selectedInteraction\.ok/);
  assert.match(shell, /selectedInteraction\.turns/);
  assert.match(shell, /WorldlineSessionsSummary/);
  assert.match(shell, /worldlineSessions\.ok/);
  assert.match(shell, /worldlineSessions\.items/);
  assert.match(shell, /!preparedAgents\.ok/);
  assert.match(shell, /!worldlineEvents\.ok/);
  assert.match(shell, /!worldlineSessions\.ok/);
  assert.match(shell, /!graphView\.ok/);
  assert.match(shell, /<FailureText \/>/);
  assert.match(shell, /turnStatus/);
  assert.match(shell, /name="anchorSessionId"/);
  assert.match(shell, /name="prepareId"/);
  assert.match(shell, /name="worldlineSessionId"/);
  assert.match(shell, /name="anchorType"/);
  assert.match(shell, /name="anchorId"/);
  assert.match(shell, /name="povAgentId"/);
  assert.match(shell, /name="mode"/);
  assert.match(shell, /name="title"/);
  assert.match(shell, /name="summary"/);
  assert.match(shell, /name="interactionId"/);
  assert.match(shell, /name="actorType"/);
  assert.match(shell, /name="actorId"/);
  assert.match(shell, /name="turnKind"/);
  assert.match(shell, /name="turnSummary"/);
  assert.doesNotMatch(shell, /name="actionJson"|name="worldStateDeltaJson"/);
  assert.doesNotMatch(shell, /name="traceId"/);
  assert.match(shell, /name="selectedInteractionId"/);
  assert.match(shell, /name="turnsInteractionId"/);
  assert.doesNotMatch(shell, /name="runtimeInteractionId"/);
  assert.match(shell, /name="statusInteractionId"/);
  assert.match(shell, /name="interactionNextStatus"/);
  assert.match(shell, /name="convertInteractionId"/);
  assert.match(shell, /name="targetChapterId"/);
  assert.match(shell, /name="targetSceneId"/);
  assert.match(shell, /name="povMode"/);
  assert.match(shell, /Create interaction/);
  assert.match(shell, /View interaction/);
  assert.match(shell, /Load turns/);
  assert.doesNotMatch(shell, /Check runtime events/);
  assert.match(shell, /Request chapter draft/);
  assert.match(shell, /Chapter draft request submitted/);
  assert.match(shell, /Load worldline events/);
  assert.match(shell, /Load prepared agents/);
  assert.match(shell, /Graph nodes/);
  assert.match(shell, /Graph node anchors/);
  assert.match(shell, /graphView\.nodes\.slice\(0,\s*4\)/);
  assert.match(shell, /node\.node_type/);
  assert.match(shell, /node\.lifecycle/);
  assert.match(shell, /node\.summary/);
  assert.match(shell, /Character dossier/);
  assert.match(shell, /selectedInteraction\.pov_agent_id/);
  assert.match(shell, /preparedAgents\.items\.find/);
  assert.match(shell, /dossierAgent\.role/);
  assert.match(shell, /dossierAgent\.status/);
  assert.match(shell, /dossierAgent\.display_name/);
  assert.match(shell, /dossierAgent\.agent_id/);
  assert.doesNotMatch(shell, /dossierAgent\.source_asset_id/);
  assert.match(shell, /dossierAgent\.summary/);
  assert.match(shell, /agentHistoryTurns/);
  assert.match(shell, /selectedInteraction\.turns\.filter/);
  assert.match(shell, /turn\.actor_id === selectedPovAgentId/);
  assert.match(shell, /turn\.actor_type === "user"/);
  assert.match(shell, /Character turn history/);
  assert.match(shell, /agentHistoryTurns\.slice\(0,\s*6\)/);
  assert.match(shell, /historyTurn\.turn_order/);
  assert.match(shell, /historyTurn\.summary/);
  assert.match(shell, /Saved paths/);
  assert.match(shell, /Record turn/);
  assert.match(shell, /Recorded turns/);
  assert.match(shell, /Turn replay/);
  assert.match(shell, /SelectedPublicTurnReplay/);
  assert.match(shell, /selectedTurns\.ok/);
  assert.match(shell, /selectedTurns\.items/);
  assert.match(shell, /turn\.turn_order/);
  assert.match(shell, /turn\.actor_type/);
  assert.match(shell, /turn\.turn_kind/);
  assert.doesNotMatch(shell, /turn\.action/);
  assert.doesNotMatch(shell, /turn\.world_state_delta/);
  assert.match(shell, /name="interactionNextStatus" value="saved"/);
  assert.match(shell, /name="interactionNextStatus" value="archived"/);
  assert.doesNotMatch(shell, /input_text|output_text|body_text|content_text/i);
  assert.doesNotMatch(shell, /api_key|encrypted_api_key|credential_ref/i);
});

test("character console API client exposes metadata-only interaction endpoints", async () => {
  const client = await fileText("lib/api.ts");
  const characterClient = [
    sourceSlice(client, "export type CharacterInteractionRecord", "export type AssetSummary"),
    sourceSlice(client, "export async function listCharacterInteractions", "export async function createWorldlinePreparation"),
    sourceSlice(client, "async function decodeCharacterInteractionsResponse", "async function decodeAssetFacetsResponse"),
    sourceSlice(client, "function decodeCharacterInteractionRecord", "function decodeAssetFacetBucket"),
  ].join("\n");

  assert.match(client, /CharacterInteractionRecord/);
  assert.match(client, /CharacterInteractionTurnRecord/);
  assert.match(client, /CreateCharacterInteractionInput/);
  assert.match(client, /UpdateCharacterInteractionStatusInput/);
  assert.match(client, /CharacterInteractionsSummary/);
  assert.match(client, /CharacterInteractionDetailSummary/);
  assert.match(client, /CharacterInteractionSummary/);
  assert.match(client, /CharacterInteractionTurnsSummary/);
  assert.match(client, /CharacterInteractionEventsSummary/);
  assert.match(client, /CharacterInteractionChapterDraftSummary/);
  assert.match(client, /CharacterProposalsSummary/);
  assert.match(client, /CharacterProposalAdoptionSummary/);
  assert.match(client, /createCharacterInteraction/);
  assert.match(client, /updateCharacterInteractionStatus/);
  assert.match(client, /listCharacterInteractions/);
  assert.match(client, /getCharacterInteraction/);
  assert.match(client, /appendCharacterInteractionTurn/);
  assert.match(client, /listCharacterInteractionTurns/);
  assert.match(client, /getCharacterInteractionEvents/);
  assert.match(client, /convertCharacterInteractionToChapterDraft/);
  assert.match(client, /getCharacterProposals/);
  assert.match(client, /adoptCharacterProposal/);
  assert.match(client, /method:\s*"POST"/);
  assert.match(client, /worldline_session_id:\s*input\.worldlineSessionId/);
  assert.match(client, /anchor_type:\s*input\.anchorType/);
  assert.match(client, /anchor_id:\s*input\.anchorId/);
  assert.match(client, /pov_agent_id:\s*input\.povAgentId/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/character-interactions`/);
  assert.match(client, /\/v1\/character-interactions\/\$\{input\.interactionId\}`/);
  assert.match(client, /method:\s*"PATCH"/);
  assert.match(client, /status:\s*input\.status/);
  assert.match(client, /items:\s*payload\.items\.map\(\(item\) => decodeCharacterInteractionTurnRecord\(item\)\)/);
  assert.match(client, /\/v1\/character-interactions\/\$\{input\.interactionId\}\/turns`/);
  assert.match(client, /\/v1\/character-interactions\/\$\{input\.interactionId\}\/events`/);
  assert.match(client, /\/v1\/character-interactions\/\$\{input\.interactionId\}\/chapter-drafts`/);
  assert.match(client, /\/v1\/character-interactions\/\$\{input\.interactionId\}\/proposals`/);
  assert.match(client, /\/v1\/character-interactions\/\$\{input\.interactionId\}\/proposals\/\$\{input\.assetId\}\/adoptions`/);
  assert.match(client, /target_chapter_id:\s*input\.targetChapterId/);
  assert.match(client, /target_scene_id:\s*input\.targetSceneId/);
  assert.match(client, /pov_mode:\s*input\.povMode/);
  assert.match(client, /run_id:\s*requiredString\(payload,\s*"run_id"\)/);
  assert.match(client, /trace_id:\s*requiredString\(payload,\s*"trace_id"\)/);
  assert.match(client, /workflow_type:\s*requiredString\(payload,\s*"workflow_type"\)/);
  assert.match(client, /X-Tenant-Id/);
  assert.match(client, /X-User-Id/);
  assert.doesNotMatch(characterClient, /draft_id/);
  assert.doesNotMatch(characterClient, /input_text:\s*string/);
  assert.doesNotMatch(characterClient, /output_text:\s*string/);
  assert.doesNotMatch(characterClient, /body_text:\s*string/);
  assert.doesNotMatch(characterClient, /content_text:\s*string/);
  assert.doesNotMatch(characterClient, /credential_ref:\s*string/);
  assert.doesNotMatch(characterClient, /encrypted_api_key:\s*string/);
});

test("retired Guide routes redirect into supported user workflows", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/guide/page.tsx");
  const legacyRoute = await fileText("app/guide/page.tsx");
  const nav = await fileText("components/project-nav.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /redirect\(`\/\$\{tenantSlug\}\/projects\/\$\{projectId\}\/overview`\)/);
  assert.doesNotMatch(page, /GuideShell|runtime|Phase\s+\d/i);
  assert.match(legacyRoute, /redirect/);
  assert.match(legacyRoute, /devEntryRedirectPath\(\)/);
  assert.doesNotMatch(legacyRoute, /mock/i);
  assert.doesNotMatch(nav, /\/guide|CircleHelp/);
});

test("Next app shell declares tenant/project Story Graph route", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/graph/page.tsx");
  const nav = await fileText("components/project-nav.tsx");

  assert.match(page, /params:\s*Promise<\{\s*tenantSlug:\s*string;\s*projectId:\s*string;?\s*\}>/);
  assert.match(page, /getStoryGraphCurrent/);
  assert.match(page, /startStoryGraphBuild/);
  assert.match(page, /startStoryGraphBondGeneration/);
  assert.match(page, /buildAction/);
  assert.match(page, /bondAction/);
  assert.match(page, /StoryGraphShell/);
  assert.match(nav, /\/graph/);
  assert.match(nav, /Story Graph/);
});

test("writer API client uses Go API base URL and tenant context headers", async () => {
  const client = await fileText("lib/api.ts");
  const writerClient = sourceSlice(client, "export async function startWriterRun", "export async function getProjectManuscript");

  assert.match(client, /MIROFISH_API_BASE_URL/);
  assert.match(writerClient, /contextHeaders\(input\)/);
  assert.match(client, /"X-Tenant-Id":\s*input\.tenantId/);
  assert.match(client, /headers\["X-User-Id"\]\s*=\s*actorUserId/);
  assert.match(client, /headers\.Cookie\s*=\s*`mirofish_session=\$\{sessionCookie\}`/);
  assert.match(writerClient, /\/v1\/projects\/\$\{(?:input\.)?projectId\}\/writer-runs/);
  assert.match(client, /trace_id/);
  assert.doesNotMatch(writerClient, /tenant_id\s*:/);
});

test("asset API client uses sanitized Go asset endpoints and tenant context headers", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /getProjectAssets/);
  assert.match(client, /getAssetFacets/);
  assert.match(client, /tags:\s*AssetFacetBucket\[\]/);
  assert.match(client, /tags:\s*arrayFromUnknown\(payload\.tags\)/);
  assert.match(client, /searchAssets/);
  assert.match(client, /getArchiveAssetMemories/);
  assert.match(client, /getArchiveAssetMemoryEvents/);
  assert.match(client, /adoptArchiveMemory/);
  assert.match(client, /rejectArchiveMemory/);
  assert.match(client, /ArchiveMemoryRecord/);
  assert.match(client, /createAsset/);
  assert.match(client, /updateAsset/);
  assert.match(client, /deleteAsset/);
  assert.match(client, /adoptAsset/);
  assert.match(client, /bulkActionAssets/);
  assert.match(client, /startAssetIngestion/);
  assert.match(client, /startAssetReindex/);
  assert.match(client, /startStyleExtraction/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/assets`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/assets\/facets`/);
  assert.match(client, /\/v1\/assets\/search`/);
  assert.match(client, /\/v1\/archive-assets\/\$\{input\.assetId\}\/memories/);
  assert.match(client, /\/v1\/archive-assets\/\$\{input\.assetId\}\/memory-events/);
  assert.match(client, /\/v1\/archive-memories\/\$\{input\.memoryId\}\/adoptions`/);
  assert.match(client, /\/v1\/archive-memories\/\$\{input\.memoryId\}\/rejections`/);
  assert.match(client, /project_id/);
  assert.match(client, /\/v1\/assets\/\$\{input\.assetId\}`/);
  assert.match(client, /\/v1\/assets\/\$\{input\.assetId\}\/adoptions`/);
  assert.match(client, /\/v1\/assets\/bulk-actions`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/assets\/reindex`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/asset-ingestions`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/style-extractions`/);
  assert.match(client, /X-Tenant-Id/);
  assert.match(client, /X-User-Id/);
  assert.match(client, /content_text/);
  assert.match(client, /target_lifecycle/);
  assert.match(client, /asset_ids/);
  assert.doesNotMatch(client, /body:\s*string/);
  assert.doesNotMatch(client, /requiredString\(value,\s*"body"\)/);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
  assert.doesNotMatch(client, /encrypted_api_key:\s*string/);
});

test("Story Graph API client uses sanitized Go story graph endpoints and tenant context headers", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /getStoryGraphCurrent/);
  assert.match(client, /getStoryGraphView/);
  assert.match(client, /getStoryGraphEvidence/);
  assert.match(client, /getStoryGraphLayout/);
  assert.match(client, /getStoryGraphClusters/);
  assert.match(client, /startStoryGraphBuild/);
  assert.match(client, /startStoryGraphBondGeneration/);
  assert.match(client, /getWorkflowRunSummary/);
  assert.match(client, /getWorkflowRunEvents/);
  assert.match(client, /WorkflowRunSummary/);
  assert.match(client, /WorkflowRunEventsSummary/);
  assert.match(client, /StoryGraphCurrentSummary/);
  assert.match(client, /StoryGraphViewSummary/);
  assert.match(client, /StoryGraphEvidenceSummary/);
  assert.match(client, /StoryGraphLayoutSummary/);
  assert.match(client, /StoryGraphClustersSummary/);
  assert.match(client, /StoryGraphBuildSummary/);
  assert.match(client, /StoryGraphBondGenerationSummary/);
  assert.match(client, /StoryGraphCandidateAdoptionSummary/);
  assert.match(client, /AdoptStoryGraphCandidateInput/);
  assert.match(client, /adoptStoryGraphCandidate/);
  assert.match(client, /\/v1\/workflow-runs\/\$\{input\.runId\}`/);
  assert.match(client, /\/v1\/workflow-runs\/\$\{input\.runId\}\/events/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/current`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/views\/\$\{input\.viewId\}`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/\$\{input\.ownerType\}s\/\$\{input\.ownerId\}\/evidence`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/layouts\/\$\{input\.viewId\}`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/clusters`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/builds`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/bond-generations`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/story-graph\/candidates\/\$\{input\.assetId\}\/adoptions`/);
  assert.match(client, /target_kind:\s*input\.targetKind/);
  assert.match(client, /workflow_type/);
  assert.match(client, /graph_id/);
  assert.match(client, /node_ids/);
  assert.match(client, /node_count/);
  assert.match(client, /edge_count/);
  assert.match(client, /target_id/);
  assert.match(client, /X-Tenant-Id/);
  assert.match(client, /X-User-Id/);
  assert.doesNotMatch(client, /snippet:\s*string/);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
  assert.doesNotMatch(client, /encrypted_api_key:\s*string/);
});

test("Story Graph shell renders explicit snapshot and build states", async () => {
  const shell = await fileText("components/story-graph-shell.tsx");

  assert.match(shell, /Story Graph/);
  assert.match(shell, /Current Snapshot/);
  assert.match(shell, /Graph canvas/);
  assert.match(shell, /Viewport/);
  assert.match(shell, /Evidence/);
  assert.match(shell, /Layout/);
  assert.match(shell, /Clusters/);
  assert.match(shell, /Build progress/);
  assert.match(shell, /Workflow events/);
  assert.match(shell, /Compose Mode/);
  assert.match(shell, /Generate bonds/);
  assert.match(shell, /Curate Mode/);
  assert.match(shell, /Graph candidates/);
  assert.match(shell, /Adopt relationship/);
  assert.match(shell, /Adopt plot thread/);
  assert.match(shell, /graphCandidates/);
  assert.match(shell, /adoptStoryGraphCandidateAction/);
  assert.match(shell, /bondAction/);
  assert.match(shell, /bondStatus/);
  assert.match(shell, /storyGraphBondStatus/);
  assert.match(shell, /workspaceMode === "build"/);
  assert.match(shell, /workspaceMode === "curate"/);
  assert.match(shell, /workspaceMode === "compose"/);
  assert.match(shell, /workflowRun\.ok/);
  assert.match(shell, /workflowEvents\.ok/);
  assert.match(shell, /event\.event_type/);
  assert.match(shell, /No build run selected/);
  assert.match(shell, /view\.ok/);
  assert.match(shell, /evidence\.ok/);
  assert.match(shell, /layout\.ok/);
  assert.match(shell, /clusters\.ok/);
  assert.match(shell, /node\.node_id/);
  assert.match(shell, /edge\.edge_id/);
  assert.match(shell, /Start build/);
  assert.match(shell, /current\.ok/);
  assert.match(shell, /node_count/);
  assert.match(shell, /edge_count/);
  assert.match(shell, /storyGraphBuildStatus/);
  assert.doesNotMatch(shell, /content_text/);
  assert.doesNotMatch(shell, /credential_ref/);
  assert.doesNotMatch(shell, /api_key/);
  assert.doesNotMatch(shell, /mock/i);
});

test("Story Graph shell renders an interactive canvas without exposing internal identifiers", async () => {
  const shell = await fileText("components/story-graph-shell.tsx");
  const styles = await fileText("app/globals.css");
  const canvasSlice = sourceSlice(shell, "function GraphCanvas", "function GraphViewport");

  assert.match(shell, /<GraphCanvas[\s\S]*clusters=\{clusters\}[\s\S]*current=\{current\}[\s\S]*layout=\{layout\}[\s\S]*locale=\{locale\}[\s\S]*view=\{view\}/);
  assert.match(canvasSlice, /StoryGraphViewSummary/);
  assert.match(canvasSlice, /view\.ok/);
  assert.match(canvasSlice, /view\.nodes\.length\s*===\s*0/);
  assert.match(canvasSlice, /No graph nodes available/);
  assert.match(canvasSlice, /InteractiveGraphCanvas/);
  assert.match(canvasSlice, /graphLayoutModel/);
  assert.match(canvasSlice, /useMemo/);
  assert.match(canvasSlice, /useState/);
  assert.match(canvasSlice, /<svg/);
  assert.match(canvasSlice, /data-graph-canvas="true"/);
  assert.match(canvasSlice, /visibleEdges\.map/);
  assert.match(canvasSlice, /filteredNodes\.map/);
  assert.match(canvasSlice, /node\.node_id/);
  assert.match(canvasSlice, /node\.node_type/);
  assert.match(canvasSlice, /node\.title/);
  assert.match(canvasSlice, /selectedNode\.lifecycle/);
  assert.match(canvasSlice, /selectedNode\.importance/);
  assert.match(canvasSlice, /selectedNode\.evidence_count/);
  assert.match(canvasSlice, /edge\.edge_id/);
  assert.match(canvasSlice, /edge\.edge_type/);
  assert.match(canvasSlice, /edge\.label/);
  assert.match(canvasSlice, /edge\.source_node_id/);
  assert.match(canvasSlice, /edge\.target_node_id/);
  assert.match(canvasSlice, /edge\.weight/);
  assert.match(canvasSlice, /aria-label=\{tx\(locale, "缩小图谱", "Zoom out"\)\}/);
  assert.match(canvasSlice, /aria-label=\{tx\(locale, "放大图谱", "Zoom in"\)\}/);
  assert.doesNotMatch(canvasSlice, /<dd>\{selectedNode\.node_id\}<\/dd>/);
  assert.doesNotMatch(canvasSlice, /node\.title \|\| node\.node_id/);
  assert.doesNotMatch(canvasSlice, /prompt|provider|response|raw_body|content_text|api_key|encrypted_api_key|credential_ref|object_key|draft|manuscript|candidate payload|evidence snippet/i);
  assert.match(styles, /\.story-graph-canvas/);
  assert.match(styles, /min-height:\s*360px/);
  assert.doesNotMatch(styles, /graph-canvas-skeleton/);
});

test("Story Graph page loads graph candidates and wires explicit adoption action", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/graph/page.tsx");

  assert.match(page, /getProjectAssets/);
  assert.match(page, /graphCandidatesFromAssets/);
  assert.match(page, /source_kind\s*===\s*"graph_bond_generation"/);
  assert.match(page, /lifecycle\s*===\s*"candidate"/);
  assert.match(page, /adoptStoryGraphCandidate/);
  assert.match(page, /adoptStoryGraphCandidateAction/);
  assert.match(page, /targetKind/);
  assert.match(page, /targetKindFromFormData\(formData\)/);
  assert.match(page, /STORY_GRAPH_CANDIDATE_ADOPTION_VALIDATION_FAILED/);
  assert.match(page, /storyGraphAdoptionMessage:\s*tx\(locale,\s*"请选择采用类型",\s*"Choose an adoption type"\)/);
  assert.match(page, /storyGraphAdoptionStatus/);
  assert.doesNotMatch(page, /content_text/);
  assert.doesNotMatch(page, /credential_ref/);
  assert.doesNotMatch(page, /api_key/);
});

test("Story Graph page loads workflow progress when a build run id is present", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/graph/page.tsx");

  assert.match(page, /runId\?:\s*string/);
  assert.match(page, /bondStatus\?:\s*string/);
  assert.match(page, /bondRunId\?:\s*string/);
  assert.match(page, /getWorkflowRunSummary/);
  assert.match(page, /getWorkflowRunEvents/);
  assert.match(page, /selectedRunId/);
  assert.match(page, /Promise\.all\(\[/);
  assert.match(page, /selectedRunId && workflowContext[\s\S]*getWorkflowRunSummary/);
  assert.match(page, /selectedRunId && workflowContext[\s\S]*getWorkflowRunEvents/);
  assert.match(page, /query\.runId\s*\?\?\s*""/);
  assert.match(page, /query\.bondRunId\s*\?\?\s*""/);
  assert.match(page, /runId:\s*status\.runId/);
});

test("Asset Library shell renders explicit archive memory review controls", async () => {
  const shell = await fileText("components/asset-library-shell.tsx");

  assert.match(shell, /Archive Memory/);
  assert.match(shell, /Memory review/);
  assert.match(shell, /archiveMemories/);
  assert.match(shell, /archiveMemoryEvents/);
  assert.match(shell, /memoryAssetAction/);
  assert.match(shell, /adoptArchiveMemoryAction/);
  assert.match(shell, /rejectArchiveMemoryAction/);
  assert.match(shell, /<Bi zh="请选择档案资产。" en="Select an archive asset\." \/>/);
  assert.match(shell, /Adopt memory/);
  assert.match(shell, /Reject memory/);
});

test("writer API client reads and exports agent traces through audited Go endpoints", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /getAgentTraceEvents/);
  assert.match(client, /exportAgentTrace/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/agent-traces\/\$\{input\.traceId\}\/events/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/agent-traces\/\$\{input\.traceId\}\/export/);
  assert.match(client, /include_full/);
});

test("writer API client can replay workflow events after a resume cursor", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /getWriterRunEvents/);
  assert.match(client, /after_event_id/);
  assert.match(client, /\/v1\/writer-runs\/\$\{input\.runId\}\/events/);
});

test("Writer shell exposes recovered stream replay cursor without sensitive content", async () => {
  const shell = await fileText("components/writer-workbench-shell.tsx");
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx");
  const replaySlice = sourceSlice(shell, "Recovered stream", "Trace Events");

  assert.match(page, /const\s+afterEventId\s*=\s*query\.after_event_id\s*\?\?\s*query\.afterEventId\s*\?\?\s*""/);
  assert.match(page, /const\s+selectedRunId\s*=\s*query\.runId\s*\?\?\s*query\.runtime_run_id\s*\?\?\s*""/);
  assert.match(page, /const\s+selectedTraceId\s*=\s*query\.traceId\s*\?\?\s*""/);
  assert.match(page, /afterEventId:\s*afterEventId/);
  assert.match(page, /selectedRunId=\{selectedRunId\}/);
  assert.match(page, /selectedTraceId=\{selectedTraceId\}/);
  assert.match(page, /afterEventId=\{afterEventId\}/);
  assert.match(shell, /afterEventId:\s*string/);
  assert.match(shell, /selectedRunId:\s*string/);
  assert.match(shell, /selectedTraceId:\s*string/);
  assert.match(shell, /const\s+replayRunId\s*=\s*runSummary\?\.ok === true \? runSummary\.run_id : selectedRunId/);
  assert.match(shell, /const\s+replayTraceId\s*=\s*selectedTraceId \|\| traceId/);
  assert.match(shell, /<dd>\{replayRunId \|\| tx\(locale, "未选择", "not selected"\)\}<\/dd>/);
  assert.match(shell, /<dd>\{replayTraceId \|\| tx\(locale, "未选择", "not selected"\)\}<\/dd>/);
  assert.match(shell, /value=\{replayTraceId\}/);
  assert.match(replaySlice, /action=\{writerHref\(tenantSlug,\s*projectId\)\}/);
  assert.match(replaySlice, /method="get"/);
  assert.match(replaySlice, /name="runId"/);
  assert.match(replaySlice, /value=\{runSummary\?\.ok === true \? runSummary\.run_id : selectedRunId\}/);
  assert.match(replaySlice, /name="traceId"/);
  assert.match(replaySlice, /value=\{selectedTraceId \|\| replayTraceId\}/);
  assert.match(replaySlice, /name="after_event_id"/);
  assert.match(replaySlice, /defaultValue=\{afterEventId\}/);
  assert.match(replaySlice, /Request replay events/);
  assert.match(replaySlice, /Event cursor/);
  assert.doesNotMatch(shell, /JSON\.stringify\(event\.payload/);
  assert.doesNotMatch(replaySlice, /api_key|encrypted_api_key|credential_ref/i);
  assert.doesNotMatch(replaySlice, /content_text|body_text|draft_text|manuscript_text|prompt|provider_response/i);
});

test("writer API client reads sanitized worldline saved path picker data", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /WorldlineSavedPathRecord/);
  assert.match(client, /WorldlineSavedPathsSummary/);
  assert.match(client, /WorldlineSessionRecord/);
  assert.match(client, /WorldlineSessionsSummary/);
  assert.match(client, /WorldlineSessionStartSummary/);
  assert.match(client, /WorldlineTimelineEventRecord/);
  assert.match(client, /WorldlineTimelineSummary/);
  assert.match(client, /WorldlineVariableRecord/);
  assert.match(client, /WorldlineVariableSummary/);
  assert.match(client, /getWorldlineSavedPaths/);
  assert.match(client, /getWorldlineSessions/);
  assert.match(client, /getWorldlineSession/);
  assert.match(client, /getWorldlineTimeline/);
  assert.match(client, /startWorldlineSession/);
  assert.match(client, /startWorldlineStep/);
  assert.match(client, /injectWorldlineVariable/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/worldline\/saved-paths`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/worldline-sessions`/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}`/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}\/timeline`/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}\/steps`/);
  assert.match(client, /\/v1\/worldline-sessions\/\$\{input\.sessionId\}\/variables`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/worldline-sessions`/);
  assert.match(client, /anchor_path_id/);
  assert.match(client, /goal_summary/);
  assert.match(client, /workflow_type/);
  assert.match(client, /selected_event_ids/);
  assert.match(client, /writer_instruction/);
  assert.match(client, /X-Tenant-Id/);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
  assert.doesNotMatch(client, /content_text:\s*string/);
  assert.doesNotMatch(client, /body_text:\s*string/);
});

test("LLM Facility API client reads sanitized module resolution, activity, and usage", async () => {
  const client = await fileText("lib/api.ts");

  assert.match(client, /createLLMChannel/);
  assert.match(client, /updateLLMChannel/);
  assert.match(client, /deleteLLMChannel/);
  assert.match(client, /syncLLMChannelModels/);
  assert.match(client, /getLLMSettings/);
  assert.match(client, /deleteLLMModuleBinding/);
  assert.match(client, /getLLMModuleBindings/);
  assert.match(client, /getLLMModules/);
  assert.match(client, /getLLMChannels/);
  assert.match(client, /getLLMChannelModels/);
  assert.match(client, /upsertLLMModuleBinding/);
  assert.match(client, /resolveLLMModuleBinding/);
  assert.match(client, /getLLMActivity/);
  assert.match(client, /getLLMUsage/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/channels`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/channels\/\$\{input\.channelId\}\/models`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/modules`/);
  assert.match(client, /\/v1\/llm\/channels`/);
  assert.match(client, /\/v1\/llm\/settings`/);
  assert.match(client, /\/v1\/llm\/channels\/\$\{input\.channelId\}`/);
  assert.match(client, /\/v1\/llm\/channels\/\$\{input\.channelId\}\/sync-models`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/module-bindings`/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/module-bindings\/\$\{input\.moduleKey\}`/);
  assert.match(client, /method:\s*"DELETE"/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/module-bindings\/\$\{input\.moduleKey\}\/resolution/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/activity/);
  assert.match(client, /\/v1\/projects\/\$\{input\.projectId\}\/llm\/usage/);
  assert.match(client, /module_key/);
  assert.doesNotMatch(client, /credential_ref:\s*string/);
});

test("writer page loads redacted trace events when a run exposes trace_id", async () => {
  const page = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx");

  assert.match(page, /getAgentTraceEvents/);
  assert.match(page, /exportAgentTrace/);
  assert.match(page, /getWriterRunEvents/);
  assert.match(page, /startWriterRun/);
  assert.match(page, /getProjectAssets/);
  assert.match(page, /getStoryGraphView/);
  assert.match(page, /getWorldlineSavedPaths/);
  assert.match(page, /startWriterRunAction/);
  assert.match(page, /selectedAssetIds/);
  assert.match(page, /selectedGraphNodeIds/);
  assert.match(page, /worldlinePathIds/);
  assert.match(page, /worldlineSavedPaths/);
  assert.match(page, /selected_asset_ids/);
  assert.match(page, /graph_node_ids/);
  assert.match(page, /worldline_path_ids/);
  assert.match(page, /exportTraceAction/);
  assert.match(page, /includeFull:\s*false/);
  assert.match(page, /runSummary\.ok\s*===\s*true\s*\?\s*runSummary\.trace_id/);
  assert.match(page, /runSummary\.ok\s*===\s*true\s*\?\s*await getWriterRunEvents/);
});

test("writer shell is an operational workbench, not a marketing page", async () => {
  const shell = await fileText("components/writer-workbench-shell.tsx");

  assert.match(shell, /Writer Agent/);
  assert.match(shell, /WriterAgentThread/);
  assert.match(shell, /writer-agent-layout/);
  assert.match(shell, /writer-agent-composer/);
  assert.match(shell, /WriterLiveDraft/);
  assert.match(shell, /initialEvents=/);
  assert.match(shell, /Writer Events/);
  assert.match(shell, /workflowEvents/);
  assert.match(shell, /Trace/);
  assert.match(shell, /Export redacted trace/);
  assert.match(shell, /exportTraceAction/);
  assert.match(shell, /traceExportStatus/);
  assert.match(shell, /Start writer run/);
  assert.match(shell, /Add story context/);
  assert.match(shell, /Project assets/);
  assert.match(shell, /Graph nodes/);
  assert.match(shell, /Worldline paths/);
  assert.match(shell, /ReferenceWorldlinePaths/);
  assert.match(shell, /worldlineSavedPaths\.ok/);
  assert.match(shell, /writerRunAction/);
  assert.match(shell, /assets\.ok/);
  assert.match(shell, /graphView\.ok/);
  assert.match(shell, /name="selectedAssetIds"/);
  assert.match(shell, /name="selectedGraphNodeIds"/);
  assert.match(shell, /name="worldlinePathIds"/);
  assert.match(shell, /path\.path_id/);
  assert.match(shell, /selected_event_ids/);
  assert.match(shell, /name="instruction"/);
  assert.match(shell, /name="traceId"/);
  assert.match(shell, /redaction_level/);
  assert.match(shell, /event_type/);
  assert.match(shell, /Draft/);
  assert.doesNotMatch(shell, /writer-workbench-prose-first|writer-composer-disclosure|writer-agent-rail/);
  assert.doesNotMatch(shell, /credential_ref/);
  assert.doesNotMatch(shell, /hero/i);
  assert.doesNotMatch(shell, /Start trial/i);
});

test("writer shell renders typed tool result cards from completed writer events", async () => {
  const shell = await fileText("components/writer-workbench-shell.tsx");

  assert.match(shell, /Tool result cards/);
  assert.match(shell, /ToolResultCards/);
  assert.match(shell, /ToolResultCard/);
  assert.match(shell, /AssetToolResultCard/);
  assert.match(shell, /GraphToolResultCard/);
  assert.match(shell, /WorldlinePathToolResultCard/);
  assert.match(shell, /writer\.tool\.completed/);
  assert.match(shell, /tool_name/);
  assert.match(shell, /query_assets/);
  assert.match(shell, /query_graph_neighbors/);
  assert.match(shell, /query_worldline_paths/);
  assert.match(shell, /is_error/);
  assert.match(shell, /asset_id/);
  assert.match(shell, /neighbor/);
  assert.match(shell, /path_id/);
  assert.match(shell, /selected_event_ids/);
  assert.match(shell, /UnknownToolResultCard/);
  assert.match(shell, /tool-result-grid/);
  assert.doesNotMatch(shell, /credential_ref/);
});

test("LLM Facility shell is an operational settings console", async () => {
  const shell = await fileText("components/llm-facility-shell.tsx");

  assert.match(shell, /Model settings/);
  assert.match(shell, /Workspace Settings/);
  assert.match(shell, /settingsSnapshot/);
  assert.match(shell, /Channels/);
  assert.match(shell, /Channel Management/);
  assert.match(shell, /LLMCreateChannelDialog/);
  assert.match(shell, /Channels and model sync/);
  assert.match(shell, /Update channel/);
  assert.match(shell, /updateChannelAction/);
  assert.match(shell, /deleteChannelAction/);
  assert.match(shell, /syncChannelAction/);
  assert.match(shell, /testModelAction/);
  assert.match(shell, /Test model/);
  assert.match(shell, /Test link/);
  assert.match(shell, /ChannelModelTestForm/);
  assert.match(shell, /Sync models/);
  assert.match(shell, /last_sync_status/);
  assert.match(shell, /llm-channel-edit-list/);
  assert.match(shell, /llm-channel-edit-card/);
  assert.match(shell, /llmChannelAnchorId/);
  assert.match(shell, /LLMChannelFocus/);
  assert.match(shell, /id=\{anchorId\}/);

  const createChannelDialog = await fileText("components/llm-create-channel-dialog.tsx");
  assert.match(createChannelDialog, /Create channel/);
  assert.match(createChannelDialog, /showModal/);
  assert.match(createChannelDialog, /name="apiKey"/);
  assert.match(createChannelDialog, /createChannelAction/);
  assert.match(createChannelDialog, /llm-create-channel-dialog/);
  assert.match(shell, /Models/);
  assert.match(shell, /Project model bindings/);
  assert.match(shell, /LLMModuleBindingsPanel/);
  assert.match(shell, /batchBindModuleAction/);
  assert.match(shell, /canManageBindings/);
  assert.match(shell, /channelModels/);
  assert.match(shell, /clearBindingAction/);
  assert.match(shell, /bindingStatus/);
  assert.match(shell, /Module Bindings/);
  assert.match(shell, /Module Catalog/);
  assert.match(shell, /modules\.items\.map/);
  assert.match(shell, /Activity/);
  assert.match(shell, /Usage/);
  assert.match(shell, /Telemetry filter/);
  assert.match(shell, /name="run"/);
  assert.match(shell, /name="channel"/);
  assert.match(shell, /name="module"/);
  assert.match(shell, /llmChannelKey/);
  assert.match(shell, /Filter telemetry/);
  assert.match(shell, /writer_composer/);
  assert.doesNotMatch(shell, /api_key/);
  assert.doesNotMatch(shell, /hero/i);
});

test("Asset Library shell is an operational asset console", async () => {
  const shell = await fileText("components/asset-library-shell.tsx");

  assert.match(shell, /Asset Library/);
  assert.match(shell, /Facets/);
  assert.match(shell, /FacetGroup label=\{tx\(locale, "标签", "Tags"\)\}/);
  assert.match(shell, /Search/);
  assert.match(shell, /SearchModeSelect/);
  assert.match(shell, /searchCapabilities/);
  assert.match(shell, /Assets/);
  assert.match(shell, /Create asset/);
  assert.match(shell, /Update asset/);
  assert.match(shell, /Delete asset/);
  assert.match(shell, /Adopt candidate/);
  assert.match(shell, /Bulk action/);
  assert.match(shell, /Ingest material/);
  assert.match(shell, /Reindex assets/);
  assert.match(shell, /Extract style/);
  assert.match(shell, /createAssetAction/);
  assert.match(shell, /updateAssetAction/);
  assert.match(shell, /deleteAssetAction/);
  assert.match(shell, /adoptAssetAction/);
  assert.match(shell, /bulkAssetAction/);
  assert.match(shell, /ingestAssetAction/);
  assert.match(shell, /reindexAssetsAction/);
  assert.match(shell, /extractStyleAction/);
  assert.match(shell, /name="contentText"/);
  assert.match(shell, /name="targetLifecycle"/);
  assert.match(shell, /name="assetIds"/);
  assert.match(shell, /name="bulkAction"/);
  assert.match(shell, /bulkStatus/);
  assert.match(shell, /assetStatus/);
  assert.match(shell, /ingestionStatus/);
  assert.match(shell, /reindexStatus/);
  assert.match(shell, /styleStatus/);
  assert.doesNotMatch(shell, /item\.body/);
  assert.doesNotMatch(shell, /api_key/);
  assert.doesNotMatch(shell, /credential_ref/);
  assert.doesNotMatch(shell, /hero/i);
});

test("asset search client decodes version and collection metadata", async () => {
  const api = await fileText("lib/api.ts");

  assert.match(api, /type AssetSearchVersion/);
  assert.match(api, /type AssetSearchCollection/);
  assert.match(api, /version: decodeAssetSearchVersion/);
  assert.match(api, /collections: arrayFromUnknown\(value\.collections\)\.map\(\(collection\) => decodeAssetSearchCollection\(collection\)\)/);
  assert.doesNotMatch(api, /body:\s*string/);
  assert.doesNotMatch(api, /requiredString\(value,\s*"body"\)/);
});

test("global styles avoid one-note purple, cream, and dark-slate dominance", async () => {
  const css = await fileText("app/globals.css");

  assert.match(css, /--surface/);
  assert.match(css, /--accent/);
  assert.doesNotMatch(css, /#fffbeb/i);
  assert.doesNotMatch(css, /#0f172a/i);
  assert.doesNotMatch(css, /purple|violet/i);
});

test("project app frame collapses to one column on mobile", async () => {
  const css = await fileText("app/globals.css");
  const polish = await fileText("app/workbench-polish.css");

  assert.match(css, /\.panel\s*\{[^}]*min-width:\s*0/s);
  assert.match(css, /@media\s*\(max-width:\s*860px\)/);
  assert.match(css, /\.app-frame\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)/s);
  assert.match(css, /\.app-main\s*\{[^}]*padding:\s*16px/s);
  assert.match(css, /\.app-sidebar\s*\{[^}]*border-right:\s*0/s);
  assert.match(
    polish,
    /@media\s*\(max-width:\s*860px\)[\s\S]*?\.app-frame\.app-frame-unified \.app-sidebar,[\s\S]*?min-height:\s*0/s,
  );
});

test("trace JSON blocks stay inside mobile workbench panels", async () => {
  const css = await fileText("app/globals.css");

  assert.match(css, /\.trace-list\s*\{[^}]*min-width:\s*0/s);
  assert.match(css, /\.trace-event\s*\{[^}]*min-width:\s*0/s);
  assert.match(css, /\.trace-event\s*\{[^}]*overflow:\s*hidden/s);
  assert.match(css, /\.trace-event-header\s*\{[^}]*flex-wrap:\s*wrap/s);
  assert.match(css, /\.trace-event pre\s*\{[^}]*max-width:\s*100%/s);
  assert.match(css, /\.trace-event pre\s*\{[^}]*min-width:\s*0/s);
  assert.match(css, /\.trace-event pre\s*\{[^}]*width:\s*100%/s);
});

test("cookie-backed locale selection controls the root document and bilingual copy", async () => {
  const locale = await fileText("lib/locale.ts");
  const requestLocale = await fileText("lib/request-locale.ts");
  const provider = await fileText("components/locale-provider.tsx");
  const switcher = await fileText("components/language-switcher.tsx");
  const bilingualText = await fileText("components/bilingual-text.tsx");
  const rootLayout = await fileText("app/layout.tsx");
  const login = await fileText("app/login/page.tsx");
  const nav = await fileText("components/project-nav.tsx");

  assert.match(locale, /export const LOCALE_COOKIE_NAME = "mirofish_locale"/);
  assert.match(locale, /export type Locale = "zh-CN" \| "en"/);
  assert.match(locale, /normalized === "en"/);
  assert.match(locale, /return "zh-CN"/);
  assert.match(locale, /return locale === "en" \? en : zh/);

  assert.match(requestLocale, /import \{ cookies \} from "next\/headers"/);
  assert.match(requestLocale, /const cookieStore = await cookies\(\)/);
  assert.match(requestLocale, /parseLocale\(cookieStore\.get\(LOCALE_COOKIE_NAME\)\?\.value\)/);

  assert.match(provider, /useState\(initialLocale\)/);
  assert.match(provider, /desiredLocaleRef/);
  assert.match(provider, /document\.documentElement\.lang = normalized/);
  assert.match(provider, /writeLocaleCookie\(normalized\)/);
  assert.match(provider, /\$\{LOCALE_COOKIE_NAME\}=\$\{locale\}; Path=\/; Max-Age=31536000; SameSite=Lax/);
  assert.match(provider, /startTransition\(\(\) => \{\s*router\.refresh\(\);\s*\}\)/);
  assert.match(provider, /LocaleContext\.Provider value=\{\{ locale, selectLocale, switching \}\}/);
  assert.match(provider, /if \(initialLocale !== desiredLocaleRef\.current\)/);

  assert.match(switcher, /import \{ Globe2 \} from "lucide-react"/);
  assert.match(switcher, /const nextLocale = locale === "en" \? "zh-CN" : "en"/);
  assert.match(switcher, /const label = locale === "en" \? "切换为中文" : "Switch to English"/);
  assert.match(switcher, /aria-label=\{label\}/);
  assert.match(switcher, /title=\{label\}/);
  assert.equal((switcher.match(/disabled=\{switching\}/g) ?? []).length, 0);
  assert.match(switcher, /data-switching=\{switching \? "true" : "false"\}/);
  assert.match(switcher, /selectLocale\(nextLocale\)/);
  assert.equal((switcher.match(/<button/g) ?? []).length, 1);
  assert.match(switcher, /<Globe2[^>]*aria-hidden="true"/);

  assert.match(bilingualText, /const \{ locale \} = useLocale\(\)/);
  assert.match(bilingualText, /return locale === "en" \? en : zh/);
  assert.match(rootLayout, /const locale = await currentRequestLocale\(\)/);
  assert.match(rootLayout, /<html data-scroll-behavior="smooth" lang=\{locale\} suppressHydrationWarning>/);
  assert.match(rootLayout, /<LocaleProvider initialLocale=\{locale\}>\{children\}<\/LocaleProvider>/);
  assert.doesNotMatch(login, /<LanguageSwitcher \/>/);
  assert.match(login, /欢迎回来/);
  assert.match(login, /auth-shell|login-main/);
  assert.match(login, /href="\/"/);
  assert.match(login, /<LoginForm action=\{loginAction\} \/>/);
  assert.match(nav, /className="sidebar-top-actions"[\s\S]*<LanguageSwitcher \/>/);
  assert.doesNotMatch(nav, /className="sidebar-bottom-row"/);
  assert.match(nav, /<Bi zh=\{item\.zh\} en=\{item\.label\} \/>/);
});

test("login page keeps the reference editorial split-screen proportions", async () => {
  const styles = await fileText("app/auth-marketing.css");

  assert.match(styles, /\.login-workspace\s*\{[^}]*grid-template-columns:\s*minmax\(560px, 43\.5%\) minmax\(0, 56\.5%\)/s);
  assert.match(styles, /\.login-copy\s*\{[^}]*width:\s*min\(100% - 80px, 455px\)/s);
  assert.match(styles, /\.login-form-panel::after\s*\{[^}]*right:\s*-200px;[^}]*width:\s*200px/s);
  assert.match(styles, /\.login-form-panel\s*\{[^}]*overflow:\s*visible/s);
  assert.match(styles, /\.login-submit\s*\{[^}]*min-height:\s*66px/s);
  assert.match(styles, /\.login-visual\s*\{[^}]*background-image:\s*url\("\/landing\/assets\/scene-5-finale\.jpg"\)/s);
  assert.match(styles, /\.login-visual-copy h2\s*\{[^}]*color:\s*#fffaf2/s);
  assert.match(styles, /font-size:\s*clamp\(2\.1rem, 2\.7vw, 2\.8rem\)/);
  assert.match(styles, /@media \(min-width: 961px\) and \(max-height: 800px\)/);
  assert.match(styles, /@media \(max-width: 960px\)[\s\S]*\.login-copy\s*\{[^}]*margin-right:\s*auto;[^}]*margin-left:\s*auto/s);
  assert.match(styles, /--login-topbar-h/);
  assert.match(
    styles,
    /@media \(max-width: 960px\)[\s\S]*\.login-form-panel\s*\{[\s\S]*align-items:\s*start/s,
  );
});

test("Project Overview keeps operational detail collapsed by default", async () => {
  const shell = await fileText("components/overview-seed-shell.tsx");
  const wall = await fileText("components/overview-seed-progress-wall.tsx");
  const css = await fileText("app/globals.css");

  assert.ok(((shell.match(/<details className="overview-details">/g) ?? []).length) >= 2);
  assert.doesNotMatch(shell, /<details className="overview-details" open/);
  assert.match(shell, /文件与分析记录/);
  assert.match(shell, /项目诊断（可选）|Project diagnostics \(optional\)/);
  assert.match(shell, /<SeedRunOverview/);
  assert.match(wall, /className="overview-run-actions overview-run-actions-soft"/);
  assert.match(wall, /data-wall="seed-progress"/);
  assert.match(css, /\.overview-details\s*\{/);
  assert.match(css, /\.overview-details > summary\s*\{[^}]*min-height:\s*60px/s);
  assert.match(
    css,
    /\.overview-secondary-stack \.overview-details-content\s*\{[^}]*max-height:\s*min\(36vh,\s*320px\)/s,
  );
  assert.match(
    css,
    /\.overview-secondary-stack \.overview-details-content\s*\{[^}]*overflow-y:\s*auto/s,
  );
  assert.match(css, /\.overview-metric-grid\s*\{[^}]*grid-template-columns:\s*repeat\(3,/s);
  assert.match(css, /\.overview-status-card\[data-density="compact"\]/);
  assert.match(css, /\.sidebar-top-actions\s*\{/);
  assert.doesNotMatch(css, /\.sidebar-bottom-row\s*\{/);
  assert.doesNotMatch(css, /\.sidebar-drawer\[data-open="false"\] \+ \.sidebar-bottom-row/);
  assert.match(css, /\.language-switcher\s*\{[^}]*width:\s*44px/s);
  assert.match(css, /\.language-switcher\s*\{[^}]*height:\s*44px/s);
  assert.match(css, /\.language-switcher\[data-switching="true"\]/);
});

test("core project routes propagate request locale into bilingual shells", async () => {
  const routes = [
    ["overview", "OverviewSeedShell", "overview-seed-shell"],
    ["assets", "AssetLibraryShell", "asset-library-shell"],
    ["graph", "StoryGraphShell", "story-graph-shell"],
    ["worldline", "WorldlineShell", "worldline-shell"],
    ["character-console", "CharacterConsoleShell", "character-console-shell"],
    ["writer", "WriterWorkbenchShell", "writer-workbench-shell"],
    ["llm-facility", "LLMFacilityShell", "llm-facility-shell"],
  ];

  for (const [route, component, shellName] of routes) {
    const pagePath = `app/(app)/[tenantSlug]/projects/[projectId]/${route}/page.tsx`;
    const shellPath = `components/${shellName}.tsx`;
    const page = await fileText(pagePath);
    const shell = await fileText(shellPath);

    assert.match(page, /currentRequestLocale/, `${pagePath} must read the locale cookie`);
    assert.match(page, /const\s+locale\s*=\s*await\s+currentRequestLocale\(\)/, `${pagePath} must resolve its locale`);
    assert.match(page, new RegExp(`<${component}\\b`), `${pagePath} must render ${component}`);
    assert.match(page, /locale=\{locale\}/, `${pagePath} must pass locale to ${component}`);
    assert.match(shell, /locale:\s*Locale;/, `${shellPath} must declare a locale prop`);
    assert.match(shell, /from "\.\/bilingual-text"/, `${shellPath} must use bilingual display copy`);
    assert.match(shell, /<Bi\b/, `${shellPath} must render bilingual display copy`);
  }
});

test("user-facing shell sources exclude development-only explanatory copy", async () => {
  const userFacingSources = (
    await Promise.all(["app", "components"].map((directory) => sourceFiles(directory)))
  ).flat();
  const forbiddenCopy = /appears until|backed by Postgres|this SaaS slice|Refactor progress|\b[A-Z][A-Z0-9_]*_RUNTIME_PENDING\b/i;

  assert.ok(userFacingSources.length > 0);
  for (const { relativePath, source } of userFacingSources) {
    assert.doesNotMatch(source, forbiddenCopy, `${relativePath} contains development-only copy`);
  }
});

test("Paper-ink design tokens and bookish app shell stay explicit", async () => {
  const css = await fileText("app/globals.css");
  const layout = await fileText("app/(app)/[tenantSlug]/projects/[projectId]/layout.tsx");
  const nav = await fileText("components/project-nav.tsx");

  assert.match(css, /--primary:\s*#8f211b|--primary:\s*var\(--accent-primary\)/);
  assert.match(css, /--accent-primary:\s*#8f211b/);
  assert.match(css, /--surface-app:\s*#f3eee4/);
  assert.match(css, /--radius-panel:\s*8px/);
  assert.match(css, /--motion-standard:\s*220ms/);
  assert.match(css, /--ease-natural:\s*cubic-bezier\(0\.2,\s*0\.8,\s*0\.2,\s*1\)/);
  assert.match(css, /Songti SC/);
  assert.match(css, /Noto Sans SC/);
  assert.match(css, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  assert.match(css, /\.mobile-nav-toggle/);
  assert.match(css, /\.sidebar-drawer\[data-open="true"\]/);
  assert.match(css, /min-height:\s*44px/);
  assert.match(css, /grid-template-columns:\s*minmax\(232px,\s*248px\)/);
  assert.doesNotMatch(css, /--primary:\s*#0f6cbd/);

  assert.match(layout, /className="skip-link"/);
  assert.match(layout, /WorkspaceContextBar|className="app-command-bar project-context-bar"/);
  assert.match(layout, /id="workspace-main"/);
  assert.match(layout, /MobileTopBar/);
  assert.match(layout, /MobileTabBar/);
  assert.match(nav, /mobile-nav-toggle/);
  assert.match(nav, /aria-expanded=\{navigationOpen\}/);
  assert.match(nav, /LanguageSwitcher/);
  assert.match(nav, /BookOpenText/);
});

test("module headers use one Lucide icon language", async () => {
  const shellPaths = [
    "components/overview-seed-shell.tsx",
    "components/asset-library-shell.tsx",
    "components/story-graph-shell.tsx",
    "components/worldline-shell.tsx",
    "components/character-console-shell.tsx",
    "components/writer-workbench-shell.tsx",
    "components/llm-facility-shell.tsx",
  ];
  const shells = (await Promise.all(shellPaths.map((path) => fileText(path)))).join("\n");

  // WorkspaceHeader owns page-title-icon for Overview/Assets; other shells still inline it.
  assert.ok((shells.match(/page-title-icon|icon=\{</g) ?? []).length >= shellPaths.length);
  assert.match(shells, /LayoutDashboard/);
  assert.match(shells, /Boxes/);
  assert.match(shells, /Network/);
  assert.match(shells, /GitBranch/);
  assert.match(shells, /UsersRound/);
  assert.match(shells, /PenLine/);
  assert.match(shells, /Cpu/);
});
