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

type WriterWorkbenchShellProps = {
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
  writerRunStatus: ActionStatus | null;
  traceExportStatus: TraceExportStatus | null;
  writerRunAction?: (formData: FormData) => Promise<void>;
  exportTraceAction?: (formData: FormData) => Promise<void>;
};

type ActionStatus = {
  status: string;
  code: string;
  message: string;
};

type TraceExportStatus = ActionStatus;

export function WriterWorkbenchShell({
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
  writerRunStatus,
  traceExportStatus,
  writerRunAction,
  exportTraceAction,
}: WriterWorkbenchShellProps) {
  const statusLabel =
    runSummary?.ok === true ? runSummary.status : runSummary?.ok === false ? "error" : "idle";
  const traceId = runSummary?.ok === true ? runSummary.trace_id : "";

  return (
    <div>
      <header>
        <p className="eyebrow">Writer Run</p>
        <h1>Writer Workbench</h1>
        <p>
          Tenant <strong>{tenantSlug}</strong> / Project <strong>{projectId}</strong>
        </p>
        <span className="status-pill">Status: {statusLabel}</span>
      </header>

      <div className="workbench-grid" style={{ marginTop: 20 }}>
        <main>
          <section className="panel" aria-labelledby="writer-command-heading">
            <p className="eyebrow">Command Row</p>
            <h2 id="writer-command-heading">Start writer run</h2>
            {writerRunStatus ? (
              <StatusLine status={writerRunStatus} />
            ) : null}
            {writerRunAction ? (
              <form action={writerRunAction} className="binding-form">
                <label htmlFor="writer-mode">Mode</label>
                <select id="writer-mode" name="mode" defaultValue="draft">
                  <option value="draft">Draft</option>
                  <option value="continue">Continue</option>
                  <option value="outline">Outline</option>
                  <option value="review">Review</option>
                </select>
                <label htmlFor="writer-instruction">Instruction</label>
                <textarea
                  id="writer-instruction"
                  name="instruction"
                  placeholder="Describe the next scene or revision target"
                  required
                  rows={4}
                />
                <ContextPickers
                  assets={assets}
                  graphView={graphView}
                  worldlineSavedPaths={worldlineSavedPaths}
                />
                <button type="submit">Start writer run</button>
              </form>
            ) : (
              <p className="form-hint">Writer run start action is not configured.</p>
            )}
          </section>

          <section
            className={`panel ${manuscript.ok ? "" : "error-box"}`}
            aria-labelledby="manuscript-metadata-heading"
          >
            <p className="eyebrow">Manuscript</p>
            <h2 id="manuscript-metadata-heading">Manuscript metadata</h2>
            <ManuscriptMetadataPanel manuscript={manuscript} />
          </section>

          <section
            className={`panel ${manuscriptExportManifest.ok ? "" : "error-box"}`}
            aria-labelledby="manuscript-export-heading"
          >
            <p className="eyebrow">Manifest</p>
            <h2 id="manuscript-export-heading">Export manifest</h2>
            <ManuscriptExportManifestPanel manifest={manuscriptExportManifest} />
          </section>

          <section className="panel" aria-labelledby="draft-heading">
            <p className="eyebrow">Draft</p>
            <h2 id="draft-heading">Candidate draft</h2>
            {runSummary?.ok === true ? (
              <p>
                Run <strong>{runSummary.run_id}</strong> is currently{" "}
                <strong>{runSummary.status}</strong>.
              </p>
            ) : (
              <p>No writer run selected. Start a run from the command row or open a run link.</p>
            )}
          </section>
        </main>

        <aside>
          <section
            className={`panel ${runSummary?.ok === false ? "error-box" : ""}`}
            aria-labelledby="trace-heading"
          >
            <p className="eyebrow">Trace</p>
            <h2 id="trace-heading">Run context</h2>
            {runSummary?.ok === false ? (
              <p>
                API error {runSummary.code}: {runSummary.message}
              </p>
            ) : (
              <dl>
                <dt>Tenant</dt>
                <dd>{tenantSlug}</dd>
                <dt>Project</dt>
                <dd>{projectId}</dd>
                <dt>Run</dt>
                <dd>{runSummary?.ok === true ? runSummary.run_id : "not selected"}</dd>
                <dt>Trace</dt>
                <dd>{traceId || "not selected"}</dd>
              </dl>
            )}
            {traceExportStatus ? (
              <p className={traceExportStatus.status === "error" ? "form-status error-box" : "form-status"}>
                {traceExportStatus.code}: {traceExportStatus.message}
              </p>
            ) : null}
            {traceId && exportTraceAction ? (
              <form action={exportTraceAction} className="inline-action-form">
                <input name="traceId" type="hidden" value={traceId} />
                <button type="submit">Export redacted trace</button>
              </form>
            ) : null}
          </section>

          <section
            className={`panel ${workflowEvents?.ok === false ? "error-box" : ""}`}
            aria-labelledby="tool-results-heading"
          >
            <p className="eyebrow">Tool Results</p>
            <h2 id="tool-results-heading">Tool result cards</h2>
            <ToolResultCards workflowEvents={workflowEvents} />
          </section>

          <section
            className={`panel ${workflowEvents?.ok === false ? "error-box" : ""}`}
            aria-labelledby="workflow-events-heading"
          >
            <p className="eyebrow">Writer Events</p>
            <h2 id="workflow-events-heading">Recovered stream</h2>
            <WriterEvents workflowEvents={workflowEvents} />
          </section>

          <section
            className={`panel ${traceEvents?.ok === false ? "error-box" : ""}`}
            aria-labelledby="trace-events-heading"
          >
            <p className="eyebrow">Trace Events</p>
            <h2 id="trace-events-heading">Event stream</h2>
            <TraceEvents traceEvents={traceEvents} />
          </section>
        </aside>
      </div>
    </div>
  );
}

function ManuscriptMetadataPanel({ manuscript }: { manuscript: ProjectManuscriptSummary }) {
  if (!manuscript.ok) {
    return <p>{apiErrorLine(manuscript, "MANUSCRIPT_BACKEND_UNCONFIGURED")}</p>;
  }

  if (manuscript.blocks.length === 0) {
    return <p className="form-hint">No manuscript metadata blocks returned.</p>;
  }

  return (
    <div>
      <dl>
        <dt>Project</dt>
        <dd>{manuscript.project_id}</dd>
        <dt>Blocks</dt>
        <dd>{manuscript.blocks.length}</dd>
      </dl>
      <div className="compact-action-list">
        {manuscript.blocks.slice(0, 8).map((block) => (
          <article className="tool-result-item" key={block.block_id}>
            <strong>{block.block_id}</strong>
            <span>
              Chapter {block.chapter_id || "unassigned"} / order {block.block_order}
            </span>
            <small>
              Source draft {block.source_draft_id || "not linked"} / {block.status || "unknown"} / words{" "}
              {block.word_count}
            </small>
            <small>
              Created {block.created_at || "unknown"} / Updated {block.updated_at || "unknown"}
            </small>
          </article>
        ))}
      </div>
    </div>
  );
}

function ManuscriptExportManifestPanel({
  manifest,
}: {
  manifest: ProjectManuscriptExportManifestSummary;
}) {
  if (!manifest.ok) {
    return <p>{apiErrorLine(manifest, "MANUSCRIPT_EXPORT_BACKEND_UNCONFIGURED")}</p>;
  }

  return (
    <div>
      <dl>
        <dt>Project</dt>
        <dd>{manifest.project_id}</dd>
        <dt>Format</dt>
        <dd>{manifest.format || "unknown"}</dd>
        <dt>Status</dt>
        <dd>{manifest.status || "unknown"}</dd>
        <dt>Blocks</dt>
        <dd>{manifest.block_count}</dd>
        <dt>Total words</dt>
        <dd>{manifest.total_word_count}</dd>
        <dt>Generated</dt>
        <dd>{manifest.generated_at || "not generated"}</dd>
      </dl>
      {manifest.blocks.length === 0 ? (
        <p className="form-hint">No manifest block metadata returned.</p>
      ) : (
        <div className="compact-action-list">
          {manifest.blocks.slice(0, 8).map((manifestBlock) => (
            <article className="tool-result-item" key={`${manifestBlock.block_id}-${manifestBlock.block_order}`}>
              <strong>{manifestBlock.block_id}</strong>
              <span>Order {manifestBlock.block_order}</span>
              <small>Words {manifestBlock.word_count}</small>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

function ContextPickers({
  assets,
  graphView,
  worldlineSavedPaths,
}: {
  assets: AssetListSummary;
  graphView: StoryGraphViewSummary;
  worldlineSavedPaths: WorldlineSavedPathsSummary;
}) {
  return (
    <section className="reference-picker" aria-labelledby="context-picker-heading">
      <p className="eyebrow">Context pickers</p>
      <h3 id="context-picker-heading">Explicit references</h3>
      <div className="reference-grid">
        <ReferenceAssets assets={assets} />
        <ReferenceGraphNodes graphView={graphView} />
        <ReferenceWorldlinePaths worldlineSavedPaths={worldlineSavedPaths} />
      </div>
    </section>
  );
}

function ReferenceAssets({ assets }: { assets: AssetListSummary }) {
  if (!assets.ok) {
    return (
      <div className="reference-card error-box">
        <strong>Project assets</strong>
        <p className="form-hint">{assets.code}: {assets.message}</p>
      </div>
    );
  }

  return (
    <div className="reference-card">
      <strong>Project assets</strong>
      {assets.items.length === 0 ? (
        <p className="form-hint">No selectable assets returned.</p>
      ) : (
        <div className="compact-action-list">
          {assets.items.slice(0, 8).map((asset) => (
            <label className="checkbox-row" key={asset.asset_id}>
              <input name="selectedAssetIds" type="checkbox" value={asset.asset_id} />
              <span>
                {asset.title || asset.asset_id}
                <small>{asset.asset_type} / {asset.lifecycle}</small>
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
        <strong>Graph nodes</strong>
        <p className="form-hint">{graphView.code}: {graphView.message}</p>
      </div>
    );
  }

  return (
    <div className="reference-card">
      <strong>Graph nodes</strong>
      {graphView.nodes.length === 0 ? (
        <p className="form-hint">No selectable graph nodes returned.</p>
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
                <small>{node.node_type} / evidence {node.evidence_count}</small>
              </span>
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

function ReferenceWorldlinePaths({
  worldlineSavedPaths,
}: {
  worldlineSavedPaths: WorldlineSavedPathsSummary;
}) {
  return (
    <div className={`reference-card ${worldlineSavedPaths.ok ? "" : "error-box"}`}>
      <strong>Worldline paths</strong>
      {!worldlineSavedPaths.ok ? (
        <p className="form-hint">{worldlineSavedPaths.code}: {worldlineSavedPaths.message}</p>
      ) : worldlineSavedPaths.items.length === 0 ? (
        <p className="form-hint">No selectable saved paths returned.</p>
      ) : (
        <div className="compact-action-list">
          {worldlineSavedPaths.items.slice(0, 8).map((path) => (
            <label className="checkbox-row" key={path.path_id}>
              <input name="worldlinePathIds" type="checkbox" value={path.path_id} />
              <span>
                {path.title || path.path_id}
                <small>
                  {path.lifecycle || "saved"} / events {path.selected_event_ids.length}
                </small>
                {path.summary || path.writer_instruction ? (
                  <small>{path.summary || path.writer_instruction}</small>
                ) : null}
              </span>
            </label>
          ))}
        </div>
      )}
      <label className="form-hint" htmlFor="worldline-path-ids">
        Manual saved path IDs
      </label>
      <textarea
        id="worldline-path-ids"
        name="worldlinePathIds"
        placeholder="path_1, path_2"
        rows={4}
      />
    </div>
  );
}

function StatusLine({ status }: { status: ActionStatus }) {
  return (
    <p className={status.status === "error" ? "form-status error-box" : "form-status success-box"}>
      {status.code}: {status.message}
    </p>
  );
}

function apiErrorLine(status: { code: string; message: string }, fallbackCode: string) {
  return `API error ${status.code || fallbackCode}: ${status.message}`;
}

type ToolCompletedEvent = {
  event: WriterRunEvent;
  toolName: string;
  isError: boolean;
  result: Record<string, unknown>;
};

function ToolResultCards({ workflowEvents }: { workflowEvents: WriterRunEventsSummary | null }) {
  if (workflowEvents?.ok === false) {
    return (
      <p>
        API error {workflowEvents.code}: {workflowEvents.message}
      </p>
    );
  }

  if (!workflowEvents) {
    return <p>No tool result stream selected.</p>;
  }

  const toolEvents = workflowEvents.items
    .filter((event) => event.event_type === "writer.tool.completed")
    .map(toToolCompletedEvent)
    .filter((event): event is ToolCompletedEvent => event !== null);

  if (toolEvents.length === 0) {
    return <p>No completed writer tool results recorded for this run.</p>;
  }

  return (
    <div className="tool-result-grid">
      {toolEvents.map((toolEvent) => (
        <ToolResultCard key={`${toolEvent.event.event_id}-${toolEvent.event.sequence}`} toolEvent={toolEvent} />
      ))}
    </div>
  );
}

function ToolResultCard({ toolEvent }: { toolEvent: ToolCompletedEvent }) {
  if (toolEvent.isError) {
    return <ToolErrorCard toolEvent={toolEvent} />;
  }

  if (toolEvent.toolName === "query_assets") {
    return <AssetToolResultCard toolEvent={toolEvent} />;
  }

  if (toolEvent.toolName === "query_graph_neighbors") {
    return <GraphToolResultCard toolEvent={toolEvent} />;
  }

  if (toolEvent.toolName === "query_worldline_paths") {
    return <WorldlinePathToolResultCard toolEvent={toolEvent} />;
  }

  return <UnknownToolResultCard toolEvent={toolEvent} />;
}

function AssetToolResultCard({ toolEvent }: { toolEvent: ToolCompletedEvent }) {
  const items = arrayOfRecords(toolEvent.result.items);

  return (
    <article className="tool-result-card">
      <ToolCardHeader toolEvent={toolEvent} label="Assets" count={items.length} />
      {items.length === 0 ? (
        <p className="trace-meta">No matching assets returned.</p>
      ) : (
        <div className="tool-result-items">
          {items.slice(0, 4).map((asset, index) => (
            <div className="tool-result-item" key={stringValue(asset, "asset_id") || index}>
              <strong>{stringValue(asset, "title") || stringValue(asset, "asset_id") || "Untitled asset"}</strong>
              <span>
                {stringValue(asset, "asset_type") || "asset"} / {stringValue(asset, "lifecycle") || "unknown"}
              </span>
              <small>{stringValue(asset, "summary") || stringValue(asset, "source") || "No public summary."}</small>
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

function GraphToolResultCard({ toolEvent }: { toolEvent: ToolCompletedEvent }) {
  const node = recordValue(toolEvent.result.node);
  const neighbors = arrayOfRecords(toolEvent.result.neighbors);

  return (
    <article className="tool-result-card">
      <ToolCardHeader toolEvent={toolEvent} label="Graph neighbors" count={neighbors.length} />
      <div className="tool-result-item">
        <strong>{stringValue(node, "title") || stringValue(node, "node_id") || "Graph node"}</strong>
        <span>{stringValue(node, "node_type") || "node"}</span>
      </div>
      {neighbors.length > 0 ? (
        <div className="tool-result-items">
          {neighbors.slice(0, 4).map((neighbor, index) => (
            <div className="tool-result-item" key={stringValue(neighbor, "node_id") || index}>
              <strong>{stringValue(neighbor, "title") || stringValue(neighbor, "node_id") || "Neighbor"}</strong>
              <span>{stringValue(neighbor, "relationship") || stringValue(neighbor, "edge_type") || "neighbor"}</span>
              <small>{stringValue(neighbor, "summary") || stringValue(neighbor, "direction") || "No public summary."}</small>
            </div>
          ))}
        </div>
      ) : (
        <p className="trace-meta">No graph neighbors returned.</p>
      )}
    </article>
  );
}

function WorldlinePathToolResultCard({ toolEvent }: { toolEvent: ToolCompletedEvent }) {
  const items = arrayOfRecords(toolEvent.result.items);

  return (
    <article className="tool-result-card">
      <ToolCardHeader toolEvent={toolEvent} label="Worldline paths" count={items.length} />
      {items.length === 0 ? (
        <p className="trace-meta">No saved worldline paths returned.</p>
      ) : (
        <div className="tool-result-items">
          {items.slice(0, 4).map((path, index) => (
            <div className="tool-result-item" key={stringValue(path, "path_id") || index}>
              <strong>{stringValue(path, "title") || stringValue(path, "path_id") || "Saved path"}</strong>
              <span>
                {stringValue(path, "lifecycle") || "reference"} / events{" "}
                {arrayOfRecords(path.selected_event_ids).length || arrayOfValues(path.selected_event_ids).length}
              </span>
              <small>{stringValue(path, "summary") || stringValue(path, "writer_instruction") || "No public summary."}</small>
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
      <ToolCardHeader toolEvent={toolEvent} label="Tool result" count={Object.keys(toolEvent.result).length} />
      <p className="trace-meta">Result shape is not yet typed. Raw payload remains available in Writer Events.</p>
    </article>
  );
}

function ToolErrorCard({ toolEvent }: { toolEvent: ToolCompletedEvent }) {
  return (
    <article className="tool-result-card error-box">
      <ToolCardHeader toolEvent={toolEvent} label="Tool error" count={0} />
      <p className="trace-meta">{stringValue(toolEvent.result, "message") || stringValue(toolEvent.result, "error") || "Tool failed."}</p>
    </article>
  );
}

function ToolCardHeader({
  toolEvent,
  label,
  count,
}: {
  toolEvent: ToolCompletedEvent;
  label: string;
  count: number;
}) {
  return (
    <div className="trace-event-header">
      <strong>{label}</strong>
      <span className="trace-redaction">{count} items</span>
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

function WriterEvents({ workflowEvents }: { workflowEvents: WriterRunEventsSummary | null }) {
  if (workflowEvents?.ok === false) {
    return (
      <p>
        API error {workflowEvents.code}: {workflowEvents.message}
      </p>
    );
  }

  if (!workflowEvents) {
    return <p>No writer event stream selected.</p>;
  }

  if (workflowEvents.items.length === 0) {
    return <p>No writer events recorded after the current replay cursor.</p>;
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
            {event.event_id} / {event.created_at}
          </p>
          <pre>{JSON.stringify(event.payload, null, 2)}</pre>
        </article>
      ))}
    </div>
  );
}

function TraceEvents({ traceEvents }: { traceEvents: AgentTraceEventsSummary | null }) {
  if (traceEvents?.ok === false) {
    return (
      <p>
        API error {traceEvents.code}: {traceEvents.message}
      </p>
    );
  }

  if (!traceEvents) {
    return <p>No trace selected.</p>;
  }

  if (traceEvents.items.length === 0) {
    return <p>No trace events recorded for this run yet.</p>;
  }

  return (
    <div className="trace-list">
      {traceEvents.items.map((event) => {
        const payloadKeys = Object.keys(event.payload);
        return (
          <article className="trace-event" key={`${event.event_id}-${event.event_order}`}>
            <div className="trace-event-header">
              <strong>{event.event_type}</strong>
              <span className="trace-redaction">{event.redaction_level}</span>
            </div>
            <p className="trace-meta">
              #{event.event_order} / {event.created_at}
            </p>
            {payloadKeys.length > 0 ? (
              <pre>{JSON.stringify(event.payload, null, 2)}</pre>
            ) : (
              <p className="trace-meta">Payload redacted.</p>
            )}
          </article>
        );
      })}
    </div>
  );
}
