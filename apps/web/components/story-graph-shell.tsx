import type {
  AssetListSummary,
  StoryGraphBondGenerationSummary,
  StoryGraphBuildSummary,
  StoryGraphClustersSummary,
  StoryGraphCurrentSummary,
  StoryGraphEvidenceSummary,
  StoryGraphLayoutSummary,
  StoryGraphViewSummary,
  WorkflowRunEventsSummary,
  WorkflowRunSummary,
} from "../lib/api";

type StoryGraphShellProps = {
  tenantSlug: string;
  projectId: string;
  buildStatus: string;
  buildCode: string;
  buildMessage: string;
  bondStatus: string;
  bondCode: string;
  bondMessage: string;
  adoptionStatus: string;
  adoptionCode: string;
  adoptionMessage: string;
  adoptionTargetId: string;
  selectedRunId: string;
  selectedBuildRunId: string;
  selectedBondRunId: string;
  current: StoryGraphCurrentSummary;
  view: StoryGraphViewSummary;
  evidence: StoryGraphEvidenceSummary;
  layout: StoryGraphLayoutSummary;
  clusters: StoryGraphClustersSummary;
  graphCandidates: AssetListSummary;
  workflowRun: WorkflowRunSummary | null;
  workflowEvents: WorkflowRunEventsSummary | null;
  buildAction: (formData: FormData) => Promise<void>;
  bondAction: (formData: FormData) => Promise<void>;
  adoptStoryGraphCandidateAction: (formData: FormData) => Promise<void>;
};

export function StoryGraphShell({
  tenantSlug,
  projectId,
  buildStatus,
  buildCode,
  buildMessage,
  bondStatus,
  bondCode,
  bondMessage,
  adoptionStatus,
  adoptionCode,
  adoptionMessage,
  adoptionTargetId,
  selectedRunId,
  selectedBuildRunId,
  selectedBondRunId,
  current,
  view,
  evidence,
  layout,
  clusters,
  graphCandidates,
  workflowRun,
  workflowEvents,
  buildAction,
  bondAction,
  adoptStoryGraphCandidateAction,
}: StoryGraphShellProps) {
  return (
    <div>
      <header>
        <p className="eyebrow">Story Graph</p>
        <h1>Story Graph</h1>
        <p>
          Tenant <strong>{tenantSlug}</strong> / Project <strong>{projectId}</strong>
        </p>
        <div className="status-row">
          <span className="status-pill">Snapshot: {current.ok ? current.status : current.code}</span>
          <span className="status-pill">Build: {buildStatus || "idle"}</span>
          <span className="status-pill">Bond: {bondStatus || "idle"}</span>
        </div>
      </header>

      <div className="workbench-grid" style={{ marginTop: 20 }}>
        <main>
          <section className={`panel ${current.ok ? "" : "error-box"}`} aria-labelledby="graph-current-heading">
            <p className="eyebrow">Current Snapshot</p>
            <h2 id="graph-current-heading">Graph snapshot</h2>
            <CurrentSnapshot current={current} />
          </section>

          <section className="panel" aria-labelledby="graph-canvas-heading">
            <p className="eyebrow">Explore</p>
            <h2 id="graph-canvas-heading">Graph canvas</h2>
            <div className="graph-canvas-skeleton" aria-label="Story graph snapshot canvas">
              <div className="graph-node primary-node">Nodes {current.ok ? current.node_count : 0}</div>
              <div className="graph-edge-line" />
              <div className="graph-node accent-node">Edges {current.ok ? current.edge_count : 0}</div>
            </div>
          </section>

          <section className={`panel ${view.ok ? "" : "error-box"}`} aria-labelledby="graph-view-heading">
            <p className="eyebrow">Viewport</p>
            <h2 id="graph-view-heading">World view</h2>
            <GraphViewport view={view} />
          </section>

          <section className={`panel ${evidence.ok ? "" : "error-box"}`} aria-labelledby="graph-evidence-heading">
            <p className="eyebrow">Evidence</p>
            <h2 id="graph-evidence-heading">Public evidence</h2>
            <GraphEvidence evidence={evidence} />
          </section>
        </main>

        <aside>
          <section className={`panel ${layout.ok ? "" : "error-box"}`} aria-labelledby="graph-layout-heading">
            <p className="eyebrow">Layout</p>
            <h2 id="graph-layout-heading">World layout</h2>
            <GraphLayoutSummary layout={layout} />
          </section>

          <section className={`panel ${clusters.ok ? "" : "error-box"}`} aria-labelledby="graph-clusters-heading">
            <p className="eyebrow">Clusters</p>
            <h2 id="graph-clusters-heading">Graph clusters</h2>
            <GraphClusters clusters={clusters} />
          </section>

          <section className="panel" aria-labelledby="graph-build-heading">
            <p className="eyebrow">Build Mode</p>
            <h2 id="graph-build-heading">Start build</h2>
            <StatusLine status={buildStatus} code={buildCode} message={buildMessage} />
            <form action={buildAction} className="binding-form">
              <label htmlFor="graph-build-mode">Mode</label>
              <select id="graph-build-mode" name="mode" defaultValue="full">
                <option value="full">Full</option>
                <option value="incremental">Incremental</option>
              </select>
              <label htmlFor="graph-build-source">Source</label>
              <select id="graph-build-source" name="source" defaultValue="seed_canon">
                <option value="seed_canon">Seed canon</option>
                <option value="assets">Assets</option>
              </select>
              <button type="submit">Build</button>
            </form>
          </section>

          <section className="panel" aria-labelledby="graph-compose-heading">
            <p className="eyebrow">Compose Mode</p>
            <h2 id="graph-compose-heading">Generate bonds</h2>
            <StatusLine status={bondStatus} code={bondCode} message={bondMessage} />
            <form action={bondAction} className="binding-form">
              <input type="hidden" name="graphId" value={current.ok ? current.graph_id : ""} />
              <label htmlFor="graph-bond-node-ids">Node IDs</label>
              <textarea
                id="graph-bond-node-ids"
                name="nodeIds"
                defaultValue={defaultBondNodeIds(view)}
                rows={3}
              />
              <label htmlFor="graph-bond-focus">Focus</label>
              <textarea
                id="graph-bond-focus"
                name="focus"
                defaultValue="relationship tension or unresolved plot thread"
                rows={3}
              />
              <label htmlFor="graph-bond-mode">Mode</label>
              <select id="graph-bond-mode" name="mode" defaultValue="bonds_and_threads">
                <option value="bonds_and_threads">Bonds and threads</option>
                <option value="bonds">Bonds only</option>
                <option value="threads">Threads only</option>
              </select>
              <button type="submit">Generate bonds</button>
            </form>
            <p className="form-hint">
              Latest bond run: {selectedBondRunId || "none"}; build run: {selectedBuildRunId || "none"}
            </p>
          </section>

          <section
            className={`panel ${graphCandidates.ok ? "" : "error-box"}`}
            aria-labelledby="graph-candidate-adoption-heading"
          >
            <p className="eyebrow">Candidate adoption</p>
            <h2 id="graph-candidate-adoption-heading">Graph candidates</h2>
            <StatusLine status={adoptionStatus} code={adoptionCode} message={adoptionMessage} />
            {adoptionTargetId ? <p className="form-hint">Adopted target: {adoptionTargetId}</p> : null}
            <GraphCandidates
              graphCandidates={graphCandidates}
              adoptStoryGraphCandidateAction={adoptStoryGraphCandidateAction}
            />
          </section>

          <section
            className={`panel ${workflowRun && !workflowRun.ok ? "error-box" : ""}`}
            aria-labelledby="graph-build-progress-heading"
          >
            <p className="eyebrow">Build Mode</p>
            <h2 id="graph-build-progress-heading">Build progress</h2>
            <WorkflowProgress selectedBuildRunId={selectedRunId} workflowRun={workflowRun} />
          </section>

          <section
            className={`panel ${workflowEvents && !workflowEvents.ok ? "error-box" : ""}`}
            aria-labelledby="graph-build-events-heading"
          >
            <p className="eyebrow">Build Mode</p>
            <h2 id="graph-build-events-heading">Workflow events</h2>
            <WorkflowEvents selectedBuildRunId={selectedRunId} workflowEvents={workflowEvents} />
          </section>
        </aside>
      </div>
    </div>
  );
}

function GraphCandidates({
  graphCandidates,
  adoptStoryGraphCandidateAction,
}: {
  graphCandidates: AssetListSummary;
  adoptStoryGraphCandidateAction: (formData: FormData) => Promise<void>;
}) {
  if (!graphCandidates.ok) {
    return <p className="form-hint">{graphCandidates.code}: {graphCandidates.message}</p>;
  }
  if (graphCandidates.items.length === 0) {
    return <p className="form-hint">No graph candidates awaiting adoption</p>;
  }
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Candidate</th>
            <th>Type</th>
            <th>Source</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {graphCandidates.items.map((candidate) => (
            <tr key={candidate.asset_id}>
              <td>
                <strong>{candidate.title || candidate.asset_id}</strong>
                <br />
                <span className="form-hint">{candidate.summary || candidate.asset_id}</span>
              </td>
              <td>{candidate.asset_type}</td>
              <td>{candidate.source_ref || "graph bond generation"}</td>
              <td>
                <form action={adoptStoryGraphCandidateAction} className="inline-action-form">
                  <input type="hidden" name="assetId" value={candidate.asset_id} />
                  <button type="submit" name="targetKind" value="relationship">Adopt relationship</button>
                  <button type="submit" name="targetKind" value="plot_thread">Adopt plot thread</button>
                </form>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function defaultBondNodeIds(view: StoryGraphViewSummary) {
  if (!view.ok) {
    return "";
  }
  return view.nodes.slice(0, 2).map((node) => node.node_id).join("\n");
}

function GraphViewport({ view }: { view: StoryGraphViewSummary }) {
  if (!view.ok) {
    return <p className="form-hint">{view.code}: {view.message}</p>;
  }
  return (
    <div className="binding-stack">
      <p className="form-hint">
        {view.nodes.length} nodes / {view.edges.length} edges from {view.graph_id}
      </p>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Node</th>
              <th>Type</th>
              <th>Lifecycle</th>
              <th>Evidence</th>
            </tr>
          </thead>
          <tbody>
            {view.nodes.map((node) => (
              <tr key={node.node_id}>
                <td>{node.title || node.node_id}</td>
                <td>{node.node_type}</td>
                <td>{node.lifecycle}</td>
                <td>{node.evidence_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Edge</th>
              <th>Type</th>
              <th>From</th>
              <th>To</th>
            </tr>
          </thead>
          <tbody>
            {view.edges.map((edge) => (
              <tr key={edge.edge_id}>
                <td>{edge.label || edge.edge_id}</td>
                <td>{edge.edge_type}</td>
                <td>{edge.source_node_id}</td>
                <td>{edge.target_node_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function GraphEvidence({ evidence }: { evidence: StoryGraphEvidenceSummary }) {
  if (!evidence.ok) {
    return <p className="form-hint">{evidence.code}: {evidence.message}</p>;
  }
  return (
    <div className="binding-stack">
      <p className="form-hint">
        {evidence.items.length} public evidence records for {evidence.owner_type} {evidence.owner_id}
      </p>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Source</th>
              <th>Reference</th>
              <th>Chapter</th>
              <th>Confidence</th>
            </tr>
          </thead>
          <tbody>
            {evidence.items.map((item) => (
              <tr key={item.evidence_id}>
                <td>{item.source_type}</td>
                <td>{item.source_id}</td>
                <td>{item.chapter_id || "none"}</td>
                <td>{item.confidence}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function GraphLayoutSummary({ layout }: { layout: StoryGraphLayoutSummary }) {
  if (!layout.ok) {
    return <p className="form-hint">{layout.code}: {layout.message}</p>;
  }
  const keys = Object.keys(layout.layout);
  return (
    <dl>
      <dt>View</dt>
      <dd>{layout.view_id}</dd>
      <dt>Keys</dt>
      <dd>{keys.length ? keys.join(", ") : "none"}</dd>
      <dt>Updated</dt>
      <dd>{layout.updated_at}</dd>
    </dl>
  );
}

function GraphClusters({ clusters }: { clusters: StoryGraphClustersSummary }) {
  if (!clusters.ok) {
    return <p className="form-hint">{clusters.code}: {clusters.message}</p>;
  }
  return (
    <div className="binding-stack">
      <p className="form-hint">{clusters.items.length} clusters from {clusters.graph_id}</p>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th>Cluster</th>
              <th>Nodes</th>
            </tr>
          </thead>
          <tbody>
            {clusters.items.map((cluster) => (
              <tr key={cluster.cluster_id}>
                <td>{cluster.title || cluster.cluster_key}</td>
                <td>{cluster.node_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CurrentSnapshot({ current }: { current: StoryGraphCurrentSummary }) {
  if (!current.ok) {
    return <p className="form-hint">{current.code}: {current.message}</p>;
  }

  return (
    <dl>
      <dt>Graph</dt>
      <dd>{current.graph_id}</dd>
      <dt>Version</dt>
      <dd>{current.version}</dd>
      <dt>Status</dt>
      <dd>{current.status}</dd>
      <dt>Build run</dt>
      <dd>{current.build_run_id || "none"}</dd>
      <dt>Source hash</dt>
      <dd>{current.source_version_hash || "none"}</dd>
      <dt>Nodes</dt>
      <dd>{current.node_count}</dd>
      <dt>Edges</dt>
      <dd>{current.edge_count}</dd>
      <dt>Updated</dt>
      <dd>{current.updated_at}</dd>
    </dl>
  );
}

function WorkflowProgress({
  selectedBuildRunId,
  workflowRun,
}: {
  selectedBuildRunId: string;
  workflowRun: WorkflowRunSummary | null;
}) {
  if (!selectedBuildRunId) {
    return <p className="form-hint">No build run selected</p>;
  }
  if (!workflowRun) {
    return <p className="form-hint">No build run selected</p>;
  }
  if (!workflowRun.ok) {
    return <p className="form-hint">{workflowRun.code}: {workflowRun.message}</p>;
  }
  return (
    <dl>
      <dt>Run</dt>
      <dd>{workflowRun.run_id}</dd>
      <dt>Type</dt>
      <dd>{workflowRun.workflow_type}</dd>
      <dt>Status</dt>
      <dd>{workflowRun.status}</dd>
      <dt>Progress</dt>
      <dd>{workflowRun.progress}%</dd>
      <dt>Message</dt>
      <dd>{workflowRun.message || "none"}</dd>
      <dt>Error</dt>
      <dd>{workflowRun.error_code || "none"} {workflowRun.error_message || ""}</dd>
      <dt>Updated</dt>
      <dd>{workflowRun.updated_at}</dd>
    </dl>
  );
}

function WorkflowEvents({
  selectedBuildRunId,
  workflowEvents,
}: {
  selectedBuildRunId: string;
  workflowEvents: WorkflowRunEventsSummary | null;
}) {
  if (!selectedBuildRunId) {
    return <p className="form-hint">No build run selected</p>;
  }
  if (!workflowEvents) {
    return <p className="form-hint">No build run selected</p>;
  }
  if (!workflowEvents.ok) {
    return <p className="form-hint">{workflowEvents.code}: {workflowEvents.message}</p>;
  }
  if (workflowEvents.items.length === 0) {
    return <p className="form-hint">No workflow events recorded for {workflowEvents.run_id}</p>;
  }
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th>Sequence</th>
            <th>Event</th>
            <th>Payload</th>
            <th>Created</th>
          </tr>
        </thead>
        <tbody>
          {workflowEvents.items.map((event) => (
            <tr key={event.event_id}>
              <td>{event.sequence}</td>
              <td>{event.event_type}</td>
              <td>{payloadKeys(event.payload)}</td>
              <td>{event.created_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function payloadKeys(payload: Record<string, unknown>) {
  const keys = Object.keys(payload);
  return keys.length ? keys.join(", ") : "none";
}

function StatusLine({ status, code, message }: { status: string; code: string; message: string }) {
  if (!status) {
    return null;
  }
  return (
    <p className={`form-status ${status === "success" ? "success-box" : "error-box"}`}>
      {code}: {message}
    </p>
  );
}

export function storyGraphBuildStatus(result: StoryGraphBuildSummary) {
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
    code: "STORY_GRAPH_BUILD_QUEUED",
    message: `${result.workflow_type} ${result.run_id} ${result.status}`,
    runId: result.run_id,
  };
}

export function storyGraphBondStatus(result: StoryGraphBondGenerationSummary) {
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
    code: "STORY_GRAPH_BOND_QUEUED",
    message: `${result.workflow_type} ${result.run_id} ${result.status}`,
    runId: result.run_id,
  };
}
