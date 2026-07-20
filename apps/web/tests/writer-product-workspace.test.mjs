import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

const root = path.resolve(import.meta.dirname, "..");
const source = (name) => readFile(path.join(root, name), "utf8");

test("writer command labels keep internal keys out of author-visible option values", async () => {
  const labels = await source("lib/writer-command-labels.ts");
  assert.match(labels, /Complete outline/);
  assert.match(labels, /Scan forbidden terms/);
  assert.doesNotMatch(labels, /option value="complete_outline"/);
  assert.match(labels, /manuscriptCommandKeyFromChoice/);
});

test("writer product client covers workspace, reviewer, manuscript, commands, dedup and exports", async () => {
  const client = await source("lib/writer-workspace-api.ts");
  for (const route of ["/chapters", "/scenes", "/versions", "/outlines", "/book-plans", "/generations", "/writer-presets", "/forbidden-lexicon", "/reviews", "/draft-review-issues/", "/manuscript-workspace", "/blocks/reorder", "/move", "/tags", "/dedup-extractions", "/dedup-patterns", "/commands", "/exports", "/v1/workflow-runs/"]) {
    assert.match(client, new RegExp(route.replaceAll("/", "\\/")), `missing ${route}`);
  }
  assert.match(client, /expected_version/);
  assert.match(client, /requestEnvelopeList/);
  assert.match(client, /function asArray<T>\(value: T\[\] \| null \| undefined\): T\[\]/);
  assert.match(client, /Array\.isArray\(value\) \? value : \[\]/);
  assert.match(client, /X-CSRF-Token/);
  assert.match(client, /X-Request-Id/);
  assert.match(client, /randomUUID\(\)/);
  assert.match(client, /mirofish_session/);
  assert.doesNotMatch(client, /OPENAI_API_KEY|credential_ref|encrypted_api_key/);
});

test("writer export sends a fresh opaque request id for each explicit mutation", () => {
  const moduleURL = pathToFileURL(path.join(root, "lib/writer-workspace-api.ts")).href;
  const script = `
    const requests = [];
    globalThis.fetch = async (_url, init) => {
      requests.push({ method: init.method || "GET", headers: init.headers });
      return new Response(JSON.stringify(init.method === "POST"
        ? { export: { export_id: "export-1" }, replay: false }
        : { exports: [] }), { status: 200, headers: { "content-type": "application/json" } });
    };
    const api = await import(${JSON.stringify(moduleURL)});
    const context = { tenantId: "tenant-1", projectId: "project-1", actorUserId: "user-1", csrfToken: "csrf-1" };
    await api.createWorkspaceExport(context, "txt");
    await api.createWorkspaceExport(context, "txt");
    await api.listWorkspaceExports(context);
    process.stdout.write(JSON.stringify(requests));
  `;
  const result = spawnSync(process.execPath, ["--conditions=react-server", "--input-type=module", "--eval", script], {
    cwd: root,
    encoding: "utf8",
  });
  assert.equal(result.status, 0, result.stderr);
  const requests = JSON.parse(result.stdout);
  assert.equal(requests.length, 3);
  const firstRequestId = requests[0].headers["X-Request-Id"];
  const secondRequestId = requests[1].headers["X-Request-Id"];
  assert.match(firstRequestId, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
  assert.match(secondRequestId, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
  assert.notEqual(firstRequestId, secondRequestId, "an explicit second export must be a new logical request");
  assert.equal(requests[0].headers["X-CSRF-Token"], "csrf-1");
  assert.equal(requests[2].headers["X-Request-Id"], undefined, "read-only export listing must not create an idempotency key");
});

test("writer empty project bootstrap does not require upload or seed", async () => {
  const workspace = await source("components/writer-product-workspace.tsx");
  assert.match(workspace, /data-empty-writer-bootstrap|EmptyWriterBootstrap/);
  assert.match(workspace, /空项目可直接写作|Empty projects can write immediately/);
  assert.match(workspace, /不需要先上传小说或运行 Seed|do not need to upload a novel or run Seed first/i);
  assert.doesNotMatch(workspace, /必须先上传|must upload before/i);
});

test("writer manuscript empty state explains sections and create falls back on stale chapter", async () => {
  const [workspace, flow, page, copy] = await Promise.all([
    source("components/writer-product-workspace.tsx"),
    source("components/writer-manuscript-flow.tsx"),
    source("app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx"),
    source("lib/user-facing-copy.ts"),
  ]);
  assert.match(workspace, /WriterManuscriptFlow/);
  assert.match(flow, /data-manuscript-empty/);
  assert.match(flow, /data-manuscript-flow/);
  assert.match(flow, /这一章还没有正文|This chapter has no prose yet/);
  assert.match(flow, /开始写这一章|Start writing this chapter/);
  assert.match(flow, /添加空白片段|Add blank section/);
  assert.match(workspace, /ActionToast/);
  const toast = await source("components/writer-action-toast.tsx");
  assert.match(toast, /humanizeFailure/);
  assert.match(page, /createBlockAction/);
  assert.match(page, /NOT_FOUND|HTTP_404/);
  assert.match(page, /chapter_id:\s*""/);
  assert.match(page, /humanizeFailure/);
  assert.match(page, /pickChapterFlowBlocks|MANUSCRIPT_FLOW_CONTENT_LIMIT|getPrivateBlock/);
  assert.match(copy, /MODULE_BINDING_MISSING|LLM_MODULE_BINDING_MISSING|MODULE_NOT_BOUND/);
  assert.match(copy, /WRITER_WORKSPACE_UNAVAILABLE/);
});

test("writer product workspace exposes manuscript asset proposal review rail", async () => {
  const [workspace, page, client] = await Promise.all([
    source("components/writer-product-workspace.tsx"),
    source("app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx"),
    source("lib/writer-workspace-api.ts"),
  ]);
  assert.match(workspace, /data-asset-proposal-rail|ProposalReviewPanel/);
  assert.match(workspace, /accept_create|接受为正典/);
  assert.match(workspace, /after_adoption|正文采用后/);
  assert.match(page, /startDistillationAction|decideProposalAction|patchDistillationSettingsAction/);
  assert.match(client, /startManuscriptAssetDistillation|listAssetProposals|decideAssetProposal|getAssetDistillationSettings/);
});

test("writer artifact views are mutually exclusive and the obsolete long-page layout stays retired", async () => {
  const [workspace, tabs, polish] = await Promise.all([
    source("components/writer-product-workspace.tsx"),
    source("components/writer-artifact-tabs.tsx"),
    source("app/workbench-polish.css"),
  ]);
  assert.match(workspace, /WriterArtifactTabs/);
  assert.match(workspace, /WriterArtifactTabChrome/);
  assert.match(workspace, /chromeInHeader/);
  assert.match(workspace, /WriterChapterSwitcher/);
  assert.match(tabs, /role="tablist"/);
  assert.match(tabs, /role="tab"/);
  assert.match(tabs, /role="tabpanel"/);
  assert.match(tabs, /WriterArtifactTabChrome/);
  assert.match(tabs, /chromeInHeader/);
  assert.match(tabs, /aria-selected=\{selected\}/);
  assert.match(tabs, /hidden=\{activeTab !== tab\.id\}/);
  assert.match(polish, /\.writer-agent-layout/);
  assert.match(polish, /\.writer-artifact-tabpanel\[hidden\]/);
  assert.match(polish, /data-mobile-view="conversation"|conversation.*artifact/);
  // Canvas is tools-rail + stage grid; the stage stays column-flex so
  // display:contents head/body + candidate + meta share space without a dead band.
  assert.match(polish, /\.writer-artifact-workspace\s*\{[^}]*display:\s*contents/s);
  assert.match(polish, /\.writer-artifact-canvas\s*\{[^}]*display:\s*grid/s);
  assert.match(polish, /\.writer-canvas-stage\s*\{[^}]*display:\s*flex/s);
  assert.doesNotMatch(
    polish,
    /\.writer-artifact-canvas\s*\{[^}]*grid-template-rows:\s*auto\s+minmax\(0,\s*1fr\)\s+auto/s,
  );
  assert.match(
    polish,
    /\.app-frame\.app-frame-unified:has\(\.writer-root\)\s+\.writer-agent-layout[\s\S]*?flex:\s*1\s+1\s+auto/s,
  );
  for (const retiredClass of ["writer-studio-grid", "writer-workbench-prose-first", "writer-composer-disclosure", "writer-agent-rail"]) {
    const pattern = new RegExp(retiredClass);
    assert.doesNotMatch(`${workspace}\n${tabs}\n${polish}`, pattern);
  }
});

test("writer product page wires all domain actions and keeps review outside composer mode", async () => {
  const [page, shell, workspace] = await Promise.all([
    source("app/(app)/[tenantSlug]/projects/[projectId]/writer/page.tsx"), source("components/writer-workbench-shell.tsx"), source("components/writer-product-workspace.tsx"),
  ]);
  for (const action of ["createChapterAction", "createSceneAction", "restoreOutlineAction", "createBookPlanAction", "generateBookPlanAction", "createPresetAction", "createLexiconAction", "updateBlockAction", "restoreBlockAction", "startDedupAction", "decideDedupAction", "startCommandAction", "createExportAction"]) assert.match(page, new RegExp(action), `missing ${action}`);
  assert.doesNotMatch(shell, /option value="review"/);
  assert.doesNotMatch(page, /mode === "review"/);
  assert.doesNotMatch(workspace, /placeholder=["']chapter_id["']/);
  assert.doesNotMatch(workspace, /option\s+value=["']complete_outline["']/);
  assert.doesNotMatch(workspace, /option\s+value=["']scan_lexicon["']/);
  assert.match(workspace, /MANUSCRIPT_COMMAND_CHOICES/);
  assert.match(workspace, /commandChoice/);
  assert.match(workspace, /commandChoice/);
  assert.match(workspace, /<ReviewerPanel \{\.\.\.props\} \/>/);
  assert.match(workspace, /status === "completed"/);
  assert.match(workspace, /exportId=/);
  assert.match(workspace, /<a className="nav-link" download href=/);
  assert.doesNotMatch(workspace, /<form[^>]+manuscript-export/);
  assert.match(workspace, /Generate candidate plan/);
  assert.match(workspace, /Extract candidate patterns/);
  assert.match(page, /block_ids: sourceKind === "block"/);
  assert.match(page, /chapter_id: sourceKind === "chapter"/);
  assert.match(page, /manuscriptCommandKeyFromChoice/);
  assert.match(page, /stringFromFormData\(formData, "blockId"\)/);
  assert.doesNotMatch(page, /startDedupExtraction[\s\S]{0,400}content_text/);
});

test("workspace surfaces stable conflict codes without rendering raw backend errors", async () => {
  const [client, workspace] = await Promise.all([source("lib/writer-workspace-api.ts"), source("components/writer-product-workspace.tsx")]);
  assert.match(client, /payload\.error\.code/);
  // Author UI maps failures to recovery copy; codes stay in actionStatus/result data, not primary JSX dumps.
  assert.match(workspace, /actionStatus|!result\.ok/);
  assert.doesNotMatch(workspace, /<strong>\{result\.code\}<\/strong>|<strong>\{value\.code\}<\/strong>/);
  assert.doesNotMatch(workspace, /result\.message|error\.message|JSON\.stringify\(.*error/);
});
