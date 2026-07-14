import { Check, ChevronRight } from "lucide-react";

import { Bi, FailureText, StatusValue } from "./bilingual-text";
import type {
  CharacterInteractionDetailSummary,
  CharacterInteractionEventsSummary,
  CharacterProposalsSummary,
  CharacterInteractionTurnsSummary,
  CharacterInteractionsSummary,
  StoryGraphViewSummary,
  WorldlineEventsSummary,
  WorldlinePreparedAgentsSummary,
  WorldlinePreparationsSummary,
  WorldlineSavedPathsSummary,
  WorldlineSessionsSummary,
} from "../lib/api";
import { tx, type Locale } from "../lib/locale";
import { InspectorPanel } from "./inspector-panel";
import { SubmitButton } from "./submit-button";
import { WorkspaceModeSwitcher } from "./workspace-mode-switcher";

type CharacterConsoleShellProps = {
  locale: Locale;
  adoptCharacterProposalAction: (formData: FormData) => Promise<void>;
  characterProposals: CharacterProposalsSummary;
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
  currentWorldSessionId: string;
  interactionStatus: {
    status: string;
    code: string;
    message: string;
    interactionId: string;
  };
  preparedAgents: WorldlinePreparedAgentsSummary;
  preparations: WorldlinePreparationsSummary;
  prepareId: string;
  selectWorldlinePreparationAction: (formData: FormData) => Promise<void>;
  runtimeStatus: {
    status: string;
    code: string;
    message: string;
    runId: string;
  };
  runtimeEvents: CharacterInteractionEventsSummary;
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
  locale,
  adoptCharacterProposalAction,
  characterProposals,
  interactions,
  tenantSlug,
  projectId,
  appendCharacterInteractionTurnAction,
  convertCharacterInteractionToChapterDraftAction,
  createCharacterInteractionAction,
  graphView,
  inspectCharacterInteractionAction,
  inspectCharacterInteractionEventsAction,
  inspectCharacterInteractionTurnsAction,
  inspectWorldlineEventAnchorsAction,
  inspectWorldlinePreparationAgentsAction,
  updateCharacterInteractionStatusAction,
  anchorSessionId,
  currentWorldSessionId,
  interactionStatus,
  preparedAgents,
  preparations,
  prepareId,
  selectWorldlinePreparationAction,
  runtimeStatus,
  runtimeEvents,
  savedPaths,
  selectedInteraction,
  selectedTurns,
  turnStatus,
  worldlineEvents,
  worldlineSessions,
}: CharacterConsoleShellProps) {
  const latestInteractionId = interactions.ok && interactions.items.length > 0
    ? interactions.items[0].interaction_id
    : "";
  const activeInteractionId = selectedInteraction.ok
    ? selectedInteraction.interaction_id
    : latestInteractionId;
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
    <div className="character-console-root">
      <div className="workbench-grid character-console-workbench">
        <main>
          <section className="panel" aria-labelledby="character-preparation-heading">
            <p className="eyebrow"><Bi zh="角色准备" en="Preparation" /></p>
            <h2 id="character-preparation-heading"><Bi zh="选择角色准备记录" en="Choose preparation" /></h2>
            <WorldlinePreparationSelector
              anchorSessionId={anchorSessionId}
              locale={locale}
              preparations={preparations}
              prepareId={prepareId}
              selectWorldlinePreparationAction={selectWorldlinePreparationAction}
            />
          </section>
          <WorkspaceModeSwitcher
            aria-label={tx(locale, "角色控制工作模式", "Character console workspace mode")}
            defaultMode={activeInteractionId ? "play" : "setup"}
            modes={[
              { id: "setup", label: <Bi zh="开场" en="Setup" /> },
              { id: "play", label: <Bi zh="互动" en="Play" /> },
              { id: "review", label: <Bi zh="回放" en="Review" /> },
            ]}
            panels={{
              setup: (
          <section className="panel" aria-labelledby="create-interaction-heading" data-character-mode="setup">
            <p className="eyebrow"><Bi zh="互动" en="Interaction" /></p>
            <h2 id="create-interaction-heading"><Bi zh="创建互动" en="Create interaction" /></h2>
            <InteractionStatusLine interactionStatus={interactionStatus} />
            <form action={createCharacterInteractionAction} className="binding-form character-create-form">
              <input type="hidden" name="anchorType" value="" />
              <input type="hidden" name="anchorId" value="" />
              <div className="character-form-field">
                <label htmlFor="character-worldline-session"><Bi zh="世界线推演" en="Worldline session" /></label>
                {worldlineSessions.ok && worldlineSessions.items.length > 0 ? (
                  <select id="character-worldline-session" name="worldlineSessionId" defaultValue={currentWorldSessionId}>
                    <option value="">{tx(locale, "不关联世界线推演", "No worldline session")}</option>
                    {worldlineSessions.items.map((session, index) => <option key={session.session_id} value={session.session_id}>{session.goal_summary || tx(locale, `未命名推演 ${index + 1}`, `Untitled session ${index + 1}`)}</option>)}
                  </select>
                ) : <select id="character-worldline-session" name="worldlineSessionId" disabled><option value="">{tx(locale, "暂无可用推演", "No session available")}</option></select>}
                {!worldlineSessions.ok ? <p className="form-hint"><FailureText /></p> : null}
              </div>

              <div className="character-form-field">
                <label htmlFor="character-interaction-mode"><Bi zh="模式" en="Mode" /></label>
                <select id="character-interaction-mode" name="mode" defaultValue="first_person">
                  <option value="first_person">{tx(locale, "第一人称", "First person")}</option>
                  <option value="director_assisted">{tx(locale, "导演辅助", "Director assisted")}</option>
                  <option value="dialogue">{tx(locale, "对话", "Dialogue")}</option>
                  <option value="replay">{tx(locale, "回放", "Replay")}</option>
                </select>
              </div>

              <div className="character-form-field">
                <label htmlFor="character-anchor-id"><Bi zh="类型化锚点" en="Typed anchor" /></label>
                {hasWorldlineEventAnchors || hasSavedPathAnchors || hasGraphNodeAnchors ? (
                  <select id="character-anchor-id" name="anchorRef" defaultValue={currentWorldSessionId ? `worldline_session:${currentWorldSessionId}` : ""}>
                    <option value="">{tx(locale, "不使用锚点", "No anchor")}</option>
                    {currentWorldSessionId ? <option value={`worldline_session:${currentWorldSessionId}`}>{tx(locale, "当前世界推演", "Current world session")}</option> : null}
                    {hasWorldlineEventAnchors ? <optgroup label={tx(locale, "世界线事件", "Worldline events")}>{worldlineEvents.items.map((event, index) => <option key={event.event_id} value={`worldline_event:${event.event_id}`}>{event.title || tx(locale, `未命名事件 ${index + 1}`, `Untitled event ${index + 1}`)}</option>)}</optgroup> : null}
                    {hasSavedPathAnchors ? <optgroup label={tx(locale, "已保存路径", "Saved paths")}>{savedPaths.items.map((path, index) => <option key={path.path_id} value={`saved_path:${path.path_id}`}>{path.title || tx(locale, `未命名路径 ${index + 1}`, `Untitled path ${index + 1}`)}</option>)}</optgroup> : null}
                    {hasGraphNodeAnchors ? <optgroup label={tx(locale, "图谱节点", "Graph nodes")}>{graphView.nodes.map((node, index) => <option key={node.node_id} value={`entity:${node.node_id}`}>{node.title || tx(locale, `未命名节点 ${index + 1}`, `Untitled node ${index + 1}`)}</option>)}</optgroup> : null}
                  </select>
                ) : <select id="character-anchor-id" name="anchorRef" disabled><option value="">{tx(locale, "暂无可用锚点", "No anchor available")}</option></select>}
                {anchorSessionId && !worldlineEvents.ok ? <p className="form-hint"><FailureText /></p> : null}
                {!savedPaths.ok ? <p className="form-hint"><FailureText /></p> : null}
                {!graphView.ok ? <p className="form-hint"><FailureText /></p> : null}
              </div>

              <div className="character-form-field">
                <label htmlFor="character-interaction-title"><Bi zh="标题" en="Title" /></label>
                <input id="character-interaction-title" name="title" placeholder={tx(locale, "雨夜谈判", "The rain-night negotiation")} required />
              </div>

              <div className="character-form-field">
                <label htmlFor="character-pov-agent"><Bi zh="视角角色" en="POV agent" /></label>
                {preparedAgents.ok && preparedAgents.items.length > 0 ? (
                  <select id="character-pov-agent" name="povAgentId" defaultValue="">
                    <option value="">{tx(locale, "未选择视角角色", "No POV agent")}</option>
                    {preparedAgents.items.map((agent, index) => <option key={agent.agent_id} value={agent.agent_id}>{agent.display_name || tx(locale, `未命名角色 ${index + 1}`, `Untitled character ${index + 1}`)}</option>)}
                  </select>
                ) : <select id="character-pov-agent" name="povAgentId" disabled><option value="">{tx(locale, "暂无可用角色", "No character available")}</option></select>}
                {prepareId && !preparedAgents.ok ? <p className="form-hint"><FailureText /></p> : null}
              </div>

              <div className="character-form-field character-summary-field">
                <label htmlFor="character-interaction-summary"><Bi zh="摘要" en="Summary" /></label>
                <textarea id="character-interaction-summary" name="summary" placeholder={tx(locale, "概括互动背景和目标", "Summarize the interaction setup and goal")} rows={3} />
              </div>

              <SubmitButton idleLabel={<Bi zh="创建互动" en="Create interaction" />} pendingLabel={<Bi zh="创建中…" en="Creating…" />} />
            </form>
          </section>
              ),
              play: (
          <section className="panel" aria-labelledby="record-turn-heading" data-character-mode="play">
            <p className="eyebrow"><Bi zh="回合" en="Turn" /></p>
            <h2 id="record-turn-heading"><Bi zh="记录回合" en="Record turn" /></h2>
            <TurnStatusLine turnStatus={turnStatus} />
            <form action={appendCharacterInteractionTurnAction} className="binding-form">
              <label htmlFor="character-turn-interaction"><Bi zh="互动" en="Interaction" /></label>
              {interactions.ok && interactions.items.length > 0 ? (
                <select
                  id="character-turn-interaction"
                  name="interactionId"
                  defaultValue={activeInteractionId}
                >
                  {interactions.items.map((interaction, index) => (
                    <option key={interaction.interaction_id} value={interaction.interaction_id}>
                      {interaction.title || tx(locale, `未命名互动 ${index + 1}`, `Untitled interaction ${index + 1}`)}
                    </option>
                  ))}
                </select>
              ) : (
                <select
                  id="character-turn-interaction"
                  name="interactionId"
                  disabled
                ><option value="">{tx(locale, "请先创建互动", "Create an interaction first")}</option></select>
              )}

              <label htmlFor="character-turn-actor-type"><Bi zh="行动者类型" en="Actor type" /></label>
              <select id="character-turn-actor-type" name="actorType" defaultValue="user">
                <option value="user">{tx(locale, "用户", "User")}</option>
                <option value="agent">{tx(locale, "角色", "Agent")}</option>
                <option value="director">{tx(locale, "导演", "Director")}</option>
                <option value="system">{tx(locale, "系统", "System")}</option>
              </select>

              <label htmlFor="character-turn-actor-id"><Bi zh="行动者" en="Actor" /></label>
              {preparedAgents.ok && preparedAgents.items.length > 0 ? (
                <select id="character-turn-actor-id" name="actorId" defaultValue="">
                  <option value="">{tx(locale, "不指定角色", "No specific character")}</option>
                  {preparedAgents.items.map((agent, index) => <option key={agent.agent_id} value={agent.agent_id}>{agent.display_name || tx(locale, `未命名角色 ${index + 1}`, `Untitled character ${index + 1}`)}</option>)}
                </select>
              ) : <select id="character-turn-actor-id" name="actorId" disabled><option value="">{tx(locale, "暂无可用角色", "No character available")}</option></select>}

              <label htmlFor="character-turn-kind"><Bi zh="回合类型" en="Turn kind" /></label>
              <select id="character-turn-kind" name="turnKind" defaultValue="action">
                <option value="action">{tx(locale, "行动", "Action")}</option>
                <option value="dialogue">{tx(locale, "对话", "Dialogue")}</option>
                <option value="thought">{tx(locale, "思绪", "Thought")}</option>
                <option value="director_note">{tx(locale, "导演备注", "Director note")}</option>
                <option value="system_note">{tx(locale, "系统备注", "System note")}</option>
              </select>

              <label htmlFor="character-turn-summary"><Bi zh="回合内容" en="Turn summary" /></label>
              <textarea
                id="character-turn-summary"
                name="turnSummary"
                placeholder={tx(locale, "描述本回合的行动、对话或思绪", "Describe the action, dialogue, or thought")}
                required
                rows={3}
              />

              <SubmitButton idleLabel={<Bi zh="记录回合" en="Record turn" />} pendingLabel={<Bi zh="记录中…" en="Recording…" />} />
            </form>
          </section>
              ),
              review: (
                <>
          <section className="panel" aria-labelledby="interaction-log-heading" data-character-mode="review">
            <p className="eyebrow"><Bi zh="记录" en="History" /></p>
            <h2 id="interaction-log-heading"><Bi zh="互动记录" en="Interaction log" /></h2>
            <form action={inspectCharacterInteractionAction} className="binding-form">
              <label htmlFor="selected-character-interaction"><Bi zh="互动" en="Interaction" /></label>
              {interactions.ok && interactions.items.length > 0 ? (
                <select
                  id="selected-character-interaction"
                  name="selectedInteractionId"
                  defaultValue={activeInteractionId}
                >
                  {interactions.items.map((interaction, index) => (
                    <option key={interaction.interaction_id} value={interaction.interaction_id}>
                      {interaction.title || tx(locale, `未命名互动 ${index + 1}`, `Untitled interaction ${index + 1}`)}
                    </option>
                  ))}
                </select>
              ) : (
                <select
                  id="selected-character-interaction"
                  name="selectedInteractionId"
                  disabled
                ><option value="">{tx(locale, "暂无互动", "No interaction available")}</option></select>
              )}
              <button type="submit"><Bi zh="查看互动" en="View interaction" /></button>
            </form>
            <form action={inspectCharacterInteractionTurnsAction} className="binding-form">
              <label htmlFor="selected-character-turns"><Bi zh="回合记录" en="Turn replay" /></label>
              {interactions.ok && interactions.items.length > 0 ? (
                <select
                  id="selected-character-turns"
                  name="turnsInteractionId"
                  defaultValue={activeInteractionId}
                >
                  {interactions.items.map((interaction, index) => (
                    <option key={interaction.interaction_id} value={interaction.interaction_id}>
                      {interaction.title || tx(locale, `未命名互动 ${index + 1}`, `Untitled interaction ${index + 1}`)}
                    </option>
                  ))}
                </select>
              ) : (
                <select
                  id="selected-character-turns"
                  name="turnsInteractionId"
                  disabled
                ><option value="">{tx(locale, "暂无互动", "No interaction available")}</option></select>
              )}
              <button type="submit"><Bi zh="加载回合" en="Load turns" /></button>
            </form>
            <form action={updateCharacterInteractionStatusAction} className="binding-form">
              <label htmlFor="status-character-interaction"><Bi zh="互动状态" en="Interaction status" /></label>
              {interactions.ok && interactions.items.length > 0 ? (
                <select
                  id="status-character-interaction"
                  name="statusInteractionId"
                  defaultValue={activeInteractionId}
                >
                  {interactions.items.map((interaction, index) => (
                    <option key={interaction.interaction_id} value={interaction.interaction_id}>
                      {interaction.title || tx(locale, `未命名互动 ${index + 1}`, `Untitled interaction ${index + 1}`)}
                    </option>
                  ))}
                </select>
              ) : (
                <select
                  id="status-character-interaction"
                  name="statusInteractionId"
                  disabled
                ><option value="">{tx(locale, "暂无互动", "No interaction available")}</option></select>
              )}
              <div className="status-row">
                <button type="submit" name="interactionNextStatus" value="saved"><Bi zh="保存" en="Save" /></button>
                <button type="submit" name="interactionNextStatus" value="archived"><Bi zh="归档" en="Archive" /></button>
                <button type="submit" name="interactionNextStatus" value="active"><Bi zh="恢复" en="Restore" /></button>
              </div>
            </form>
            {interactions.ok ? (
              interactions.items.length > 0 ? (
                <div className="stack">
                  {interactions.items.map((interaction, index) => (
                    <article className="subtle-card" key={interaction.interaction_id}>
                      <div className="status-row">
                        <span className="status-pill"><StatusValue value={interaction.mode} /></span>
                        <span className="status-pill"><StatusValue value={interaction.status} /></span>
                      </div>
                      <h3>{interaction.title || tx(locale, `未命名互动 ${index + 1}`, `Untitled interaction ${index + 1}`)}</h3>
                      <p className="form-hint">{interaction.summary || <Bi zh="暂无摘要。" en="No summary available." />}</p>
                      <p className="form-hint">
                        <Bi zh="锚点" en="Anchor" /> <StatusValue value={interaction.anchor_type || "none"} />
                      </p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="form-hint"><Bi zh="该项目暂无互动记录。" en="No interactions are available for this project." /></p>
              )
            ) : (
              <div className="error-box">
                <p className="form-hint"><FailureText /></p>
              </div>
            )}
          </section>

          <section
            className={`panel ${selectedInteraction.ok ? "" : "error-box"}`}
            aria-labelledby="selected-interaction-heading"
          >
            <p className="eyebrow"><Bi zh="当前互动" en="Selected interaction" /></p>
            <h2 id="selected-interaction-heading"><Bi zh="已记录回合" en="Recorded turns" /></h2>
            <SelectedInteractionDetail selectedInteraction={selectedInteraction} />
          </section>

          <section
            className={`panel ${selectedTurns.ok ? "" : "error-box"}`}
            aria-labelledby="public-turn-replay-heading"
          >
            <p className="eyebrow"><Bi zh="回放" en="Replay" /></p>
            <h2 id="public-turn-replay-heading"><Bi zh="回合回放" en="Turn replay" /></h2>
            <SelectedPublicTurnReplay selectedTurns={selectedTurns} />
          </section>
                </>
              ),
            }}
          />
        </main>

        <InspectorPanel
          title={<Bi zh="角色检视" en="Character inspector" />}
          status={<Bi zh="锚点、档案与转稿" en="Anchors, dossier, and conversion" />}
        >
          <details className="character-module-group" open>
            <summary><span><Bi zh="世界线锚点" en="Worldline anchor" /></span></summary>
            <div className="character-module-content">
          <section className="panel" aria-labelledby="anchor-heading">
            <p className="eyebrow"><Bi zh="锚点" en="Anchor" /></p>
            <h2 id="anchor-heading"><Bi zh="世界线锚点" en="Worldline anchor" /></h2>
            <form action={inspectWorldlineEventAnchorsAction} className="binding-form">
              <label htmlFor="character-anchor-session-id"><Bi zh="推演" en="Session" /></label>
              {worldlineSessions.ok && worldlineSessions.items.length > 0 ? (
                <select
                  id="character-anchor-session-id"
                  name="anchorSessionId"
                  defaultValue={anchorSessionId}
                >
                  <option value="">{tx(locale, "选择推演", "Select session")}</option>
                  {worldlineSessions.items.map((session, index) => (
                    <option key={session.session_id} value={session.session_id}>
                      {session.goal_summary || tx(locale, `未命名推演 ${index + 1}`, `Untitled session ${index + 1}`)}
                    </option>
                  ))}
                </select>
              ) : (
                <select
                  id="character-anchor-session-id"
                  name="anchorSessionId"
                  disabled
                ><option value="">{tx(locale, "暂无可用推演", "No session available")}</option></select>
              )}
              <button type="submit"><Bi zh="加载世界线事件" en="Load worldline events" /></button>
            </form>
            {worldlineSessions.ok ? (
              worldlineSessions.items.length > 0 ? (
                <div className="stack">
                  {worldlineSessions.items.slice(0, 4).map((session, index) => (
                    <article className="subtle-card" key={session.session_id}>
                      <div className="status-row">
                        <span className="status-pill"><StatusValue value={session.status} /></span>
                        <span className="status-pill"><StatusValue value={session.lifecycle} /></span>
                      </div>
                      <h3>{session.goal_summary || tx(locale, `未命名推演 ${index + 1}`, `Untitled session ${index + 1}`)}</h3>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="form-hint"><Bi zh="暂无可用的世界线推演。" en="No worldline sessions are available." /></p>
              )
            ) : (
              <p className="form-hint">
                <FailureText />
              </p>
            )}
            <h3><Bi zh="已保存路径" en="Saved paths" /></h3>
            {savedPaths.ok ? (
              savedPaths.items.length > 0 ? (
                <div className="stack">
                  {savedPaths.items.slice(0, 4).map((path, index) => (
                    <article className="subtle-card" key={path.path_id}>
                      <div className="status-row">
                        <span className="status-pill"><StatusValue value={path.lifecycle} /></span>
                        <span className="status-pill">{path.selected_event_ids.length} <Bi zh="个事件" en="events" /></span>
                      </div>
                      <h3>{path.title || tx(locale, `未命名路径 ${index + 1}`, `Untitled path ${index + 1}`)}</h3>
                      <p className="form-hint">{path.summary || <Bi zh="暂无摘要。" en="No summary available." />}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="form-hint"><Bi zh="该项目暂无已保存路径。" en="No saved paths are available for this project." /></p>
              )
            ) : (
              <p className="form-hint">
                <FailureText />
              </p>
            )}
            <h3><Bi zh="图谱节点锚点" en="Graph node anchors" /></h3>
            {graphView.ok ? (
              graphView.nodes.length > 0 ? (
                <div className="stack">
                  {graphView.nodes.slice(0, 4).map((node, index) => (
                    <article className="subtle-card" key={node.node_id}>
                      <div className="status-row">
                        <span className="status-pill">{node.node_type}</span>
                        <span className="status-pill"><StatusValue value={node.lifecycle} /></span>
                      </div>
                      <h3>{node.title || tx(locale, `未命名节点 ${index + 1}`, `Untitled node ${index + 1}`)}</h3>
                      <p className="form-hint">{node.summary || <Bi zh="暂无摘要。" en="No summary available." />}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="form-hint"><Bi zh="该项目暂无故事图谱节点。" en="No Story Graph nodes are available for this project." /></p>
              )
            ) : (
              <p className="form-hint">
                <FailureText />
              </p>
            )}
          </section>
            </div>
          </details>

          <details className="character-module-group">
            <summary><span><Bi zh="角色与档案" en="Roster and dossier" /></span></summary>
            <div className="character-module-content">
          <section className="panel" aria-labelledby="roster-heading">
            <p className="eyebrow"><Bi zh="角色" en="Roster" /></p>
            <h2 id="roster-heading"><Bi zh="角色列表" en="Characters" /></h2>
            <form action={inspectWorldlinePreparationAgentsAction} className="binding-form">
              <label htmlFor="character-preparation-id"><Bi zh="角色准备记录" en="Worldline preparation" /></label>
              <input
                id="character-preparation-id"
                name="prepareId"
                type="hidden"
                defaultValue={prepareId}
              />
              <button type="submit" disabled={!prepareId}><Bi zh="加载角色" en="Load prepared agents" /></button>
            </form>
            {preparedAgents.ok ? (
              preparedAgents.items.length > 0 ? (
                <div className="stack">
                  {preparedAgents.items.map((agent, index) => (
                    <article className="subtle-card" key={agent.agent_id}>
                      <div className="status-row">
                        <span className="status-pill"><StatusValue value={agent.status} /></span>
                        <span className="status-pill"><StatusValue value={agent.role} /></span>
                      </div>
                      <h3>{agent.display_name || tx(locale, `未命名角色 ${index + 1}`, `Untitled character ${index + 1}`)}</h3>
                      <p className="form-hint">{agent.summary || <Bi zh="暂无摘要。" en="No summary available." />}</p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="form-hint"><Bi zh="该准备记录暂无角色。" en="No agents are available for this preparation." /></p>
              )
            ) : (
              <p className="form-hint">
                <FailureText />
              </p>
            )}
          </section>

          <section className="panel" aria-labelledby="dossier-heading">
            <p className="eyebrow"><Bi zh="档案" en="Dossier" /></p>
            <h2 id="dossier-heading"><Bi zh="角色档案" en="Character dossier" /></h2>
            {dossierAgent ? (
              <article className="subtle-card" data-agent-id={dossierAgent.agent_id}>
                <div className="status-row">
                  <span className="status-pill"><StatusValue value={dossierAgent.role} /></span>
                  <span className="status-pill"><StatusValue value={dossierAgent.status} /></span>
                </div>
                <h3>{dossierAgent.display_name || <Bi zh="未命名角色" en="Untitled character" />}</h3>
                <p className="form-hint">{dossierAgent.summary || <Bi zh="暂无摘要。" en="No summary available." />}</p>
              </article>
            ) : (
              <p className="form-hint">
                <Bi zh="当前互动暂无视角角色档案。" en="No POV character dossier is available for this interaction." />
              </p>
            )}
          </section>
            </div>
          </details>

          <details className="character-module-group">
            <summary><span><Bi zh="历史与转稿" en="History and conversion" /></span></summary>
            <div className="character-module-content">
          <section className="panel" aria-labelledby="public-history-heading">
            <p className="eyebrow"><Bi zh="历史" en="History" /></p>
            <h2 id="public-history-heading"><Bi zh="角色回合历史" en="Character turn history" /></h2>
            {agentHistoryTurns.length > 0 ? (
              <div className="stack">
                {agentHistoryTurns.slice(0, 6).map((historyTurn) => (
                  <article className="subtle-card" key={historyTurn.turn_id}>
                    <div className="status-row">
                      <span className="status-pill"><Bi zh="回合" en="Turn" /> {historyTurn.turn_order}</span>
                      <span className="status-pill"><StatusValue value={historyTurn.actor_type} /></span>
                      <span className="status-pill"><StatusValue value={historyTurn.turn_kind} /></span>
                    </div>
                    <p className="form-hint">{historyTurn.summary || <Bi zh="暂无摘要。" en="No summary available." />}</p>
                  </article>
                ))}
              </div>
            ) : (
              <p className="form-hint"><Bi zh="该角色暂无回合历史。" en="No turn history is available for this character." /></p>
            )}
          </section>

          <section className="panel" aria-labelledby="convert-heading">
            <p className="eyebrow"><Bi zh="写作台" en="Writer" /></p>
            <h2 id="convert-heading"><Bi zh="转为章节草稿" en="Convert to chapter draft" /></h2>
            <RuntimeStatusLine runtimeStatus={runtimeStatus} />
            {runtimeStatus.status === "success" && runtimeStatus.runId ? (
              <a className="overview-next-link" href={writerRunHref(tenantSlug, projectId, runtimeStatus.runId)}>
                <Bi zh="在写作台查看" en="View in Writer" />
                <ChevronRight aria-hidden="true" size={18} />
              </a>
            ) : null}
            <form action={convertCharacterInteractionToChapterDraftAction} className="binding-form">
              <label htmlFor="character-convert-interaction"><Bi zh="互动" en="Interaction" /></label>
              {interactions.ok && interactions.items.length > 0 ? (
                <select
                  id="character-convert-interaction"
                  name="convertInteractionId"
                  defaultValue={activeInteractionId}
                >
                  {interactions.items.map((interaction, index) => (
                    <option key={interaction.interaction_id} value={interaction.interaction_id}>
                      {interaction.title || tx(locale, `未命名互动 ${index + 1}`, `Untitled interaction ${index + 1}`)}
                    </option>
                  ))}
                </select>
              ) : (
                <select
                  id="character-convert-interaction"
                  name="convertInteractionId"
                  disabled
                ><option value="">{tx(locale, "暂无互动", "No interaction available")}</option></select>
              )}
              <label htmlFor="character-target-chapter"><Bi zh="目标章节" en="Target chapter" /></label>
              <input id="character-target-chapter" name="targetChapterId" placeholder={tx(locale, "可选章节", "Optional chapter")} />
              <label htmlFor="character-target-scene"><Bi zh="目标场景" en="Target scene" /></label>
              <input id="character-target-scene" name="targetSceneId" placeholder={tx(locale, "可选场景", "Optional scene")} />
              <label htmlFor="character-pov-mode"><Bi zh="视角模式" en="POV mode" /></label>
              <select id="character-pov-mode" name="povMode" defaultValue="keep_first_person">
                <option value="keep_first_person">{tx(locale, "保持第一人称", "Keep first person")}</option>
                <option value="first_person_to_third_person">{tx(locale, "第一人称转第三人称", "First to third person")}</option>
              </select>
              <SubmitButton idleLabel={<Bi zh="提交章节草稿" en="Request chapter draft" />} pendingLabel={<Bi zh="提交中…" en="Submitting…" />} />
            </form>
          </section>

          <section className="panel" aria-labelledby="character-proposals-heading">
            <p className="eyebrow"><Bi zh="候选" en="Proposals" /></p>
            <h2 id="character-proposals-heading"><Bi zh="互动候选" en="Interaction proposals" /></h2>
            <CharacterProposalReview
              action={adoptCharacterProposalAction}
              proposals={characterProposals}
            />
          </section>
            </div>
          </details>
        </InspectorPanel>
      </div>
    </div>
  );
}

function WorldlinePreparationSelector({
  anchorSessionId,
  locale,
  preparations,
  prepareId,
  selectWorldlinePreparationAction,
}: {
  anchorSessionId: string;
  locale: Locale;
  preparations: WorldlinePreparationsSummary;
  prepareId: string;
  selectWorldlinePreparationAction: (formData: FormData) => Promise<void>;
}) {
  if (!preparations.ok) {
    return <p className="form-hint"><FailureText /></p>;
  }
  if (preparations.items.length === 0) {
    return (
      <p className="form-hint">
        <Bi zh="暂无角色准备记录。请先在「世界线」完成角色准备。" en="No preparations are available yet. Prepare agents in Worldline first." />
      </p>
    );
  }

  return (
    <form action={selectWorldlinePreparationAction} className="binding-form">
      <input name="anchorSessionId" type="hidden" value={anchorSessionId} />
      <label htmlFor="character-preparation-select"><Bi zh="准备记录" en="Preparation" /></label>
      <select id="character-preparation-select" name="prepareId" defaultValue={prepareId}>
        <option value="">{tx(locale, "选择准备记录", "Select preparation")}</option>
        {preparations.items.map((preparation, index) => (
          <option key={preparation.prepare_id} value={preparation.prepare_id}>
            {(preparation.goal_summary || tx(locale, `未命名准备 ${index + 1}`, `Untitled preparation ${index + 1}`))
              + ` · ${preparation.status}`}
          </option>
        ))}
      </select>
      <button type="submit"><Bi zh="载入准备记录" en="Load preparation" /></button>
    </form>
  );
}

function writerRunHref(tenantSlug: string, projectId: string, runId: string) {
  const query = new URLSearchParams();
  query.set("runId", runId);
  return `/${encodeURIComponent(tenantSlug)}/projects/${encodeURIComponent(projectId)}/writer?${query.toString()}`;
}

function CharacterProposalReview({
  action,
  proposals,
}: {
  action: (formData: FormData) => Promise<void>;
  proposals: CharacterProposalsSummary;
}) {
  if (!proposals.ok) {
    if (proposals.code === "CHARACTER_PROPOSALS_NOT_SELECTED") {
      return null;
    }
    return (
      <div className="error-box">
        <p className="form-hint"><FailureText /></p>
      </div>
    );
  }
  if (proposals.items.length === 0) {
    return <p className="form-hint"><Bi zh="暂无互动候选。" en="No interaction proposals are available." /></p>;
  }
  return (
    <div className="stack">
      {proposals.items.map((proposal) => (
        <article className="subtle-card" key={proposal.asset_id}>
          <div className="status-row">
            <span className="status-pill"><StatusValue value={proposal.proposal_type} /></span>
            <span className="status-pill"><StatusValue value={proposal.lifecycle} /></span>
          </div>
          <h3>{proposal.title}</h3>
          <p className="form-hint">{proposal.summary}</p>
          {proposal.lifecycle === "candidate" ? (
            <form action={action} className="binding-form">
              <input type="hidden" name="proposalInteractionId" value={proposal.interaction_id} />
              <input type="hidden" name="proposalAssetId" value={proposal.asset_id} />
              <label htmlFor={`proposal-note-${proposal.asset_id}`}><Bi zh="采用备注" en="Adoption note" /></label>
              <input id={`proposal-note-${proposal.asset_id}`} name="proposalNote" />
              <button type="submit">
                <Check size={16} aria-hidden="true" />
                <Bi zh="采用" en="Adopt" />
              </button>
            </form>
          ) : null}
        </article>
      ))}
    </div>
  );
}

function CharacterRuntimeEvents({ events }: { events: CharacterInteractionEventsSummary }) {
  if (!events.ok) {
    if (events.code === "CHARACTER_INTERACTION_EVENTS_NOT_SELECTED") {
      return null;
    }
    return (
      <div className="error-box">
        <p className="form-hint"><FailureText /></p>
      </div>
    );
  }
  if (events.items.length === 0) {
    return <p className="form-hint"><Bi zh="暂无运行事件。" en="No runtime events are available." /></p>;
  }
  return (
    <div className="stack" aria-label="Character runtime events">
      {events.items.map((event) => (
        <article className="subtle-card" key={event.event_id}>
          <div className="status-row">
            <span className="status-pill"><StatusValue value={event.event_type} /></span>
            <span className="status-pill">#{event.sequence}</span>
          </div>
          <p className="form-hint">
            <StatusValue value={stringMetadata(event.payload.status) || "recorded"} />
            {numberMetadata(event.payload.memory_candidate_count) > 0
              ? ` · memory ${numberMetadata(event.payload.memory_candidate_count)}`
              : ""}
            {numberMetadata(event.payload.relation_candidate_count) > 0
              ? ` · relation ${numberMetadata(event.payload.relation_candidate_count)}`
              : ""}
            {numberMetadata(event.payload.world_state_candidate_count) > 0
              ? ` · world ${numberMetadata(event.payload.world_state_candidate_count)}`
              : ""}
          </p>
        </article>
      ))}
    </div>
  );
}

function stringMetadata(value: unknown) {
  return typeof value === "string" ? value : "";
}

function numberMetadata(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function SelectedPublicTurnReplay({
  selectedTurns,
}: {
  selectedTurns: CharacterInteractionTurnsSummary;
}) {
  if (!selectedTurns.ok) {
    return (
      <div>
        <p className="form-hint"><FailureText /></p>
      </div>
    );
  }

  if (selectedTurns.items.length === 0) {
    return <p className="form-hint"><Bi zh="当前互动暂无回合记录。" en="No turns are recorded for this interaction." /></p>;
  }

  return (
    <div className="stack">
      {selectedTurns.items.map((turn) => (
        <article className="subtle-card" key={turn.turn_id}>
          <div className="status-row">
            <span className="status-pill"><Bi zh="回合" en="Turn" /> {turn.turn_order}</span>
            <span className="status-pill"><StatusValue value={turn.actor_type} /></span>
            <span className="status-pill"><StatusValue value={turn.turn_kind} /></span>
          </div>
          <p className="form-hint">{turn.summary || <Bi zh="暂无摘要。" en="No summary available." />}</p>
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
        <p className="form-hint"><FailureText /></p>
      </div>
    );
  }

  return (
    <div className="stack">
      <article className="subtle-card">
        <div className="status-row">
          <span className="status-pill"><StatusValue value={selectedInteraction.mode} /></span>
          <span className="status-pill"><StatusValue value={selectedInteraction.status} /></span>
          <span className="status-pill">{selectedInteraction.turns.length} <Bi zh="个回合" en="turns" /></span>
        </div>
        <h3>{selectedInteraction.title || <Bi zh="未命名互动" en="Untitled interaction" />}</h3>
        <p className="form-hint">{selectedInteraction.summary || <Bi zh="暂无摘要。" en="No summary available." />}</p>
      </article>

      {selectedInteraction.turns.length > 0 ? (
        selectedInteraction.turns.map((turn) => (
          <article className="subtle-card" key={turn.turn_id}>
            <div className="status-row">
              <span className="status-pill"><Bi zh="回合" en="Turn" /> {turn.turn_order}</span>
              <span className="status-pill"><StatusValue value={turn.actor_type} /></span>
              <span className="status-pill"><StatusValue value={turn.turn_kind} /></span>
            </div>
            <p className="form-hint">{turn.summary || <Bi zh="暂无摘要。" en="No summary available." />}</p>
          </article>
        ))
      ) : (
        <p className="form-hint"><Bi zh="当前互动暂无回合记录。" en="No turns are recorded for this interaction." /></p>
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
      <p className="form-hint">
        {interactionStatus.status === "success" ? <Bi zh="互动已更新。" en="Interaction updated." /> : <Bi zh="操作未完成，请检查输入或稍后重试。" en="The action could not be completed. Check the input or try again." />}
      </p>
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
      <p className="form-hint">
        {turnStatus.status === "success" ? <Bi zh="回合已记录。" en="Turn recorded." /> : <Bi zh="操作未完成，请检查输入或稍后重试。" en="The action could not be completed. Check the input or try again." />}
      </p>
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
    runId: string;
  };
}) {
  if (!runtimeStatus.status) {
    return null;
  }

  const eventsStatus = runtimeStatus.code === "CHARACTER_INTERACTION_EVENTS_AVAILABLE";

  return (
    <div className={runtimeStatus.status === "success" ? "success-box" : "error-box"}>
      <p className="form-hint">
        {runtimeStatus.status === "success" ? (
          eventsStatus
            ? <Bi zh="运行事件已刷新。" en="Runtime events refreshed." />
            : <Bi zh="章节候选草稿任务已提交。" en="Chapter draft request submitted as a candidate." />
        ) : <Bi zh="操作未完成，请检查输入或稍后重试。" en="The action could not be completed. Check the input or try again." />}
      </p>
    </div>
  );
}
