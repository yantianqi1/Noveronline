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
import { canCancelSeedRun, canRetrySeedRun } from "./overview-seed-run-controls";

type ActionStatus = {
  status: string;
  code: string;
  message: string;
};

type OverviewSeedShellProps = {
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
  uploadAndStartSeedAction: (formData: FormData) => Promise<void>;
  completeUploadAction: (formData: FormData) => Promise<void>;
  startSeedRunAction: (formData: FormData) => Promise<void>;
  cancelSeedRunAction: (formData: FormData) => Promise<void>;
  retrySeedRunAction: (formData: FormData) => Promise<void>;
};

export function OverviewSeedShell({
  tenantSlug,
  projectId,
  projectOverview,
  projectReadiness,
  sourceFiles,
  seedRuns,
  selectedRunId,
  afterEventId,
  selectedSeedRun,
  seedEvents,
  sourceStatus,
  seedStatus,
  uploadAndStartSeedAction,
  completeUploadAction,
  startSeedRunAction,
  cancelSeedRunAction,
  retrySeedRunAction,
}: OverviewSeedShellProps) {
  const cancelSeedRunEnabled = canCancelSeedRun(selectedSeedRun);
  const retrySeedRunEnabled = canRetrySeedRun(selectedSeedRun);

  return (
    <div>
      <header>
        <p className="eyebrow">Overview</p>
        <h1>Project Overview</h1>
        <p>
          Tenant <strong>{tenantSlug}</strong> / Project <strong>{projectId}</strong>
        </p>
        <div className="status-row">
          <span className="status-pill">Project status: {projectOverview.ok ? projectOverview.status : projectOverview.code}</span>
          <span className="status-pill">Source files: {projectOverview.ok ? projectOverview.source_file_count : sourceFiles.ok ? sourceFiles.items.length : sourceFiles.code}</span>
          <span className="status-pill">Seed runs: {projectOverview.ok ? projectOverview.seed_run_count : seedRuns.ok ? seedRuns.items.length : seedRuns.code}</span>
          <span className="status-pill">Active workflow: {projectOverview.ok ? activeWorkflowSummary(projectOverview) : "unavailable"}</span>
          <span className="status-pill">Selected run: {selectedRunId || "none"}</span>
          <span className="status-pill">Event cursor: {afterEventId || "beginning"}</span>
        </div>
      </header>

      <div className="workbench-grid" style={{ marginTop: 20 }}>
        <main>
          <section
            className={`panel ${projectOverview.ok ? "" : "error-box"}`}
            aria-labelledby="project-health-heading"
          >
            <p className="eyebrow">Project Health</p>
            <h2 id="project-health-heading">Project health</h2>
            <ProjectHealthPanel projectOverview={projectOverview} />
          </section>

          <section
            className={`panel ${projectReadiness.ok ? "" : "error-box"}`}
            aria-labelledby="project-readiness-heading"
          >
            <p className="eyebrow">Readiness</p>
            <h2 id="project-readiness-heading">Project readiness</h2>
            <ProjectReadinessPanel projectReadiness={projectReadiness} />
          </section>

          <section className={`panel ${sourceFiles.ok ? "" : "error-box"}`} aria-labelledby="source-files-heading">
            <p className="eyebrow">Source files</p>
            <h2 id="source-files-heading">Source files</h2>
            <SourceFilesTable
              completeUploadAction={completeUploadAction}
              sourceFiles={sourceFiles}
              startSeedRunAction={startSeedRunAction}
            />
          </section>

          <section className={`panel ${seedRuns.ok ? "" : "error-box"}`} aria-labelledby="seed-runs-heading">
            <p className="eyebrow">Seed pipeline</p>
            <h2 id="seed-runs-heading">Seed runs</h2>
            <SeedRunsTable seedRuns={seedRuns} tenantSlug={tenantSlug} projectId={projectId} />
          </section>

          <section
            className={`panel ${selectedSeedRun && !selectedSeedRun.ok ? "error-box" : ""}`}
            aria-labelledby="seed-run-detail-heading"
          >
            <p className="eyebrow">Seed pipeline</p>
            <h2 id="seed-run-detail-heading">Selected Seed run</h2>
            <SeedRunDetail selectedRunId={selectedRunId} selectedSeedRun={selectedSeedRun} />
          </section>

          <section
            className={`panel ${seedEvents && !seedEvents.ok ? "error-box" : ""}`}
            aria-labelledby="seed-events-heading"
          >
            <p className="eyebrow">Seed pipeline</p>
            <h2 id="seed-events-heading">Seed events</h2>
            <SeedEvents selectedRunId={selectedRunId} afterEventId={afterEventId} seedEvents={seedEvents} />
          </section>
        </main>

        <aside>
          <section className="panel" aria-labelledby="upload-and-start-seed-heading">
            <p className="eyebrow">Seed pipeline</p>
            <h2 id="upload-and-start-seed-heading">Upload and start Seed</h2>
            <StatusLine status={sourceStatus} />
            <StatusLine status={seedStatus} />
            <form action={uploadAndStartSeedAction} className="binding-form">
              <label htmlFor="source-file">Source file</label>
              <input
                accept=".txt,.md,.markdown,.pdf,text/plain,text/markdown,application/pdf"
                id="source-file"
                name="file"
                required
                type="file"
              />
              <label htmlFor="seed-mode">Mode</label>
              <select id="seed-mode" name="mode" defaultValue="full">
                <option value="full">Full</option>
                <option value="resume">Resume</option>
              </select>
              <button type="submit">Upload and start Seed</button>
            </form>
            <p className="form-hint">
              Files up to 64 MB are read server-side, checked, stored, completed, and admitted into Seed. Missing source backends remain explicit SOURCE_FILE_BACKEND_UNCONFIGURED errors.
            </p>
          </section>

          <section className="panel" aria-labelledby="control-seed-heading">
            <p className="eyebrow">Seed pipeline</p>
            <h2 id="control-seed-heading">Control Seed run</h2>
            <form
              action={overviewHref(tenantSlug, projectId)}
              className="binding-form"
              method="get"
            >
              <label htmlFor="inspect-seed-run-id">Inspect Seed run</label>
              <input id="inspect-seed-run-id" name="runId" defaultValue={selectedRunId} />
              <label htmlFor="inspect-seed-event-cursor">Event cursor</label>
              <input
                id="inspect-seed-event-cursor"
                name="after_event_id"
                defaultValue={afterEventId}
                placeholder="evt_..."
              />
              <button type="submit">Inspect Seed run</button>
            </form>
            <p className="form-hint">Selected run: {selectedRunId || "none"}</p>
            <div className="compact-action-list">
              <form action={cancelSeedRunAction} className="inline-action-form">
                <input type="hidden" name="runId" value={selectedRunId} />
                <span>Cancel Seed run</span>
                <button disabled={!cancelSeedRunEnabled} type="submit">Cancel Seed run</button>
              </form>
              <form action={retrySeedRunAction} className="inline-action-form">
                <input type="hidden" name="runId" value={selectedRunId} />
                <span>Retry Seed run</span>
                <button disabled={!retrySeedRunEnabled} type="submit">Retry Seed run</button>
              </form>
            </div>
            <p className="form-hint">
              Missing control backends remain explicit WORKFLOW_CANCEL_BACKEND_UNCONFIGURED or WORKFLOW_RETRY_BACKEND_UNCONFIGURED errors.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}

export function sourceFileActionStatus(result: SourceFileSummary): ActionStatus {
  if (!result.ok) {
    return {
      status: "error",
      code: result.code,
      message: result.message,
    };
  }
  return {
    status: "success",
    code: result.parse_status || "SOURCE_FILE_ADMITTED",
    message: "source file accepted",
  };
}

export function sourceFileObjectActionStatus(result: SourceFileObjectUploadSummary): ActionStatus {
  if (!result.ok) {
    return {
      status: "error",
      code: result.code,
      message: result.message,
    };
  }
  return {
    status: "success",
    code: result.status || "SOURCE_FILE_OBJECT_STORED",
    message: `upload ${result.upload_id} stored`,
  };
}

export function seedRunActionStatus(result: SeedRunStartSummary): ActionStatus & { runId: string } {
  if (!result.ok) {
    return {
      status: "error",
      code: result.code,
      message: result.message,
      runId: "",
    };
  }
  return {
    status: "success",
    code: result.status,
    message: `${result.workflow_type} accepted for ${result.project_id}`,
    runId: result.run_id,
  };
}

export function seedRunControlStatus(
  result: WorkflowControlSummary,
  action: "cancel" | "retry",
): ActionStatus & { runId: string } {
  if (!result.ok) {
    return {
      status: "error",
      code: result.code,
      message: result.message,
      runId: "",
    };
  }
  const verb = action === "cancel" ? "Cancellation" : "Retry";
  return {
    status: "success",
    code: result.status,
    message: `${verb} accepted for ${result.run_id}`,
    runId: result.run_id,
  };
}

function SourceFilesTable({
  completeUploadAction,
  sourceFiles,
  startSeedRunAction,
}: {
  completeUploadAction: (formData: FormData) => Promise<void>;
  sourceFiles: SourceFilesSummary;
  startSeedRunAction: (formData: FormData) => Promise<void>;
}) {
  if (!sourceFiles.ok) {
    return <p className="form-hint">{sourceFiles.code}: {sourceFiles.message}</p>;
  }
  if (sourceFiles.items.length === 0) {
    return <p className="form-hint">No source files have been admitted for this project.</p>;
  }
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Filename</th>
            <th>Upload</th>
            <th>Status</th>
            <th>Size</th>
            <th>Purpose</th>
            <th>Created</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {sourceFiles.items.map((file) => (
            <tr key={file.file_id}>
              <td>{file.filename}</td>
              <td>{file.upload_id}</td>
              <td>{file.parse_status}</td>
              <td>{file.size_bytes}</td>
              <td>{file.purpose}</td>
              <td>{file.created_at}</td>
              <td>
                <div className="compact-action-list">
                  <form action={completeUploadAction} className="inline-action-form">
                    <input type="hidden" name="uploadId" value={file.upload_id} />
                    <span>Complete upload</span>
                    <button disabled={file.parse_status !== "pending"} type="submit">
                      Complete
                    </button>
                  </form>
                  <form action={startSeedRunAction} className="inline-action-form">
                    <input type="hidden" name="uploadId" value={file.upload_id} />
                    <input type="hidden" name="mode" value="full" />
                    <span>Start Seed</span>
                    <button disabled={file.parse_status !== "uploaded"} type="submit">
                      Start
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

function ProjectHealthPanel({
  projectOverview,
}: {
  projectOverview: ProjectOverviewSummary;
}) {
  if (!projectOverview.ok) {
    return (
      <>
        <p className="form-hint">{projectOverview.code}: {projectOverview.message}</p>
        <p className="form-hint">Missing overview backend remains explicit PROJECT_OVERVIEW_BACKEND_UNCONFIGURED.</p>
      </>
    );
  }
  const metrics = [
    ["Source files", projectOverview.source_file_count],
    ["Seed runs", projectOverview.seed_run_count],
    ["Assets ready", projectOverview.ready_asset_count],
    ["Entities ready", projectOverview.ready_entity_count],
    ["Relationships ready", projectOverview.ready_relationship_count],
    ["World rules ready", projectOverview.ready_world_rule_count],
    ["Asset records", projectOverview.asset_count],
    ["Graph nodes", projectOverview.graph_node_count],
    ["Graph edges", projectOverview.graph_edge_count],
    ["Worldline sessions", projectOverview.worldline_session_count],
    ["Worldline events", projectOverview.worldline_event_count],
    ["Character interactions", projectOverview.character_interaction_count],
    ["Writer runs", projectOverview.writer_run_count],
    ["LLM calls", projectOverview.llm_activity_count],
    ["LLM tokens", projectOverview.llm_token_count],
    ["LLM enabled channels", projectOverview.llm_enabled_channel_count],
    ["LLM bound modules", projectOverview.llm_bound_module_count],
    ["LLM missing core modules", projectOverview.llm_missing_core_module_count],
    ["LLM sync ok channels", projectOverview.llm_sync_ok_channel_count],
    ["LLM sync failed channels", projectOverview.llm_sync_failed_channel_count],
    ["LLM sync pending channels", projectOverview.llm_sync_pending_channel_count],
  ];
  return (
    <>
      <div className="status-row" aria-label="Project health counts">
        <span className="status-pill">Status: {projectOverview.status}</span>
        {metrics.map(([label, value]) => (
          <span className="status-pill" key={label}>
            {label}: {value}
          </span>
        ))}
      </div>
      <dl>
        <dt>Project</dt>
        <dd>{projectOverview.project_id}</dd>
        <dt>Active workflow</dt>
        <dd>{activeWorkflowSummary(projectOverview)}</dd>
        <dt>Active workflow id</dt>
        <dd>{projectOverview.active_workflow_run_id || "none"}</dd>
        <dt>Active workflow type</dt>
        <dd>{projectOverview.active_workflow_type || "none"}</dd>
        <dt>Active workflow status</dt>
        <dd>{projectOverview.active_workflow_status || "none"}</dd>
        <dt>Latest failed workflow</dt>
        <dd>{failedWorkflowSummary(projectOverview)}</dd>
        <dt>Failure code</dt>
        <dd>{projectOverview.latest_failed_workflow_error_code || "none"}</dd>
        <dt>Failure updated</dt>
        <dd>{projectOverview.latest_failed_workflow_updated_at || "none"}</dd>
        <dt>LLM latest sync</dt>
        <dd>{projectOverview.llm_latest_sync_at || "none"}</dd>
        <dt>Readiness snapshot</dt>
        <dd>{projectOverview.readiness_snapshot_id || "none"}</dd>
        <dt>Readiness run</dt>
        <dd>{projectOverview.readiness_run_id || "none"}</dd>
        <dt>Updated</dt>
        <dd>{projectOverview.updated_at || "none"}</dd>
      </dl>
    </>
  );
}

function ProjectReadinessPanel({
  projectReadiness,
}: {
  projectReadiness: ProjectReadinessSummary;
}) {
  if (!projectReadiness.ok) {
    return (
      <>
        <p className="form-hint">{projectReadiness.code}: {projectReadiness.message}</p>
        <p className="form-hint">Missing readiness backend remains explicit PROJECT_READINESS_BACKEND_UNCONFIGURED.</p>
      </>
    );
  }
  const metrics = [
    ["Assets", projectReadiness.ready_asset_count],
    ["Entities", projectReadiness.ready_entity_count],
    ["Relationships", projectReadiness.ready_relationship_count],
    ["World rules", projectReadiness.ready_world_rule_count],
  ];
  return (
    <>
      <div className="status-row" aria-label="Project readiness counts">
        {metrics.map(([label, value]) => (
          <span className="status-pill" key={label}>
            {label}: {value}
          </span>
        ))}
      </div>
      <dl>
        <dt>Snapshot</dt>
        <dd>{projectReadiness.project_readiness_snapshot_id}</dd>
        <dt>Run</dt>
        <dd>{projectReadiness.run_id}</dd>
        <dt>Updated</dt>
        <dd>{projectReadiness.updated_at}</dd>
      </dl>
    </>
  );
}

function SeedRunsTable({
  seedRuns,
  tenantSlug,
  projectId,
}: {
  seedRuns: SeedRunsSummary;
  tenantSlug: string;
  projectId: string;
}) {
  if (!seedRuns.ok) {
    return <p className="form-hint">{seedRuns.code}: {seedRuns.message}</p>;
  }
  if (seedRuns.items.length === 0) {
    return <p className="form-hint">No Seed runs have been queued for this project.</p>;
  }
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Run</th>
            <th>Status</th>
            <th>Progress</th>
            <th>Message</th>
            <th>Updated</th>
            <th>Inspect</th>
          </tr>
        </thead>
        <tbody>
          {seedRuns.items.map((run, index) => run.ok ? (
            <tr key={run.run_id}>
              <td>{run.run_id}</td>
              <td>{run.status}</td>
              <td>{run.progress}</td>
              <td>{run.message || run.error_message || "-"}</td>
              <td>{run.updated_at}</td>
              <td><a href={overviewHref(tenantSlug, projectId, run.run_id)}>Inspect</a></td>
            </tr>
          ) : (
            <tr key={`${run.code}-${index}`}>
              <td>{run.code}</td>
              <td>error</td>
              <td>0</td>
              <td>{run.message}</td>
              <td>{run.request_id}</td>
              <td>-</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SeedRunDetail({
  selectedRunId,
  selectedSeedRun,
}: {
  selectedRunId: string;
  selectedSeedRun: WorkflowRunSummary | null;
}) {
  if (!selectedRunId) {
    return <p className="form-hint">No Seed run selected.</p>;
  }
  if (!selectedSeedRun) {
    return <p className="form-hint">Seed run detail has not been loaded.</p>;
  }
  if (!selectedSeedRun.ok) {
    return <p className="form-hint">{selectedSeedRun.code}: {selectedSeedRun.message}</p>;
  }
  return (
    <dl>
      <dt>Run</dt>
      <dd>{selectedSeedRun.run_id}</dd>
      <dt>Status</dt>
      <dd>{selectedSeedRun.status}</dd>
      <dt>Progress</dt>
      <dd>{selectedSeedRun.progress}</dd>
      <dt>Message</dt>
      <dd>{selectedSeedRun.message || selectedSeedRun.error_message || "-"}</dd>
      <dt>Updated</dt>
      <dd>{selectedSeedRun.updated_at}</dd>
    </dl>
  );
}

function SeedEvents({
  selectedRunId,
  afterEventId,
  seedEvents,
}: {
  selectedRunId: string;
  afterEventId: string;
  seedEvents: WorkflowRunEventsSummary | null;
}) {
  if (!selectedRunId) {
    return <p className="form-hint">Select or start a Seed run to inspect events.</p>;
  }
  if (!seedEvents) {
    return <p className="form-hint">Seed event replay has not been loaded.</p>;
  }
  if (!seedEvents.ok) {
    return <p className="form-hint">{seedEvents.code}: {seedEvents.message}</p>;
  }
  if (seedEvents.items.length === 0) {
    return <p className="form-hint">No Seed events after the current cursor.</p>;
  }
  return (
    <>
      <p className="form-hint">Event cursor: {afterEventId || "beginning"}</p>
      <div className="trace-list">
        {seedEvents.items.map((event) => (
          <article className="trace-event" key={event.event_id}>
            <div className="trace-event-header">
              <strong>{event.event_type}</strong>
              <span className="trace-redaction">seq {event.sequence}</span>
            </div>
            <p className="trace-meta">{event.created_at}</p>
            <pre>{JSON.stringify(event.payload, null, 2)}</pre>
          </article>
        ))}
      </div>
    </>
  );
}

function StatusLine({ status }: { status: ActionStatus | null }) {
  if (!status) {
    return null;
  }
  const className = status.status === "success" ? "form-status success-box" : "form-status error-box";
  return (
    <p className={className}>
      {status.code}: {status.message}
    </p>
  );
}

function activeWorkflowSummary(projectOverview: ProjectOverviewSummary) {
  if (!projectOverview.ok || !projectOverview.active_workflow_run_id) {
    return "none";
  }
  const workflowType = projectOverview.active_workflow_type || "workflow";
  const workflowStatus = projectOverview.active_workflow_status || "unknown";
  return `${workflowType} / ${workflowStatus} / ${projectOverview.active_workflow_run_id}`;
}

function failedWorkflowSummary(projectOverview: ProjectOverviewSummary) {
  if (!projectOverview.ok || !projectOverview.latest_failed_workflow_run_id) {
    return "none";
  }
  const workflowType = projectOverview.latest_failed_workflow_type || "workflow";
  return `${workflowType} / ${projectOverview.latest_failed_workflow_run_id}`;
}

function overviewHref(tenantSlug: string, projectId: string, runId = "") {
  const query = new URLSearchParams();
  if (runId) {
    query.set("runId", runId);
  }
  const suffix = query.toString();
  return `/${tenantSlug}/projects/${projectId}/overview${suffix ? `?${suffix}` : ""}`;
}
