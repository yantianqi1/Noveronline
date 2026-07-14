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

test("Phase 2: TipTap manuscript editor + PE textarea name=content", async () => {
  const editor = await source("components/writer-manuscript-editor.tsx");
  const panel = await source("components/writer-manuscript-panel-client.tsx");
  const product = await source("components/writer-product-workspace.tsx");
  const pkg = await source("package.json");

  assert.match(pkg, /@tiptap\/react/);
  assert.match(pkg, /@tiptap\/starter-kit/);
  assert.match(editor, /next\/dynamic/);
  assert.match(editor, /ssr:\s*false/);
  assert.match(editor, /writer-manuscript-editor-inner/);
  const inner = await source("components/writer-manuscript-editor-inner.tsx");
  assert.match(inner, /useEditor/);
  assert.match(inner, /StarterKit/);
  assert.match(inner, /@tiptap\/react/);
  assert.match(panel, /name="content"/);
  assert.match(panel, /updateBlockAction/);
  assert.match(panel, /expectedVersion/);
  assert.match(product, /WriterManuscriptPanelClient/);
  assert.match(product, /reviseSelection/);
});

test("Phase 3: selection toolbar + revision diff + pure writer-diff", async () => {
  const toolbar = await source("components/writer-selection-toolbar.tsx");
  const diffUi = await source("components/writer-revision-diff.tsx");
  const diffLib = await source("lib/writer-diff.ts");
  assert.match(toolbar, /writer-selection-toolbar/);
  assert.match(toolbar, /rewrite/);
  assert.match(toolbar, /expand/);
  assert.match(toolbar, /condense/);
  assert.match(toolbar, /polish/);
  assert.match(toolbar, /correct/);
  assert.match(diffUi, /writer-revision-diff/);
  assert.match(diffUi, /Accept all|全部接受/);
  assert.match(diffLib, /computeRevisionHunks/);
  assert.match(diffLib, /applyHunkDecisions/);
});

test("Phase 4: activity timeline + context chips + thread helpers", async () => {
  const timeline = await source("components/writer-activity-timeline.tsx");
  const chip = await source("components/writer-context-chip.tsx");
  const thread = await source("lib/writer-thread.ts");
  const shell = await source("components/writer-workbench-shell.tsx");
  assert.match(timeline, /writer-activity-timeline/);
  assert.match(timeline, /activityItemsFromEvents/);
  // One run lifecycle row: started is updated by failed/completed (no dual spinner+fail).
  assert.match(timeline, /writer-run-lifecycle|RUN_LIFECYCLE_ID/);
  assert.match(timeline, /writer\.run\.failed/);
  assert.match(chip, /writer-context-chip/);
  assert.match(chip, /assets|graph|worldline/);
  assert.match(thread, /sortThreadMessages/);
  assert.match(shell, /threadMessages|data-thread-persistent/);
  assert.match(shell, /WriterComposerInput|WriterTransientToast/);
  assert.match(shell, /Pi Writer/);
});

test("Phase 5: SSE client + approval card + held-open stream route", async () => {
  const sse = await source("lib/writer-sse-client.ts");
  const live = await source("components/writer-live-draft.tsx");
  const approval = await source("components/writer-approval-card.tsx");
  const route = await source("app/api/writer-events/[tenantId]/[projectId]/route.ts");
  assert.match(sse, /EventSource/);
  assert.match(sse, /Last-Event-ID|after_event_id/);
  assert.match(sse, /stream=1|stream/);
  assert.match(live, /connectWriterEventStream/);
  assert.match(live, /WriterApprovalCard|WriterActivityTimeline/);
  assert.match(approval, /writer-approval-card/);
  assert.match(approval, /approve|reject/);
  assert.match(route, /text\/event-stream/);
  assert.match(route, /stream/);
});

test("Phase 2–5 plan, migration 0019, shared revise mode exist", async () => {
  const plan = await repositorySource("docs/refactor-saas/30-writer-agentification-and-editor-plan.md");
  const migration = await repositorySource("infra/postgres/migrations/0019_writer_threads.sql");
  const schema = await repositorySource("packages/shared-contracts/schemas/writer-workflow-input.schema.json");
  const events = await repositorySource("packages/shared-contracts/schemas/writer-public-event.schema.json");
  const contracts = await repositorySource("packages/shared-contracts/src/index.js");
  const readiness = await repositorySource("apps/api/cmd/api/readiness.go");
  const piRun = await repositorySource("apps/pi-agent-runtime/src/contracts/writer-run.ts");
  const workerSpec = await repositorySource("apps/pi-agent-runtime/src/worker-spec.ts");

  assert.match(plan, /TipTap/);
  assert.match(migration, /writer_threads/);
  assert.match(migration, /writer_thread_messages/);
  assert.match(migration, /writer_approvals/);
  assert.match(migration, /FORCE ROW LEVEL SECURITY/);
  assert.match(schema, /"revise"/);
  assert.match(events, /writer\.revision\.proposed/);
  assert.match(events, /writer\.approval\.required/);
  assert.match(contracts, /revise/);
  assert.match(readiness, /0019_writer_threads/);
  assert.match(readiness, /requiredMigrationCount\s*=\s*19/);
  assert.match(piRun, /revise/);
  assert.match(workerSpec, /revise/);
  await access(path.join(repositoryRoot, "infra/postgres/rollbacks/0019_writer_threads.sql"));
});

test("Phase 6: visual polish classes for manuscript paper and a11y", async () => {
  const css = await source("app/workbench-polish.css");
  assert.match(css, /\.writer-manuscript-paper/);
  assert.match(css, /#fbf8f1/);
  assert.match(css, /\.writer-selection-toolbar/);
  assert.match(css, /\.writer-revision-diff/);
  assert.match(css, /\.writer-activity-timeline/);
  assert.match(css, /\.writer-approval-card/);
  assert.match(css, /prefers-reduced-motion/);
});
