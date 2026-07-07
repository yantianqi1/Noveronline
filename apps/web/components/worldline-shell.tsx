import type {
  WorldlineEventsSummary,
  WorldlinePreparationSummary,
  WorldlinePreparedAgentsSummary,
  WorldlineSavedPathsSummary,
  WorldlineSessionsSummary,
  WorldlineTimelineSummary,
} from "../lib/api";

type WorldlineShellProps = {
  tenantSlug: string;
  projectId: string;
  savedPaths: WorldlineSavedPathsSummary;
  sessions: WorldlineSessionsSummary;
  timeline: WorldlineTimelineSummary;
  events: WorldlineEventsSummary;
  preparation: WorldlinePreparationSummary;
  preparedAgents: WorldlinePreparedAgentsSummary;
  startWorldlineSessionAction: (formData: FormData) => Promise<void>;
  startWorldlineStepAction: (formData: FormData) => Promise<void>;
  createWorldlinePreparationAction: (formData: FormData) => Promise<void>;
  injectWorldlineVariableAction: (formData: FormData) => Promise<void>;
  createWorldlineSavedPathAction: (formData: FormData) => Promise<void>;
  adoptWorldlineEventAction: (formData: FormData) => Promise<void>;
  updateWorldlineEventAction: (formData: FormData) => Promise<void>;
  worldlineSessionStatus: {
    status: string;
    code: string;
    message: string;
    runId: string;
  };
  worldlineStepStatus: {
    status: string;
    code: string;
    message: string;
    runId: string;
  };
  worldlinePreparationStatus: {
    status: string;
    code: string;
    message: string;
    prepareId: string;
  };
  worldlineVariableStatus: {
    status: string;
    code: string;
    message: string;
    variableId: string;
  };
  worldlineSavedPathStatus: {
    status: string;
    code: string;
    message: string;
    pathId: string;
  };
  worldlineEventAdoptionStatus: {
    status: string;
    code: string;
    message: string;
    eventId: string;
  };
  worldlineEventMutationStatus: {
    status: string;
    code: string;
    message: string;
    eventId: string;
  };
};

export function WorldlineShell({
  tenantSlug,
  projectId,
  savedPaths,
  sessions,
  timeline,
  events,
  preparation,
  preparedAgents,
  startWorldlineSessionAction,
  startWorldlineStepAction,
  createWorldlinePreparationAction,
  injectWorldlineVariableAction,
  createWorldlineSavedPathAction,
  adoptWorldlineEventAction,
  updateWorldlineEventAction,
  worldlineSessionStatus,
  worldlineStepStatus,
  worldlinePreparationStatus,
  worldlineVariableStatus,
  worldlineSavedPathStatus,
  worldlineEventAdoptionStatus,
  worldlineEventMutationStatus,
}: WorldlineShellProps) {
  const latestSessionId = sessions.ok && sessions.items.length > 0 ? sessions.items[0].session_id : "";

  return (
    <div>
      <header>
        <p className="eyebrow">Worldline</p>
        <h1>Worldline</h1>
        <p>
          Tenant <strong>{tenantSlug}</strong> / Project <strong>{projectId}</strong>
        </p>
        <div className="status-row">
          <span className="status-pill">
            Saved paths: {savedPaths.ok ? savedPaths.items.length : savedPaths.code}
          </span>
          <span className="status-pill">
            Sessions: {sessions.ok ? sessions.items.length : sessions.code}
          </span>
          <span className="status-pill">
            Timeline: {timeline.ok ? timeline.items.length : timeline.code}
          </span>
          <span className="status-pill">
            Events: {events.ok ? events.items.length : events.code}
          </span>
          <span className="status-pill">
            Preparation: {preparation.ok ? preparation.status : preparation.code}
          </span>
          <span className="status-pill">Current world</span>
        </div>
      </header>

      <div className="workbench-grid" style={{ marginTop: 20 }}>
        <main>
          <section className="panel" aria-labelledby="start-session-heading">
            <p className="eyebrow">Session</p>
            <h2 id="start-session-heading">Start session</h2>
            <StatusLine worldlineSessionStatus={worldlineSessionStatus} />
            <form action={startWorldlineSessionAction} className="binding-form">
              <label htmlFor="worldline-session-goal">Goal</label>
              <textarea
                id="worldline-session-goal"
                name="goal"
                placeholder="Explore one concrete current-world consequence"
                required
                rows={4}
              />

              <label htmlFor="worldline-anchor-path">Anchor path</label>
              {savedPaths.ok && savedPaths.items.length > 0 ? (
                <select id="worldline-anchor-path" name="anchorPathId" defaultValue="">
                  <option value="">No anchor path</option>
                  {savedPaths.items.map((path) => (
                    <option key={path.path_id} value={path.path_id}>
                      {path.title || path.path_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="worldline-anchor-path"
                  name="anchorPathId"
                  placeholder="Optional saved path id"
                />
              )}
              <p className="form-hint">
                WORLDLINE_SESSION_BACKEND_UNCONFIGURED appears until a real session backend is wired.
              </p>
              <button type="submit">Start session</button>
            </form>
          </section>

          <section
            aria-labelledby="saved-paths-heading"
            className={`panel ${savedPaths.ok ? "" : "error-box"}`}
          >
            <p className="eyebrow">References</p>
            <h2 id="saved-paths-heading">Saved paths</h2>
            <SavedPathList savedPaths={savedPaths} />
          </section>

          <section
            aria-labelledby="session-history-heading"
            className={`panel ${sessions.ok ? "" : "error-box"}`}
          >
            <p className="eyebrow">Sessions</p>
            <h2 id="session-history-heading">Session history</h2>
            <SessionList sessions={sessions} />
          </section>

          <section className="panel" aria-labelledby="step-session-heading">
            <p className="eyebrow">Runtime Admission</p>
            <h2 id="step-session-heading">Step session</h2>
            <StepStatusLine worldlineStepStatus={worldlineStepStatus} />
            <form action={startWorldlineStepAction} className="binding-form">
              <label htmlFor="worldline-step-session">Session</label>
              {sessions.ok && sessions.items.length > 0 ? (
                <select
                  id="worldline-step-session"
                  name="sessionId"
                  defaultValue={latestSessionId}
                >
                  {sessions.items.map((session) => (
                    <option key={session.session_id} value={session.session_id}>
                      {session.goal_summary || session.session_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="worldline-step-session"
                  name="sessionId"
                  placeholder="Admitted session id"
                />
              )}

              <label htmlFor="worldline-step-mode">Mode</label>
              <select id="worldline-step-mode" name="stepMode" defaultValue="director">
                <option value="director">Director</option>
                <option value="agent_turn">Agent turn</option>
                <option value="evaluation">Evaluation</option>
              </select>

              <p className="form-hint">
                WORLDLINE_STEP_BACKEND_UNCONFIGURED appears until step admission is backed by
                Postgres or a runtime starter.
              </p>
              <button type="submit">Step session</button>
            </form>
          </section>

          <section className="panel" aria-labelledby="variable-injection-heading">
            <p className="eyebrow">Variable</p>
            <h2 id="variable-injection-heading">Variable injection</h2>
            <VariableStatusLine worldlineVariableStatus={worldlineVariableStatus} />
            <form action={injectWorldlineVariableAction} className="binding-form">
              <label htmlFor="worldline-variable-session">Session</label>
              {sessions.ok && sessions.items.length > 0 ? (
                <select
                  id="worldline-variable-session"
                  name="sessionId"
                  defaultValue={latestSessionId}
                >
                  {sessions.items.map((session) => (
                    <option key={session.session_id} value={session.session_id}>
                      {session.goal_summary || session.session_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="worldline-variable-session"
                  name="sessionId"
                  placeholder="Admitted session id"
                />
              )}

              <label htmlFor="worldline-variable-name">Name</label>
              <input
                id="worldline-variable-name"
                name="variableName"
                placeholder="主角亲族提前失踪"
                required
              />

              <label htmlFor="worldline-variable-description">Description</label>
              <textarea
                id="worldline-variable-description"
                name="variableDescription"
                placeholder="Public metadata summary for this current-world variable"
                rows={3}
              />

              <label htmlFor="worldline-variable-impact-axis">Impact axis</label>
              <input
                id="worldline-variable-impact-axis"
                name="impactAxis"
                placeholder="kinship_pressure"
              />

              <label className="checkbox-row" htmlFor="worldline-variable-locked">
                <input id="worldline-variable-locked" name="locked" type="checkbox" />
                Lock variable
              </label>

              <p className="form-hint">
                WORLDLINE_VARIABLE_BACKEND_UNCONFIGURED appears until variable metadata writes are
                backed by Postgres.
              </p>
              <button type="submit">Inject variable</button>
            </form>
          </section>
        </main>

        <aside>
          <section className="panel" aria-labelledby="prepare-agents-heading">
            <p className="eyebrow">Preparation</p>
            <h2 id="prepare-agents-heading">Prepare agents</h2>
            <PreparationStatusLine worldlinePreparationStatus={worldlinePreparationStatus} />
            <form action={createWorldlinePreparationAction} className="binding-form">
              <label htmlFor="worldline-preparation-goal">Goal</label>
              <textarea
                id="worldline-preparation-goal"
                name="preparationGoal"
                placeholder="Prepare current-world agents for one focused interaction"
                required
                rows={4}
              />

              <label htmlFor="worldline-preparation-anchor-path">Anchor path</label>
              {savedPaths.ok && savedPaths.items.length > 0 ? (
                <select
                  id="worldline-preparation-anchor-path"
                  name="preparationAnchorPathId"
                  defaultValue=""
                >
                  <option value="">No anchor path</option>
                  {savedPaths.items.map((path) => (
                    <option key={path.path_id} value={path.path_id}>
                      {path.title || path.path_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="worldline-preparation-anchor-path"
                  name="preparationAnchorPathId"
                  placeholder="Optional saved path id"
                />
              )}
              <p className="form-hint">
                WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED appears until preparation admission is
                backed by Postgres.
              </p>
              <button type="submit">Prepare agents</button>
            </form>
          </section>

          <section
            className={`panel ${preparation.ok && preparedAgents.ok ? "" : "error-box"}`}
            aria-labelledby="prepared-agents-heading"
          >
            <p className="eyebrow">Agent Metadata</p>
            <h2 id="prepared-agents-heading">Prepared agents</h2>
            <PreparationDetail preparation={preparation} preparedAgents={preparedAgents} />
          </section>

          <section className="panel error-box" aria-labelledby="worldline-runtime-heading">
            <p className="eyebrow">Runtime</p>
            <h2 id="worldline-runtime-heading">Worldline runtime</h2>
            <p className="form-hint">
              WORLDLINE_RUNTIME_PENDING: session preparation, timeline stepping, and event adoption
              are not wired in this SaaS slice.
            </p>
          </section>

          <section
            className={`panel ${timeline.ok ? "" : "error-box"}`}
            aria-labelledby="worldline-timeline-heading"
          >
            <p className="eyebrow">Timeline</p>
            <h2 id="worldline-timeline-heading">Timeline</h2>
            <TimelineList timeline={timeline} />
          </section>

          <section
            className={`panel ${events.ok ? "" : "error-box"}`}
            aria-labelledby="worldline-events-heading"
          >
            <p className="eyebrow">Candidates</p>
            <h2 id="worldline-events-heading">Candidate events</h2>
            <EventList events={events} />
          </section>

          <section className="panel" aria-labelledby="edit-event-heading">
            <p className="eyebrow">Candidate Metadata</p>
            <h2 id="edit-event-heading">Edit event</h2>
            <EventMutationStatusLine worldlineEventMutationStatus={worldlineEventMutationStatus} />
            <form action={updateWorldlineEventAction} className="binding-form">
              <label htmlFor="worldline-edit-event">Candidate event</label>
              {events.ok && events.items.length > 0 ? (
                <select id="worldline-edit-event" name="eventId" defaultValue="">
                  <option value="">Select candidate event</option>
                  {events.items.map((event) => (
                    <option key={event.event_id} value={event.event_id}>
                      {event.title || event.event_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input id="worldline-edit-event" name="eventId" placeholder="Candidate event id" />
              )}

              <label htmlFor="worldline-event-title">Title</label>
              <input
                id="worldline-event-title"
                name="eventTitle"
                placeholder="Public event title"
              />

              <label htmlFor="worldline-event-summary">Summary</label>
              <textarea
                id="worldline-event-summary"
                name="eventSummary"
                placeholder="Public metadata summary"
                rows={3}
              />

              <label htmlFor="worldline-event-kind">Kind</label>
              <input
                id="worldline-event-kind"
                name="eventKind"
                placeholder="director_revision"
              />

              <p className="form-hint">
                WORLDLINE_EVENT_MUTATION_BACKEND_UNCONFIGURED appears until event metadata edits
                are backed by Postgres.
              </p>
              <button type="submit">Update event</button>
            </form>
          </section>

          <section className="panel" aria-labelledby="adopt-event-heading">
            <p className="eyebrow">Canon Boundary</p>
            <h2 id="adopt-event-heading">Adopt event</h2>
            <EventAdoptionStatusLine worldlineEventAdoptionStatus={worldlineEventAdoptionStatus} />
            <form action={adoptWorldlineEventAction} className="binding-form">
              <label htmlFor="worldline-adopt-event">Candidate event</label>
              {events.ok && events.items.length > 0 ? (
                <select id="worldline-adopt-event" name="eventId" defaultValue="">
                  <option value="">Select candidate event</option>
                  {events.items.map((event) => (
                    <option key={event.event_id} value={event.event_id}>
                      {event.title || event.event_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input id="worldline-adopt-event" name="eventId" placeholder="Candidate event id" />
              )}

              <label htmlFor="worldline-adoption-note">Note</label>
              <textarea
                id="worldline-adoption-note"
                name="adoptionNote"
                placeholder="Public adoption note"
                rows={3}
              />

              <p className="form-hint">
                WORLDLINE_EVENT_ADOPTION_BACKEND_UNCONFIGURED appears until event adoption writes
                are backed by Postgres.
              </p>
              <button type="submit">Adopt event</button>
            </form>
          </section>

          <section className="panel" aria-labelledby="save-path-heading">
            <p className="eyebrow">Reference Path</p>
            <h2 id="save-path-heading">Save path</h2>
            <SavedPathStatusLine worldlineSavedPathStatus={worldlineSavedPathStatus} />
            <form action={createWorldlineSavedPathAction} className="binding-form">
              <label htmlFor="worldline-save-path-session">Session</label>
              {sessions.ok && sessions.items.length > 0 ? (
                <select
                  id="worldline-save-path-session"
                  name="sessionId"
                  defaultValue={latestSessionId}
                >
                  {sessions.items.map((session) => (
                    <option key={session.session_id} value={session.session_id}>
                      {session.goal_summary || session.session_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="worldline-save-path-session"
                  name="sessionId"
                  placeholder="Admitted session id"
                />
              )}

              <label htmlFor="worldline-saved-path-title">Title</label>
              <input
                id="worldline-saved-path-title"
                name="savedPathTitle"
                placeholder="雨夜谈判路线"
                required
              />

              <label htmlFor="worldline-saved-path-summary">Summary</label>
              <textarea
                id="worldline-saved-path-summary"
                name="savedPathSummary"
                placeholder="Public path summary"
                rows={3}
              />

              <fieldset className="checkbox-group">
                <legend>Candidate events</legend>
                {events.ok && events.items.length > 0 ? (
                  events.items.map((event) => (
                    <label className="checkbox-row" key={event.event_id}>
                      <input name="selectedEventIds" type="checkbox" value={event.event_id} />
                      <span>{event.title || event.event_id}</span>
                    </label>
                  ))
                ) : (
                  <p className="form-hint">
                    {events.ok
                      ? "No candidate events have been written for this session."
                      : `${events.code}: ${events.message}`}
                  </p>
                )}
              </fieldset>

              <label htmlFor="worldline-manual-event-ids">Event IDs</label>
              <textarea
                id="worldline-manual-event-ids"
                name="manualEventIds"
                placeholder="Optional event ids, one per line"
                rows={3}
              />

              <label htmlFor="worldline-writer-instruction">Writer instruction</label>
              <textarea
                id="worldline-writer-instruction"
                name="writerInstruction"
                placeholder="How Writer should use this saved path as a reference"
                rows={3}
              />

              <p className="form-hint">
                WORLDLINE_SAVED_PATH_BACKEND_UNCONFIGURED appears until saved-path writes are
                backed by Postgres.
              </p>
              <button type="submit">Save path</button>
            </form>
          </section>

          <section className="panel" aria-labelledby="worldline-boundary-heading">
            <p className="eyebrow">Canon Boundary</p>
            <h2 id="worldline-boundary-heading">Current world</h2>
            <p className="form-hint">
              Saved paths remain Writer references; candidate events enter canon only through the
              explicit adoption action above.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}

function StatusLine({
  worldlineSessionStatus,
}: {
  worldlineSessionStatus: WorldlineShellProps["worldlineSessionStatus"];
}) {
  if (!worldlineSessionStatus.status) {
    return null;
  }
  const statusClass = worldlineSessionStatus.status === "success" ? "success-box" : "error-box";
  return (
    <p className={`form-status ${statusClass}`} data-status={worldlineSessionStatus.status}>
      {worldlineSessionStatus.code || "WORLDLINE_SESSION_BACKEND_UNCONFIGURED"}:{" "}
      {worldlineSessionStatus.message}
      {worldlineSessionStatus.runId ? ` Run ${worldlineSessionStatus.runId}` : ""}
    </p>
  );
}

function StepStatusLine({
  worldlineStepStatus,
}: {
  worldlineStepStatus: WorldlineShellProps["worldlineStepStatus"];
}) {
  if (!worldlineStepStatus.status) {
    return null;
  }
  const statusClass = worldlineStepStatus.status === "success" ? "success-box" : "error-box";
  return (
    <p className={`form-status ${statusClass}`} data-status={worldlineStepStatus.status}>
      {worldlineStepStatus.code || "WORLDLINE_STEP_BACKEND_UNCONFIGURED"}:{" "}
      {worldlineStepStatus.message}
      {worldlineStepStatus.runId ? ` Run ${worldlineStepStatus.runId}` : ""}
    </p>
  );
}

function PreparationStatusLine({
  worldlinePreparationStatus,
}: {
  worldlinePreparationStatus: WorldlineShellProps["worldlinePreparationStatus"];
}) {
  if (!worldlinePreparationStatus.status) {
    return null;
  }
  const statusClass =
    worldlinePreparationStatus.status === "success" ? "success-box" : "error-box";
  return (
    <p className={`form-status ${statusClass}`} data-status={worldlinePreparationStatus.status}>
      {worldlinePreparationStatus.code || "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED"}:{" "}
      {worldlinePreparationStatus.message}
      {worldlinePreparationStatus.prepareId ? ` Preparation ${worldlinePreparationStatus.prepareId}` : ""}
    </p>
  );
}

function VariableStatusLine({
  worldlineVariableStatus,
}: {
  worldlineVariableStatus: WorldlineShellProps["worldlineVariableStatus"];
}) {
  if (!worldlineVariableStatus.status) {
    return null;
  }
  const statusClass = worldlineVariableStatus.status === "success" ? "success-box" : "error-box";
  return (
    <p className={`form-status ${statusClass}`} data-status={worldlineVariableStatus.status}>
      {worldlineVariableStatus.code || "WORLDLINE_VARIABLE_BACKEND_UNCONFIGURED"}:{" "}
      {worldlineVariableStatus.message}
      {worldlineVariableStatus.variableId ? ` Variable ${worldlineVariableStatus.variableId}` : ""}
    </p>
  );
}

function SavedPathStatusLine({
  worldlineSavedPathStatus,
}: {
  worldlineSavedPathStatus: WorldlineShellProps["worldlineSavedPathStatus"];
}) {
  if (!worldlineSavedPathStatus.status) {
    return null;
  }
  const statusClass = worldlineSavedPathStatus.status === "success" ? "success-box" : "error-box";
  return (
    <p className={`form-status ${statusClass}`} data-status={worldlineSavedPathStatus.status}>
      {worldlineSavedPathStatus.code || "WORLDLINE_SAVED_PATH_BACKEND_UNCONFIGURED"}:{" "}
      {worldlineSavedPathStatus.message}
      {worldlineSavedPathStatus.pathId ? ` Path ${worldlineSavedPathStatus.pathId}` : ""}
    </p>
  );
}

function EventAdoptionStatusLine({
  worldlineEventAdoptionStatus,
}: {
  worldlineEventAdoptionStatus: WorldlineShellProps["worldlineEventAdoptionStatus"];
}) {
  if (!worldlineEventAdoptionStatus.status) {
    return null;
  }
  const statusClass =
    worldlineEventAdoptionStatus.status === "success" ? "success-box" : "error-box";
  return (
    <p className={`form-status ${statusClass}`} data-status={worldlineEventAdoptionStatus.status}>
      {worldlineEventAdoptionStatus.code || "WORLDLINE_EVENT_ADOPTION_BACKEND_UNCONFIGURED"}:{" "}
      {worldlineEventAdoptionStatus.message}
      {worldlineEventAdoptionStatus.eventId ? ` Event ${worldlineEventAdoptionStatus.eventId}` : ""}
    </p>
  );
}

function EventMutationStatusLine({
  worldlineEventMutationStatus,
}: {
  worldlineEventMutationStatus: WorldlineShellProps["worldlineEventMutationStatus"];
}) {
  if (!worldlineEventMutationStatus.status) {
    return null;
  }
  const statusClass =
    worldlineEventMutationStatus.status === "success" ? "success-box" : "error-box";
  return (
    <p className={`form-status ${statusClass}`} data-status={worldlineEventMutationStatus.status}>
      {worldlineEventMutationStatus.code || "WORLDLINE_EVENT_MUTATION_BACKEND_UNCONFIGURED"}:{" "}
      {worldlineEventMutationStatus.message}
      {worldlineEventMutationStatus.eventId ? ` Event ${worldlineEventMutationStatus.eventId}` : ""}
    </p>
  );
}

function PreparationDetail({
  preparation,
  preparedAgents,
}: {
  preparation: WorldlinePreparationSummary;
  preparedAgents: WorldlinePreparedAgentsSummary;
}) {
  if (!preparation.ok) {
    return (
      <p className="form-hint">
        {preparation.code || "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED"}: {preparation.message}
      </p>
    );
  }

  return (
    <div className="binding-stack">
      <article className="reference-card">
        <div className="status-row">
          <span className="status-pill">{preparation.status}</span>
          <span className="status-pill">{preparation.lifecycle}</span>
        </div>
        <h3>{preparation.goal_summary || preparation.prepare_id}</h3>
        <p className="trace-meta">Preparation {preparation.prepare_id}</p>
        <p className="trace-meta">Run {preparation.run_id}</p>
        {preparation.anchor_path_id ? (
          <p className="trace-meta">Anchor {preparation.anchor_path_id}</p>
        ) : null}
      </article>
      <PreparedAgentList preparedAgents={preparedAgents} />
    </div>
  );
}

function PreparedAgentList({
  preparedAgents,
}: {
  preparedAgents: WorldlinePreparedAgentsSummary;
}) {
  if (!preparedAgents.ok) {
    return (
      <p className="form-hint">
        {preparedAgents.code || "WORLDLINE_PREPARATION_BACKEND_UNCONFIGURED"}:{" "}
        {preparedAgents.message}
      </p>
    );
  }
  if (preparedAgents.items.length === 0) {
    return (
      <p className="form-hint">
        No prepared agents have been written for this preparation yet.
      </p>
    );
  }
  return (
    <div className="binding-stack">
      {preparedAgents.items.map((agent) => (
        <article className="reference-card" key={agent.agent_id}>
          <div className="status-row">
            <span className="status-pill">{agent.status}</span>
            <span className="status-pill">{agent.role || "agent"}</span>
          </div>
          <h3>{agent.display_name || agent.agent_id}</h3>
          <p className="form-hint">{agent.summary || "No public summary."}</p>
          <p className="trace-meta">Agent {agent.agent_id}</p>
          {agent.source_asset_id ? (
            <p className="trace-meta">Source asset {agent.source_asset_id}</p>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function SessionList({ sessions }: { sessions: WorldlineSessionsSummary }) {
  if (!sessions.ok) {
    return (
      <p className="form-hint">
        {sessions.code || "WORLDLINE_SESSION_BACKEND_UNCONFIGURED"}: {sessions.message}
      </p>
    );
  }
  if (sessions.items.length === 0) {
    return <p className="form-hint">No worldline sessions have been admitted for this project.</p>;
  }

  return (
    <div className="binding-stack">
      {sessions.items.map((session) => (
        <article className="reference-card" key={session.session_id}>
          <div className="status-row">
            <span className="status-pill">{session.status}</span>
            <span className="status-pill">{session.lifecycle}</span>
          </div>
          <h3>{session.goal_summary || session.session_id}</h3>
          <p className="trace-meta">Session {session.session_id}</p>
          <p className="trace-meta">Run {session.run_id}</p>
          {session.anchor_path_id ? <p className="trace-meta">Anchor {session.anchor_path_id}</p> : null}
        </article>
      ))}
    </div>
  );
}

function TimelineList({ timeline }: { timeline: WorldlineTimelineSummary }) {
  if (!timeline.ok) {
    return (
      <p className="form-hint">
        {timeline.code || "WORLDLINE_TIMELINE_BACKEND_UNCONFIGURED"}: {timeline.message}
      </p>
    );
  }
  if (timeline.items.length === 0) {
    return <p className="form-hint">No public timeline events have been written for this session.</p>;
  }

  return (
    <div className="binding-stack">
      {timeline.items.map((event) => (
        <article className="reference-card" key={event.event_id}>
          <div className="status-row">
            <span className="status-pill">#{event.sequence}</span>
            <span className="status-pill">{event.status || event.event_type}</span>
            {event.kind ? <span className="status-pill">{event.kind}</span> : null}
          </div>
          <h3>{event.title || event.event_type}</h3>
          <p className="form-hint">{event.summary || "No public summary."}</p>
          <p className="trace-meta">Event {event.event_id}</p>
          <p className="trace-meta">Run {event.run_id}</p>
        </article>
      ))}
    </div>
  );
}

function EventList({ events }: { events: WorldlineEventsSummary }) {
  if (!events.ok) {
    return (
      <p className="form-hint">
        {events.code || "WORLDLINE_EVENT_BACKEND_UNCONFIGURED"}: {events.message}
      </p>
    );
  }
  if (events.items.length === 0) {
    return <p className="form-hint">No candidate events have been written for this session.</p>;
  }

  return (
    <div className="binding-stack">
      {events.items.map((event) => (
        <article className="reference-card" key={event.event_id}>
          <div className="status-row">
            <span className="status-pill">Step {event.step}</span>
            <span className="status-pill">{event.status}</span>
            <span className="status-pill">{event.lifecycle}</span>
            {event.kind ? <span className="status-pill">{event.kind}</span> : null}
          </div>
          <h3>{event.title || event.event_id}</h3>
          <p className="form-hint">{event.summary || "No public summary."}</p>
          <p className="trace-meta">Event {event.event_id}</p>
          {event.confidence ? <p className="trace-meta">Confidence {event.confidence}</p> : null}
          {event.involved_agent_ids.length > 0 ? (
            <p className="trace-meta">Agents {event.involved_agent_ids.join(", ")}</p>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function SavedPathList({ savedPaths }: { savedPaths: WorldlineSavedPathsSummary }) {
  if (!savedPaths.ok) {
    return (
      <p className="form-hint">
        {savedPaths.code || "WORLDLINE_BACKEND_UNCONFIGURED"}: {savedPaths.message}
      </p>
    );
  }
  if (savedPaths.items.length === 0) {
    return <p className="form-hint">No saved paths are available for this project.</p>;
  }

  return (
    <div className="binding-stack">
      {savedPaths.items.map((path) => (
        <article className="reference-card" key={path.path_id}>
          <div className="status-row">
            <span className="status-pill">{path.lifecycle}</span>
            <span className="status-pill">{path.selected_event_ids.length} events</span>
          </div>
          <h3>{path.title || path.path_id}</h3>
          <p className="form-hint">{path.summary || "No public summary."}</p>
          <p className="trace-meta">Path {path.path_id}</p>
          <p className="trace-meta">Session {path.session_id}</p>
          {path.writer_instruction ? (
            <p className="form-hint">{path.writer_instruction}</p>
          ) : null}
        </article>
      ))}
    </div>
  );
}
