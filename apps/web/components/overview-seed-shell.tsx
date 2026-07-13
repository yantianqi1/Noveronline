import {
  Activity,
  ChevronRight,
  Feather,
  FileText,
  FolderOpen,
  Globe2,
  LayoutDashboard,
  Network,
  RotateCcw,
  Upload,
  UserRound,
  XCircle,
} from "lucide-react";

import { evaluateCreationReadiness, llmFacilityProjectHref } from "../lib/llm-creation-readiness";
import { type Locale, tx } from "../lib/locale";
import type {
  ProjectOverviewSummary,
  ProjectReadinessSummary,
  SeedRunStartSummary,
  SeedRunsSummary,
  SourceFileObjectUploadSummary,
  SourceFilesSummary,
  SourceFileSummary,
  WorkflowControlSummary,
  WorkflowRunEventsSummary,
  WorkflowRunSummary,
} from "../lib/api";
import { Bi, FailureText, StatusValue } from "./bilingual-text";
import { PublicErrorNotice } from "./public-error-notice";
import { canCancelSeedRun, canRetrySeedRun } from "./overview-seed-run-controls";
import { OverviewSeedUploadForm } from "./overview-seed-upload-form";
import { SeedRunAutoRefresh } from "./seed-run-auto-refresh";
import { SubmitButton } from "./submit-button";
import { WorkflowProgress } from "./workflow-progress";
import { WorkspaceHeader } from "./workspace-header";

type ActionStatus = {
  status: string;
  code: string;
  message: string;
};

type OverviewSeedShellProps = {
  locale: Locale;
  tenantSlug: string;
  projectId: string;
  projectOverview: ProjectOverviewSummary;
  projectReadiness: ProjectReadinessSummary;
  sourceFiles: SourceFilesSummary;
  seedRuns: SeedRunsSummary;
  selectedRunId: string;
  afterEventId: string;
  selectedSeedRun: WorkflowRunSummary | null;
  seedEvents: WorkflowRunEventsSummary | null;
  sourceStatus: ActionStatus | null;
  seedStatus: ActionStatus | null;
  bootstrapStatus: ActionStatus | null;
  bootstrapIdeaAction: (formData: FormData) => Promise<void>;
  uploadAndStartSeedAction: (formData: FormData) => Promise<void>;
  completeUploadAction: (formData: FormData) => Promise<void>;
  startSeedRunAction: (formData: FormData) => Promise<void>;
  cancelSeedRunAction: (formData: FormData) => Promise<void>;
  retrySeedRunAction: (formData: FormData) => Promise<void>;
};

export function OverviewSeedShell({
  locale,
  tenantSlug,
  projectId,
  projectOverview,
  projectReadiness,
  sourceFiles,
  seedRuns,
  selectedRunId,
  selectedSeedRun,
  seedEvents,
  sourceStatus,
  seedStatus,
  bootstrapStatus,
  bootstrapIdeaAction,
  uploadAndStartSeedAction,
  completeUploadAction,
  startSeedRunAction,
  cancelSeedRunAction,
  retrySeedRunAction,
}: OverviewSeedShellProps) {
  const cancelSeedRunEnabled = canCancelSeedRun(selectedSeedRun);
  const retrySeedRunEnabled = canRetrySeedRun(selectedSeedRun);
  const creationReadiness = evaluateCreationReadiness(projectOverview, tenantSlug, projectId);
  const isEmptyProject = projectOverview.ok
    && projectOverview.source_file_count === 0
    && (!seedRuns.ok || seedRuns.items.length === 0)
    && !selectedRunId;
  // LLM readiness gates Seed/AI analysis, not idea-first structure bootstrap.
  const showCreationReadinessPanel = !creationReadiness.ready;
  const foldHealthPanel = isEmptyProject || !creationReadiness.ready;
  const seedRunActive = Boolean(
    selectedSeedRun
    && selectedSeedRun.ok
    && (selectedSeedRun.status === "queued" || selectedSeedRun.status === "running"),
  );

  return (
    <div className="overview-root">
      <SeedRunAutoRefresh active={seedRunActive} />
      <WorkspaceHeader
        className="overview-header"
        description={<Bi zh="从想法开始，或导入小说建立故事资料。" en="Start from an idea, or import a manuscript." />}
        icon={<LayoutDashboard size={22} strokeWidth={1.8} />}
        meta={(
          <>
            <span className="status-pill">
              {projectOverview.ok ? <StatusValue value={projectOverview.status} /> : <Bi zh="暂不可用" en="Unavailable" />}
            </span>
            <span className="status-pill">
              {projectOverview.ok && projectOverview.active_workflow_status
                ? <StatusValue value={projectOverview.active_workflow_status} />
                : <Bi zh="无进行中分析" en="No active analysis" />}
            </span>
          </>
        )}
        title={<Bi zh="项目总览" en="Project Overview" />}
      />

      <div className="workbench-grid">
        <main>
          <section
            className={`panel overview-next-panel ${selectedSeedRun && !selectedSeedRun.ok ? "error-box" : ""} ${showCreationReadinessPanel && !isEmptyProject ? "overview-next-blocked" : ""}`}
            aria-labelledby="recent-seed-run-heading"
          >
            <p className="eyebrow"><Bi zh="当前重点" en="Next step" /></p>
            <h2 id="recent-seed-run-heading"><Bi zh="下一步" en="Next step" /></h2>
            {showCreationReadinessPanel && !isEmptyProject ? (
              <div className="overview-readiness-inline">
                <CreationReadinessPanel
                  creationReadiness={creationReadiness}
                  locale={locale}
                  projectOverview={projectOverview}
                />
              </div>
            ) : null}
            <OverviewNextStep
              bootstrapIdeaAction={bootstrapIdeaAction}
              bootstrapStatus={bootstrapStatus}
              cancelSeedRunAction={cancelSeedRunAction}
              cancelSeedRunEnabled={cancelSeedRunEnabled}
              completeUploadAction={completeUploadAction}
              creationReadiness={creationReadiness}
              locale={locale}
              projectId={projectId}
              projectOverview={projectOverview}
              retrySeedRunAction={retrySeedRunAction}
              retrySeedRunEnabled={retrySeedRunEnabled}
              seedEvents={seedEvents}
              selectedRunId={selectedRunId}
              selectedSeedRun={selectedSeedRun}
              sourceFiles={sourceFiles}
              startSeedRunAction={startSeedRunAction}
              tenantSlug={tenantSlug}
            />
          </section>

          {showCreationReadinessPanel && !isEmptyProject ? (
            <section
              className="panel overview-readiness-panel"
              aria-labelledby="creation-readiness-heading"
            >
              <p className="eyebrow"><Bi zh="创作就绪" en="Creation readiness" /></p>
              <h2 id="creation-readiness-heading"><Bi zh="模型与预算" en="Models and budget" /></h2>
              <CreationReadinessPanel
                creationReadiness={creationReadiness}
                locale={locale}
                projectOverview={projectOverview}
              />
            </section>
          ) : null}

          {!foldHealthPanel ? (
          <section
            className={`panel ${projectOverview.ok ? "" : "error-box"}`}
            aria-labelledby="project-health-heading"
          >
            <p className="eyebrow"><Bi zh="创作基础" en="Project Health" /></p>
            <h2 id="project-health-heading"><Bi zh="故事基础" en="Story foundation" /></h2>
            <ProjectHealthPanel locale={locale} projectId={projectId} projectOverview={projectOverview} tenantSlug={tenantSlug} />
          </section>
          ) : (
          <details className="overview-details">
            <summary>
              <LayoutDashboard aria-hidden="true" size={18} strokeWidth={1.8} />
              <span>
                <strong><Bi zh="故事基础" en="Story foundation" /></strong>
                <small><Bi zh={isEmptyProject ? "开始创作后查看指标" : "就绪后查看指标"} en={isEmptyProject ? "Metrics appear after you start writing" : "Available after readiness"} /></small>
              </span>
              <ChevronRight className="overview-details-chevron" aria-hidden="true" size={18} />
            </summary>
            <div className="overview-details-content">
              <ProjectHealthPanel locale={locale} projectId={projectId} projectOverview={projectOverview} tenantSlug={tenantSlug} />
            </div>
          </details>
          )}

          <details className="overview-details">
            <summary>
              <FileText aria-hidden="true" size={18} strokeWidth={1.8} />
              <span>
                <strong><Bi zh="文件与分析记录" en="Files and analysis history" /></strong>
                <small>
                  {sourceFiles.ok ? sourceFiles.items.length : 0} <Bi zh="个文件" en="files" /> · {seedRuns.ok ? seedRuns.items.length : 0} <Bi zh="次分析" en="runs" />
                </small>
              </span>
              <ChevronRight className="overview-details-chevron" aria-hidden="true" size={18} />
            </summary>
            <div className="overview-details-content">
              <section className={sourceFiles.ok ? "" : "error-box"} aria-labelledby="source-files-heading">
                <h3 id="source-files-heading"><Bi zh="源文件" en="Source files" /></h3>
                <SourceFilesTable
                  completeUploadAction={completeUploadAction}
                  locale={locale}
                  projectId={projectId}
                  sourceFiles={sourceFiles}
                  startSeedRunAction={startSeedRunAction}
                  tenantSlug={tenantSlug}
                />
              </section>
              <section className={seedRuns.ok ? "" : "error-box"} aria-labelledby="seed-runs-heading">
                <h3 id="seed-runs-heading"><Bi zh="分析历史" en="Analysis history" /></h3>
                <SeedRunsTable locale={locale} projectId={projectId} seedRuns={seedRuns} tenantSlug={tenantSlug} />
              </section>
            </div>
          </details>

          <details className="overview-details">
            <summary>
              <Activity aria-hidden="true" size={18} strokeWidth={1.8} />
              <span>
                <strong><Bi zh="进度与活动" en="Progress and activity" /></strong>
                <small><Bi zh="就绪度、当前任务与事件" en="Readiness, current run, and events" /></small>
              </span>
              <ChevronRight className="overview-details-chevron" aria-hidden="true" size={18} />
            </summary>
            <div className="overview-details-content">
              <section aria-labelledby="project-details-heading">
                <h3 id="project-details-heading"><Bi zh="项目状态详情" en="Project health details" /></h3>
                <ProjectHealthDetails locale={locale} projectId={projectId} projectOverview={projectOverview} tenantSlug={tenantSlug} />
              </section>
              <section className={projectReadiness.ok ? "" : "error-box"} aria-labelledby="project-readiness-heading">
                <h3 id="project-readiness-heading"><Bi zh="项目就绪度" en="Project readiness" /></h3>
                <ProjectReadinessPanel locale={locale} projectId={projectId} projectReadiness={projectReadiness} tenantSlug={tenantSlug} />
              </section>
              <section className={selectedSeedRun && !selectedSeedRun.ok ? "error-box" : ""} aria-labelledby="seed-run-detail-heading">
                <h3 id="seed-run-detail-heading"><Bi zh="当前任务" en="Current analysis" /></h3>
                <SeedRunDetail locale={locale} projectId={projectId} selectedRunId={selectedRunId} selectedSeedRun={selectedSeedRun} tenantSlug={tenantSlug} />
              </section>
              <section className={seedEvents && !seedEvents.ok ? "error-box" : ""} aria-labelledby="seed-events-heading">
                <h3 id="seed-events-heading"><Bi zh="任务事件" en="Analysis events" /></h3>
                <SeedEvents locale={locale} projectId={projectId} seedEvents={seedEvents} selectedRunId={selectedRunId} tenantSlug={tenantSlug} />
              </section>
            </div>
          </details>
        </main>

        <aside>
          <details className="panel overview-details overview-upload-disclosure" open={!selectedRunId}>
            <summary>
              <Upload aria-hidden="true" size={18} strokeWidth={1.8} />
              <span>
                <strong><Bi zh="导入小说" en="Import manuscript" /></strong>
                <small><Bi zh="上传 TXT、Markdown 或 PDF 并开始分析" en="Upload TXT, Markdown, or PDF and start analysis" /></small>
              </span>
              <ChevronRight className="overview-details-chevron" aria-hidden="true" size={18} />
            </summary>
            <div className="overview-details-content">
              <section aria-labelledby="upload-and-start-seed-heading">
                <h2 id="upload-and-start-seed-heading"><Bi zh="上传并开始分析" en="Upload and start analysis" /></h2>
                <OverviewSeedUploadForm
                  action={uploadAndStartSeedAction}
                  locale={locale}
                  seedStatus={<StatusLine status={seedStatus} />}
                  sourceStatus={<StatusLine status={sourceStatus} />}
                />
              </section>
            </div>
          </details>

        </aside>
      </div>
    </div>
  );
}

function OverviewNextStep({
  bootstrapIdeaAction,
  bootstrapStatus,
  cancelSeedRunAction,
  cancelSeedRunEnabled,
  completeUploadAction,
  creationReadiness,
  locale,
  projectId,
  projectOverview,
  retrySeedRunAction,
  retrySeedRunEnabled,
  seedEvents,
  selectedRunId,
  selectedSeedRun,
  sourceFiles,
  startSeedRunAction,
  tenantSlug,
}: {
  bootstrapIdeaAction: (formData: FormData) => Promise<void>;
  bootstrapStatus: ActionStatus | null;
  cancelSeedRunAction: (formData: FormData) => Promise<void>;
  cancelSeedRunEnabled: boolean;
  completeUploadAction: (formData: FormData) => Promise<void>;
  creationReadiness: ReturnType<typeof evaluateCreationReadiness>;
  locale: Locale;
  projectId: string;
  projectOverview: ProjectOverviewSummary;
  retrySeedRunAction: (formData: FormData) => Promise<void>;
  retrySeedRunEnabled: boolean;
  seedEvents: WorkflowRunEventsSummary | null;
  selectedRunId: string;
  selectedSeedRun: WorkflowRunSummary | null;
  sourceFiles: SourceFilesSummary;
  startSeedRunAction: (formData: FormData) => Promise<void>;
  tenantSlug: string;
}) {
  if (selectedRunId) {
    if (!selectedSeedRun) {
      return <p className="form-hint"><Bi zh="正在载入当前分析进度。" en="Loading the current analysis progress." /></p>;
    }
    if (!selectedSeedRun.ok) {
      return <OverviewPublicFailureNotice code={selectedSeedRun.code} locale={locale} projectId={projectId} tenantSlug={tenantSlug} />;
    }
    const completed = selectedSeedRun.status === "completed";
    const interrupted = selectedSeedRun.status === "failed" || selectedSeedRun.status === "cancelled";
    const displayProgress = seedDisplayProgress(selectedSeedRun, seedEvents);
    const stageStates = seedPipelineStages(locale, selectedSeedRun, seedEvents);
    const latestStage = latestSeedStageLabel(locale, seedEvents);
    return (
      <>
        <p className="overview-next-copy">
          <strong>
            {completed
              ? <Bi zh="审阅已整理的故事资产" en="Review the extracted story assets" />
              : interrupted
                ? <Bi zh="继续中断的分析" en="Continue the interrupted analysis" />
                : <Bi zh="故事分析正在推进" en="Story analysis is in progress" />}
          </strong>
        </p>
        <p className="form-hint">
          {completed
            ? <Bi zh={`已有 ${projectOverview.ok ? projectOverview.ready_asset_count : 0} 项资产可供审阅。`} en={`${projectOverview.ok ? projectOverview.ready_asset_count : 0} assets are ready to review.`} />
            : interrupted
              ? (
                <>
                  <Bi zh="任务未完成，可在下方重试；已有内容不会被删除。" en="The run did not finish. Retry below; existing work is preserved." />
                  {selectedSeedRun.error_code ? (
                    <>
                      {" "}
                      <Bi zh={`原因：${publicSeedFailureHint(locale, selectedSeedRun.error_code)}`} en={`Reason: ${publicSeedFailureHint(locale, selectedSeedRun.error_code)}`} />
                    </>
                  ) : null}
                </>
              )
              : (
                <>
                  <Bi zh="页面会自动刷新阶段进度（不是正文 token 流）。" en="This page auto-refreshes stage progress (not prose token streaming)." />
                  {latestStage ? <>{" "}{latestStage}</> : null}
                </>
              )}
        </p>
        <WorkflowProgress
          actions={(
            <div className="overview-run-actions">
              <form action={cancelSeedRunAction}>
                <input type="hidden" name="runId" value={selectedRunId} />
                <button className="danger-action" disabled={!cancelSeedRunEnabled} type="submit">
                  <XCircle aria-hidden="true" size={18} />
                  <Bi zh="取消分析" en="Cancel analysis" />
                </button>
              </form>
              <form action={retrySeedRunAction}>
                <input type="hidden" name="runId" value={selectedRunId} />
                <button disabled={!retrySeedRunEnabled} type="submit">
                  <RotateCcw aria-hidden="true" size={18} />
                  <Bi zh="重试分析" en="Retry analysis" />
                </button>
              </form>
              {completed ? (
                <a className="overview-next-link" href={projectSectionHref(tenantSlug, projectId, "assets")}>
                  <Bi zh="查看资产" en="Review assets" />
                  <ChevronRight aria-hidden="true" size={18} />
                </a>
              ) : null}
            </div>
          )}
          currentLabel={<StatusValue value={selectedSeedRun.status} />}
          progressLabel={<Bi zh={`进度 ${displayProgress}%`} en={`Progress ${displayProgress}%`} />}
          stages={stageStates}
          title={<Bi zh="分析进度" en="Analysis progress" />}
        />
        <SeedRunOverview
          displayProgress={displayProgress}
          locale={locale}
          projectId={projectId}
          selectedRunId={selectedRunId}
          selectedSeedRun={selectedSeedRun}
          tenantSlug={tenantSlug}
        />
      </>
    );
  }

  if (!sourceFiles.ok) {
    return <OverviewPublicFailureNotice code={sourceFiles.code} locale={locale} projectId={projectId} tenantSlug={tenantSlug} />;
  }
  const preparedFile = sourceFiles.items.find((file) => file.parse_status === "uploaded");
  const pendingFile = sourceFiles.items.find((file) => file.parse_status === "pending");
  if (preparedFile) {
    if (!creationReadiness.ready) {
      return (
        <>
          <p className="overview-next-copy"><strong><Bi zh="开始故事分析前，先完成模型与预算设置" en="Finish model and budget setup before story analysis" /></strong></p>
          <CreationReadinessPanel
            creationReadiness={creationReadiness}
            locale={locale}
            projectOverview={projectOverview}
          />
          <EmptyProjectDualEntry
            bootstrapIdeaAction={bootstrapIdeaAction}
            bootstrapStatus={bootstrapStatus}
            locale={locale}
            projectId={projectId}
            tenantSlug={tenantSlug}
          />
        </>
      );
    }
    return (
      <>
        <p className="overview-next-copy"><strong><Bi zh="开始故事分析" en="Start story analysis" /></strong></p>
        <p className="form-hint"><Bi zh={`「${preparedFile.filename}」已经准备好。`} en={`“${preparedFile.filename}” is ready.`} /></p>
        <form action={startSeedRunAction} className="overview-run-actions">
          <input type="hidden" name="uploadId" value={preparedFile.upload_id} />
          <input type="hidden" name="mode" value="full" />
          <SubmitButton idleLabel={<Bi zh="开始分析" en="Start analysis" />} pendingLabel={<Bi zh="启动中…" en="Starting…" />} />
        </form>
      </>
    );
  }
  if (pendingFile) {
    return (
      <>
        <p className="overview-next-copy"><strong><Bi zh="完成文件准备" en="Finish preparing the file" /></strong></p>
        <p className="form-hint"><Bi zh={`「${pendingFile.filename}」等待确认后即可分析。`} en={`“${pendingFile.filename}” can be analyzed after preparation finishes.`} /></p>
        <form action={completeUploadAction} className="overview-run-actions">
          <input type="hidden" name="uploadId" value={pendingFile.upload_id} />
          <SubmitButton idleLabel={<Bi zh="完成准备" en="Complete upload" />} pendingLabel={<Bi zh="处理中…" en="Working…" />} />
        </form>
      </>
    );
  }
  return (
    <EmptyProjectDualEntry
      bootstrapIdeaAction={bootstrapIdeaAction}
      bootstrapStatus={bootstrapStatus}
      creationReadiness={creationReadiness}
      locale={locale}
      projectId={projectId}
      projectOverview={projectOverview}
      tenantSlug={tenantSlug}
    />
  );
}

function EmptyProjectDualEntry({
  bootstrapIdeaAction,
  bootstrapStatus,
  creationReadiness,
  locale,
  projectId,
  projectOverview,
  tenantSlug,
}: {
  bootstrapIdeaAction: (formData: FormData) => Promise<void>;
  bootstrapStatus: ActionStatus | null;
  creationReadiness?: ReturnType<typeof evaluateCreationReadiness>;
  locale: Locale;
  projectId: string;
  projectOverview?: ProjectOverviewSummary;
  tenantSlug: string;
}) {
  return (
    <div className="overview-dual-entry" data-empty-project-entry="true">
      <p className="overview-next-copy">
        <strong><Bi zh="选择如何开始这个项目" en="Choose how to start this project" /></strong>
      </p>
      {bootstrapStatus ? <StatusLine status={bootstrapStatus} /> : null}
      <div className="overview-dual-entry-grid">
        <section className="overview-entry-card" aria-labelledby="idea-first-entry-heading">
          <p className="eyebrow"><Bi zh="入口 A" en="Entry A" /></p>
          <h3 id="idea-first-entry-heading"><Bi zh="从一个想法开始" en="Start from an idea" /></h3>
          <p className="form-hint">
            <Bi
              zh="创建最小书籍计划与首章，直接进入写作台。"
              en="Create a minimal book plan and first chapter, then open Writer."
            />
          </p>
          <form action={bootstrapIdeaAction} className="binding-form overview-bootstrap-form">
            <label htmlFor="bootstrap-premise"><Bi zh="故事前提" en="Story premise" /></label>
            <textarea
              id="bootstrap-premise"
              name="premise"
              required
              rows={3}
              placeholder={tx(locale, "用一两句话写下故事核心。", "Describe the core idea in one or two sentences.")}
            />
            <label htmlFor="bootstrap-title"><Bi zh="计划名称（可选）" en="Plan title (optional)" /></label>
            <input
              id="bootstrap-title"
              name="title"
              placeholder={tx(locale, "默认使用前提前缀", "Defaults from the premise")}
            />
            <label htmlFor="bootstrap-chapter"><Bi zh="第一章标题（可选）" en="Chapter 1 title (optional)" /></label>
            <input
              id="bootstrap-chapter"
              name="chapterTitle"
              placeholder={tx(locale, "第一章", "Chapter 1")}
            />
            <SubmitButton
              idleLabel={(
                <>
                  <Feather aria-hidden="true" size={16} />
                  <Bi zh="建立并进入写作台" en="Create and open Writer" />
                </>
              )}
              pendingLabel={<Bi zh="创建中…" en="Creating…" />}
            />
          </form>
          <a className="overview-next-link" href={projectSectionHref(tenantSlug, projectId, "writer")}>
            <Bi zh="直接打开空写作台" en="Open empty Writer" />
            <ChevronRight aria-hidden="true" size={18} />
          </a>
        </section>
        <section className="overview-entry-card" aria-labelledby="upload-first-entry-heading">
          <p className="eyebrow"><Bi zh="入口 B" en="Entry B" /></p>
          <h3 id="upload-first-entry-heading"><Bi zh="上传已有文本" en="Upload existing text" /></h3>
          <p className="form-hint">
            <Bi
              zh="上传 TXT / Markdown / PDF，分析后建立资产与图谱。"
              en="Upload TXT, Markdown, or PDF to build assets and graph."
            />
          </p>
          {creationReadiness && projectOverview && !creationReadiness.ready ? (
            <CreationReadinessPanel
              creationReadiness={creationReadiness}
              locale={locale}
              projectOverview={projectOverview}
            />
          ) : (
            <a className="overview-next-link" href="#upload-and-start-seed-heading">
              <Upload aria-hidden="true" size={16} />
              <Bi zh="选择文件并开始分析" en="Choose a file and start analysis" />
              <ChevronRight aria-hidden="true" size={18} />
            </a>
          )}
        </section>
      </div>
    </div>
  );
}

export function sourceFileActionStatus(result: SourceFileSummary, locale: Locale): ActionStatus {
  if (!result.ok) {
    return {
      status: "error",
      code: result.code,
      message: tx(locale, "文件处理未完成，请检查文件后重试。", "The file could not be processed. Check it and try again."),
    };
  }
  return {
    status: "success",
    code: result.parse_status || "SOURCE_FILE_ADMITTED",
    message: tx(locale, "源文件已接收", "Source file accepted"),
  };
}

export function sourceFileObjectActionStatus(result: SourceFileObjectUploadSummary, locale: Locale): ActionStatus {
  if (!result.ok) {
    return {
      status: "error",
      code: result.code,
      message: tx(locale, "文件上传未完成，请重新选择文件。", "The upload did not finish. Choose the file again."),
    };
  }
  return {
    status: "success",
    code: result.status || "SOURCE_FILE_OBJECT_STORED",
    message: tx(locale, "文件已保存", "File stored"),
  };
}

export function seedRunActionStatus(result: SeedRunStartSummary, locale: Locale): ActionStatus & { runId: string } {
  if (!result.ok) {
    return {
      status: "error",
      code: result.code,
      message: tx(locale, "分析任务未开始，请检查文件和模型配置。", "The analysis did not start. Check the file and model configuration."),
      runId: "",
    };
  }
  return {
    status: "success",
    code: result.status,
    message: tx(locale, "分析任务已接收", "Analysis accepted"),
    runId: result.run_id,
  };
}

export function seedRunControlStatus(
  result: WorkflowControlSummary,
  action: "cancel" | "retry",
  locale: Locale,
): ActionStatus & { runId: string } {
  if (!result.ok) {
    return {
      status: "error",
      code: result.code,
      message: tx(locale, "任务控制操作未完成，请稍后重试。", "The task action did not finish. Try again shortly."),
      runId: "",
    };
  }
  const verb = action === "cancel"
    ? tx(locale, "取消请求", "Cancellation")
    : tx(locale, "重试请求", "Retry");
  return {
    status: "success",
    code: result.status,
    message: tx(locale, `${verb}已提交`, `${verb} submitted`),
    runId: result.run_id,
  };
}

function SourceFilesTable({
  completeUploadAction,
  locale,
  projectId,
  sourceFiles,
  startSeedRunAction,
  tenantSlug,
}: {
  completeUploadAction: (formData: FormData) => Promise<void>;
  locale: Locale;
  projectId: string;
  sourceFiles: SourceFilesSummary;
  startSeedRunAction: (formData: FormData) => Promise<void>;
  tenantSlug: string;
}) {
  if (!sourceFiles.ok) {
    return <OverviewPublicFailureNotice code={sourceFiles.code} locale={locale} projectId={projectId} tenantSlug={tenantSlug} />;
  }
  if (sourceFiles.items.length === 0) {
    return <p className="form-hint"><Bi zh="项目中还没有源文件。" en="No source files have been admitted for this project." /></p>;
  }
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th><Bi zh="文件名" en="Filename" /></th>
            <th><Bi zh="状态" en="Status" /></th>
            <th><Bi zh="大小" en="Size" /></th>
            <th><Bi zh="创建时间" en="Created" /></th>
            <th><Bi zh="操作" en="Action" /></th>
          </tr>
        </thead>
        <tbody>
          {sourceFiles.items.map((file) => (
            <tr key={file.file_id}>
              <td>{file.filename}</td>
              <td><StatusValue value={file.parse_status} /></td>
              <td>{formatFileSize(file.size_bytes)}</td>
              <td>{file.created_at}</td>
              <td>
                <div className="compact-action-list">
                  <form action={completeUploadAction} className="inline-action-form">
                    <input type="hidden" name="uploadId" value={file.upload_id} />
                    <span><Bi zh="完成上传" en="Complete upload" /></span>
                    <button disabled={file.parse_status !== "pending"} type="submit">
                      <Bi zh="完成" en="Complete" />
                    </button>
                  </form>
                  <form action={startSeedRunAction} className="inline-action-form">
                    <input type="hidden" name="uploadId" value={file.upload_id} />
                    <input type="hidden" name="mode" value="full" />
                    <span><Bi zh="开始分析" en="Start analysis" /></span>
                    <button disabled={file.parse_status !== "uploaded"} type="submit">
                      <Bi zh="开始" en="Start" />
                    </button>
                  </form>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CreationReadinessPanel({
  creationReadiness,
  locale,
  projectOverview,
}: {
  creationReadiness: ReturnType<typeof evaluateCreationReadiness>;
  locale: Locale;
  projectOverview: ProjectOverviewSummary;
}) {
  return (
    <>
      <p className="overview-next-copy">
        <strong>
          {creationReadiness.ready
            ? <Bi zh="模型与预算已就绪，可用于 Seed 分析和 AI 写作。" en="Models and budget are ready for Seed analysis and AI writing." />
            : <Bi zh="AI 分析与生成前需完成模型与预算设置；从想法开始的结构创建不依赖此步骤。" en="Model and budget setup is required before AI analysis or generation; idea-first structure bootstrap does not depend on it." />}
        </strong>
      </p>
      {projectOverview.ok && projectOverview.source_file_count === 0 ? (
        <p className="form-hint">
          <Bi zh="当前没有源文件。你可以先从想法进入写作台，上传只是可选入口。" en="No source files yet. You can open Writer from an idea first; upload is optional." />
        </p>
      ) : null}
      {creationReadiness.blockers.length > 0 ? (
        <ul className="creation-readiness-blockers">
          {creationReadiness.blockers.map((blocker) => (
            <li key={blocker.en}>
              <Bi zh={blocker.zh} en={blocker.en} />
            </li>
          ))}
        </ul>
      ) : null}
      {creationReadiness.primaryAction ? (
        <a className="overview-next-link" href={creationReadiness.llmFacilityHref}>
          <Bi zh={creationReadiness.primaryAction.zh} en={creationReadiness.primaryAction.en} />
          <ChevronRight aria-hidden="true" size={18} />
        </a>
      ) : null}
      {projectOverview.ok ? (
        <div className="status-row" aria-label={tx(locale, "LLM 就绪指标", "LLM readiness metrics")}>
          <span className="status-pill">
            <Bi zh={`启用通道：${projectOverview.llm_enabled_channel_count}`} en={`Enabled channels: ${projectOverview.llm_enabled_channel_count}`} />
          </span>
          <span className="status-pill">
            <Bi zh={`未绑定核心模块：${projectOverview.llm_missing_core_module_count}`} en={`Unbound core modules: ${projectOverview.llm_missing_core_module_count}`} />
          </span>
          <span className="status-pill">
            <Bi
              zh={projectOverview.llm_has_quota_policy ? "配额策略：已配置" : "配额策略：未配置"}
              en={projectOverview.llm_has_quota_policy ? "Quota policy: configured" : "Quota policy: missing"}
            />
          </span>
        </div>
      ) : null}
    </>
  );
}

function OverviewPublicFailureNotice({
  code,
  locale,
  projectId,
  tenantSlug,
}: {
  code: string;
  locale: Locale;
  projectId: string;
  tenantSlug: string;
}) {
  const notice = overviewFailureNotice(locale, code, tenantSlug, projectId);
  return (
    <PublicErrorNotice
      action={(
        <a className="overview-next-link" href={notice.llmFacilityHref}>
          <Bi zh="打开模型设置" en="Open model settings" />
          <ChevronRight aria-hidden="true" size={18} />
        </a>
      )}
      message={<Bi zh={notice.messageZh} en={notice.messageEn} />}
      recovery={<Bi zh={notice.recoveryZh} en={notice.recoveryEn} />}
      title={<Bi zh={notice.titleZh} en={notice.titleEn} />}
    />
  );
}

function overviewFailureNotice(locale: Locale, code: string, tenantSlug: string, projectId: string) {
  const llmFacilityHref = llmFacilityProjectHref(tenantSlug, projectId);
  const normalized = code.trim().toUpperCase();
  const defaults = {
    titleZh: "操作未完成",
    titleEn: "Action incomplete",
    messageZh: "这次操作没有完成，当前页面状态已保留。",
    messageEn: "This action did not finish. Your page state is kept.",
    recoveryZh: "请检查输入后重试，或前往模型设置完成配置。",
    recoveryEn: "Check your input and retry, or open model settings to finish setup.",
    llmFacilityHref,
  };

  if (normalized === "LLM_QUOTA_POLICY_UNAVAILABLE") {
    return {
      ...defaults,
      titleZh: "缺少调用预算策略",
      titleEn: "Usage budget policy missing",
      messageZh: "创作服务需要预算策略才能预留调用额度；没有策略时任务会在中途失败。",
      messageEn: "Creative workflows need a budget policy to reserve usage; without one, runs fail partway through.",
      recoveryZh: "前往模型设置配置预算策略，然后回到此处重试。",
      recoveryEn: "Open model settings to configure a budget policy, then return here and retry.",
    };
  }

  if (normalized === "LLM_MODULE_UNBOUND") {
    return {
      ...defaults,
      titleZh: "模型能力未绑定",
      titleEn: "Model capability unbound",
      messageZh: "当前任务所需的模型能力尚未绑定到可用渠道。",
      messageEn: "A required model capability is not bound to an available channel for this task.",
      recoveryZh: "在模型设置中绑定缺失能力后重试。",
      recoveryEn: "Bind the missing capability in model settings, then retry.",
    };
  }

  if (normalized.startsWith("LLM_QUOTA_")) {
    return {
      ...defaults,
      titleZh: "调用额度受限",
      titleEn: "Usage limit reached",
      messageZh: "本次调用超出当前预算限制，任务未能完成。",
      messageEn: "This call exceeded the current budget limit, so the task did not finish.",
      recoveryZh: "在模型设置中调整预算后重试。",
      recoveryEn: "Adjust the budget in model settings, then retry.",
    };
  }

  void locale;
  return defaults;
}

function ProjectHealthPanel({
  locale,
  projectId,
  projectOverview,
  tenantSlug,
}: {
  locale: Locale;
  projectId: string;
  projectOverview: ProjectOverviewSummary;
  tenantSlug: string;
}) {
  if (!projectOverview.ok) {
    return <OverviewPublicFailureNotice code={projectOverview.code} locale={locale} projectId={projectId} tenantSlug={tenantSlug} />;
  }
  const metrics = [
    ["source-files", "源文件", "Source files", projectOverview.source_file_count, FileText],
    ["seed-runs", "分析任务", "Analysis runs", projectOverview.seed_run_count, LayoutDashboard],
    ["assets-ready", "就绪资产", "Assets ready", projectOverview.ready_asset_count, FolderOpen],
    ["entities-ready", "就绪实体", "Entities ready", projectOverview.ready_entity_count, UserRound],
    ["relationships-ready", "就绪关系", "Relationships ready", projectOverview.ready_relationship_count, Network],
    ["world-rules-ready", "就绪世界规则", "World rules ready", projectOverview.ready_world_rule_count, Globe2],
  ] as const;
  return (
    <div className="overview-metric-grid" aria-label={tx(locale, "项目核心统计", "Core project counts")}>
      {metrics.map(([key, zh, en, value, Icon]) => {
        return (
          <div className="overview-metric" key={key}>
            <strong>{value}</strong>
            <span><Bi zh={zh} en={en} /></span>
            <Icon aria-hidden="true" size={24} strokeWidth={1.35} />
          </div>
        );
      })}
    </div>
  );
}

function ProjectHealthDetails({
  locale,
  projectId,
  projectOverview,
  tenantSlug,
}: {
  locale: Locale;
  projectId: string;
  projectOverview: ProjectOverviewSummary;
  tenantSlug: string;
}) {
  if (!projectOverview.ok) {
    return <OverviewPublicFailureNotice code={projectOverview.code} locale={locale} projectId={projectId} tenantSlug={tenantSlug} />;
  }
  const metrics = [
    ["asset-records", "资产记录", "Asset records", projectOverview.asset_count],
    ["graph-nodes", "图谱节点", "Graph nodes", projectOverview.graph_node_count],
    ["graph-edges", "图谱关系", "Graph edges", projectOverview.graph_edge_count],
    ["worldline-sessions", "世界线会话", "Worldline sessions", projectOverview.worldline_session_count],
    ["worldline-events", "世界线事件", "Worldline events", projectOverview.worldline_event_count],
    ["character-interactions", "角色互动", "Character interactions", projectOverview.character_interaction_count],
    ["writer-runs", "写作任务", "Writer runs", projectOverview.writer_run_count],
  ];
  const readinessAvailable = Boolean(projectOverview.readiness_snapshot_id && projectOverview.readiness_run_id);
  return (
    <>
      <div className="status-row" aria-label={tx(locale, "项目详细统计", "Detailed project counts")}>
        {metrics.map(([key, zh, en, value]) => (
          <span className="status-pill" key={key}>
            <Bi zh={`${zh}：`} en={`${en}: `} />{value}
          </span>
        ))}
      </div>
      <dl>
        <dt><Bi zh="当前任务" en="Active workflow" /></dt>
        <dd>{activeWorkflowSummary(projectOverview, locale)}</dd>
        <dt><Bi zh="最近中断" en="Latest interruption" /></dt>
        <dd>{failedWorkflowSummary(projectOverview, locale)}</dd>
        <dt><Bi zh="中断时间" en="Interruption updated" /></dt>
        <dd>{projectOverview.latest_failed_workflow_updated_at || tx(locale, "无", "none")}</dd>
        <dt><Bi zh="就绪度" en="Readiness" /></dt>
        <dd>{readinessAvailable ? tx(locale, "已更新", "Up to date") : tx(locale, "等待首次分析", "Waiting for the first analysis")}</dd>
        <dt><Bi zh="更新时间" en="Updated" /></dt>
        <dd>{projectOverview.updated_at || tx(locale, "无", "none")}</dd>
      </dl>
    </>
  );
}

function SeedRunOverview({
  displayProgress,
  locale,
  projectId,
  selectedRunId,
  selectedSeedRun,
  tenantSlug,
}: {
  displayProgress?: number;
  locale: Locale;
  projectId: string;
  selectedRunId: string;
  selectedSeedRun: WorkflowRunSummary | null;
  tenantSlug: string;
}) {
  if (!selectedRunId) {
    return <p className="form-hint"><Bi zh="暂无分析任务。" en="No analysis runs yet." /></p>;
  }
  if (!selectedSeedRun) {
    return <p className="form-hint"><Bi zh="分析状态尚未加载。" en="Analysis status has not loaded." /></p>;
  }
  if (!selectedSeedRun.ok) {
    return <OverviewPublicFailureNotice code={selectedSeedRun.code} locale={locale} projectId={projectId} tenantSlug={tenantSlug} />;
  }
  const progress = typeof displayProgress === "number" ? displayProgress : selectedSeedRun.progress;
  return (
    <div className="overview-run-summary">
      <div className="overview-run-heading">
        <span><Bi zh="状态" en="Status" /></span>
        <strong><StatusValue value={selectedSeedRun.status} /></strong>
      </div>
      <div className="overview-progress-heading">
        <span><Bi zh="分析进度" en="Analysis progress" /></span>
        <strong>{progress}%</strong>
      </div>
      <progress
        aria-label={tx(locale, "分析进度", "Analysis progress")}
        max={100}
        value={progress}
      />
      {selectedSeedRun.status === "failed" && selectedSeedRun.error_code ? (
        <p className="form-hint">
          <Bi zh={`失败原因：${publicSeedFailureHint(locale, selectedSeedRun.error_code)}`} en={`Failure: ${publicSeedFailureHint(locale, selectedSeedRun.error_code)}`} />
        </p>
      ) : null}
      <p className="form-hint"><Bi zh="更新时间：" en="Updated: " />{selectedSeedRun.updated_at}</p>
    </div>
  );
}

const SEED_PIPELINE_STAGE_ORDER = [
  "parse_file",
  "segment_text",
  "sequential_reading",
  "persist_runtime_facts",
  "global_aggregation",
  "story_ontology",
  "entity_resolution",
  "agent_profiles",
  "archive_candidates",
  "index_assets",
  "finalize",
] as const;

const SEED_STAGE_PROGRESS: Record<string, number> = {
  parse_file: 12,
  segment_text: 24,
  sequential_reading: 42,
  persist_runtime_facts: 52,
  global_aggregation: 62,
  story_ontology: 72,
  entity_resolution: 80,
  agent_profiles: 86,
  archive_candidates: 92,
  index_assets: 96,
  finalize: 100,
};

function seedStageLabel(locale: Locale, stage: string) {
  const labels: Record<string, [string, string]> = {
    parse_file: ["解析文件", "Parse file"],
    segment_text: ["智能分段", "Segment text"],
    sequential_reading: ["顺序精读", "Sequential reading"],
    persist_runtime_facts: ["写入事实", "Persist facts"],
    global_aggregation: ["全局聚合", "Global aggregation"],
    story_ontology: ["故事本体", "Story ontology"],
    entity_resolution: ["实体解析", "Entity resolution"],
    agent_profiles: ["角色档案", "Agent profiles"],
    archive_candidates: ["档案候选", "Archive candidates"],
    index_assets: ["资产索引", "Index assets"],
    finalize: ["收尾", "Finalize"],
  };
  const pair = labels[stage];
  return pair ? tx(locale, pair[0], pair[1]) : stage;
}

function seedDisplayProgress(
  run: Extract<WorkflowRunSummary, { ok: true }>,
  seedEvents: WorkflowRunEventsSummary | null,
): number {
  if (run.status === "completed" || run.status === "failed") {
    return 100;
  }
  let fromEvents = 0;
  if (seedEvents?.ok) {
    for (const event of seedEvents.items) {
      const stage = typeof event.payload?.stage === "string" ? event.payload.stage : "";
      const eventStatus = typeof event.payload?.status === "string" ? event.payload.status : "";
      if (!stage || !(stage in SEED_STAGE_PROGRESS)) continue;
      const base = SEED_STAGE_PROGRESS[stage] ?? 0;
      fromEvents = Math.max(fromEvents, eventStatus === "completed" ? base : Math.max(0, base - 4));
    }
  }
  return Math.max(run.progress ?? 0, fromEvents, run.status === "running" ? 5 : 0);
}

function seedPipelineStages(
  locale: Locale,
  run: Extract<WorkflowRunSummary, { ok: true }>,
  seedEvents: WorkflowRunEventsSummary | null,
) {
  const stageMap = new Map<string, "pending" | "active" | "done" | "failed">();
  for (const stage of SEED_PIPELINE_STAGE_ORDER) {
    stageMap.set(stage, "pending");
  }
  if (seedEvents?.ok) {
    for (const event of seedEvents.items) {
      const stage = typeof event.payload?.stage === "string" ? event.payload.stage : "";
      const eventStatus = typeof event.payload?.status === "string" ? event.payload.status : "";
      if (!stageMap.has(stage)) continue;
      if (eventStatus === "completed") stageMap.set(stage, "done");
      else if (eventStatus === "failed") stageMap.set(stage, "failed");
      else if (eventStatus === "pending") stageMap.set(stage, run.status === "failed" ? "failed" : "active");
    }
  }
  if (run.status === "queued") {
    // Keep first stage pending until worker marks running/pending parse.
  }
  return SEED_PIPELINE_STAGE_ORDER.map((id) => ({
    id,
    label: seedStageLabel(locale, id),
    state: stageMap.get(id) ?? "pending",
  }));
}

function latestSeedStageLabel(locale: Locale, seedEvents: WorkflowRunEventsSummary | null) {
  if (!seedEvents?.ok || seedEvents.items.length === 0) return null;
  for (let index = seedEvents.items.length - 1; index >= 0; index -= 1) {
    const event = seedEvents.items[index];
    const stage = typeof event.payload?.stage === "string" ? event.payload.stage : "";
    const status = typeof event.payload?.status === "string" ? event.payload.status : "";
    if (!stage) continue;
    const label = seedStageLabel(locale, stage);
    if (status === "failed") return tx(locale, `当前阶段：${label}（失败）`, `Current stage: ${label} (failed)`);
    if (status === "pending") return tx(locale, `当前阶段：${label}`, `Current stage: ${label}`);
    if (status === "completed") return tx(locale, `已完成：${label}`, `Completed: ${label}`);
  }
  return null;
}

function publicSeedFailureHint(locale: Locale, code: string) {
  if (code === "LLM_MODULE_CAPABILITY_MISSING") {
    return tx(
      locale,
      "绑定模型不支持结构化输出，请在模型设置中为顺序精读等能力换用支持 JSON 的模型后重试。",
      "The bound model lacks JSON capability. Bind a JSON-capable model for sequential reading and retry.",
    );
  }
  if (code === "LLM_QUOTA_RESERVATION_UNAVAILABLE") {
    return tx(
      locale,
      "模型已绑定，但预算预留失败：缺少输出上限或模型上下文窗口。请在模型设置中补全输出上限与上下文信息。",
      "The model is bound, but quota reservation failed: set an output limit and ensure the model has context window metadata.",
    );
  }
  if (code === "LLM_MODULE_UNBOUND") {
    return tx(locale, "核心分析能力未绑定模型。", "A required analysis capability is unbound.");
  }
  if (code === "LLM_QUOTA_TOKENS_EXCEEDED" || code === "LLM_QUOTA_COST_EXCEEDED") {
    return tx(locale, "本周期调用额度已用尽，请提高额度或等待周期重置。", "Usage quota for this period is exhausted. Raise the limit or wait for reset.");
  }
  if (code === "LLM_QUOTA_CONCURRENCY_EXCEEDED") {
    return tx(locale, "并发调用已达上限，请稍后重试。", "Concurrent LLM calls hit the limit. Retry shortly.");
  }
  return tx(locale, "分析未能完成，请稍后重试或检查模型设置。", "Analysis could not finish. Retry later or check model settings.");
}

function ProjectReadinessPanel({
  locale,
  projectId,
  projectReadiness,
  tenantSlug,
}: {
  locale: Locale;
  projectId: string;
  projectReadiness: ProjectReadinessSummary;
  tenantSlug: string;
}) {
  if (!projectReadiness.ok) {
    return <OverviewPublicFailureNotice code={projectReadiness.code} locale={locale} projectId={projectId} tenantSlug={tenantSlug} />;
  }
  const metrics = [
    ["assets", "资产", "Assets", projectReadiness.ready_asset_count],
    ["entities", "实体", "Entities", projectReadiness.ready_entity_count],
    ["relationships", "关系", "Relationships", projectReadiness.ready_relationship_count],
    ["world-rules", "世界规则", "World rules", projectReadiness.ready_world_rule_count],
  ];
  return (
    <>
      <div className="status-row" aria-label={tx(locale, "项目就绪度统计", "Project readiness counts")}>
        {metrics.map(([key, zh, en, value]) => (
          <span className="status-pill" key={key}>
            <Bi zh={`${zh}：`} en={`${en}: `} />{value}
          </span>
        ))}
      </div>
      <p className="form-hint"><Bi zh="更新时间：" en="Updated: " />{projectReadiness.updated_at}</p>
    </>
  );
}

function SeedRunsTable({
  locale,
  projectId,
  seedRuns,
  tenantSlug,
}: {
  locale: Locale;
  projectId: string;
  seedRuns: SeedRunsSummary;
  tenantSlug: string;
}) {
  if (!seedRuns.ok) {
    return <OverviewPublicFailureNotice code={seedRuns.code} locale={locale} projectId={projectId} tenantSlug={tenantSlug} />;
  }
  if (seedRuns.items.length === 0) {
    return <p className="form-hint"><Bi zh="项目中还没有分析任务。" en="No analysis runs have been queued for this project." /></p>;
  }
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th><Bi zh="任务" en="Run" /></th>
            <th><Bi zh="状态" en="Status" /></th>
            <th><Bi zh="进度" en="Progress" /></th>
            <th><Bi zh="消息" en="Message" /></th>
            <th><Bi zh="更新时间" en="Updated" /></th>
            <th><Bi zh="查看" en="Inspect" /></th>
          </tr>
        </thead>
        <tbody>
          {seedRuns.items.map((run, index) => run.ok ? (
            <tr key={run.run_id}>
              <td><Bi zh={`分析 ${seedRuns.items.length - index}`} en={`Analysis ${seedRuns.items.length - index}`} /></td>
              <td><StatusValue value={run.status} /></td>
              <td>{run.progress}%</td>
              <td>{run.error_code ? <FailureText /> : <StatusValue value={run.status} />}</td>
              <td>{run.updated_at}</td>
              <td><a href={overviewHref(tenantSlug, projectId, run.run_id)}><Bi zh="查看" en="Inspect" /></a></td>
            </tr>
          ) : (
            <tr key={`${run.code}-${index}`}>
              <td><Bi zh={`分析 ${seedRuns.items.length - index}`} en={`Analysis ${seedRuns.items.length - index}`} /></td>
              <td><Bi zh="错误" en="error" /></td>
              <td>0</td>
              <td><FailureText /></td>
              <td>-</td>
              <td>-</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SeedRunDetail({
  locale,
  projectId,
  selectedRunId,
  selectedSeedRun,
  tenantSlug,
}: {
  locale: Locale;
  projectId: string;
  selectedRunId: string;
  selectedSeedRun: WorkflowRunSummary | null;
  tenantSlug: string;
}) {
  if (!selectedRunId) {
    return <p className="form-hint"><Bi zh="尚未选择分析任务。" en="No analysis run selected." /></p>;
  }
  if (!selectedSeedRun) {
    return <p className="form-hint"><Bi zh="分析任务详情尚未加载。" en="Analysis detail has not been loaded." /></p>;
  }
  if (!selectedSeedRun.ok) {
    return <OverviewPublicFailureNotice code={selectedSeedRun.code} locale={locale} projectId={projectId} tenantSlug={tenantSlug} />;
  }
  return (
    <dl>
      <dt><Bi zh="状态" en="Status" /></dt>
      <dd><StatusValue value={selectedSeedRun.status} /></dd>
      <dt><Bi zh="进度" en="Progress" /></dt>
      <dd>{selectedSeedRun.progress}%</dd>
      {selectedSeedRun.error_code ? (
        <>
          <dt><Bi zh="恢复建议" en="Recovery" /></dt>
          <dd><Bi zh="请重试任务；若仍未完成，请检查模型配置。" en="Retry the run. If it still does not finish, check model configuration." /></dd>
        </>
      ) : null}
      <dt><Bi zh="更新时间" en="Updated" /></dt>
      <dd>{selectedSeedRun.updated_at}</dd>
    </dl>
  );
}

function SeedEvents({
  locale,
  projectId,
  selectedRunId,
  seedEvents,
  tenantSlug,
}: {
  locale: Locale;
  projectId: string;
  selectedRunId: string;
  seedEvents: WorkflowRunEventsSummary | null;
  tenantSlug: string;
}) {
  if (!selectedRunId) {
    return <p className="form-hint"><Bi zh="选择或开始分析后查看事件。" en="Select or start analysis to inspect events." /></p>;
  }
  if (!seedEvents) {
    return <p className="form-hint"><Bi zh="事件回放尚未加载。" en="Event replay has not been loaded." /></p>;
  }
  if (!seedEvents.ok) {
    return <OverviewPublicFailureNotice code={seedEvents.code} locale={locale} projectId={projectId} tenantSlug={tenantSlug} />;
  }
  if (seedEvents.items.length === 0) {
    return <p className="form-hint"><Bi zh="当前之后没有新事件。" en="No events after the current cursor." /></p>;
  }
  return (
    <div className="trace-list">
      {seedEvents.items.map((event) => (
        <article className="trace-event" key={event.event_id}>
          <div className="trace-event-header">
            <strong>{event.event_type}</strong>
            <span className="trace-redaction"><Bi zh="序号 " en="seq " />{event.sequence}</span>
          </div>
          <p className="trace-meta">{event.created_at}</p>
        </article>
      ))}
    </div>
  );
}

function StatusLine({ status }: { status: ActionStatus | null }) {
  if (!status) {
    return null;
  }
  const className = status.status === "success" ? "form-status success-box" : "form-status error-box";
  return (
    <p className={className} role={status.status === "success" ? "status" : "alert"}>
      {status.status === "success" ? <Bi zh="操作已完成。" en="Action completed." /> : <Bi zh="操作未完成，请检查输入或稍后重试。" en="The action could not be completed. Check the input or try again." />}
    </p>
  );
}

function activeWorkflowSummary(projectOverview: ProjectOverviewSummary, locale: Locale) {
  if (!projectOverview.ok || !projectOverview.active_workflow_run_id) {
    return tx(locale, "无", "none");
  }
  const workflowType = workflowTypeLabel(locale, projectOverview.active_workflow_type);
  const workflowStatus = workflowStatusLabel(locale, projectOverview.active_workflow_status);
  return `${workflowType} · ${tx(locale, "状态", "status")}: ${workflowStatus}`;
}

function failedWorkflowSummary(projectOverview: ProjectOverviewSummary, locale: Locale) {
  if (!projectOverview.ok || !projectOverview.latest_failed_workflow_run_id) {
    return tx(locale, "无", "none");
  }
  const workflowType = workflowTypeLabel(locale, projectOverview.latest_failed_workflow_type);
  return projectOverview.latest_failed_workflow_error_code
    ? tx(locale, `${workflowType}需要处理，可从当前任务重试。`, `${workflowType} needs attention and can be retried from the current task.`)
    : workflowType;
}

function overviewHref(tenantSlug: string, projectId: string, runId = "") {
  const query = new URLSearchParams();
  if (runId) {
    query.set("runId", runId);
  }
  const suffix = query.toString();
  return `${projectSectionHref(tenantSlug, projectId, "overview")}${suffix ? `?${suffix}` : ""}`;
}

function projectSectionHref(tenantSlug: string, projectId: string, section: string) {
  return `/${encodeURIComponent(tenantSlug)}/projects/${encodeURIComponent(projectId)}/${section}`;
}

function workflowTypeLabel(locale: Locale, workflowType: string) {
  const labels: Record<string, [string, string]> = {
    asset_ingestion: ["素材导入", "Material import"],
    asset_reindex: ["资产搜索刷新", "Asset search refresh"],
    seed_pipeline: ["故事分析", "Story analysis"],
    story_graph: ["故事图谱", "Story graph"],
    story_graph_build: ["故事图谱构建", "Story graph build"],
    worldline: ["世界线推演", "Worldline simulation"],
    writer: ["正文创作", "Manuscript writing"],
  };
  const normalized = workflowType.trim().toLowerCase();
  const label = labels[normalized];
  if (label) {
    return tx(locale, label[0], label[1]);
  }
  if (!workflowType) {
    return tx(locale, "工作任务", "Workflow");
  }
  return workflowType.replaceAll("_", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function workflowStatusLabel(locale: Locale, status: string) {
  const labels: Record<string, [string, string]> = {
    cancelled: ["已取消", "Cancelled"],
    completed: ["已完成", "Completed"],
    failed: ["需要处理", "Needs attention"],
    queued: ["等待开始", "Waiting to start"],
    running: ["进行中", "In progress"],
  };
  const label = labels[status.trim().toLowerCase()];
  return label ? tx(locale, label[0], label[1]) : tx(locale, "未知", "Unknown");
}

function formatFileSize(sizeBytes: number) {
  if (!Number.isFinite(sizeBytes) || sizeBytes <= 0) {
    return "0 KB";
  }
  if (sizeBytes < 1024 * 1024) {
    return `${Math.max(1, Math.round(sizeBytes / 1024))} KB`;
  }
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}
