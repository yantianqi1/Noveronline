import type {
  CharacterInteractionDetailSummary,
  CharacterInteractionTurnsSummary,
  CharacterInteractionsSummary,
  StoryGraphViewSummary,
  WorldlineEventsSummary,
  WorldlinePreparedAgentsSummary,
  WorldlineSavedPathsSummary,
  WorldlineSessionsSummary,
} from "../lib/api";

type CharacterConsoleShellProps = {
  interactions: CharacterInteractionsSummary;
  tenantSlug: string;
  projectId: string;
  appendCharacterInteractionTurnAction: (formData: FormData) => Promise<void>;
  convertCharacterInteractionToChapterDraftAction: (formData: FormData) => Promise<void>;
  createCharacterInteractionAction: (formData: FormData) => Promise<void>;
  graphView: StoryGraphViewSummary;
  inspectCharacterInteractionAction: (formData: FormData) => Promise<void>;
  inspectCharacterInteractionTurnsAction: (formData: FormData) => Promise<void>;
  inspectCharacterInteractionEventsAction: (formData: FormData) => Promise<void>;
  inspectWorldlineEventAnchorsAction: (formData: FormData) => Promise<void>;
  inspectWorldlinePreparationAgentsAction: (formData: FormData) => Promise<void>;
  updateCharacterInteractionStatusAction: (formData: FormData) => Promise<void>;
  anchorSessionId: string;
  interactionStatus: {
    status: string;
    code: string;
    message: string;
    interactionId: string;
  };
  preparedAgents: WorldlinePreparedAgentsSummary;
  prepareId: string;
  runtimeStatus: {
    status: string;
    code: string;
    message: string;
  };
  savedPaths: WorldlineSavedPathsSummary;
  selectedInteraction: CharacterInteractionDetailSummary;
  selectedTurns: CharacterInteractionTurnsSummary;
  turnStatus: {
    status: string;
    code: string;
    message: string;
    turnId: string;
  };
  worldlineEvents: WorldlineEventsSummary;
  worldlineSessions: WorldlineSessionsSummary;
};

export function CharacterConsoleShell({
  interactions,
  tenantSlug,
  projectId,
  appendCharacterInteractionTurnAction,
  convertCharacterInteractionToChapterDraftAction,
  createCharacterInteractionAction,
  graphView,
  inspectCharacterInteractionAction,
  inspectCharacterInteractionTurnsAction,
  inspectCharacterInteractionEventsAction,
  inspectWorldlineEventAnchorsAction,
  inspectWorldlinePreparationAgentsAction,
  updateCharacterInteractionStatusAction,
  anchorSessionId,
  interactionStatus,
  preparedAgents,
  prepareId,
  runtimeStatus,
  savedPaths,
  selectedInteraction,
  selectedTurns,
  turnStatus,
  worldlineEvents,
  worldlineSessions,
}: CharacterConsoleShellProps) {
  const interactionCount = interactions.ok ? interactions.items.length : 0;
  const latestInteractionId = interactions.ok && interactions.items.length > 0
    ? interactions.items[0].interaction_id
    : "";
  const hasWorldlineEventAnchors = worldlineEvents.ok && worldlineEvents.items.length > 0;
  const hasSavedPathAnchors = savedPaths.ok && savedPaths.items.length > 0;
  const hasGraphNodeAnchors = graphView.ok && graphView.nodes.length > 0;
  const selectedPovAgentId = selectedInteraction.ok ? selectedInteraction.pov_agent_id : "";
  const dossierAgent = preparedAgents.ok
    ? preparedAgents.items.find((agent) => agent.agent_id === selectedPovAgentId)
    : undefined;
  const agentHistoryTurns = selectedInteraction.ok
    ? selectedInteraction.turns.filter((turn) =>
        turn.actor_id === selectedPovAgentId || turn.actor_type === "user",
      )
    : [];

  return (
    <div>
      <header>
        <p className="eyebrow">Character Console</p>
        <h1>Character Console</h1>
        <p>
          Tenant <strong>{tenantSlug}</strong> / Project <strong>{projectId}</strong>
        </p>
        <div className="status-row">
          <span className="status-pill">WORLDLINE_SESSION_REQUIRED</span>
          <span className="status-pill">CHARACTER_CONSOLE_RUNTIME_PENDING</span>
          <span className="status-pill">{interactionCount} interactions</span>
          <span className="status-pill">
            Sessions: {worldlineSessions.ok ? worldlineSessions.items.length : worldlineSessions.code}
          </span>
        </div>
      </header>

      <div className="workbench-grid" style={{ marginTop: 20 }}>
        <main>
          <section className="panel" aria-labelledby="create-interaction-heading">
            <p className="eyebrow">Interaction Metadata</p>
            <h2 id="create-interaction-heading">Create interaction</h2>
            <InteractionStatusLine interactionStatus={interactionStatus} />
            <form action={createCharacterInteractionAction} className="binding-form">
              <label htmlFor="character-worldline-session">Worldline session</label>
              {worldlineSessions.ok && worldlineSessions.items.length > 0 ? (
                <select id="character-worldline-session" name="worldlineSessionId" defaultValue="">
                  <option value="">No worldline session</option>
                  {worldlineSessions.items.map((session) => (
                    <option key={session.session_id} value={session.session_id}>
                      {session.goal_summary || session.session_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="character-worldline-session"
                  name="worldlineSessionId"
                  placeholder="Optional admitted worldline session id"
                />
              )}
              {!worldlineSessions.ok ? (
                <p className="form-hint">
                  {worldlineSessions.code}: {worldlineSessions.message}
                </p>
              ) : null}

              <label htmlFor="character-anchor-type">Anchor type</label>
              <select id="character-anchor-type" name="anchorType" defaultValue="worldline_session">
                <option value="worldline_session">Worldline session</option>
                <option value="worldline_event">Worldline event</option>
                <option value="saved_path">Saved path</option>
                <option value="scene">Scene</option>
                <option value="graph_node">Graph node</option>
              </select>

              <label htmlFor="character-anchor-id">Anchor id</label>
              {hasWorldlineEventAnchors || hasSavedPathAnchors || hasGraphNodeAnchors ? (
                <select id="character-anchor-id" name="anchorId" defaultValue="">
                  <option value="">No anchor</option>
                  {hasWorldlineEventAnchors ? (
                    <optgroup label="Worldline events">
                      {worldlineEvents.items.map((event) => (
                        <option key={event.event_id} value={event.event_id}>
                          {event.title || event.event_id}
                        </option>
                      ))}
                    </optgroup>
                  ) : null}
                  {hasSavedPathAnchors ? (
                    <optgroup label="Saved paths">
                      {savedPaths.items.map((path) => (
                        <option key={path.path_id} value={path.path_id}>
                          {path.title || path.path_id}
                        </option>
                      ))}
                    </optgroup>
                  ) : null}
                  {hasGraphNodeAnchors ? (
                    <optgroup label="Graph nodes">
                      {graphView.nodes.map((node) => (
                        <option key={node.node_id} value={node.node_id}>
                          {node.title || node.node_id}
                        </option>
                      ))}
                    </optgroup>
                  ) : null}
                </select>
              ) : (
                <input
                  id="character-anchor-id"
                  name="anchorId"
                  placeholder="Optional public anchor id"
                />
              )}
              {anchorSessionId && !worldlineEvents.ok ? (
                <p className="form-hint">
                  {worldlineEvents.code || "WORLDLINE_EVENT_QUERY_FAILED"}: {worldlineEvents.message}
                </p>
              ) : null}
              {!savedPaths.ok ? (
                <p className="form-hint">
                  {savedPaths.code || "WORLDLINE_BACKEND_UNCONFIGURED"}: {savedPaths.message}
                </p>
              ) : null}
              {!graphView.ok ? (
                <p className="form-hint">
                  {graphView.code || "STORY_GRAPH_BACKEND_UNCONFIGURED"}: {graphView.message}
                </p>
              ) : null}

              <label htmlFor="character-pov-agent">POV agent</label>
              {preparedAgents.ok && preparedAgents.items.length > 0 ? (
                <select id="character-pov-agent" name="povAgentId" defaultValue="">
                  <option value="">No POV agent</option>
                  {preparedAgents.items.map((agent) => (
                    <option key={agent.agent_id} value={agent.agent_id}>
                      {agent.display_name || agent.agent_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="character-pov-agent"
                  name="povAgentId"
                  placeholder="Optional character or agent id"
                />
              )}
              {prepareId && !preparedAgents.ok ? (
                <p className="form-hint">
                  {preparedAgents.code || "WORLDLINE_PREPARED_AGENTS_QUERY_FAILED"}: {preparedAgents.message}
                </p>
              ) : null}

              <label htmlFor="character-interaction-mode">Mode</label>
              <select id="character-interaction-mode" name="mode" defaultValue="first_person">
                <option value="first_person">First person</option>
                <option value="director_assisted">Director assisted</option>
                <option value="dialogue">Dialogue</option>
                <option value="replay">Replay</option>
              </select>

              <label htmlFor="character-interaction-title">Title</label>
              <input
                id="character-interaction-title"
                name="title"
                placeholder="Rain negotiation before the breach"
                required
              />

              <label htmlFor="character-interaction-summary">Summary</label>
              <textarea
                id="character-interaction-summary"
                name="summary"
                placeholder="Public metadata summary for the interaction setup"
                rows={3}
              />

              <p className="form-hint">
                CHARACTER_INTERACTION_BACKEND_UNCONFIGURED appears until interaction metadata writes are backed by Postgres.
              </p>
              <button type="submit">Create interaction</button>
            </form>
          </section>

          <section className="panel" aria-labelledby="record-turn-heading">
            <p className="eyebrow">Turn Metadata</p>
            <h2 id="record-turn-heading">Record turn</h2>
            <TurnStatusLine turnStatus={turnStatus} />
            <form action={appendCharacterInteractionTurnAction} className="binding-form">
              <label htmlFor="character-turn-interaction">Interaction</label>
              {interactions.ok && interactions.items.length > 0 ? (
                <select
                  id="character-turn-interaction"
                  name="interactionId"
                  defaultValue={latestInteractionId}
                >
                  {interactions.items.map((interaction) => (
                    <option key={interaction.interaction_id} value={interaction.interaction_id}>
                      {interaction.title || interaction.interaction_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="character-turn-interaction"
                  name="interactionId"
                  placeholder="Persisted interaction id"
                />
              )}

              <label htmlFor="character-turn-actor-type">Actor type</label>
              <select id="character-turn-actor-type" name="actorType" defaultValue="user">
                <option value="user">User</option>
                <option value="agent">Agent</option>
                <option value="director">Director</option>
                <option value="system">System</option>
              </select>

              <label htmlFor="character-turn-actor-id">Actor id</label>
              <input
                id="character-turn-actor-id"
                name="actorId"
                placeholder="Optional actor or character id"
              />

              <label htmlFor="character-turn-kind">Turn kind</label>
              <select id="character-turn-kind" name="turnKind" defaultValue="action">
                <option value="action">Action</option>
                <option value="dialogue">Dialogue</option>
                <option value="thought">Thought</option>
                <option value="director_note">Director note</option>
                <option value="system_note">System note</option>
              </select>

              <label htmlFor="character-turn-summary">Summary</label>
              <textarea
                id="character-turn-summary"
                name="turnSummary"
                placeholder="Public metadata summary of the explicit turn"
                required
                rows={3}
              />

              <label htmlFor="character-turn-action-json">Action metadata</label>
              <textarea
                id="character-turn-action-json"
                name="actionJson"
                placeholder='Optional JSON object, for example {"intent":"negotiate"}'
                rows={3}
              />

              <label htmlFor="character-turn-world-delta-json">World state delta metadata</label>
              <textarea
                id="character-turn-world-delta-json"
                name="worldStateDeltaJson"
                placeholder='Optional JSON object, for example {"tension":"rising"}'
                rows={3}
              />

              <label htmlFor="character-turn-trace">Trace id</label>
              <input
                id="character-turn-trace"
                name="traceId"
                placeholder="Optional trace id"
              />

              <p className="form-hint">
                This records explicit public turn metadata only; it does not request an Agent reply.
              </p>
              <button type="submit">Record turn</button>
            </form>
          </section>

          <section className="panel error-box" aria-labelledby="interaction-heading">
            <p className="eyebrow">Interaction</p>
            <h2 id="interaction-heading">Scene stream</h2>
            <RuntimeStatusLine runtimeStatus={runtimeStatus} />
            <div className="binding-form">
              <p className="form-hint">
                CHARACTER_CONSOLE_RUNTIME_PENDING: live turns require a persisted interaction session.
              </p>
              <form action={inspectCharacterInteractionEventsAction} className="binding-form">
                <label htmlFor="character-runtime-interaction">Runtime interaction</label>
                {interactions.ok && interactions.items.length > 0 ? (
                  <select
                    id="character-runtime-interaction"
                    name="runtimeInteractionId"
                    defaultValue={selectedInteraction.ok ? selectedInteraction.interaction_id : latestInteractionId}
                  >
                    {interactions.items.map((interaction) => (
                      <option key={interaction.interaction_id} value={interaction.interaction_id}>
                        {interaction.title || interaction.interaction_id}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id="character-runtime-interaction"
                    name="runtimeInteractionId"
                    placeholder="Persisted interaction id"
                  />
                )}
                <button type="submit">Check runtime events</button>
              </form>
              <label className="form-hint" htmlFor="character-console-input">
                First-person turn
              </label>
              <textarea
                disabled
                id="character-console-input"
                name="characterConsoleTurn"
                rows={6}
                defaultValue=""
              />
              <button disabled type="button">Send turn</button>
            </div>
          </section>

          <section className="panel" aria-labelledby="interaction-log-heading">
            <p className="eyebrow">Replay</p>
            <h2 id="interaction-log-heading">Interaction log</h2>
            <form action={inspectCharacterInteractionAction} className="binding-form">
              <label htmlFor="selected-character-interaction">Inspect interaction</label>
              {interactions.ok && interactions.items.length > 0 ? (
                <select
                  id="selected-character-interaction"
                  name="selectedInteractionId"
                  defaultValue={selectedInteraction.ok ? selectedInteraction.interaction_id : latestInteractionId}
                >
                  {interactions.items.map((interaction) => (
                    <option key={interaction.interaction_id} value={interaction.interaction_id}>
                      {interaction.title || interaction.interaction_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="selected-character-interaction"
                  name="selectedInteractionId"
                  placeholder="Persisted interaction id"
                />
              )}
              <button type="submit">Inspect interaction</button>
            </form>
            <form action={inspectCharacterInteractionTurnsAction} className="binding-form">
              <label htmlFor="selected-character-turns">Public turn replay</label>
              {interactions.ok && interactions.items.length > 0 ? (
                <select
                  id="selected-character-turns"
                  name="turnsInteractionId"
                  defaultValue={selectedInteraction.ok ? selectedInteraction.interaction_id : latestInteractionId}
                >
                  {interactions.items.map((interaction) => (
                    <option key={interaction.interaction_id} value={interaction.interaction_id}>
                      {interaction.title || interaction.interaction_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="selected-character-turns"
                  name="turnsInteractionId"
                  placeholder="Persisted interaction id"
                />
              )}
              <button type="submit">Load public turns</button>
            </form>
            <form action={updateCharacterInteractionStatusAction} className="binding-form">
              <label htmlFor="status-character-interaction">Status interaction</label>
              {interactions.ok && interactions.items.length > 0 ? (
                <select
                  id="status-character-interaction"
                  name="statusInteractionId"
                  defaultValue={selectedInteraction.ok ? selectedInteraction.interaction_id : latestInteractionId}
                >
                  {interactions.items.map((interaction) => (
                    <option key={interaction.interaction_id} value={interaction.interaction_id}>
                      {interaction.title || interaction.interaction_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="status-character-interaction"
                  name="statusInteractionId"
                  placeholder="Persisted interaction id"
                />
              )}
              <div className="status-row">
                <button type="submit" name="interactionNextStatus" value="saved">Save interaction</button>
                <button type="submit" name="interactionNextStatus" value="archived">Archive interaction</button>
                <button type="submit" name="interactionNextStatus" value="active">Restore active</button>
              </div>
            </form>
            {interactions.ok ? (
              interactions.items.length > 0 ? (
                <div className="stack">
                  {interactions.items.map((interaction) => (
                    <article className="subtle-card" key={interaction.interaction_id}>
                      <div className="status-row">
                        <span className="status-pill">{interaction.mode}</span>
                        <span className="status-pill">{interaction.status}</span>
                      </div>
                      <h3>{interaction.title || interaction.interaction_id}</h3>
                      <p className="form-hint">{interaction.summary || "No public summary saved."}</p>
                      <p className="form-hint">
                        Anchor {interaction.anchor_type || "none"} / {interaction.anchor_id || "none"}
                      </p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="form-hint">No tenant/project scoped interaction turns are available.</p>
              )
            ) : (
              <div className="error-box">
                <strong>{interactions.code}</strong>
                <p className="form-hint">{interactions.message}</p>
              </div>
            )}
          </section>

          <section
            className={`panel ${selectedInteraction.ok ? "" : "error-box"}`}
            aria-labelledby="selected-interaction-heading"
          >
            <p className="eyebrow">Selected Interaction</p>
            <h2 id="selected-interaction-heading">Recorded turns</h2>
            <SelectedInteractionDetail selectedInteraction={selectedInteraction} />
          </section>

          <section
            className={`panel ${selectedTurns.ok ? "" : "error-box"}`}
            aria-labelledby="public-turn-replay-heading"
          >
            <p className="eyebrow">Replay</p>
            <h2 id="public-turn-replay-heading">Public turn replay</h2>
            <SelectedPublicTurnReplay selectedTurns={selectedTurns} />
          </section>
        </main>

        <aside>
          <section className="panel error-box" aria-labelledby="anchor-heading">
            <p className="eyebrow">Anchor</p>
            <h2 id="anchor-heading">Worldline anchor</h2>
            <form action={inspectWorldlineEventAnchorsAction} className="binding-form">
              <label htmlFor="character-anchor-session-id">Event anchor session</label>
              {worldlineSessions.ok && worldlineSessions.items.length > 0 ? (
                <select
                  id="character-anchor-session-id"
                  name="anchorSessionId"
                  defaultValue={anchorSessionId}
                >
                  <option value="">Select session</option>
                  {worldlineSessions.items.map((session) => (
                    <option key={session.session_id} value={session.session_id}>
                      {session.goal_summary || session.session_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="character-anchor-session-id"
                  name="anchorSessionId"
                  placeholder="Persisted worldline session id"
                  defaultValue={anchorSessionId}
                />
              )}
              <button type="submit">Load worldline events</button>
            </form>
            {worldlineSessions.ok ? (
              worldlineSessions.items.length > 0 ? (
                <div className="stack">
                  {worldlineSessions.items.slice(0, 4).map((session) => (
                    <article className="subtle-card" key={session.session_id}>
                      <div className="status-row">
                        <span className="status-pill">{session.status}</span>
                        <span className="status-pill">{session.lifecycle}</span>
                      </div>
                      <h3>{session.goal_summary || session.session_id}</h3>
                      <p className="form-hint">Session {session.session_id}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="form-hint">
                  WORLDLINE_SESSION_REQUIRED: no persisted session or saved path is attached.
                </p>
              )
            ) : (
              <p className="form-hint">
                {worldlineSessions.code || "WORLDLINE_SESSION_BACKEND_UNCONFIGURED"}: {worldlineSessions.message}
              </p>
            )}
            <h3>Saved paths</h3>
            {savedPaths.ok ? (
              savedPaths.items.length > 0 ? (
                <div className="stack">
                  {savedPaths.items.slice(0, 4).map((path) => (
                    <article className="subtle-card" key={path.path_id}>
                      <div className="status-row">
                        <span className="status-pill">{path.lifecycle}</span>
                        <span className="status-pill">{path.selected_event_ids.length} events</span>
                      </div>
                      <h3>{path.title || path.path_id}</h3>
                      <p className="form-hint">{path.summary || "No public path summary saved."}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="form-hint">No saved paths are available for this project.</p>
              )
            ) : (
              <p className="form-hint">
                {savedPaths.code || "WORLDLINE_BACKEND_UNCONFIGURED"}: {savedPaths.message}
              </p>
            )}
            <h3>Graph node anchors</h3>
            {graphView.ok ? (
              graphView.nodes.length > 0 ? (
                <div className="stack">
                  {graphView.nodes.slice(0, 4).map((node) => (
                    <article className="subtle-card" key={node.node_id}>
                      <div className="status-row">
                        <span className="status-pill">{node.node_type}</span>
                        <span className="status-pill">{node.lifecycle}</span>
                      </div>
                      <h3>{node.title || node.node_id}</h3>
                      <p className="form-hint">{node.summary || "No public node summary saved."}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="form-hint">No Story Graph nodes are available for this project.</p>
              )
            ) : (
              <p className="form-hint">
                {graphView.code || "STORY_GRAPH_BACKEND_UNCONFIGURED"}: {graphView.message}
              </p>
            )}
          </section>

          <section className="panel" aria-labelledby="roster-heading">
            <p className="eyebrow">Roster</p>
            <h2 id="roster-heading">Characters</h2>
            <form action={inspectWorldlinePreparationAgentsAction} className="binding-form">
              <label htmlFor="character-preparation-id">Worldline preparation</label>
              <input
                id="character-preparation-id"
                name="prepareId"
                placeholder="Persisted preparation id"
                defaultValue={prepareId}
              />
              <button type="submit">Load prepared agents</button>
            </form>
            {preparedAgents.ok ? (
              preparedAgents.items.length > 0 ? (
                <div className="stack">
                  {preparedAgents.items.map((agent) => (
                    <article className="subtle-card" key={agent.agent_id}>
                      <div className="status-row">
                        <span className="status-pill">{agent.status}</span>
                        <span className="status-pill">{agent.role}</span>
                      </div>
                      <h3>{agent.display_name || agent.agent_id}</h3>
                      <p className="form-hint">{agent.summary || "No public agent summary saved."}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="form-hint">No prepared agents are available for this preparation.</p>
              )
            ) : (
              <p className="form-hint">
                {preparedAgents.code || "WORLDLINE_PREPARED_AGENTS_QUERY_FAILED"}: {preparedAgents.message}
              </p>
            )}
          </section>

          <section className="panel" aria-labelledby="dossier-heading">
            <p className="eyebrow">Dossier</p>
            <h2 id="dossier-heading">Character dossier</h2>
            {dossierAgent ? (
              <article className="subtle-card">
                <div className="status-row">
                  <span className="status-pill">{dossierAgent.role}</span>
                  <span className="status-pill">{dossierAgent.status}</span>
                </div>
                <h3>{dossierAgent.display_name || dossierAgent.agent_id}</h3>
                <p className="form-hint">{dossierAgent.summary || "No public dossier summary saved."}</p>
                <p className="form-hint">Source asset {dossierAgent.source_asset_id || "none"}</p>
              </article>
            ) : (
              <p className="form-hint">
                No POV agent public dossier is available for the selected interaction.
              </p>
            )}
            <p className="form-hint">No character memory is available for this interaction.</p>
          </section>

          <section className="panel" aria-labelledby="public-history-heading">
            <p className="eyebrow">History</p>
            <h2 id="public-history-heading">Public turn history</h2>
            {agentHistoryTurns.length > 0 ? (
              <div className="stack">
                {agentHistoryTurns.slice(0, 6).map((historyTurn) => (
                  <article className="subtle-card" key={historyTurn.turn_id}>
                    <div className="status-row">
                      <span className="status-pill">Turn {historyTurn.turn_order}</span>
                      <span className="status-pill">{historyTurn.actor_type}</span>
                      <span className="status-pill">{historyTurn.turn_kind}</span>
                    </div>
                    <p className="form-hint">{historyTurn.summary || "No public turn summary saved."}</p>
                  </article>
                ))}
              </div>
            ) : (
              <p className="form-hint">No public turn history is available for this POV agent.</p>
            )}
          </section>

          <section className="panel error-box" aria-labelledby="convert-heading">
            <p className="eyebrow">Draft Handoff</p>
            <h2 id="convert-heading">Convert to chapter draft</h2>
            <RuntimeStatusLine runtimeStatus={runtimeStatus} />
            <form action={convertCharacterInteractionToChapterDraftAction} className="binding-form">
              <label htmlFor="character-convert-interaction">Interaction</label>
              {interactions.ok && interactions.items.length > 0 ? (
                <select
                  id="character-convert-interaction"
                  name="convertInteractionId"
                  defaultValue={selectedInteraction.ok ? selectedInteraction.interaction_id : latestInteractionId}
                >
                  {interactions.items.map((interaction) => (
                    <option key={interaction.interaction_id} value={interaction.interaction_id}>
                      {interaction.title || interaction.interaction_id}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id="character-convert-interaction"
                  name="convertInteractionId"
                  placeholder="Persisted interaction id"
                />
              )}
              <label htmlFor="character-target-chapter">Target chapter</label>
              <input
                id="character-target-chapter"
                name="targetChapterId"
                placeholder="Optional chapter id"
              />
              <label htmlFor="character-pov-mode">POV mode</label>
              <select id="character-pov-mode" name="povMode" defaultValue="keep_first_person">
                <option value="keep_first_person">Keep first person</option>
                <option value="first_person_to_third_person">First to third person</option>
              </select>
              <button type="submit">Request chapter draft conversion</button>
            </form>
            <p className="form-hint">
              Writer run queued: the handoff starts the real Writer pipeline and does not fabricate a draft in this panel.
            </p>
          </section>
        </aside>
      </div>
    </div>
  );
}

function SelectedPublicTurnReplay({
  selectedTurns,
}: {
  selectedTurns: CharacterInteractionTurnsSummary;
}) {
  if (!selectedTurns.ok) {
    return (
      <div>
        <strong>{selectedTurns.code}</strong>
        <p className="form-hint">{selectedTurns.message}</p>
      </div>
    );
  }

  if (selectedTurns.items.length === 0) {
    return <p className="form-hint">No public turn metadata is recorded for this interaction.</p>;
  }

  return (
    <div className="stack">
      {selectedTurns.items.map((turn) => (
        <article className="subtle-card" key={turn.turn_id}>
          <div className="status-row">
            <span className="status-pill">Turn {turn.turn_order}</span>
            <span className="status-pill">{turn.actor_type}</span>
            <span className="status-pill">{turn.turn_kind}</span>
          </div>
          <p className="form-hint">{turn.summary || "No public turn summary saved."}</p>
          <pre className="json-block">{JSON.stringify(turn.action, null, 2)}</pre>
          <pre className="json-block">{JSON.stringify(turn.world_state_delta, null, 2)}</pre>
        </article>
      ))}
    </div>
  );
}

function SelectedInteractionDetail({
  selectedInteraction,
}: {
  selectedInteraction: CharacterInteractionDetailSummary;
}) {
  if (!selectedInteraction.ok) {
    return (
      <div>
        <strong>{selectedInteraction.code}</strong>
        <p className="form-hint">{selectedInteraction.message}</p>
      </div>
    );
  }

  return (
    <div className="stack">
      <article className="subtle-card">
        <div className="status-row">
          <span className="status-pill">{selectedInteraction.mode}</span>
          <span className="status-pill">{selectedInteraction.status}</span>
          <span className="status-pill">{selectedInteraction.turns.length} turns</span>
        </div>
        <h3>{selectedInteraction.title || selectedInteraction.interaction_id}</h3>
        <p className="form-hint">{selectedInteraction.summary || "No public summary saved."}</p>
      </article>

      {selectedInteraction.turns.length > 0 ? (
        selectedInteraction.turns.map((turn) => (
          <article className="subtle-card" key={turn.turn_id}>
            <div className="status-row">
              <span className="status-pill">Turn {turn.turn_order}</span>
              <span className="status-pill">{turn.actor_type}</span>
              <span className="status-pill">{turn.turn_kind}</span>
            </div>
            <p className="form-hint">{turn.summary || "No public turn summary saved."}</p>
            <pre className="json-block">{JSON.stringify(turn.action, null, 2)}</pre>
            <pre className="json-block">{JSON.stringify(turn.world_state_delta, null, 2)}</pre>
          </article>
        ))
      ) : (
        <p className="form-hint">No explicit public turns are recorded for this interaction.</p>
      )}
    </div>
  );
}

function InteractionStatusLine({
  interactionStatus,
}: {
  interactionStatus: {
    status: string;
    code: string;
    message: string;
    interactionId: string;
  };
}) {
  if (!interactionStatus.status) {
    return null;
  }

  return (
    <div className={interactionStatus.status === "success" ? "success-box" : "error-box"}>
      <strong>{interactionStatus.code}</strong>
      <p className="form-hint">{interactionStatus.message}</p>
      {interactionStatus.interactionId ? (
        <p className="form-hint">Interaction {interactionStatus.interactionId}</p>
      ) : null}
    </div>
  );
}

function TurnStatusLine({
  turnStatus,
}: {
  turnStatus: {
    status: string;
    code: string;
    message: string;
    turnId: string;
  };
}) {
  if (!turnStatus.status) {
    return null;
  }

  return (
    <div className={turnStatus.status === "success" ? "success-box" : "error-box"}>
      <strong>{turnStatus.code}</strong>
      <p className="form-hint">{turnStatus.message}</p>
      {turnStatus.turnId ? (
        <p className="form-hint">Turn {turnStatus.turnId}</p>
      ) : null}
    </div>
  );
}

function RuntimeStatusLine({
  runtimeStatus,
}: {
  runtimeStatus: {
    status: string;
    code: string;
    message: string;
  };
}) {
  if (!runtimeStatus.status) {
    return null;
  }

  return (
    <div className={runtimeStatus.status === "success" ? "success-box" : "error-box"}>
      <strong>{runtimeStatus.code}</strong>
      <p className="form-hint">{runtimeStatus.message}</p>
    </div>
  );
}
