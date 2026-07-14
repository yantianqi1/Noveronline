import {
  Activity,
  Bot,
  Check,
  ChevronDown,
  ChevronRight,
  CircleStop,
  Download,
  FileCheck2,
  LoaderCircle,
  Paperclip,
  PenLine,
  RefreshCcw,
  RotateCw,
  Send,
  Sparkles,
} from "lucide-react";
import type { ReactNode } from "react";

import { type Locale, tx } from "../lib/locale";
import type {
  AgentTraceEventsSummary,
  AssetListSummary,
  ProjectManuscriptExportManifestSummary,
  ProjectManuscriptSummary,
  StoryGraphViewSummary,
  WorldlineSavedPathsSummary,
  WriterRunEvent,
  WriterRunEventsSummary,
  WriterRunSummary,
} from "../lib/api";
import { Bi, FailureText, StatusValue } from "./bilingual-text";
import { PublicErrorNotice } from "./public-error-notice";
import { SubmitButton } from "./submit-button";
import { TechnicalDetailsDrawer } from "./technical-details-drawer";
import { WorkspaceHeader } from "./workspace-header";
import { WriterLiveDraft } from "./writer-live-draft";
import { WriterCommandPalette, WriterCommandPaletteTrigger } from "./writer-command-palette";
import { WriterComposerKeyboard } from "./writer-composer-keyboard";
import { WriterMobileSwitch } from "./writer-mobile-switch";
import { WriterWorkbenchProvider } from "./writer-workbench-context";

type WriterWorkbenchShellProps = {
  locale: Locale;
  tenantSlug: string;
  projectId: string;
  runSummary: WriterRunSummary | null;
  workflowEvents: WriterRunEventsSummary | null;
  traceEvents: AgentTraceEventsSummary | null;
  assets: AssetListSummary;
  graphView: StoryGraphViewSummary;
  worldlineSavedPaths: WorldlineSavedPathsSummary;
  manuscript: ProjectManuscriptSummary;
  manuscriptExportManifest: ProjectManuscriptExportManifestSummary;
  afterEventId: string;
  selectedRunId: string;
  selectedTraceId: string;
  writerRunStatus: ActionStatus | null;
  traceExportStatus: TraceExportStatus | null;
  draftAdoptionStatus?: ActionStatus | null;
  manuscriptExportStatus?: ActionStatus | null;
  writerControlStatus?: ActionStatus | null;
  selectedDraftId?: string;
  selectedChapterId?: string;
  selectedSceneId?: string;
  manuscriptExportArtifact?: WriterManuscriptExportArtifact | null;
  writerRunAction?: (formData: FormData) => Promise<void>;
  exportTraceAction?: (formData: FormData) => Promise<void>;
  adoptDraftAction?: (formData: FormData) => Promise<void>;
  exportManuscriptAction?: (formData: FormData) => Promise<void>;
  cancelWriterRunAction?: (formData: FormData) => Promise<void>;
  decideApprovalAction?: (formData: FormData) => Promise<void>;
  productWorkspace?: ReactNode;
  structureNav?: ReactNode;
  /** Persistent thread messages when backend thread store is available. */
  threadMessages?: { role: string; body: string; created_at?: string }[];
};

export type WriterManuscriptExportArtifact = {
  artifact_id: string;
  file_name: string;
  media_type: string;
  size_bytes: number;
  download_href: string;
  created_at?: string;
};

type ActionStatus = {
  status: string;
  code: string;
  message: string;
};

type TraceExportStatus = ActionStatus;

export function WriterWorkbenchShell({
  locale,
  tenantSlug,
  projectId,
  runSummary,
  workflowEvents,
  traceEvents,
  assets,
  graphView,
  worldlineSavedPaths,
  manuscript,
  manuscriptExportManifest,
  afterEventId,
  selectedRunId,
  selectedTraceId,
  writerRunStatus,
  traceExportStatus,
  draftAdoptionStatus = null,
  manuscriptExportStatus = null,
  writerControlStatus = null,
  selectedDraftId = "",
  selectedChapterId = "",
  selectedSceneId = "",
  manuscriptExportArtifact = null,
  writerRunAction,
  exportTraceAction,
  adoptDraftAction,
  exportManuscriptAction,
  cancelWriterRunAction,
  decideApprovalAction,
  productWorkspace,
  structureNav,
  threadMessages = [],
}: WriterWorkbenchShellProps) {
  const statusLabel =
    runSummary?.ok === true
      ? runSummary.status
      : runSummary?.ok === false
        ? tx(locale, "错误", "error")
        : tx(locale, "空闲", "idle");
  const traceId = runSummary?.ok === true ? runSummary.trace_id : "";
  const replayRunId = runSummary?.ok === true ? runSummary.run_id : selectedRunId;
  const replayTraceId = selectedTraceId || traceId;
  const recoveredDraftId = recoverDraftId(selectedDraftId, runSummary, workflowEvents);
  const draftIsAdopted = manuscript.ok
    ? manuscript.blocks.some((block) => block.source_draft_id === recoveredDraftId)
    : false;
  const latestRecoveredEvent = latestWriterEvent(workflowEvents);
  const runActive = runSummary?.ok === true && isActiveWriterStatus(runSummary.status);

  return (
    <div className="writer-root">
      <WriterWorkbenchProvider>
      <WriterComposerKeyboard />
      <WorkspaceHeader
        actions={
          <>
            <WriterRunStateChip active={runActive} isError={runSummary?.ok === false} label={statusLabel} locale={locale} />
            <span className="writer-sync-chip" title={tx(locale, "所有更改在提交时即时保存到服务器", "All changes are saved to the server on submit")}>
              <Check aria-hidden="true" size={14} />
              <Bi zh="已同步" en="Synced" />
            </span>
            <WriterCommandPaletteTrigger locale={locale} />
            <TechnicalDetailsDrawer
              description={<Bi zh="恢复、回放与支持信息" en="Recovery, replay, and support information" />}
              label={<><Activity aria-hidden="true" size={16} /><Bi zh="技术详情" en="Technical details" /></>}
            >
            <WriterDiagnostics
              afterEventId={afterEventId}
              draftId={recoveredDraftId}
              exportTraceAction={exportTraceAction}
              latestEvent={latestRecoveredEvent}
              locale={locale}
              replayRunId={replayRunId}
              replayTraceId={replayTraceId}
              runSummary={runSummary}
              selectedRunId={selectedRunId}
              selectedTraceId={selectedTraceId}
              tenantSlug={tenantSlug}
              projectId={projectId}
              traceEvents={traceEvents}
              traceExportStatus={traceExportStatus}
              workflowEvents={workflowEvents}
            />
          </TechnicalDetailsDrawer>
          </>
        }
        className="writer-header"
        eyebrow={
          <nav className="writer-breadcrumb" aria-label={tx(locale, "面包屑导航", "Breadcrumb")}>
            <a className="writer-breadcrumb-link" href={`/${tenantSlug}/projects/${projectId}/overview`}>
              <Bi zh="项目总览" en="Project overview" />
            </a>
            <ChevronRight aria-hidden="true" size={13} />
            <span aria-current="page"><Bi zh="写作 Agent" en="Writer Agent" /></span>
          </nav>
        }
        icon={<Bot size={22} strokeWidth={1.8} />}
        title={<Bi zh="写作台" en="Writer" />}
      />

      <WriterMobileSwitch locale={locale} hasStructure={Boolean(structureNav)} />
      <div className="writer-agent-layout" data-layout="manuscript-primary" data-has-structure={structureNav ? "true" : "false"} data-mobile-view="agent">
        {structureNav ? (
          <nav className="writer-structure-rail" aria-label={tx(locale, "创作结构导航", "Manuscript structure")}>
            {structureNav}
          </nav>
        ) : null}
        <main className="writer-artifact-canvas" aria-label={tx(locale, "稿件工作区", "Manuscript workspace")}>
          <div className="writer-artifact-heading">
            <div>
              <p className="eyebrow"><Bi zh="当前作品" en="Current work" /></p>
              <h2><Bi zh="稿件与创作结构" en="Manuscript and structure" /></h2>
            </div>
            <span>{manuscript.ok ? manuscript.blocks.length : 0} <Bi zh="段" en="blocks" /></span>
          </div>
          {productWorkspace}
          <details className="writer-artifact-meta">
            <summary>
              <span><FileCheck2 aria-hidden="true" size={16} /><Bi zh="稿件状态与导出" en="Manuscript status and export" /></span>
              <ChevronDown aria-hidden="true" size={16} />
            </summary>
            <div className="writer-artifact-meta-content">
              <section className={manuscript.ok ? "" : "error-box"} aria-labelledby="manuscript-metadata-heading">
                <h3 id="manuscript-metadata-heading"><Bi zh="手稿元数据" en="Manuscript metadata" /></h3>
                <ManuscriptMetadataPanel locale={locale} manuscript={manuscript} />
              </section>
              <section
                className={manuscriptExportManifest.ok && manuscriptExportStatus?.status !== "error" ? "" : "error-box"}
                aria-labelledby="manuscript-export-heading"
              >
                <h3 id="manuscript-export-heading"><Bi zh="导出正文" en="Export manuscript" /></h3>
                <ManuscriptExportManifestPanel
                  artifact={manuscriptExportArtifact}
                  exportAction={exportManuscriptAction}
                  locale={locale}
                  manifest={manuscriptExportManifest}
                  status={manuscriptExportStatus}
                />
              </section>
            </div>
          </details>
        </main>

        <aside className="writer-agent-dock" aria-label={tx(locale, "写作 Agent", "Writer Agent")}>
          <WriterAgentThread
            adoptDraftAction={adoptDraftAction}
            assets={assets}
            cancelWriterRunAction={cancelWriterRunAction}
            decideApprovalAction={decideApprovalAction}
            draftAdoptionStatus={draftAdoptionStatus}
            draftIsAdopted={draftIsAdopted}
            graphView={graphView}
            locale={locale}
            projectId={projectId}
            tenantSlug={tenantSlug}
            recoveredDraftId={recoveredDraftId}
            runActive={runActive}
            runSummary={runSummary}
            selectedChapterId={selectedChapterId}
            selectedSceneId={selectedSceneId}
            threadMessages={threadMessages}
            workflowEvents={workflowEvents}
            worldlineSavedPaths={worldlineSavedPaths}
            writerControlStatus={writerControlStatus}
            writerRunAction={writerRunAction}
            writerRunStatus={writerRunStatus}
          />
        </aside>
      </div>
      <WriterCommandPalette locale={locale} />
      </WriterWorkbenchProvider>
    </div>
  );
}

function WriterRunStateChip({
  active,
  isError,
  label,
  locale,
}: {
  active: boolean;
  isError: boolean;
  label: string;
  locale: Locale;
}) {
  const state = isError ? "error" : active ? "active" : "idle";
  return (
    <span className="writer-run-state-chip" data-state={state} title={tx(locale, "写作运行状态", "Writer run state")}>
      <span aria-hidden="true" className="writer-run-state-dot" />
      <span className="writer-run-state-label"><Bi zh="状态：" en="Status: " />{label}</span>
    </span>
  );
}

function WriterAgentThread({
  adoptDraftAction,
  assets,
  cancelWriterRunAction,
  decideApprovalAction,
  draftAdoptionStatus,
  draftIsAdopted,
  graphView,
  locale,
  projectId,
  tenantSlug,
  recoveredDraftId,
  runActive,
  runSummary,
  selectedChapterId,
  selectedSceneId,
  threadMessages,
  workflowEvents,
  worldlineSavedPaths,
  writerControlStatus,
  writerRunAction,
  writerRunStatus,
}: {
  adoptDraftAction?: (formData: FormData) => Promise<void>;
  assets: AssetListSummary;
  cancelWriterRunAction?: (formData: FormData) => Promise<void>;
  decideApprovalAction?: (formData: FormData) => Promise<void>;
  draftAdoptionStatus: ActionStatus | null;
  draftIsAdopted: boolean;
  graphView: StoryGraphViewSummary;
  locale: Locale;
  projectId: string;
  tenantSlug: string;
  recoveredDraftId: string;
  runActive: boolean;
  runSummary: WriterRunSummary | null;
  selectedChapterId: string;
  selectedSceneId: string;
  threadMessages: { role: string; body: string; created_at?: string }[];
  workflowEvents: WriterRunEventsSummary | null;
  worldlineSavedPaths: WorldlineSavedPathsSummary;
  writerControlStatus: ActionStatus | null;
  writerRunAction?: (formData: FormData) => Promise<void>;
  writerRunStatus: ActionStatus | null;
}) {
  const run = runSummary?.ok === true ? runSummary : null;
  const hasPersistentThread = threadMessages.length > 0;
  return (
    <section className="writer-agent-thread" aria-labelledby="writer-agent-thread-heading" data-thread-persistent={hasPersistentThread ? "true" : "false"}>
      <header className="writer-agent-toolbar">
        <div className="writer-agent-identity">
          <span className="writer-agent-avatar"><Bot aria-hidden="true" size={19} /></span>
          <div>
            <h2 id="writer-agent-thread-heading">MiroFish Writer</h2>
            <small>{writerStageLabel(locale, run, workflowEvents)}</small>
          </div>
        </div>
        {run ? (
          <WriterRunControl
            action={cancelWriterRunAction}
            runId={run.run_id}
            runStatus={run.status}
            status={writerControlStatus}
          />
        ) : null}
      </header>

      <div className="writer-thread-scroll">
        {hasPersistentThread
          ? threadMessages.map((message, index) => (
              <article
                className={`writer-message writer-message-${message.role === "user" ? "user" : "agent"}`}
                key={`thread-${index}-${message.created_at ?? ""}`}
                data-thread-message="true"
              >
                <div className="writer-message-meta">
                  <span>
                    {message.role === "user" ? <PenLine aria-hidden="true" size={15} /> : <Sparkles aria-hidden="true" size={15} />}
                    {message.role === "user" ? <Bi zh="你" en="You" /> : "MiroFish Writer"}
                  </span>
                </div>
                <p>{message.body}</p>
              </article>
            ))
          : null}
        {runSummary?.ok === false ? (
          <PublicErrorNotice message={<FailureText />} title={<Bi zh="写作会话暂不可用" en="Writer session unavailable" />} />
        ) : run ? (
          <>
            {!hasPersistentThread ? (
              <article className="writer-message writer-message-user">
                <div className="writer-message-meta">
                  <span><PenLine aria-hidden="true" size={15} /><Bi zh="你" en="You" /></span>
                  <small>{writerModeLabel(locale, run.mode)}</small>
                </div>
                <p>{run.instruction}</p>
              </article>
            ) : null}
            <article className="writer-message writer-message-agent">
              <div className="writer-message-meta">
                <span><Sparkles aria-hidden="true" size={15} />MiroFish Writer</span>
                <small><StatusValue value={run.status} /></small>
              </div>
              <WriterLiveDraft
                active={runActive}
                decideApprovalAction={decideApprovalAction}
                initialEvents={workflowEvents?.ok === true ? workflowEvents.items : []}
                locale={locale}
                projectId={projectId}
                runId={run.run_id}
                tenantSlug={tenantSlug}
              />
              {recoveredDraftId ? (
                <div className="writer-candidate-actions">
                  <div>
                    <strong><Bi zh="候选稿" en="Candidate draft" /></strong>
                    <small>{draftIsAdopted ? <Bi zh="已进入手稿" en="Adopted into manuscript" /> : <Bi zh="等待你的决定" en="Waiting for your decision" />}</small>
                  </div>
                  <DraftAdoptionPanel
                    action={adoptDraftAction}
                    adopted={draftIsAdopted}
                    chapterId={selectedChapterId}
                    draftId={recoveredDraftId}
                    status={draftAdoptionStatus}
                  />
                </div>
              ) : null}
            </article>
          </>
        ) : !hasPersistentThread ? (
          <div className="writer-agent-empty">
            <span><Sparkles aria-hidden="true" size={24} /></span>
            <h2><Bi zh="从下一段开始" en="Begin with the next passage" /></h2>
            <p><Bi zh="把这一刻写清楚。" en="Make this moment precise." /></p>
          </div>
        ) : null}
      </div>

      <div className="writer-composer-dock">
        {writerRunStatus ? <StatusLine status={writerRunStatus} /> : null}
        {writerRunAction ? (
          <form action={writerRunAction} className="writer-agent-composer">
            <input name="chapterId" type="hidden" value={selectedChapterId} />
            <input name="sceneId" type="hidden" value={selectedSceneId} />
            <fieldset className="writer-mode-segmented">
              <legend className="sr-only"><Bi zh="写作模式" en="Writing mode" /></legend>
              {(["draft", "continue", "outline", "revise"] as const).map((mode, index) => (
                <label key={mode}>
                  <input defaultChecked={index === 0} name="mode" type="radio" value={mode} />
                  <span>{writerModeLabel(locale, mode)}</span>
                </label>
              ))}
            </fieldset>
            <label className="sr-only" htmlFor="writer-instruction"><Bi zh="写作指令" en="Instruction" /></label>
            <div className="writer-composer-input-row">
              <textarea
                id="writer-instruction"
                name="instruction"
                placeholder={tx(locale, "写下下一段要发生什么……", "What should happen next?")}
                required
                rows={3}
              />
              <SubmitButton
                aria-label={tx(locale, "开始写作", "Start writer run")}
                className="writer-send-button"
                idleLabel={<><Send aria-hidden="true" size={18} /><span className="sr-only"><Bi zh="开始写作" en="Start writer run" /></span></>}
                pendingLabel={<><LoaderCircle aria-hidden="true" className="is-spinning" size={18} /><span className="sr-only"><Bi zh="启动中" en="Starting" /></span></>}
                title={tx(locale, "开始写作", "Start writer run")}
              />
            </div>
            <ContextPickers assets={assets} graphView={graphView} locale={locale} worldlineSavedPaths={worldlineSavedPaths} />
          </form>
        ) : (
          <p className="form-hint"><Bi zh="当前无法开始写作任务。" en="Writer runs are currently unavailable." /></p>
        )}
      </div>
    </section>
  );
}

function WriterDiagnostics({
  afterEventId,
  draftId,
  exportTraceAction,
  latestEvent,
  locale,
  projectId,
  replayRunId,
  replayTraceId,
  runSummary,
  selectedRunId,
  selectedTraceId,
  tenantSlug,
  traceEvents,
  traceExportStatus,
  workflowEvents,
}: {
  afterEventId: string;
  draftId: string;
  exportTraceAction?: (formData: FormData) => Promise<void>;
  latestEvent: WriterRunEvent | null;
  locale: Locale;
  projectId: string;
  replayRunId: string;
  replayTraceId: string;
  runSummary: WriterRunSummary | null;
  selectedRunId: string;
  selectedTraceId: string;
  tenantSlug: string;
  traceEvents: AgentTraceEventsSummary | null;
  traceExportStatus: TraceExportStatus | null;
  workflowEvents: WriterRunEventsSummary | null;
}) {
  return (
    <div className="writer-diagnostics-grid">
      <section className={`panel ${runSummary?.ok === false ? "error-box" : ""}`} aria-labelledby="trace-heading">
        <p className="eyebrow"><Bi zh="追踪" en="Trace" /></p>
        <h2 id="trace-heading"><Bi zh="任务上下文" en="Run context" /></h2>
        {runSummary?.ok === false ? <PublicErrorNotice message={<FailureText />} title={<Bi zh="任务暂不可用" en="Run unavailable" />} /> : (
          <dl className="technical-recovery-fields">
            <dt><Bi zh="任务" en="Run" /></dt><dd>{replayRunId || tx(locale, "未选择", "not selected")}</dd>
            <dt><Bi zh="追踪" en="Trace" /></dt><dd>{replayTraceId || tx(locale, "未选择", "not selected")}</dd>
          </dl>
        )}
        {traceExportStatus ? <p className={traceExportStatus.status === "error" ? "form-status error-box" : "form-status"}>{traceExportStatus.status === "error" ? <FailureText /> : <Bi zh="追踪记录已准备好。" en="Trace export is ready." />}</p> : null}
        {replayTraceId && exportTraceAction ? <form action={exportTraceAction} className="inline-action-form"><input name="traceId" type="hidden" value={replayTraceId} /><button type="submit"><Bi zh="导出脱敏追踪" en="Export redacted trace" /></button></form> : null}
      </section>

      <section className={`panel ${workflowEvents?.ok === false ? "error-box" : ""}`} aria-labelledby="tool-results-heading">
        <p className="eyebrow"><Bi zh="工具结果" en="Tool Results" /></p>
        <h2 id="tool-results-heading"><Bi zh="工具结果" en="Tool result cards" /></h2>
        <ToolResultCards locale={locale} workflowEvents={workflowEvents} />
      </section>

      <section className={`panel ${workflowEvents?.ok === false ? "error-box" : ""}`} aria-labelledby="workflow-events-heading">
        <p className="eyebrow"><Bi zh="写作事件" en="Writer Events" /></p>
        <h2 id="workflow-events-heading"><Bi zh="事件回放" en="Recovered stream" /></h2>
        <RecoveryActions afterEventId={afterEventId} draftId={draftId} latestEvent={latestEvent} runId={replayRunId} target={writerHref(tenantSlug, projectId)} traceId={replayTraceId} />
        <form action={writerHref(tenantSlug, projectId)} className="binding-form" method="get">
          <input name="runId" type="hidden" value={runSummary?.ok === true ? runSummary.run_id : selectedRunId} />
          <input name="traceId" type="hidden" value={selectedTraceId || replayTraceId} />
          {draftId ? <input name="draftId" type="hidden" value={draftId} /> : null}
          <label htmlFor="writer-event-cursor"><Bi zh="事件游标" en="Event cursor" /></label>
          <input id="writer-event-cursor" name="after_event_id" defaultValue={afterEventId} placeholder="evt_..." />
          <button type="submit"><Bi zh="请求回放事件" en="Request replay events" /></button>
        </form>
        <WriterEvents workflowEvents={workflowEvents} />
      </section>

      <section className={`panel ${traceEvents?.ok === false ? "error-box" : ""}`} aria-labelledby="trace-events-heading">
        <p className="eyebrow"><Bi zh="追踪事件" en="Trace Events" /></p>
        <h2 id="trace-events-heading"><Bi zh="事件流" en="Event stream" /></h2>
        <TraceEvents traceEvents={traceEvents} />
      </section>
    </div>
  );
}

function writerProgressStage(workflowEvents: WriterRunEventsSummary | null) {
  if (workflowEvents?.ok !== true) {
    return 0;
  }
  const eventTypes = new Set(workflowEvents.items.map((event) => event.event_type));
  if (eventTypes.has("writer.draft.saved") || eventTypes.has("writer.run.completed")) return 3;
  if (eventTypes.has("writer.token")) return 2;
  if (eventTypes.has("writer.tool.started") || eventTypes.has("writer.tool.completed")) return 1;
  return 0;
}

function writerStageLabel(locale: Locale, run: Extract<WriterRunSummary, { ok: true }> | null, workflowEvents: WriterRunEventsSummary | null) {
  if (!run) return tx(locale, "等待指令", "Ready for direction");
  if (run.status === "completed") return tx(locale, "候选稿已完成", "Candidate complete");
  if (run.status === "failed") return tx(locale, "本次写作未完成", "Run did not complete");
  if (run.status === "cancelled") return tx(locale, "本次写作已取消", "Run cancelled");
  const stage = writerProgressStage(workflowEvents);
  return [
    tx(locale, "正在理解任务", "Understanding the task"),
    tx(locale, "正在检索创作上下文", "Retrieving story context"),
    tx(locale, "正在起草正文", "Drafting prose"),
    tx(locale, "正在保存候选稿", "Saving candidate"),
  ][stage];
}

function writerModeLabel(locale: Locale, mode: string) {
  if (mode === "continue") return tx(locale, "续写", "Continue");
  if (mode === "outline") return tx(locale, "大纲", "Outline");
  if (mode === "revise") return tx(locale, "修订", "Revise");
  return tx(locale, "起草", "Draft");
}

function isActiveWriterStatus(status: string) {
  return status === "queued" || status === "running";
}

function WriterRunControl({
  action,
  runId,
  runStatus,
  status,
}: {
  action?: (formData: FormData) => Promise<void>;
  runId: string;
  runStatus: string;
  status: ActionStatus | null;
}) {
  const active = runStatus === "queued" || runStatus === "running";
  return (
    <div className="compact-action-list">
      {status ? <StatusLine status={status} /> : null}
      {active && action ? (
        <form action={action} className="inline-action-form">
          <input name="runId" type="hidden" value={runId} />
          <button type="submit">
            <CircleStop aria-hidden="true" size={16} />
            <Bi zh="取消写作任务" en="Cancel writer run" />
          </button>
        </form>
      ) : null}
    </div>
  );
}

function RecoveryActions({
  afterEventId,
  draftId,
  latestEvent,
  runId,
  target,
  traceId,
}: {
  afterEventId: string;
  draftId: string;
  latestEvent: WriterRunEvent | null;
  runId: string;
  target: string;
  traceId: string;
}) {
  if (!runId) {
    return null;
  }

  const reconnectCursor = latestEvent?.event_id || afterEventId;
  return (
    <div className="compact-action-list" aria-label="Writer stream recovery controls">
      <form action={target} className="inline-action-form" method="get">
        <RecoveryFields afterEventId={afterEventId} draftId={draftId} runId={runId} traceId={traceId} />
        <button type="submit">
          <RefreshCcw aria-hidden="true" size={16} />
          <Bi zh="刷新任务状态" en="Refresh run status" />
        </button>
      </form>
      {reconnectCursor ? (
        <form action={target} className="inline-action-form" method="get">
          <RecoveryFields afterEventId={reconnectCursor} draftId={draftId} runId={runId} traceId={traceId} />
          <button type="submit">
            <RotateCw aria-hidden="true" size={16} />
            <Bi zh="从最新事件重连" en="Reconnect after latest event" />
          </button>
        </form>
      ) : null}
      {latestEvent ? (
        <p className="trace-meta">
          <Bi zh="最新已接收事件" en="Latest received event" />: #{latestEvent.sequence} / {latestEvent.event_type} / {latestEvent.event_id}
        </p>
      ) : null}
    </div>
  );
}

function RecoveryFields({
  afterEventId,
  draftId,
  runId,
  traceId,
}: {
  afterEventId: string;
  draftId: string;
  runId: string;
  traceId: string;
}) {
  return (
    <>
      <input name="runId" type="hidden" value={runId} />
      <input name="traceId" type="hidden" value={traceId} />
      <input name="after_event_id" type="hidden" value={afterEventId} />
      {draftId ? <input name="draftId" type="hidden" value={draftId} /> : null}
    </>
  );
}

function DraftAdoptionPanel({
  action,
  adopted,
  chapterId = "",
  draftId,
  status,
}: {
  action?: (formData: FormData) => Promise<void>;
  adopted: boolean;
  chapterId?: string;
  draftId: string;
  status: ActionStatus | null;
}) {
  if (!draftId) {
    return <p className="form-hint"><Bi zh="候选草稿尚不可用。" en="Candidate draft unavailable." /></p>;
  }

  return (
    <div className="compact-action-list">
      <p className="trace-meta">
        <Bi zh="候选草稿" en="Candidate draft" />{" "}
        <strong><StatusValue value={adopted ? "adopted" : "candidate"} /></strong>
      </p>
      {status ? <StatusLine status={status} /> : null}
      {!adopted && action ? (
        <form action={action} className="inline-action-form">
          <input name="draftId" type="hidden" value={draftId} />
          {chapterId ? <input name="chapterId" type="hidden" value={chapterId} /> : null}
          <button type="submit">
            <FileCheck2 aria-hidden="true" size={16} />
            <Bi zh="采用为手稿" en="Adopt draft into manuscript" />
          </button>
        </form>
      ) : null}
    </div>
  );
}

function ManuscriptMetadataPanel({ locale, manuscript }: { locale: Locale; manuscript: ProjectManuscriptSummary }) {
  if (!manuscript.ok) {
    return <p>{apiErrorLine(manuscript, "MANUSCRIPT_BACKEND_UNCONFIGURED", locale)}</p>;
  }

  if (manuscript.blocks.length === 0) {
    return <p className="form-hint"><Bi zh="暂无手稿块元数据。" en="No manuscript metadata blocks returned." /></p>;
  }

  return (
    <div>
      <dl>
        <dt><Bi zh="手稿块" en="Blocks" /></dt>
        <dd>{manuscript.blocks.length}</dd>
      </dl>
      <div className="compact-action-list">
        {manuscript.blocks.slice(0, 8).map((block, index) => (
          <article className="tool-result-item" key={block.block_id} data-block-id={block.block_id} data-chapter-id={block.chapter_id || ""} data-source-draft-id={block.source_draft_id || ""}>
            <strong><Bi zh={`正文块 ${index + 1}`} en={`Manuscript block ${index + 1}`} /></strong>
            <span>
              <Bi zh="顺序 " en="Order " />{block.block_order} / <StatusValue value={block.status || "unknown"} />
            </span>
            <small>
              <Bi zh="字数 " en="Words " />{block.word_count}
            </small>
            <small>
              <Bi zh="更新于 " en="Updated " />{block.updated_at || tx(locale, "未知", "unknown")}
            </small>
          </article>
        ))}
      </div>
    </div>
  );
}

function ManuscriptExportManifestPanel({
  artifact,
  exportAction,
  locale,
  manifest,
  status,
}: {
  artifact: WriterManuscriptExportArtifact | null;
  exportAction?: (formData: FormData) => Promise<void>;
  locale: Locale;
  manifest: ProjectManuscriptExportManifestSummary;
  status: ActionStatus | null;
}) {
  if (!manifest.ok) {
    return <p>{apiErrorLine(manifest, "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED", locale)}</p>;
  }

  return (
    <div>
      <dl>
        <dt><Bi zh="格式" en="Format" /></dt>
        <dd>{manifest.format || tx(locale, "未知", "unknown")}</dd>
        <dt><Bi zh="状态" en="Status" /></dt>
        <dd>{manifest.status || tx(locale, "未知", "unknown")}</dd>
        <dt><Bi zh="手稿块" en="Blocks" /></dt>
        <dd>{manifest.block_count}</dd>
        <dt><Bi zh="总字数" en="Total words" /></dt>
        <dd>{manifest.total_word_count}</dd>
        <dt><Bi zh="生成时间" en="Generated" /></dt>
        <dd>{manifest.generated_at || tx(locale, "尚未生成", "not generated")}</dd>
      </dl>
      {manifest.blocks.length === 0 ? (
        <p className="form-hint"><Bi zh="暂无导出清单块元数据。" en="No manifest block metadata returned." /></p>
      ) : (
        <div className="compact-action-list">
          {manifest.blocks.slice(0, 8).map((manifestBlock, index) => (
            <article className="tool-result-item" key={`${manifestBlock.block_id}-${manifestBlock.block_order}`}>
              <strong><Bi zh={`正文块 ${index + 1}`} en={`Manuscript block ${index + 1}`} /></strong>
              <span><Bi zh="顺序 " en="Order " />{manifestBlock.block_order}</span>
              <small><Bi zh="字数 " en="Words " />{manifestBlock.word_count}</small>
            </article>
          ))}
        </div>
      )}
      {status ? <StatusLine status={status} /> : null}
      {exportAction ? (
        <form action={exportAction} className="inline-action-form">
          <input name="format" type="hidden" value="text" />
          <button disabled={manifest.block_count === 0} type="submit">
            <Download aria-hidden="true" size={16} />
            <Bi zh="生成正文导出文件" en="Generate manuscript export" />
          </button>
        </form>
      ) : null}
      {artifact ? <ManuscriptArtifactDownload artifact={artifact} locale={locale} /> : null}
    </div>
  );
}

function ManuscriptArtifactDownload({
  artifact,
  locale,
}: {
  artifact: WriterManuscriptExportArtifact;
  locale: Locale;
}) {
  if (!artifact.artifact_id || !artifact.download_href) {
    return (
      <p className="form-status error-box" role="alert">
        <FailureText />
      </p>
    );
  }

  return (
    <div className="compact-action-list">
      <dl>
        <dt><Bi zh="文件" en="File" /></dt>
        <dd>{artifact.file_name || tx(locale, "导出的手稿", "Exported manuscript")}</dd>
        <dt><Bi zh="类型" en="Media type" /></dt>
        <dd>{artifact.media_type || tx(locale, "未知", "unknown")}</dd>
		{artifact.size_bytes > 0 ? (
			<>
				<dt><Bi zh="大小" en="Size" /></dt>
				<dd>{formatByteSize(artifact.size_bytes, locale)}</dd>
			</>
		) : null}
      </dl>
      <form action={artifact.download_href} className="inline-action-form" method="get">
        <button type="submit">
          <Download aria-hidden="true" size={16} />
          <Bi zh="下载导出的手稿" en="Download exported manuscript" />
        </button>
      </form>
    </div>
  );
}

function ContextPickers({
  assets,
  graphView,
  locale,
  worldlineSavedPaths,
}: {
  assets: AssetListSummary;
  graphView: StoryGraphViewSummary;
  locale: Locale;
  worldlineSavedPaths: WorldlineSavedPathsSummary;
}) {
  return (
    <details className="writer-context-disclosure">
      <summary id="context-picker-heading"><span><Paperclip aria-hidden="true" size={15} /><Bi zh="添加创作上下文" en="Add story context" /></span></summary>
      <section className="reference-picker" aria-labelledby="context-picker-heading">
      <div className="reference-grid">
        <ReferenceAssets assets={assets} />
        <ReferenceGraphNodes graphView={graphView} />
        <ReferenceWorldlinePaths locale={locale} worldlineSavedPaths={worldlineSavedPaths} />
      </div>
      </section>
    </details>
  );
}

function ReferenceAssets({ assets }: { assets: AssetListSummary }) {
  if (!assets.ok) {
    return (
      <div className="reference-card error-box">
        <strong><Bi zh="项目资产" en="Project assets" /></strong>
        <p className="form-hint"><FailureText /></p>
      </div>
    );
  }

  return (
    <div className="reference-card">
      <strong><Bi zh="项目资产" en="Project assets" /></strong>
      {assets.items.length === 0 ? (
        <p className="form-hint"><Bi zh="暂无可选资产。" en="No selectable assets returned." /></p>
      ) : (
        <div className="compact-action-list">
          {assets.items.slice(0, 8).map((asset) => (
            <label className="checkbox-row" key={asset.asset_id}>
              <input name="selectedAssetIds" type="checkbox" value={asset.asset_id} />
              <span>
                {asset.title || asset.asset_id}
                <small>{asset.asset_type} / <StatusValue value={asset.lifecycle} /></small>
              </span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function ReferenceGraphNodes({ graphView }: { graphView: StoryGraphViewSummary }) {
  if (!graphView.ok) {
    return (
      <div className="reference-card error-box">
        <strong><Bi zh="图谱节点" en="Graph nodes" /></strong>
        <p className="form-hint"><FailureText /></p>
      </div>
    );
  }

  return (
    <div className="reference-card">
      <strong><Bi zh="图谱节点" en="Graph nodes" /></strong>
      {graphView.nodes.length === 0 ? (
        <p className="form-hint"><Bi zh="暂无可选图谱节点。" en="No selectable graph nodes returned." /></p>
      ) : (
        <div className="compact-action-list">
          {graphView.nodes.slice(0, 8).map((node) => (
            <label className="checkbox-row" key={node.node_id}>
              <input
                name="selectedGraphNodeIds"
                type="checkbox"
                value={`${node.node_id}\t${node.title}`}
              />
              <span>
                {node.title || node.node_id}
                <small>{node.node_type} / <Bi zh="证据 " en="evidence " />{node.evidence_count}</small>
              </span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function ReferenceWorldlinePaths({
  locale,
  worldlineSavedPaths,
}: {
  locale: Locale;
  worldlineSavedPaths: WorldlineSavedPathsSummary;
}) {
  return (
    <div className={`reference-card ${worldlineSavedPaths.ok ? "" : "error-box"}`}>
      <strong><Bi zh="世界线路径" en="Worldline paths" /></strong>
      {!worldlineSavedPaths.ok ? (
        <p className="form-hint"><FailureText /></p>
      ) : worldlineSavedPaths.items.length === 0 ? (
        <p className="form-hint"><Bi zh="暂无可选的已保存路径。" en="No selectable saved paths returned." /></p>
      ) : (
        <div className="compact-action-list">
          {worldlineSavedPaths.items.slice(0, 8).map((path) => (
            <label className="checkbox-row" key={path.path_id}>
              <input name="worldlinePathIds" type="checkbox" value={path.path_id} />
              <span>
                {path.title || path.path_id}
                <small>
                  {path.lifecycle || tx(locale, "已保存", "saved")} / <Bi zh="事件 " en="events " />{path.selected_event_ids.length}
                </small>
                {path.summary || path.writer_instruction ? (
                  <small>{path.summary || path.writer_instruction}</small>
                ) : null}
              </span>
            </label>
          ))}
        </div>
      )}
      <p className="form-hint">
        <Bi
          zh="在 Worldline 中保存路径后，可在此勾选作为写作参考。"
          en="After saving paths in Worldline, select them here as writer references."
        />
      </p>
    </div>
  );
}

function StatusLine({ status }: { status: ActionStatus }) {
  if (status.status === "error") {
    return (
      <PublicErrorNotice
        message={<FailureText />}
        recovery={<Bi zh="请检查输入后重试。" en="Check the input and try again." />}
        title={<Bi zh="操作未完成" en="Action incomplete" />}
      />
    );
  }
  return (
    <p className="form-status success-box">
      <Bi zh="操作已提交。" en="Action submitted." />
    </p>
  );
}

function apiErrorLine(status: { code: string; message: string }, fallbackCode: string, locale: Locale) {
  const code = status.code || fallbackCode;
  return tx(locale, `${code}: 暂时无法加载，请稍后重试。`, `${code}: Unable to load this data. Try again shortly.`);
}

type ToolCompletedEvent = {
  event: WriterRunEvent;
  toolName: string;
  isError: boolean;
  result: Record<string, unknown>;
};

function ToolResultCards({ locale, workflowEvents }: { locale: Locale; workflowEvents: WriterRunEventsSummary | null }) {
  if (workflowEvents?.ok === false) {
    return (
      <p>
        <FailureText />
      </p>
    );
  }

  if (!workflowEvents) {
    return <p><Bi zh="尚未选择工具结果流。" en="No tool result stream selected." /></p>;
  }

  const toolEvents = workflowEvents.items
    .filter((event) => event.event_type === "writer.tool.completed")
    .map(toToolCompletedEvent)
    .filter((event): event is ToolCompletedEvent => event !== null);

  if (toolEvents.length === 0) {
    return <p><Bi zh="该任务还没有已完成的写作工具结果。" en="No completed writer tool results recorded for this run." /></p>;
  }

  return (
    <div className="tool-result-grid">
      {toolEvents.map((toolEvent) => (
        <ToolResultCard key={`${toolEvent.event.event_id}-${toolEvent.event.sequence}`} locale={locale} toolEvent={toolEvent} />
      ))}
    </div>
  );
}

function ToolResultCard({ locale, toolEvent }: { locale: Locale; toolEvent: ToolCompletedEvent }) {
  if (toolEvent.isError) {
    return <ToolErrorCard locale={locale} toolEvent={toolEvent} />;
  }

  if (toolEvent.toolName === "query_assets") {
    return <AssetToolResultCard locale={locale} toolEvent={toolEvent} />;
  }

  if (toolEvent.toolName === "query_graph_neighbors") {
    return <GraphToolResultCard locale={locale} toolEvent={toolEvent} />;
  }

  if (toolEvent.toolName === "query_worldline_paths") {
    return <WorldlinePathToolResultCard locale={locale} toolEvent={toolEvent} />;
  }

  return <UnknownToolResultCard toolEvent={toolEvent} />;
}

function writerHref(tenantSlug: string, projectId: string) {
  return `/${tenantSlug}/projects/${projectId}/writer`;
}

function AssetToolResultCard({ locale, toolEvent }: { locale: Locale; toolEvent: ToolCompletedEvent }) {
  const items = arrayOfRecords(toolEvent.result.items);

  return (
    <article className="tool-result-card">
      <ToolCardHeader toolEvent={toolEvent} label={<Bi zh="资产" en="Assets" />} count={items.length} />
      {items.length === 0 ? (
        <p className="trace-meta"><Bi zh="没有匹配的资产。" en="No matching assets returned." /></p>
      ) : (
        <div className="tool-result-items">
          {items.slice(0, 4).map((asset, index) => (
            <div className="tool-result-item" key={stringValue(asset, "asset_id") || index}>
              <strong>{stringValue(asset, "title") || stringValue(asset, "asset_id") || tx(locale, "未命名资产", "Untitled asset")}</strong>
              <span>
                {stringValue(asset, "asset_type") || tx(locale, "资产", "asset")} / {stringValue(asset, "lifecycle") || tx(locale, "未知", "unknown")}
              </span>
              <small>{stringValue(asset, "summary") || stringValue(asset, "source") || tx(locale, "暂无公开摘要。", "No public summary.")}</small>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

function GraphToolResultCard({ locale, toolEvent }: { locale: Locale; toolEvent: ToolCompletedEvent }) {
  const node = recordValue(toolEvent.result.node);
  const neighbors = arrayOfRecords(toolEvent.result.neighbors);

  return (
    <article className="tool-result-card">
      <ToolCardHeader toolEvent={toolEvent} label={<Bi zh="图谱邻接节点" en="Graph neighbors" />} count={neighbors.length} />
      <div className="tool-result-item">
        <strong>{stringValue(node, "title") || stringValue(node, "node_id") || tx(locale, "图谱节点", "Graph node")}</strong>
        <span>{stringValue(node, "node_type") || tx(locale, "节点", "node")}</span>
      </div>
      {neighbors.length > 0 ? (
        <div className="tool-result-items">
          {neighbors.slice(0, 4).map((neighbor, index) => (
            <div className="tool-result-item" key={stringValue(neighbor, "node_id") || index}>
              <strong>{stringValue(neighbor, "title") || stringValue(neighbor, "node_id") || tx(locale, "邻接节点", "Neighbor")}</strong>
              <span>{stringValue(neighbor, "relationship") || stringValue(neighbor, "edge_type") || tx(locale, "邻接", "neighbor")}</span>
              <small>{stringValue(neighbor, "summary") || stringValue(neighbor, "direction") || tx(locale, "暂无公开摘要。", "No public summary.")}</small>
            </div>
          ))}
        </div>
      ) : (
        <p className="trace-meta"><Bi zh="没有返回图谱邻接节点。" en="No graph neighbors returned." /></p>
      )}
    </article>
  );
}

function WorldlinePathToolResultCard({ locale, toolEvent }: { locale: Locale; toolEvent: ToolCompletedEvent }) {
  const items = arrayOfRecords(toolEvent.result.items);

  return (
    <article className="tool-result-card">
      <ToolCardHeader toolEvent={toolEvent} label={<Bi zh="世界线路径" en="Worldline paths" />} count={items.length} />
      {items.length === 0 ? (
        <p className="trace-meta"><Bi zh="没有返回已保存的世界线路径。" en="No saved worldline paths returned." /></p>
      ) : (
        <div className="tool-result-items">
          {items.slice(0, 4).map((path, index) => (
            <div className="tool-result-item" key={stringValue(path, "path_id") || index}>
              <strong>{stringValue(path, "title") || stringValue(path, "path_id") || tx(locale, "已保存路径", "Saved path")}</strong>
              <span>
                {stringValue(path, "lifecycle") || tx(locale, "参考", "reference")} / <Bi zh="事件 " en="events " />
                {arrayOfRecords(path.selected_event_ids).length || arrayOfValues(path.selected_event_ids).length}
              </span>
              <small>{stringValue(path, "summary") || stringValue(path, "writer_instruction") || tx(locale, "暂无公开摘要。", "No public summary.")}</small>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

function UnknownToolResultCard({ toolEvent }: { toolEvent: ToolCompletedEvent }) {
  return (
    <article className="tool-result-card">
      <ToolCardHeader toolEvent={toolEvent} label={<Bi zh="工具结果" en="Tool result" />} count={Object.keys(toolEvent.result).length} />
    </article>
  );
}

function ToolErrorCard({ locale, toolEvent }: { locale: Locale; toolEvent: ToolCompletedEvent }) {
  return (
    <article className="tool-result-card error-box">
      <ToolCardHeader toolEvent={toolEvent} label={<Bi zh="工具错误" en="Tool error" />} count={0} />
      <p className="trace-meta">{tx(locale, "工具执行失败。", "Tool failed.")}</p>
    </article>
  );
}

function ToolCardHeader({
  toolEvent,
  label,
  count,
}: {
  toolEvent: ToolCompletedEvent;
  label: ReactNode;
  count: number;
}) {
  return (
    <div className="trace-event-header">
      <strong>{label}</strong>
      <span className="trace-redaction">{count} <Bi zh="项" en="items" /></span>
      <small className="trace-meta">
        {toolEvent.toolName} / #{toolEvent.event.sequence}
      </small>
    </div>
  );
}

function toToolCompletedEvent(event: WriterRunEvent): ToolCompletedEvent | null {
  const payload = event.payload;
  const toolName = stringValue(payload, "tool_name") || stringValue(payload, "tool");
  const result = recordValue(payload.result) ?? recordValue(payload.full_result) ?? payload;

  if (!toolName) {
    return null;
  }

  return {
    event,
    toolName,
    isError: Boolean(payload.is_error),
    result,
  };
}

function recordValue(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function arrayOfRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(recordValue).filter((item): item is Record<string, unknown> => item !== null) : [];
}

function arrayOfValues(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringValue(record: Record<string, unknown> | null, key: string): string {
  const value = record?.[key];
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return "";
}

function recoverDraftId(
  selectedDraftId: string,
  runSummary: WriterRunSummary | null,
  workflowEvents: WriterRunEventsSummary | null,
) {
  const selected = selectedDraftId.trim();
  if (selected) {
    return selected;
  }
  if (runSummary?.ok === true) {
    const persisted = stringValue(recordValue(runSummary), "draft_id");
    if (persisted) {
      return persisted;
    }
  }
  if (workflowEvents?.ok !== true) {
    return "";
  }
  for (let index = workflowEvents.items.length - 1; index >= 0; index -= 1) {
    const event = workflowEvents.items[index];
    if (event.event_type !== "writer.draft.saved" && event.event_type !== "writer.run.completed") {
      continue;
    }
    const draftId = stringValue(event.payload, "draft_id");
    if (draftId) {
      return draftId;
    }
  }
  return "";
}

function latestWriterEvent(workflowEvents: WriterRunEventsSummary | null) {
  if (workflowEvents?.ok !== true || workflowEvents.items.length === 0) {
    return null;
  }
  return workflowEvents.items.reduce((latest, event) => event.sequence > latest.sequence ? event : latest);
}

function formatByteSize(value: number, locale: Locale) {
  if (!Number.isFinite(value) || value < 0) {
    return tx(locale, "未知", "unknown");
  }
  return `${new Intl.NumberFormat(locale === "zh-CN" ? "zh-CN" : "en-US").format(value)} B`;
}

function WriterEvents({ workflowEvents }: { workflowEvents: WriterRunEventsSummary | null }) {
  if (workflowEvents?.ok === false) {
    return (
      <p>
        <FailureText />
      </p>
    );
  }

  if (!workflowEvents) {
    return <p><Bi zh="尚未选择写作事件流。" en="No writer event stream selected." /></p>;
  }

  if (workflowEvents.items.length === 0) {
    return <p><Bi zh="当前回放游标之后没有写作事件。" en="No writer events recorded after the current replay cursor." /></p>;
  }

  return (
    <div className="trace-list">
      {workflowEvents.items.map((event) => (
        <article className="trace-event" key={`${event.event_id}-${event.sequence}`}>
          <div className="trace-event-header">
            <strong>{event.event_type}</strong>
            <span className="trace-redaction">#{event.sequence}</span>
          </div>
          <p className="trace-meta">
            {event.created_at}
          </p>
        </article>
      ))}
    </div>
  );
}

function TraceEvents({ traceEvents }: { traceEvents: AgentTraceEventsSummary | null }) {
  if (traceEvents?.ok === false) {
    return (
      <p>
        <FailureText />
      </p>
    );
  }

  if (!traceEvents) {
    return <p><Bi zh="尚未选择追踪。" en="No trace selected." /></p>;
  }

  if (traceEvents.items.length === 0) {
    return <p><Bi zh="该任务还没有追踪事件。" en="No trace events recorded for this run yet." /></p>;
  }

  return (
    <div className="trace-list">
      {traceEvents.items.map((event) => (
          <article className="trace-event" key={`${event.event_id}-${event.event_order}`} data-redaction-level={event.redaction_level || "public"}>
            <div className="trace-event-header">
              <strong>{event.event_type}</strong>
            </div>
            <p className="trace-meta">
              #{event.event_order} / {event.created_at}
              {event.redaction_level ? ` / ${event.redaction_level}` : ""}
            </p>
          </article>
      ))}
    </div>
  );
}
