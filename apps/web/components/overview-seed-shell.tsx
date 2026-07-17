import {
  Activity,
  ChevronRight,
  Feather,
  FileText,
  FolderOpen,
  Globe2,
  LayoutDashboard,
  Library,
  Network,
  Upload,
  UserRound,
} from "lucide-react";

import { evaluateCreationReadiness, llmFacilityProjectHref } from "../lib/llm-creation-readiness";
import { formatBeijingTime, formatBeijingTimeLabel } from "../lib/beijing-time";
import { type Locale, tx } from "../lib/locale";
import type {
  AnalysisCandidatesSummary,
  AnalysisRunStartSummary,
  AnalysisWorkspaceFileSummary,
  AnalysisWorkspaceFilesSummary,
  ProjectOverviewSummary,
  ProjectReadinessSummary,
  SeedRunStartSummary,
  SeedRunsSummary,
  SourceFileObjectUploadSummary,
  SourceFilesSummary,
  SourceFileSummary,
  WorkflowControlSummary,
  WorkflowRunEvent,
  WorkflowRunEventsSummary,
  WorkflowRunSummary,
} from "../lib/api";
import {
  analysisActivityLogFromEvents,
  analysisStageFromEvent,
  analysisStageLabel,
  ANALYSIS_PIPELINE_STAGE_ORDER,
  ANALYSIS_STAGE_PROGRESS,
  publicAnalysisFailureHint,
} from "../lib/overview-analysis-activity";
import { Bi, FailureText, StatusValue } from "./bilingual-text";
import { PublicErrorNotice } from "./public-error-notice";
import { canCancelSeedRun, canRetrySeedRun } from "./overview-seed-run-controls";
import { OverviewAnalysisCandidatesPanel, analysisCandidatesSummaryHint } from "./overview-analysis-candidates-panel";
import { OverviewAnalysisWorkspacePanel, analysisWorkspaceSummaryHint } from "./overview-analysis-workspace-panel";
import { OverviewCompletedBoard } from "./overview-completed-board";
import {
  OverviewSeedProgressWall,
  type SeedActivityLogLine,
} from "./overview-seed-progress-wall";
import { OverviewSeedUploadForm } from "./overview-seed-upload-form";
import { OverviewActivityLogLive } from "./overview-activity-log-live";
import { SeedRunAutoRefresh } from "./seed-run-auto-refresh";
import { SubmitButton } from "./submit-button";

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
  workspaceFiles?: AnalysisWorkspaceFilesSummary | null;
  selectedWorkspaceFile?: AnalysisWorkspaceFileSummary | null;
  selectedWorkspacePath?: string;
  /** Completed-board modal id from ?board= (or inferred when a workspace file is open). */
  initialBoardId?: string;
  analysisCandidates?: AnalysisCandidatesSummary | null;
  materialsHref?: string;
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
  workspaceFiles = null,
  selectedWorkspaceFile = null,
  selectedWorkspacePath = "",
  initialBoardId = "",
  analysisCandidates = null,
  materialsHref = "",
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
  const seedRunActive = Boolean(
    selectedSeedRun
    && selectedSeedRun.ok
    && (selectedSeedRun.status === "queued" || selectedSeedRun.status === "running"),
  );
  const isCompletedRun = Boolean(
    selectedSeedRun
    && selectedSeedRun.ok
    && selectedSeedRun.status === "completed",
  );
  const overviewState = isCompletedRun
    ? "completed"
    : seedRunActive
      ? "active"
      : isEmptyProject
        ? "empty"
        : "idle";

  const uploadForm = (
    <OverviewSeedUploadForm
      action={uploadAndStartSeedAction}
      locale={locale}
      seedStatus={<StatusLine status={seedStatus} />}
      sourceStatus={<StatusLine status={sourceStatus} />}
      variant={isCompletedRun ? "split" : "stack"}
    />
  );

  return (
    <div
      className="overview-root"
      data-layout="foundation-bar"
      data-overview-state={overviewState}
    >
      <SeedRunAutoRefresh active={seedRunActive} />
      <section
        className={`overview-foundation-bar ${projectOverview.ok ? "" : "error-box"}`}
        aria-labelledby="project-health-heading"
        data-density="compact"
      >
        <div className="overview-foundation-bar-label">
          <LayoutDashboard aria-hidden="true" size={15} strokeWidth={1.8} />
          <h2 id="project-health-heading"><Bi zh="故事基础" en="Story foundation" /></h2>
        </div>
        <ProjectHealthPanel
          compact
          locale={locale}
          projectId={projectId}
          projectOverview={projectOverview}
          tenantSlug={tenantSlug}
        />
      </section>

      {isCompletedRun ? (
        <div className="workbench-grid overview-completed-layout">
          <main className="overview-completed-main">
            <section
              className={`panel overview-next-panel overview-completed-panel ${selectedSeedRun && !selectedSeedRun.ok ? "error-box" : ""}`}
              aria-labelledby="recent-seed-run-heading"
            >
              <p className="eyebrow overview-visually-hidden">
                <Bi zh="当前重点" en="Next step" />
              </p>
              <h2 id="recent-seed-run-heading" className="overview-visually-hidden">
                <Bi zh="下一步" en="Next step" />
              </h2>
              <OverviewNextStep
                analysisCandidates={analysisCandidates}
                bootstrapIdeaAction={bootstrapIdeaAction}
                bootstrapStatus={bootstrapStatus}
                cancelSeedRunAction={cancelSeedRunAction}
                cancelSeedRunEnabled={cancelSeedRunEnabled}
                completeUploadAction={completeUploadAction}
                creationReadiness={creationReadiness}
                embedResults={false}
                locale={locale}
                materialsHref={materialsHref || `/${tenantSlug}/projects/${projectId}/materials`}
                projectId={projectId}
                projectOverview={projectOverview}
                retrySeedRunAction={retrySeedRunAction}
                retrySeedRunEnabled={retrySeedRunEnabled}
                seedEvents={seedEvents}
                selectedRunId={selectedRunId}
                selectedSeedRun={selectedSeedRun}
                selectedWorkspaceFile={selectedWorkspaceFile}
                selectedWorkspacePath={selectedWorkspacePath}
                sourceFiles={sourceFiles}
                startSeedRunAction={startSeedRunAction}
                tenantSlug={tenantSlug}
                workspaceFiles={workspaceFiles}
              />
              <OverviewCompletedBoard
                initialActiveId={initialBoardId || null}
                cards={[
                  {
                    id: "results",
                    icon: <Library aria-hidden="true" size={18} strokeWidth={1.8} />,
                    title: <Bi zh="拆解结果（已自动入库）" en="Analysis results (auto-imported)" />,
                    subtitle: analysisCandidatesSummaryHint(locale, analysisCandidates),
                    body: (
                      <OverviewAnalysisCandidatesPanel
                        candidates={analysisCandidates}
                        locale={locale}
                        materialsHref={materialsHref || `/${tenantSlug}/projects/${projectId}/materials`}
                        presentation="body"
                      />
                    ),
                  },
                  {
                    id: "workspace",
                    icon: <FolderOpen aria-hidden="true" size={18} strokeWidth={1.8} />,
                    title: <Bi zh="分析工作区" en="Analysis workspace" />,
                    subtitle: analysisWorkspaceSummaryHint(locale, workspaceFiles),
                    body: (
                      <OverviewAnalysisWorkspacePanel
                        locale={locale}
                        presentation="body"
                        projectId={projectId}
                        runId={selectedRunId}
                        selectedFile={selectedWorkspaceFile}
                        selectedPath={selectedWorkspacePath}
                        tenantSlug={tenantSlug}
                        workspaceFiles={workspaceFiles}
                      />
                    ),
                  },
                  {
                    id: "files",
                    icon: <FileText aria-hidden="true" size={18} strokeWidth={1.8} />,
                    title: <Bi zh="文件与分析记录" en="Files and analysis history" />,
                    subtitle: (
                      <>
                        {sourceFiles.ok ? sourceFiles.items.length : 0} <Bi zh="个文件" en="files" /> · {seedRuns.ok ? seedRuns.items.length : 0} <Bi zh="次分析" en="runs" />
                      </>
                    ),
                    body: (
                      <>
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
                      </>
                    ),
                  },
                  {
                    id: "diagnostics",
                    icon: <Activity aria-hidden="true" size={18} strokeWidth={1.8} />,
                    title: <Bi zh="项目诊断（可选）" en="Project diagnostics (optional)" />,
                    subtitle: <Bi zh="就绪度与任务摘要，不含拆解结果" en="Readiness and run summary — not analysis results" />,
                    body: (
                      <>
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
                      </>
                    ),
                  },
                ]}
              />

              <section
                className="overview-completed-import overview-upload-disclosure"
                aria-labelledby="upload-and-start-seed-heading"
                data-density="compact"
              >
                <div className="overview-completed-import-heading">
                  <p className="eyebrow"><Bi zh="次级操作" en="Secondary action" /></p>
                  <h3 id="upload-and-start-seed-heading">
                    <Bi zh="导入新文本" en="Import new manuscript" />
                  </h3>
                </div>
                {uploadForm}
              </section>
            </section>
          </main>
        </div>
      ) : (
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
                analysisCandidates={analysisCandidates}
                bootstrapIdeaAction={bootstrapIdeaAction}
                bootstrapStatus={bootstrapStatus}
                cancelSeedRunAction={cancelSeedRunAction}
                cancelSeedRunEnabled={cancelSeedRunEnabled}
                completeUploadAction={completeUploadAction}
                creationReadiness={creationReadiness}
                locale={locale}
                materialsHref={materialsHref || `/${tenantSlug}/projects/${projectId}/materials`}
                projectId={projectId}
                projectOverview={projectOverview}
                retrySeedRunAction={retrySeedRunAction}
                retrySeedRunEnabled={retrySeedRunEnabled}
                seedEvents={seedEvents}
                selectedRunId={selectedRunId}
                selectedSeedRun={selectedSeedRun}
                selectedWorkspaceFile={selectedWorkspaceFile}
                selectedWorkspacePath={selectedWorkspacePath}
                sourceFiles={sourceFiles}
                startSeedRunAction={startSeedRunAction}
                tenantSlug={tenantSlug}
                workspaceFiles={workspaceFiles}
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
          </main>

          <aside className="overview-rail">
            <section
              className="panel overview-upload-panel overview-upload-disclosure"
              aria-labelledby="upload-and-start-seed-heading"
              data-elevated={selectedRunId ? "true" : "false"}
              data-density="compact"
            >
              <p className="eyebrow"><Bi zh="导入" en="Import" /></p>
              <h2 id="upload-and-start-seed-heading"><Bi zh="导入小说" en="Import manuscript" /></h2>
              {uploadForm}
            </section>

            <div className="overview-secondary-stack">
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
                    <strong><Bi zh="项目诊断（可选）" en="Project diagnostics (optional)" /></strong>
                    <small><Bi zh="就绪度与任务摘要，不含拆解结果" en="Readiness and run summary — not analysis results" /></small>
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
                </div>
              </details>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

function OverviewNextStep({
  analysisCandidates = null,
  bootstrapIdeaAction,
  bootstrapStatus,
  cancelSeedRunAction,
  cancelSeedRunEnabled,
  completeUploadAction,
  creationReadiness,
  embedResults = true,
  locale,
  materialsHref = "",
  projectId,
  projectOverview,
  retrySeedRunAction,
  retrySeedRunEnabled,
  seedEvents,
  selectedRunId,
  selectedSeedRun,
  selectedWorkspaceFile = null,
  selectedWorkspacePath = "",
  sourceFiles,
  startSeedRunAction,
  tenantSlug,
  workspaceFiles = null,
}: {
  analysisCandidates?: AnalysisCandidatesSummary | null;
  bootstrapIdeaAction: (formData: FormData) => Promise<void>;
  bootstrapStatus: ActionStatus | null;
  cancelSeedRunAction: (formData: FormData) => Promise<void>;
  cancelSeedRunEnabled: boolean;
  completeUploadAction: (formData: FormData) => Promise<void>;
  creationReadiness: ReturnType<typeof evaluateCreationReadiness>;
  embedResults?: boolean;
  locale: Locale;
  materialsHref?: string;
  projectId: string;
  projectOverview: ProjectOverviewSummary;
  retrySeedRunAction: (formData: FormData) => Promise<void>;
  retrySeedRunEnabled: boolean;
  seedEvents: WorkflowRunEventsSummary | null;
  selectedRunId: string;
  selectedSeedRun: WorkflowRunSummary | null;
  selectedWorkspaceFile?: AnalysisWorkspaceFileSummary | null;
  selectedWorkspacePath?: string;
  sourceFiles: SourceFilesSummary;
  startSeedRunAction: (formData: FormData) => Promise<void>;
  tenantSlug: string;
  workspaceFiles?: AnalysisWorkspaceFilesSummary | null;
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
    const isAnalysisRun = selectedSeedRun.workflow_type === "analysis_run"
      || (seedEvents?.ok === true && seedEvents.items.some((event) => event.event_type.startsWith("analysis.")));
    const displayProgress = isAnalysisRun
      ? analysisDisplayProgress(selectedSeedRun, seedEvents)
      : seedDisplayProgress(selectedSeedRun, seedEvents);
    const stageStates = isAnalysisRun
      ? analysisPipelineStages(locale, selectedSeedRun, seedEvents)
      : seedPipelineStages(locale, selectedSeedRun, seedEvents);
    const activityLog = isAnalysisRun
      ? analysisActivityLog(locale, seedEvents)
      : seedActivityLog(locale, seedEvents);
    const runTone = overviewStatusTone(selectedSeedRun.status);
    const failureHint = selectedSeedRun.error_code
      ? publicSeedFailureHint(locale, selectedSeedRun.error_code)
      : null;
    const showResults = embedResults && (
      completed || Boolean(
        (workspaceFiles && workspaceFiles.ok && workspaceFiles.items.length > 0)
        || (analysisCandidates && analysisCandidates.ok && analysisCandidates.items.length > 0),
      )
    );
    return (
      <>
        <OverviewSeedProgressWall
          cancelSeedRunAction={cancelSeedRunAction}
          cancelSeedRunEnabled={cancelSeedRunEnabled}
          completed={completed}
          displayProgress={displayProgress}
          failureHint={failureHint}
          failureRecoveryHref={
            selectedSeedRun.error_code === "LLM_MODULE_UNBOUND"
              || selectedSeedRun.error_code === "LLM_MODULE_CAPABILITY_MISSING"
              || selectedSeedRun.error_code === "LLM_CREDENTIAL_UNCONFIGURED"
              ? llmFacilityProjectHref(tenantSlug, projectId)
              : ""
          }
          interrupted={interrupted}
          retrySeedRunAction={retrySeedRunAction}
          retrySeedRunEnabled={retrySeedRunEnabled}
          runOverview={(
            <SeedRunOverview
              activityLog={activityLog}
              displayProgress={displayProgress}
              initialEvents={seedEvents?.ok ? seedEvents.items : []}
              isAnalysisRun={isAnalysisRun}
              locale={locale}
              projectId={projectId}
              selectedRunId={selectedRunId}
              selectedSeedRun={selectedSeedRun}
              tenantSlug={tenantSlug}
            />
          )}
          runTone={runTone}
          selectedRunId={selectedRunId}
          selectedSeedRun={selectedSeedRun}
          stageStates={stageStates}
        />
        {showResults && isAnalysisRun ? (
          <div className="overview-analysis-results" data-completed={completed ? "true" : "false"}>
            <OverviewAnalysisCandidatesPanel
              candidates={analysisCandidates}
              locale={locale}
              materialsHref={materialsHref || projectSectionHref(tenantSlug, projectId, "materials")}
            />
            <OverviewAnalysisWorkspacePanel
              locale={locale}
              projectId={projectId}
              runId={selectedRunId}
              selectedFile={selectedWorkspaceFile}
              selectedPath={selectedWorkspacePath}
              tenantSlug={tenantSlug}
              workspaceFiles={workspaceFiles}
            />
          </div>
        ) : null}
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
  const writerHref = projectSectionHref(tenantSlug, projectId, "writer");
  return (
    <div className="overview-dual-entry overview-dual-entry-slim" data-empty-project-entry="true">
      <p className="overview-next-copy">
        <strong><Bi zh="开始创作" en="Start creating" /></strong>
      </p>
      <p className="form-hint">
        <Bi
          zh="在写作台告诉助手你想写什么；也可以先上传已有文本做分析。"
          en="Tell the assistant what you want in Writer, or upload existing text to analyze."
        />
      </p>
      {bootstrapStatus ? <StatusLine status={bootstrapStatus} /> : null}
      <div className="overview-slim-primary">
        <a className="overview-primary-writer-link" href={writerHref}>
          <Feather aria-hidden="true" size={18} />
          <span>
            <strong><Bi zh="打开写作台" en="Open Writer" /></strong>
            <small><Bi zh="对话优先 · 立刻开始" en="Conversation-first · start now" /></small>
          </span>
          <ChevronRight aria-hidden="true" size={18} />
        </a>
      </div>
      <details className="overview-slim-more">
        <summary><Bi zh="更多开始方式" en="More ways to start" /></summary>
        <div className="overview-dual-entry-grid">
          <section className="overview-entry-card" aria-labelledby="idea-first-entry-heading">
            <p className="eyebrow"><Bi zh="可选" en="Optional" /></p>
            <h3 id="idea-first-entry-heading"><Bi zh="从一个想法建立首章" en="Bootstrap from an idea" /></h3>
            <p className="form-hint">
              <Bi
                zh="创建最小书籍计划与首章，再进入写作台。"
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
          </section>
          <section className="overview-entry-card" aria-labelledby="upload-first-entry-heading">
            <p className="eyebrow"><Bi zh="可选" en="Optional" /></p>
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
      </details>
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

export function seedRunActionStatus(
  result: SeedRunStartSummary | AnalysisRunStartSummary,
  locale: Locale,
): ActionStatus & { runId: string } {
  if (!result.ok) {
    const hint = publicAnalysisFailureHint(locale, result.code);
    return {
      status: "error",
      code: result.code,
      message: hint
        || tx(locale, "分析任务未开始，请检查文件和模型配置。", "The analysis did not start. Check the file and model configuration."),
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
      titleZh: "分析模型未就绪",
      titleEn: "Analysis model not ready",
      messageZh: "拆解小说需要「分析规划」与「分析执行」模型绑定。若已连接写作助手，重试时会自动补齐。",
      messageEn: "Novel analysis needs Analysis Planner and Worker bindings. If a writing model is already connected, retry will inherit it.",
      recoveryZh: "打开模型设置完成绑定，或直接点「重试任务」。",
      recoveryEn: "Open model settings to bind, or tap Retry analysis.",
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
  compact = false,
  locale,
  projectId,
  projectOverview,
  tenantSlug,
}: {
  compact?: boolean;
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
    <div
      className="overview-metric-grid"
      data-density={compact ? "compact" : "default"}
      aria-label={tx(locale, "项目核心统计", "Core project counts")}
    >
      {metrics.map(([key, zh, en, value, Icon]) => {
        return (
          <div className="overview-metric" key={key}>
            <strong>{value}</strong>
            <span><Bi zh={zh} en={en} /></span>
            {compact ? null : <Icon aria-hidden="true" size={24} strokeWidth={1.35} />}
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
        <dd>
          {projectOverview.latest_failed_workflow_updated_at
            ? formatBeijingTimeLabel(locale, projectOverview.latest_failed_workflow_updated_at)
            : tx(locale, "无", "none")}
        </dd>
        <dt><Bi zh="就绪度" en="Readiness" /></dt>
        <dd>{readinessAvailable ? tx(locale, "已更新", "Up to date") : tx(locale, "等待首次分析", "Waiting for the first analysis")}</dd>
        <dt><Bi zh="更新时间" en="Updated" /></dt>
        <dd>
          {projectOverview.updated_at
            ? formatBeijingTimeLabel(locale, projectOverview.updated_at)
            : tx(locale, "无", "none")}
        </dd>
      </dl>
    </>
  );
}

function SeedRunOverview({
  activityLog,
  displayProgress,
  initialEvents = [],
  isAnalysisRun = false,
  locale,
  projectId,
  selectedRunId,
  selectedSeedRun,
  tenantSlug,
}: {
  activityLog?: SeedActivityLogLine[];
  displayProgress?: number;
  initialEvents?: WorkflowRunEvent[];
  isAnalysisRun?: boolean;
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
  const isFailed = selectedSeedRun.status === "failed";
  const isInterrupted = isFailed || selectedSeedRun.status === "cancelled";
  const isActive = selectedSeedRun.status === "running" || selectedSeedRun.status === "queued";
  const updatedLabel = formatBeijingTimeLabel(locale, selectedSeedRun.updated_at);
  return (
    <div
      className="overview-run-summary"
      data-density={isInterrupted ? "compact" : "default"}
      data-run-state={selectedSeedRun.status}
    >
      {!isInterrupted ? (
        <>
          <div className="overview-run-heading">
            <span><Bi zh="状态" en="Status" /></span>
            <strong><StatusValue value={selectedSeedRun.status} /></strong>
          </div>
          <div className="overview-progress-heading">
            <span><Bi zh="分析进度" en="Analysis progress" /></span>
            <strong>{progress}%</strong>
          </div>
          <progress
            className="overview-progress-thin"
            aria-label={tx(locale, "分析进度", "Analysis progress")}
            max={100}
            value={progress}
          />
        </>
      ) : null}
      <OverviewActivityLogLive
        initialEvents={initialEvents}
        isActive={isActive}
        locale={locale}
        projectId={projectId}
        runId={selectedRunId}
        staticLines={activityLog}
        streamKind={isAnalysisRun ? "analysis" : "static"}
        tenantSlug={tenantSlug}
      />
      {/* Failure reason is shown once on the progress wall card; avoid duplicating here. */}
      {updatedLabel ? (
        <p className="form-hint overview-run-updated">
          <Bi zh="更新时间：" en="Updated: " />
          {updatedLabel}
        </p>
      ) : null}
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

function analysisDisplayProgress(
  run: Extract<WorkflowRunSummary, { ok: true }>,
  events: WorkflowRunEventsSummary | null,
): number {
  if (run.status === "completed") {
    return 100;
  }
  if (run.status === "failed" || run.status === "cancelled") {
    // Keep a real stage-based ceiling for interrupted runs; do not jump to 100
    // just because finalize failed, and do not invent near-complete progress.
    let interrupted = Math.max(run.progress ?? 0, 5);
    if (events?.ok) {
      for (const event of events.items) {
        const stage = analysisStageFromEvent(event);
        if (!stage || !(stage in ANALYSIS_STAGE_PROGRESS)) continue;
        if (stage === "finalize") continue;
        const base = ANALYSIS_STAGE_PROGRESS[stage] ?? 0;
        const done = event.event_type.endsWith(".completed")
          || event.event_type === "analysis.candidates.saved"
          || event.payload?.status === "completed";
        interrupted = Math.max(interrupted, done ? base : Math.max(0, base - 8));
      }
    }
    return Math.min(interrupted, 95);
  }
  let fromEvents = 0;
  if (events?.ok) {
    for (const event of events.items) {
      const stage = analysisStageFromEvent(event);
      if (!stage || !(stage in ANALYSIS_STAGE_PROGRESS)) continue;
      // Ignore terminal finalize noise while the run is still active/queued —
      // a failed finalize event previously inflated progress to 92%.
      if (stage === "finalize" && run.status !== "completed") continue;
      if (event.event_type.endsWith(".failed") || event.payload?.status === "failed") continue;
      const base = ANALYSIS_STAGE_PROGRESS[stage] ?? 0;
      const done = event.event_type.endsWith(".completed")
        || event.event_type === "analysis.candidates.saved"
        || event.event_type === "analysis.run.completed"
        || event.payload?.status === "completed";
      fromEvents = Math.max(fromEvents, done ? base : Math.max(0, base - 8));
    }
  }
  return Math.max(run.progress ?? 0, fromEvents, run.status === "running" ? 5 : 0);
}

function analysisPipelineStages(
  locale: Locale,
  run: Extract<WorkflowRunSummary, { ok: true }>,
  events: WorkflowRunEventsSummary | null,
) {
  const stageMap = new Map<string, "pending" | "active" | "done" | "failed">();
  for (const stage of ANALYSIS_PIPELINE_STAGE_ORDER) {
    stageMap.set(stage, "pending");
  }
  if (events?.ok) {
    for (const event of events.items) {
      const stage = analysisStageFromEvent(event);
      if (!stage || !stageMap.has(stage)) continue;
      if (event.event_type.endsWith(".failed") || event.payload?.status === "failed") {
        stageMap.set(stage, "failed");
        continue;
      }
      if (
        event.event_type.endsWith(".completed")
        || event.event_type === "analysis.candidates.saved"
        || event.event_type === "analysis.run.completed"
        || event.payload?.status === "completed"
      ) {
        stageMap.set(stage, "done");
        continue;
      }
      if (
        event.event_type.endsWith(".started")
        || event.event_type === "analysis.run.started"
        || event.event_type === "analysis.file.written"
        || event.event_type === "analysis.tool.started"
        || event.event_type === "analysis.tool.completed"
        || event.payload?.status === "running"
      ) {
        if (stageMap.get(stage) !== "done" && stageMap.get(stage) !== "failed") {
          stageMap.set(stage, run.status === "failed" ? "failed" : "active");
        }
      }
    }
  }
  if (run.status === "completed") {
    for (const stage of ANALYSIS_PIPELINE_STAGE_ORDER) {
      if (stageMap.get(stage) !== "failed") {
        stageMap.set(stage, "done");
      }
    }
  }
  return ANALYSIS_PIPELINE_STAGE_ORDER.map((id) => ({
    id,
    label: analysisStageLabel(locale, id),
    state: stageMap.get(id) ?? "pending",
  }));
}

function analysisActivityLog(
  locale: Locale,
  events: WorkflowRunEventsSummary | null,
  limit = 12,
): SeedActivityLogLine[] {
  if (!events?.ok) return [];
  return analysisActivityLogFromEvents(locale, events.items, limit);
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
      if (event.event_type === "seed.sequential_reading.progress" || stage === "sequential_reading") {
        const batchProgress = sequentialReadingBatchProgress(event.payload);
        if (batchProgress !== null) {
          fromEvents = Math.max(fromEvents, batchProgress);
          continue;
        }
      }
      fromEvents = Math.max(fromEvents, eventStatus === "completed" ? base : Math.max(0, base - 4));
    }
  }
  return Math.max(run.progress ?? 0, fromEvents, run.status === "running" ? 5 : 0);
}

function sequentialReadingBatchProgress(payload: Record<string, unknown> | undefined): number | null {
  if (!payload) return null;
  const completed = payload.completed_segments;
  const total = payload.total_segments;
  if (typeof completed !== "number" || typeof total !== "number" || total <= 0) {
    return null;
  }
  const start = SEED_STAGE_PROGRESS.segment_text ?? 24;
  const end = SEED_STAGE_PROGRESS.sequential_reading ?? 42;
  const ratio = Math.max(0, Math.min(1, completed / total));
  const value = start + Math.round((end - start) * ratio);
  return completed >= total ? end : Math.min(end - 1, Math.max(start, value));
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
      if (eventStatus === "completed" && event.event_type !== "seed.sequential_reading.progress") {
        stageMap.set(stage, "done");
      } else if (eventStatus === "failed") {
        stageMap.set(stage, "failed");
      } else if (
        eventStatus === "pending"
        || eventStatus === "running"
        || event.event_type === "seed.sequential_reading.progress"
      ) {
        if (stageMap.get(stage) !== "done" && stageMap.get(stage) !== "failed") {
          stageMap.set(stage, run.status === "failed" ? "failed" : "active");
        }
      }
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

function seedActivityLog(
  locale: Locale,
  seedEvents: WorkflowRunEventsSummary | null,
  limit = 24,
): SeedActivityLogLine[] {
  if (!seedEvents?.ok || seedEvents.items.length === 0) {
    return [];
  }
  const lines: SeedActivityLogLine[] = [];
  for (const event of seedEvents.items) {
    const line = seedActivityLineFromEvent(locale, event);
    if (line) {
      lines.push(line);
    }
  }
  if (lines.length <= limit) {
    return lines;
  }
  return lines.slice(lines.length - limit);
}

function seedActivityLineFromEvent(
  locale: Locale,
  event: {
    event_id: string;
    event_type: string;
    payload: Record<string, unknown>;
    created_at: string;
    sequence: number;
  },
): SeedActivityLogLine | null {
  const stage = typeof event.payload?.stage === "string" ? event.payload.stage : "";
  const status = typeof event.payload?.status === "string" ? event.payload.status : "";
  const payloadMessage = typeof event.payload?.message === "string" ? event.payload.message.trim() : "";
  const timeLabel = formatBeijingTime(locale, event.created_at);
  const stageLabel = stage ? seedStageLabel(locale, stage) : "";

  if (event.event_type === "seed.sequential_reading.progress" || stage === "sequential_reading") {
    if (payloadMessage) {
      const tone = status === "failed"
        ? "failed"
        : status === "completed" && event.event_type === "seed.sequential_reading.progress"
          ? "done"
          : status === "completed"
            ? "done"
            : "running";
      return {
        id: event.event_id || `seq-${event.sequence}`,
        tone: event.event_type === "seed.stage.completed" ? "done" : tone,
        message: payloadMessage,
        timeLabel: timeLabel || null,
      };
    }
  }

  if (event.event_type === "seed.stage.pending" && stageLabel) {
    return {
      id: event.event_id || `pending-${event.sequence}`,
      tone: "running",
      message: payloadMessage || tx(locale, `开始：${stageLabel}`, `Starting: ${stageLabel}`),
      timeLabel: timeLabel || null,
    };
  }
  if (event.event_type === "seed.stage.completed" && stageLabel) {
    return {
      id: event.event_id || `done-${event.sequence}`,
      tone: "done",
      message: payloadMessage || tx(locale, `完成：${stageLabel}`, `Completed: ${stageLabel}`),
      timeLabel: timeLabel || null,
    };
  }
  if (event.event_type === "seed.stage.failed" && stageLabel) {
    const errorCode = typeof event.payload?.error_code === "string" ? event.payload.error_code : "";
    const hint = errorCode ? publicSeedFailureHint(locale, errorCode) : "";
    return {
      id: event.event_id || `fail-${event.sequence}`,
      tone: "failed",
      message: payloadMessage
        || (hint
          ? tx(locale, `${stageLabel}失败：${hint}`, `${stageLabel} failed: ${hint}`)
          : tx(locale, `${stageLabel}失败`, `${stageLabel} failed`)),
      timeLabel: timeLabel || null,
    };
  }
  if (event.event_type === "workflow.queued") {
    return {
      id: event.event_id || `queued-${event.sequence}`,
      tone: "info",
      message: tx(locale, "任务已入队", "Run queued"),
      timeLabel: timeLabel || null,
    };
  }
  return null;
}

function publicSeedFailureHint(locale: Locale, code: string) {
  const analysisHint = publicAnalysisFailureHint(locale, code);
  if (analysisHint) return analysisHint;
  if (code === "LLM_QUOTA_RESERVATION_CLOSED") {
    return tx(
      locale,
      "上次调用的额度预留已关闭，请重试分析。若仍失败，检查模型通道是否可用。",
      "The previous quota reservation closed. Retry analysis; if it still fails, check that the model channel is reachable.",
    );
  }
  if (code === "LLM_PROVIDER_CALL_CONFLICT") {
    return tx(
      locale,
      "分析调用与上次预留冲突（常见于换模型后重试）。请再点一次重试；若仍失败，到模型设置测试连通性。",
      "This analysis call conflicted with a previous quota reservation (common after rebinding models). Retry once more; if it still fails, use Test model in settings.",
    );
  }
  if (code === "SCHEMA_VALIDATION_FAILED") {
    return tx(
      locale,
      "某一批顺序精读返回了无法解析的结果（模型未按 JSON 输出）。系统会自动重试/拆批；请再点重试。若反复失败，可在模型设置中换用更稳定的聊天模型。",
      "A sequential-reading batch returned unparsable output (not valid JSON). The system will auto-retry/split batches; retry the run. If it keeps failing, switch to a more stable chat model.",
    );
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
      <p className="form-hint">
        <Bi zh="更新时间：" en="Updated: " />
        {formatBeijingTimeLabel(locale, projectReadiness.updated_at)}
      </p>
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
              <td>{formatBeijingTime(locale, run.updated_at)}</td>
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
      <dd>{formatBeijingTimeLabel(locale, selectedSeedRun.updated_at)}</dd>
    </dl>
  );
}

function StatusLine({ status }: { status: ActionStatus | null }) {
  if (!status) {
    return null;
  }
  const isSuccess = status.status === "success";
  const className = isSuccess
    ? "form-status success-box overview-action-status"
    : "form-status error-box overview-action-status";
  return (
    <div
      className={className}
      data-tone={isSuccess ? "success" : "danger"}
      role={isSuccess ? "status" : "alert"}
    >
      {isSuccess ? (
        <p>{status.message || <Bi zh="操作已完成。" en="Action completed." />}</p>
      ) : (
        <>
          <p>
            <strong><Bi zh="未能完成" en="Could not finish" /></strong>
            {" "}
            {status.message || <Bi zh="请检查输入或稍后重试。" en="Check the input or try again." />}
          </p>
          {status.code === "LLM_MODULE_UNBOUND"
            || status.code === "LLM_MODULE_CAPABILITY_MISSING"
            || status.code === "LLM_CREDENTIAL_UNCONFIGURED" ? (
            <p className="overview-action-status-hint">
              <Bi zh="可到模型设置检查通道与绑定，或直接重试分析。" en="Check model settings, or retry analysis." />
            </p>
          ) : null}
        </>
      )}
    </div>
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
    analysis_run: ["智能分析", "Analysis"],
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

function overviewStatusTone(status: string) {
  const normalized = status.trim().toLowerCase();
  if (normalized === "failed" || normalized === "blocked" || normalized === "error") {
    return "danger";
  }
  if (normalized === "running" || normalized === "active" || normalized === "in_progress") {
    return "live";
  }
  if (normalized === "completed" || normalized === "ready" || normalized === "success") {
    return "success";
  }
  if (normalized === "queued" || normalized === "pending" || normalized === "cancelled" || normalized === "canceled") {
    return "warn";
  }
  return "muted";
}
