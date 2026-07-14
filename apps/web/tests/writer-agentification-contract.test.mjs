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
  const toast = await source("components/writer-transient-toast.tsx");
  const composer = await source("components/writer-agent-composer.tsx");
  const copy = await source("lib/user-facing-copy.ts");
  const authorCopy = await source("lib/author-copy.ts");
  const taskStatus = await source("lib/writer-task-status.ts");
  const statusLine = await source("components/writer-task-status-line.tsx");
  assert.match(timeline, /writer-activity-timeline/);
  assert.match(timeline, /activityItemsFromEvents/);
  // One run lifecycle row: started is updated by failed/completed (no dual spinner+fail).
  assert.match(timeline, /writer-run-lifecycle|RUN_LIFECYCLE_ID/);
  assert.match(timeline, /writer\.run\.failed/);
  assert.match(timeline, /humanizeFailure/);
  assert.match(timeline, /authorToolLabel/);
  assert.doesNotMatch(timeline, /正在调用 \$\{toolName\}|Calling \$\{toolName\}/);
  assert.match(chip, /writer-context-chip/);
  assert.match(chip, /assets|graph|worldline/);
  assert.match(thread, /sortThreadMessages/);
  assert.match(shell, /threadMessages|WriterAgentThread/);
  assert.match(shell, /WriterCandidateSheet/);
  assert.match(shell, /writer-canvas-tools|TechnicalDetailsDrawer/);
  // No double RSC navigation when clearing admission query params.
  assert.doesNotMatch(toast, /useRouter|from "next\/navigation".*useRouter|router\.replace\(/);
  assert.match(toast, /history\.replaceState/);
  assert.doesNotMatch(toast, /import \{[^}]*useRouter/);
  // Client composer keeps instruction on failure and returns structured result (no redirect flash).
  assert.match(composer, /writerRunAction/);
  assert.match(composer, /preventDefault/);
  assert.match(composer, /writer-composer-inline-error/);
  // Admission navigates via router.replace so App Router sees runId (not replaceState+refresh).
  assert.match(composer, /router\.replace/);
  assert.doesNotMatch(composer, /history\.replaceState/);
  assert.doesNotMatch(composer, /writer-composer-inline-success/);
  assert.doesNotMatch(composer, /写作任务已加入队列/);
  const agentThread = await source("components/writer-agent-thread.tsx");
  assert.match(agentThread, /pendingInstruction|data-pending-message/);
  assert.match(agentThread, /data-thread-persistent/);
  assert.match(agentThread, /MiroFish Writer/);
  assert.match(agentThread, /summarizeWriterTaskStatus/);
  assert.match(agentThread, /WriterTransientToast/);
  assert.match(agentThread, /data-busy|useWriterRunSession/);
  assert.match(agentThread, /data-starting|正在分析需求/);
  assert.match(composer, /beginSubmit|useWriterRunSession/);
  assert.match(composer, /sendLocked|session\?\.busy/);
  const runSession = await source("components/writer-run-session.tsx");
  assert.match(runSession, /WriterRunSessionProvider/);
  assert.match(runSession, /admitRun|beginSubmit|busy/);
  assert.match(runSession, /WriterHomeOrTask/);
  assert.match(copy, /LLM_MODEL_TOOLS_UNSUPPORTED/);
  assert.match(copy, /must support tools/);
  // Doc 36 W1: collapsed task status line + author dictionary.
  assert.match(authorCopy, /authorToolLabel/);
  assert.match(authorCopy, /authorTaskStatusLine/);
  assert.match(authorCopy, /query_assets/);
  assert.match(taskStatus, /summarizeWriterTaskStatus/);
  assert.match(statusLine, /writer-task-status/);
  assert.match(statusLine, /summarizeWriterTaskStatus/);
});

test("Phase 5: SSE client + approval card + held-open stream route", async () => {
  const sse = await source("lib/writer-sse-client.ts");
  const live = await source("components/writer-live-draft.tsx");
  const approval = await source("components/writer-approval-card.tsx");
  const route = await source("app/api/writer-events/[tenantId]/[projectId]/route.ts");
  const shell = await source("components/writer-workbench-shell.tsx");
  const candidate = await source("components/writer-candidate-sheet.tsx");
  const stream = await source("components/writer-run-stream.tsx");
  assert.match(sse, /EventSource/);
  assert.match(sse, /Last-Event-ID|after_event_id/);
  assert.match(sse, /stream=1|stream/);
  assert.match(live, /connectWriterEventStream|useWriterRunStream/);
  assert.match(live, /WriterApprovalCard|WriterTaskStatusLine/);
  assert.match(live, /WriterTaskStatusLine/);
  assert.match(live, /proseOnCanvas|writer-result-summary/);
  assert.doesNotMatch(live, /WriterActivityTimeline/);
  assert.doesNotMatch(live, /ConnectionBanner/);
  assert.match(candidate, /writer-candidate-sheet/);
  assert.match(candidate, /采用为手稿|Adopt into manuscript/);
  assert.match(candidate, /revealArtifact/);
  assert.match(stream, /WriterRunStreamProvider/);
  assert.match(shell, /WriterCandidateSheet|WriterRunSessionProvider/);
  assert.match(shell, /WriterHomeState|writer-home-state|data-home/);
  assert.match(shell, /WriterHomeOrTask/);
  assert.match(shell, /data-layout="conversation-first"/);
  assert.match(shell, /data-mobile-view="conversation"/);
  const home = await source("components/writer-home-state.tsx");
  assert.match(home, /writer-home-state/);
  assert.match(home, /把你想写的告诉我|Tell me what you want to write/);
  assert.match(home, /writer-home-pending-thread|正在分析需求/);
  assert.match(home, /useWriterRunSession/);
  const session = await source("components/writer-run-session.tsx");
  assert.match(session, /WriterRunSessionProvider/);
  assert.match(session, /optimisticRunId|beginSubmit|admitRun/);
  const chapterSwitcher = await source("components/writer-chapter-switcher.tsx");
  assert.match(chapterSwitcher, /WriterChapterSwitcher/);
  const context = await source("components/writer-workbench-context.tsx");
  assert.match(context, /revealArtifact/);
  assert.match(context, /mobileView/);
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
