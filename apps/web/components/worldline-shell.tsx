import { ChevronRight, GitBranch } from "lucide-react";

import { Bi, FailureText, StatusValue } from "./bilingual-text";
import type {
  AssetListSummary,
  StoryGraphViewSummary,
  WorldlineEventsSummary,
  WorldlineGoalStartSummary,
  WorldlinePreparationSummary,
  WorldlinePreparedAgentsSummary,
  WorldlineSavedPathsSummary,
  WorldlineSessionsSummary,
  WorldlineTimelineSummary,
} from "../lib/api";
import { encodeJourneyRef } from "../lib/worldline-character-journey";
import { tx, type Locale } from "../lib/locale";
import { SubmitButton } from "./submit-button";
import { WorkspaceHeader } from "./workspace-header";
import { WorkspaceModeSwitcher } from "./workspace-mode-switcher";

type WorldlineShellProps = {
  locale: Locale;
  tenantSlug: string;
  projectId: string;
  savedPaths: WorldlineSavedPathsSummary;
  sessions: WorldlineSessionsSummary;
  timeline: WorldlineTimelineSummary;
  events: WorldlineEventsSummary;
  pathEvents: WorldlineEventsSummary;
  preparation: WorldlinePreparationSummary;
  preparedAgents: WorldlinePreparedAgentsSummary;
  goalStart: WorldlineGoalStartSummary;
  assets: AssetListSummary;
  graphView: StoryGraphViewSummary;
  selectedSessionId: string;
  selectedAgentRefs: string[];
  selectedSourceRefs: string[];
  selectWorldlineSessionAction: (formData: FormData) => Promise<void>;
  refreshWorldlinePreparationAction: (formData: FormData) => Promise<void>;
  refreshWorldlineGoalStartAction: (formData: FormData) => Promise<void>;
  createWorldlineGoalStartAction: (formData: FormData) => Promise<void>;
  startWorldlineStepAction: (formData: FormData) => Promise<void>;
  startWorldlineAutoEvolutionAction: (formData: FormData) => Promise<void>;
  createWorldlinePreparationAction: (formData: FormData) => Promise<void>;
  injectWorldlineVariableAction: (formData: FormData) => Promise<void>;
  createWorldlineSavedPathAction: (formData: FormData) => Promise<void>;
  adoptWorldlineEventAction: (formData: FormData) => Promise<void>;
  updateWorldlineEventAction: (formData: FormData) => Promise<void>;
  worldlineGoalStartStatus: {
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
  worldlineAutoStatus: {
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
  locale,
  projectId,
  tenantSlug,
  savedPaths,
  sessions,
  timeline,
  events,
  pathEvents,
  preparation,
  preparedAgents,
  goalStart,
  assets,
  graphView,
  selectedSessionId,
  selectedAgentRefs,
  selectedSourceRefs,
  selectWorldlineSessionAction,
  refreshWorldlinePreparationAction,
  refreshWorldlineGoalStartAction,
  createWorldlineGoalStartAction,
  startWorldlineStepAction,
  startWorldlineAutoEvolutionAction,
  createWorldlinePreparationAction,
  injectWorldlineVariableAction,
  createWorldlineSavedPathAction,
  adoptWorldlineEventAction,
  updateWorldlineEventAction,
  worldlineGoalStartStatus,
  worldlineStepStatus,
  worldlineAutoStatus,
  worldlinePreparationStatus,
  worldlineVariableStatus,
  worldlineSavedPathStatus,
  worldlineEventAdoptionStatus,
  worldlineEventMutationStatus,
}: WorldlineShellProps) {
  const activeSessions = sessions.ok
    ? sessions.items.filter((session) => session.lifecycle === "active")
    : [];
  const activeSessionId = activeSessions.some((session) => session.session_id === selectedSessionId)
    ? selectedSessionId
    : activeSessions[0]?.session_id ?? "";

  return (
    <div className="worldline-root">
      <WorkspaceHeader
        className="worldline-header"
        description={<Bi zh="在当前世界中推演剧情。" en="Simulate story events in the current world." />}
        icon={<GitBranch size={22} strokeWidth={1.8} />}
        meta={(
          <>
            <span className="status-pill">{activeSessionId ? <Bi zh="推演中" en="Active" /> : <Bi zh="尚未开始" en="Not started" />}</span>
            <span className="status-pill">
              {timeline.ok ? timeline.items.length : "—"} <Bi zh="条时间线" en="timeline" />
            </span>
          </>
        )}
        title={<Bi zh="世界线" en="Worldline" />}
      />

      <div className="workbench-grid worldline-workbench">
        <main>
          <WorkspaceModeSwitcher
            aria-label={tx(locale, "世界线工作模式", "Worldline workspace mode")}
            defaultMode={activeSessionId ? "simulate" : "start"}
            modes={[
              { id: "start", label: <Bi zh="开始" en="Start" /> },
              { id: "simulate", label: <Bi zh="推演" en="Simulate" /> },
              { id: "records", label: <Bi zh="记录" en="Records" /> },
            ]}
            panels={{
              start: (
          <section className="panel" aria-labelledby="start-session-heading" data-worldline-mode="start">
            <p className="eyebrow"><Bi zh="推演" en="Session" /></p>
            <h2 id="start-session-heading"><Bi zh="开始推演" en="Start session" /></h2>
            <p className="form-hint">
              <Bi
                zh="只需写下推演目标。智能体会分析所需角色与上下文，自动准备后直接开始推演。"
                en="Enter the simulation goal. The agent selects cast and context, prepares dossiers, then starts the session."
              />
            </p>
            <GoalStartStatusLine worldlineGoalStartStatus={worldlineGoalStartStatus} />
            <form action={createWorldlineGoalStartAction} className="binding-form">
              <label htmlFor="worldline-session-goal"><Bi zh="目标" en="Goal" /></label>
              <textarea
                id="worldline-session-goal"
                name="goal"
                placeholder={tx(locale, "描述本次推演要探索的情节结果", "Describe the story consequence to explore")}
                required
                rows={4}
              />

              <label htmlFor="worldline-anchor-path"><Bi zh="参考路径" en="Anchor path" /></label>
              {savedPaths.ok && savedPaths.items.length > 0 ? (
                <select id="worldline-anchor-path" name="anchorPathId" defaultValue="">
                  <option value="">{tx(locale, "不使用参考路径", "No anchor path")}</option>
                  {savedPaths.items.map((path, index) => (
                    <option key={path.path_id} value={path.path_id}>
                      {path.title || tx(locale, `未命名路径 ${index + 1}`, `Untitled path ${index + 1}`)}
                    </option>
                  ))}
                </select>
              ) : (
                <select
                  id="worldline-anchor-path"
                  name="anchorPathId"
                  disabled
                ><option value="">{tx(locale, "暂无参考路径", "No saved path available")}</option></select>
              )}
              <SubmitButton idleLabel={<Bi zh="开始推演" en="Start session" />} pendingLabel={<Bi zh="分析并启动中…" en="Casting…" />} />
            </form>
            <GoalStartProgress
              goalStart={goalStart}
              locale={locale}
              refreshWorldlineGoalStartAction={refreshWorldlineGoalStartAction}
            />
          </section>
              ),
              records: (
                <>
          <section
            aria-labelledby="saved-paths-heading"
            className={`panel ${savedPaths.ok ? "" : "error-box"}`}
            data-worldline-mode="records"
          >
            <p className="eyebrow"><Bi zh="参考" en="References" /></p>
            <h2 id="saved-paths-heading"><Bi zh="已保存路径" en="Saved paths" /></h2>
            <SavedPathList savedPaths={savedPaths} />
          </section>

          <section
            aria-labelledby="session-history-heading"
            className={`panel ${sessions.ok ? "" : "error-box"}`}
            data-worldline-mode="records"
          >
            <p className="eyebrow"><Bi zh="历史" en="Sessions" /></p>
            <h2 id="session-history-heading"><Bi zh="推演记录" en="Session history" /></h2>
            <SessionList sessions={sessions} />
            <form action={selectWorldlineSessionAction} className="binding-form">
              <label htmlFor="worldline-current-session"><Bi zh="当前世界" en="Current world" /></label>
              <select id="worldline-current-session" name="selectedSessionId" defaultValue={activeSessionId} disabled={activeSessions.length === 0}>
                {activeSessions.length === 0 ? <option value="">{tx(locale, "没有 active 推演", "No active session")}</option> : null}
                {activeSessions.map((session, index) => (
                  <option key={session.session_id} value={session.session_id}>{session.goal_summary || tx(locale, `未命名推演 ${index + 1}`, `Untitled session ${index + 1}`)}</option>
                ))}
              </select>
              <SubmitButton disabled={activeSessions.length === 0} idleLabel={<Bi zh="载入当前世界" en="Load current world" />} pendingLabel={<Bi zh="载入中…" en="Loading…" />} />
            </form>
          </section>
                </>
              ),
              simulate: (
                <>
          <section
            className={`panel worldline-timeline-primary ${timeline.ok ? "" : "error-box"}`}
            aria-labelledby="worldline-timeline-heading"
            data-worldline-mode="simulate"
          >
            <p className="eyebrow"><Bi zh="当前世界" en="Current world" /></p>
            <h2 id="worldline-timeline-heading"><Bi zh="时间线" en="Timeline" /></h2>
            <TimelineList timeline={timeline} />
          </section>

          <section className="panel worldline-simulate-toolbar" aria-labelledby="step-session-heading" data-worldline-mode="simulate">
            <p className="eyebrow"><Bi zh="推进" en="Progress" /></p>
            <h2 id="step-session-heading"><Bi zh="推演操作" en="Simulation controls" /></h2>
            <StepStatusLine worldlineStepStatus={worldlineStepStatus} />
            <form action={startWorldlineStepAction} className="binding-form worldline-toolbar-form">
              <input type="hidden" name="sessionId" value={activeSessionId} />
              {preparation.ok ? <input type="hidden" name="prepareId" value={preparation.prepare_id} /> : null}
              <label htmlFor="worldline-step-mode"><Bi zh="模式" en="Mode" /></label>
              <select id="worldline-step-mode" name="stepMode" defaultValue="director" disabled={!activeSessionId}>
                <option value="director">{tx(locale, "导演", "Director")}</option>
                <option value="agent_turn">{tx(locale, "角色回合", "Agent turn")}</option>
                <option value="evaluation">{tx(locale, "评估", "Evaluation")}</option>
              </select>
              <SubmitButton disabled={!activeSessionId} idleLabel={<Bi zh="推进一步" en="Step once" />} pendingLabel={<Bi zh="推进中…" en="Stepping…" />} />
            </form>
            <details className="worldline-module-group">
              <summary>
                <span><Bi zh="多步与变量" en="Auto steps and variables" /></span>
                <small><Bi zh="次要控制" en="Secondary controls" /></small>
              </summary>
              <div className="worldline-module-content">
                <AutoStatusLine worldlineAutoStatus={worldlineAutoStatus} />
                <form action={startWorldlineAutoEvolutionAction} className="binding-form">
                  <input type="hidden" name="sessionId" value={activeSessionId} />
                  <label htmlFor="worldline-auto-max-steps"><Bi zh="最大步数" en="Maximum steps" /></label>
                  <input id="worldline-auto-max-steps" name="maxSteps" type="number" min={1} max={50} defaultValue={3} inputMode="numeric" disabled={!activeSessionId} />
                  <SubmitButton tone="secondary" disabled={!activeSessionId} idleLabel={<Bi zh="多步推演" en="Auto evolve" />} pendingLabel={<Bi zh="启动中…" en="Starting…" />} />
                </form>
                <VariableStatusLine worldlineVariableStatus={worldlineVariableStatus} />
                <form action={injectWorldlineVariableAction} className="binding-form">
                  <input type="hidden" name="sessionId" value={activeSessionId} />
                  <label htmlFor="worldline-variable-name"><Bi zh="名称" en="Name" /></label>
                  <input id="worldline-variable-name" name="variableName" placeholder={tx(locale, "变量名称", "Variable name")} required disabled={!activeSessionId} />
                  <label htmlFor="worldline-variable-description"><Bi zh="描述" en="Description" /></label>
                  <textarea id="worldline-variable-description" name="variableDescription" placeholder={tx(locale, "描述变量及其情节作用", "Describe the variable and its story effect")} rows={2} disabled={!activeSessionId} />
                  <label htmlFor="worldline-variable-impact-axis"><Bi zh="影响方向" en="Story impact" /></label>
                  <input id="worldline-variable-impact-axis" name="impactAxis" placeholder={tx(locale, "例如：亲族关系压力", "For example: family relationship pressure")} disabled={!activeSessionId} />
                  <label className="checkbox-row" htmlFor="worldline-variable-locked">
                    <input id="worldline-variable-locked" name="locked" type="checkbox" disabled={!activeSessionId} />
                    <Bi zh="锁定变量" en="Lock variable" />
                  </label>
                  <SubmitButton tone="secondary" disabled={!activeSessionId} idleLabel={<Bi zh="注入变量" en="Inject variable" />} pendingLabel={<Bi zh="注入中…" en="Injecting…" />} />
                </form>
              </div>
            </details>
          </section>

          <section
            className={`panel ${events.ok ? "" : "error-box"}`}
            aria-labelledby="worldline-events-heading"
            data-worldline-mode="simulate"
          >
            <p className="eyebrow"><Bi zh="候选" en="Candidates" /></p>
            <h2 id="worldline-events-heading"><Bi zh="候选事件" en="Candidate events" /></h2>
            <EventList events={events} />
          </section>
                </>
              ),
            }}
          />
        </main>

        <aside>
          <details className="worldline-module-group worldline-module-group-dark" open={preparation.ok}>
            <summary>
              <span><Bi zh="高级：手动选角" en="Advanced: manual cast" /></span>
              <small>{preparedAgents.ok ? preparedAgents.items.length : 0} <Bi zh="名角色" en="agents" /></small>
            </summary>
            <div className="worldline-module-content">
          <section className="panel" aria-labelledby="prepare-agents-heading">
            <p className="eyebrow"><Bi zh="可选" en="Optional" /></p>
            <h2 id="prepare-agents-heading"><Bi zh="手动准备角色" en="Prepare agents manually" /></h2>
            <p className="form-hint">
              <Bi
                zh="默认请在左侧只填写目标；这里仅供需要精确指定角色时使用。"
                en="Prefer the goal-only start flow; use this only when you need an exact cast."
              />
            </p>
            <PreparationStatusLine worldlinePreparationStatus={worldlinePreparationStatus} />
            <form action={createWorldlinePreparationAction} className="binding-form">
              <label htmlFor="worldline-preparation-goal"><Bi zh="目标" en="Goal" /></label>
              <textarea
                id="worldline-preparation-goal"
                name="preparationGoal"
                placeholder={tx(locale, "描述角色需要参与的互动", "Describe the interaction to prepare")}
                required
                rows={4}
              />

              <label htmlFor="worldline-preparation-anchor-path"><Bi zh="参考路径" en="Anchor path" /></label>
              {savedPaths.ok && savedPaths.items.length > 0 ? (
                <select
                  id="worldline-preparation-anchor-path"
                  name="preparationAnchorPathId"
                  defaultValue=""
                >
                  <option value="">{tx(locale, "不使用参考路径", "No anchor path")}</option>
                  {savedPaths.items.map((path, index) => (
                    <option key={path.path_id} value={path.path_id}>
                      {path.title || tx(locale, `未命名路径 ${index + 1}`, `Untitled path ${index + 1}`)}
                    </option>
                  ))}
                </select>
              ) : (
                <select
                  id="worldline-preparation-anchor-path"
                  name="preparationAnchorPathId"
                  disabled
                ><option value="">{tx(locale, "暂无参考路径", "No saved path available")}</option></select>
              )}
              <TypedReferenceChoices
                assets={assets}
                events={events}
                graphView={graphView}
                savedPaths={savedPaths}
                selectedAgentRefs={selectedAgentRefs}
                selectedSourceRefs={selectedSourceRefs}
              />
              <button type="submit"><Bi zh="准备角色" en="Prepare agents" /></button>
            </form>
          </section>

          <section
            className={`panel ${preparation.ok && preparedAgents.ok ? "" : "error-box"}`}
            aria-labelledby="prepared-agents-heading"
          >
            <p className="eyebrow"><Bi zh="角色" en="Agents" /></p>
            <h2 id="prepared-agents-heading"><Bi zh="已准备角色" en="Prepared agents" /></h2>
            <PreparationDetail preparation={preparation} preparedAgents={preparedAgents} />
            {preparation.ok && (preparation.status === "completed" || preparation.status === "ready") ? (
              <a
                className="overview-next-link"
                href={characterConsoleHref(tenantSlug, projectId, preparation.prepare_id, activeSessionId)}
              >
                <Bi zh="进入角色" en="Enter Characters" />
                <ChevronRight aria-hidden="true" size={18} />
              </a>
            ) : null}
            {preparation.ok ? (
              <form action={refreshWorldlinePreparationAction} className="binding-form">
                <input type="hidden" name="prepareId" value={preparation.prepare_id} />
                <input type="hidden" name="selectedAgentRefs" value={selectedAgentRefs.join(",")} />
                <input type="hidden" name="selectedSourceRefs" value={selectedSourceRefs.join(",")} />
                <button type="submit"><Bi zh="刷新准备状态与角色" en="Refresh preparation and roster" /></button>
              </form>
            ) : null}
          </section>
            </div>
          </details>

          <details className="worldline-module-group worldline-module-group-dark">
            <summary>
              <span><Bi zh="事件与路径" en="Events and paths" /></span>
              <small><Bi zh="编辑、采纳与保存" en="Edit, adopt and save" /></small>
            </summary>
            <div className="worldline-module-content">
          <section className="panel" aria-labelledby="edit-event-heading">
            <p className="eyebrow"><Bi zh="候选事件" en="Candidate event" /></p>
            <h2 id="edit-event-heading"><Bi zh="编辑事件" en="Edit event" /></h2>
            <EventMutationStatusLine worldlineEventMutationStatus={worldlineEventMutationStatus} />
            <form action={updateWorldlineEventAction} className="binding-form">
              <label htmlFor="worldline-edit-event"><Bi zh="候选事件" en="Candidate event" /></label>
              {events.ok && events.items.length > 0 ? (
                <select id="worldline-edit-event" name="eventId" defaultValue="">
                  <option value="">{tx(locale, "选择候选事件", "Select candidate event")}</option>
                  {events.items.map((event, index) => (
                    <option key={event.event_id} value={event.event_id}>
                      {event.title || tx(locale, `未命名事件 ${index + 1}`, `Untitled event ${index + 1}`)}
                    </option>
                  ))}
                </select>
              ) : (
                <select id="worldline-edit-event" name="eventId" disabled><option value="">{tx(locale, "暂无候选事件", "No candidate event")}</option></select>
              )}

              <label htmlFor="worldline-event-title"><Bi zh="标题" en="Title" /></label>
              <input
                id="worldline-event-title"
                name="eventTitle"
                placeholder={tx(locale, "事件标题", "Event title")}
              />

              <label htmlFor="worldline-event-summary"><Bi zh="摘要" en="Summary" /></label>
              <textarea
                id="worldline-event-summary"
                name="eventSummary"
                placeholder={tx(locale, "事件摘要", "Event summary")}
                rows={3}
              />

              <label htmlFor="worldline-event-kind"><Bi zh="类型" en="Kind" /></label>
              <select
                id="worldline-event-kind"
                name="eventKind"
                defaultValue="director_revision"
              >
                <option value="director_revision">{tx(locale, "导演修订", "Director revision")}</option>
                <option value="plot_turn">{tx(locale, "剧情转折", "Plot turn")}</option>
                <option value="character_choice">{tx(locale, "角色选择", "Character choice")}</option>
              </select>

              <button type="submit"><Bi zh="更新事件" en="Update event" /></button>
            </form>
          </section>

          <section className="panel" aria-labelledby="adopt-event-heading">
            <p className="eyebrow"><Bi zh="正史" en="Canon" /></p>
            <h2 id="adopt-event-heading"><Bi zh="采纳事件" en="Adopt event" /></h2>
            <EventAdoptionStatusLine worldlineEventAdoptionStatus={worldlineEventAdoptionStatus} />
            <form action={adoptWorldlineEventAction} className="binding-form">
              <label htmlFor="worldline-adopt-event"><Bi zh="候选事件" en="Candidate event" /></label>
              {events.ok && events.items.length > 0 ? (
                <select id="worldline-adopt-event" name="eventId" defaultValue="">
                  <option value="">{tx(locale, "选择候选事件", "Select candidate event")}</option>
                  {events.items.map((event, index) => (
                    <option key={event.event_id} value={event.event_id}>
                      {event.title || tx(locale, `未命名事件 ${index + 1}`, `Untitled event ${index + 1}`)}
                    </option>
                  ))}
                </select>
              ) : (
                <select id="worldline-adopt-event" name="eventId" disabled><option value="">{tx(locale, "暂无候选事件", "No candidate event")}</option></select>
              )}

              <label htmlFor="worldline-adoption-note"><Bi zh="备注" en="Note" /></label>
              <textarea
                id="worldline-adoption-note"
                name="adoptionNote"
                placeholder={tx(locale, "采纳备注", "Adoption note")}
                rows={3}
              />

              <button type="submit"><Bi zh="采纳事件" en="Adopt event" /></button>
            </form>
          </section>

          <section className="panel" aria-labelledby="save-path-heading">
            <p className="eyebrow"><Bi zh="参考" en="Reference" /></p>
            <h2 id="save-path-heading"><Bi zh="保存路径" en="Save path" /></h2>
            <SavedPathStatusLine worldlineSavedPathStatus={worldlineSavedPathStatus} />
            <form action={createWorldlineSavedPathAction} className="binding-form">
              <label htmlFor="worldline-save-path-session"><Bi zh="推演" en="Session" /></label>
              {sessions.ok && sessions.items.length > 0 ? (
                <select
                  id="worldline-save-path-session"
                  name="sessionId"
                  defaultValue={activeSessionId}
                >
                  {sessions.items.map((session, index) => (
                    <option key={session.session_id} value={session.session_id}>
                      {session.goal_summary || tx(locale, `未命名推演 ${index + 1}`, `Untitled session ${index + 1}`)}
                    </option>
                  ))}
                </select>
              ) : (
                <select
                  id="worldline-save-path-session"
                  name="sessionId"
                  disabled
                ><option value="">{tx(locale, "暂无可用推演", "No session available")}</option></select>
              )}

              <label htmlFor="worldline-saved-path-title"><Bi zh="标题" en="Title" /></label>
              <input
                id="worldline-saved-path-title"
                name="savedPathTitle"
                placeholder="雨夜谈判路线"
                required
              />

              <label htmlFor="worldline-saved-path-summary"><Bi zh="摘要" en="Summary" /></label>
              <textarea
                id="worldline-saved-path-summary"
                name="savedPathSummary"
                placeholder={tx(locale, "路径摘要", "Path summary")}
                rows={3}
              />

              <fieldset className="checkbox-group">
                <legend><Bi zh="推演事件" en="Session events" /></legend>
                {pathEvents.ok && pathEvents.items.length > 0 ? (
                  pathEvents.items.map((event, index) => (
                    <label className="checkbox-row" key={event.event_id}>
                      <input name="selectedEventIds" type="checkbox" value={event.event_id} />
                      <span>{event.title || tx(locale, `未命名事件 ${index + 1}`, `Untitled event ${index + 1}`)}</span>
                    </label>
                  ))
                ) : (
                  <p className="form-hint">
                    {pathEvents.ok
                      ? <Bi zh="当前推演暂无事件。" en="No events are available for this session." />
                      : <FailureText />}
                  </p>
                )}
              </fieldset>

              <label htmlFor="worldline-writer-instruction"><Bi zh="写作要求" en="Writer instruction" /></label>
              <textarea
                id="worldline-writer-instruction"
                name="writerInstruction"
                placeholder={tx(locale, "说明写作台如何使用这条路径", "How Writer should use this path")}
                rows={3}
              />
              <button type="submit"><Bi zh="保存路径" en="Save path" /></button>
            </form>
          </section>
            </div>
          </details>
        </aside>
      </div>
    </div>
  );
}

function GoalStartStatusLine({
  worldlineGoalStartStatus,
}: {
  worldlineGoalStartStatus: WorldlineShellProps["worldlineGoalStartStatus"];
}) {
  if (!worldlineGoalStartStatus.status) {
    return null;
  }
  return (
    <ActionFeedback
      code={worldlineGoalStartStatus.code}
      status={worldlineGoalStartStatus.status}
      successEn="Goal-start queued. Cast analysis is running."
      successZh="已提交目标驱动启动，正在分析选角。"
    />
  );
}

function GoalStartProgress({
  goalStart,
  locale,
  refreshWorldlineGoalStartAction,
}: {
  goalStart: WorldlineGoalStartSummary;
  locale: Locale;
  refreshWorldlineGoalStartAction: (formData: FormData) => Promise<void>;
}) {
  if (!goalStart.ok) {
    return null;
  }
  const agentRefs = goalStart.agent_refs ?? [];
  const sourceRefs = goalStart.source_refs ?? [];
  return (
    <div className="binding-stack worldline-goal-start-progress" data-goal-start-status={goalStart.status}>
      <article className="reference-card">
        <div className="status-row">
          <span className="status-pill"><StatusValue value={goalStart.status} /></span>
          {goalStart.prepare_id ? <span className="status-pill"><Bi zh="已准备" en="Prepared" /></span> : null}
          {goalStart.session_id ? <span className="status-pill"><Bi zh="已开推演" en="Session ready" /></span> : null}
        </div>
        <h3>{goalStart.goal || <Bi zh="目标驱动推演" en="Goal-driven session" />}</h3>
        {goalStart.rationale ? <p className="form-hint">{goalStart.rationale}</p> : null}
        {goalStart.error_message ? <p className="form-hint error-box">{goalStart.error_message}</p> : null}
      </article>
      <fieldset className="checkbox-group">
        <legend><Bi zh="参与角色（自动）" en="Agent refs (auto)" /></legend>
        {agentRefs.length === 0 ? (
          <p className="form-hint"><Bi zh="智能体尚未提交角色。" en="Cast has not been committed yet." /></p>
        ) : (
          agentRefs.map((ref) => (
            <p className="form-hint" key={encodeJourneyRef(ref)}>
              <strong>{ref.source_kind}</strong> {ref.source_id}
            </p>
          ))
        )}
      </fieldset>
      <fieldset className="checkbox-group">
        <legend><Bi zh="上下文来源（自动）" en="Source refs (auto)" /></legend>
        {sourceRefs.length === 0 ? (
          <p className="form-hint"><Bi zh="暂无额外上下文来源。" en="No extra context sources yet." /></p>
        ) : (
          sourceRefs.map((ref) => (
            <p className="form-hint" key={encodeJourneyRef(ref)}>
              <strong>{ref.source_kind}</strong> {ref.source_id}
            </p>
          ))
        )}
      </fieldset>
      {goalStart.status !== "ready" && goalStart.status !== "failed" ? (
        <form action={refreshWorldlineGoalStartAction} className="binding-form">
          <input type="hidden" name="goalStartRunId" value={goalStart.run_id} />
          <SubmitButton
            idleLabel={<Bi zh="刷新进度" en="Refresh progress" />}
            pendingLabel={<Bi zh="刷新中…" en="Refreshing…" />}
          />
          <p className="form-hint">
            {tx(locale, "选角与准备完成后会自动进入推演。", "The session starts automatically after cast and prepare finish.")}
          </p>
        </form>
      ) : null}
    </div>
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
  return <ActionFeedback code={worldlineStepStatus.code} status={worldlineStepStatus.status} successEn="Session step queued." successZh="推演推进已提交。" />;
}

function AutoStatusLine({
  worldlineAutoStatus,
}: {
  worldlineAutoStatus: WorldlineShellProps["worldlineAutoStatus"];
}) {
  if (!worldlineAutoStatus.status) return null;
  return <ActionFeedback code={worldlineAutoStatus.code} status={worldlineAutoStatus.status} successEn="Auto evolution queued for the active current world." successZh="当前世界多步推演已提交。" />;
}

function PreparationStatusLine({
  worldlinePreparationStatus,
}: {
  worldlinePreparationStatus: WorldlineShellProps["worldlinePreparationStatus"];
}) {
  if (!worldlinePreparationStatus.status) {
    return null;
  }
  return <ActionFeedback code={worldlinePreparationStatus.code} status={worldlinePreparationStatus.status} successEn="Agents prepared." successZh="角色准备完成。" />;
}

function VariableStatusLine({
  worldlineVariableStatus,
}: {
  worldlineVariableStatus: WorldlineShellProps["worldlineVariableStatus"];
}) {
  if (!worldlineVariableStatus.status) {
    return null;
  }
  return <ActionFeedback code={worldlineVariableStatus.code} status={worldlineVariableStatus.status} successEn="Variable injected." successZh="变量已注入。" />;
}

function SavedPathStatusLine({
  worldlineSavedPathStatus,
}: {
  worldlineSavedPathStatus: WorldlineShellProps["worldlineSavedPathStatus"];
}) {
  if (!worldlineSavedPathStatus.status) {
    return null;
  }
  return <ActionFeedback code={worldlineSavedPathStatus.code} status={worldlineSavedPathStatus.status} successEn="Path saved." successZh="路径已保存。" />;
}

function EventAdoptionStatusLine({
  worldlineEventAdoptionStatus,
}: {
  worldlineEventAdoptionStatus: WorldlineShellProps["worldlineEventAdoptionStatus"];
}) {
  if (!worldlineEventAdoptionStatus.status) {
    return null;
  }
  return <ActionFeedback code={worldlineEventAdoptionStatus.code} status={worldlineEventAdoptionStatus.status} successEn="Event adopted." successZh="事件已采纳。" />;
}

function EventMutationStatusLine({
  worldlineEventMutationStatus,
}: {
  worldlineEventMutationStatus: WorldlineShellProps["worldlineEventMutationStatus"];
}) {
  if (!worldlineEventMutationStatus.status) {
    return null;
  }
  return <ActionFeedback code={worldlineEventMutationStatus.code} status={worldlineEventMutationStatus.status} successEn="Event updated." successZh="事件已更新。" />;
}

function ActionFeedback({
  code: _code,
  status,
  successEn,
  successZh,
}: {
  code: string;
  status: string;
  successEn: string;
  successZh: string;
}) {
  const success = status === "success";
  return (
    <p className={`form-status ${success ? "success-box" : "error-box"}`} data-status={status}>
      {success ? (
        <Bi zh={successZh} en={successEn} />
      ) : (
        <Bi zh="操作未完成，请检查输入或稍后重试。" en="The action could not be completed. Check the input or try again." />
      )}
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
        <FailureText />
      </p>
    );
  }

  return (
    <div className="binding-stack">
      <article className="reference-card">
        <div className="status-row">
          <span className="status-pill"><StatusValue value={preparation.status} /></span>
          <span className="status-pill"><StatusValue value={preparation.lifecycle} /></span>
        </div>
        <h3>{preparation.goal_summary || <Bi zh="未命名角色准备" en="Untitled preparation" />}</h3>
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
        <FailureText />
      </p>
    );
  }
  if (preparedAgents.items.length === 0) {
    return (
      <p className="form-hint">
        <Bi zh="当前准备中暂无角色。" en="No agents are available for this preparation." />
      </p>
    );
  }
  return (
    <div className="binding-stack">
      {preparedAgents.items.map((agent) => (
        <article className="reference-card" key={agent.agent_id}>
          <div className="status-row">
            <span className="status-pill"><StatusValue value={agent.status} /></span>
            <span className="status-pill">{agent.role || <Bi zh="角色" en="Agent" />}</span>
          </div>
          <h3>{agent.display_name || agent.agent_id}</h3>
          <p className="form-hint">{agent.summary || <Bi zh="暂无摘要。" en="No summary available." />}</p>
        </article>
      ))}
    </div>
  );
}

function TypedReferenceChoices({
  assets,
  events,
  graphView,
  savedPaths,
  selectedAgentRefs,
  selectedSourceRefs,
}: {
  assets: AssetListSummary;
  events: WorldlineEventsSummary;
  graphView: StoryGraphViewSummary;
  savedPaths: WorldlineSavedPathsSummary;
  selectedAgentRefs: string[];
  selectedSourceRefs: string[];
}) {
  const selectableAssets = assets.ok
    ? assets.items.filter((asset) => asset.enabled && asset.lifecycle !== "archived").slice(0, 60)
    : [];
  const selectableEntities = graphView.ok
    ? graphView.nodes.filter((node) => node.lifecycle !== "archived").slice(0, 60)
    : [];
  return (
    <>
      <details className="worldline-reference-disclosure">
        <summary><Bi zh="选择角色与上下文" en="Choose agents and context" /></summary>
        <div className="worldline-reference-content">
      <fieldset className="checkbox-group">
        <legend><Bi zh="参与角色引用" en="Agent refs" /></legend>
        {selectableAssets.map((asset) => (
          <label className="checkbox-row" key={`agent-asset-${asset.asset_id}`}>
            <input name="agentRefs" type="checkbox" value={`asset:${asset.asset_id}`} defaultChecked={selectedAgentRefs.includes(`asset:${asset.asset_id}`)} />
            <span><strong>Asset</strong> {asset.title || asset.asset_id}</span>
          </label>
        ))}
        {selectableEntities.map((entity) => {
          const entityRef = graphEntitySelectionRef(entity);
          return (
          <label className="checkbox-row" key={`agent-entity-${entity.node_id}`}>
            <input name="agentRefs" type="checkbox" value={entityRef} defaultChecked={selectedAgentRefs.includes(entityRef) || selectedAgentRefs.includes(`entity:${entity.node_id}`)} />
            <span><strong><Bi zh="故事角色" en="Story entity" /></strong> {entity.title || <Bi zh="未命名节点" en="Untitled node" />}</span>
          </label>
          );
        })}
        {selectableAssets.length + selectableEntities.length === 0 ? (
          <p className="form-hint"><Bi zh="没有可用的真实 Asset 或 Entity；准备请求不会生成占位角色。" en="No real Asset or Entity is available; preparation will not create placeholder agents." /></p>
        ) : null}
      </fieldset>
      <fieldset className="checkbox-group">
        <legend><Bi zh="上下文来源引用" en="Source refs" /></legend>
        {selectableAssets.map((asset) => (
          <label className="checkbox-row" key={`source-asset-${asset.asset_id}`}>
            <input name="sourceRefs" type="checkbox" value={`asset:${asset.asset_id}`} defaultChecked={selectedSourceRefs.includes(`asset:${asset.asset_id}`)} />
            <span><strong>Asset</strong> {asset.title || asset.asset_id}</span>
          </label>
        ))}
        {selectableEntities.map((entity) => {
          const entityRef = graphEntitySelectionRef(entity);
          return (
          <label className="checkbox-row" key={`source-entity-${entity.node_id}`}>
            <input name="sourceRefs" type="checkbox" value={entityRef} defaultChecked={selectedSourceRefs.includes(entityRef) || selectedSourceRefs.includes(`entity:${entity.node_id}`)} />
            <span><strong><Bi zh="故事节点" en="Story entity" /></strong> {entity.title || <Bi zh="未命名节点" en="Untitled node" />}</span>
          </label>
          );
        })}
        {savedPaths.ok ? savedPaths.items.map((path) => (
          <label className="checkbox-row" key={`source-path-${path.path_id}`}>
            <input name="sourceRefs" type="checkbox" value={`saved_path:${path.path_id}`} defaultChecked={selectedSourceRefs.includes(`saved_path:${path.path_id}`)} />
            <span><strong><Bi zh="已保存路径" en="Saved path" /></strong> {path.title || <Bi zh="未命名路径" en="Untitled path" />}</span>
          </label>
        )) : null}
        {events.ok ? events.items.map((event) => (
          <label className="checkbox-row" key={`source-event-${event.event_id}`}>
            <input name="sourceRefs" type="checkbox" value={`worldline_event:${event.event_id}`} defaultChecked={selectedSourceRefs.includes(`worldline_event:${event.event_id}`)} />
            <span><strong><Bi zh="世界线事件" en="Worldline event" /></strong> {event.title || <Bi zh="未命名事件" en="Untitled event" />}</span>
          </label>
        )) : null}
      </fieldset>
      {!assets.ok ? <p className="form-hint"><FailureText /></p> : null}
      {!graphView.ok ? <p className="form-hint"><FailureText /></p> : null}
        </div>
      </details>
    </>
  );
}

function SessionList({ sessions }: { sessions: WorldlineSessionsSummary }) {
  if (!sessions.ok) {
    return (
      <p className="form-hint">
        <FailureText />
      </p>
    );
  }
  if (sessions.items.length === 0) {
    return <p className="form-hint"><Bi zh="该项目暂无推演记录。" en="No worldline sessions are available for this project." /></p>;
  }

  return (
    <div className="binding-stack">
      {sessions.items.map((session) => (
        <article className="reference-card" key={session.session_id}>
          <div className="status-row">
            <span className="status-pill"><StatusValue value={session.status} /></span>
            <span className="status-pill"><StatusValue value={session.lifecycle} /></span>
          </div>
          <h3>{session.goal_summary || <Bi zh="未命名推演" en="Untitled session" />}</h3>
        </article>
      ))}
    </div>
  );
}

function TimelineList({ timeline }: { timeline: WorldlineTimelineSummary }) {
  if (!timeline.ok) {
    return (
      <p className="form-hint">
        <FailureText />
      </p>
    );
  }
  if (timeline.items.length === 0) {
    return <p className="form-hint"><Bi zh="当前推演暂无时间线事件。" en="No timeline events are available for this session." /></p>;
  }

  return (
    <div className="binding-stack">
      {timeline.items.map((event) => (
        <article className="reference-card" key={event.event_id}>
          <div className="status-row">
            <span className="status-pill">#{event.sequence}</span>
            <span className="status-pill"><StatusValue value={event.status || event.event_type} /></span>
            {event.kind ? <span className="status-pill">{event.kind}</span> : null}
          </div>
          <h3>{event.title || event.event_type}</h3>
          <p className="form-hint">{event.summary || <Bi zh="暂无摘要。" en="No summary available." />}</p>
        </article>
      ))}
    </div>
  );
}

function EventList({ events }: { events: WorldlineEventsSummary }) {
  if (!events.ok) {
    return (
      <p className="form-hint">
        <FailureText />
      </p>
    );
  }
  if (events.items.length === 0) {
    return <p className="form-hint"><Bi zh="当前推演暂无候选事件。" en="No candidate events are available for this session." /></p>;
  }

  return (
    <div className="binding-stack">
      {events.items.map((event) => (
        <article className="reference-card" key={event.event_id}>
          <div className="status-row">
            <span className="status-pill"><Bi zh="步骤" en="Step" /> {event.step}</span>
            <span className="status-pill"><StatusValue value={event.status} /></span>
            <span className="status-pill"><StatusValue value={event.lifecycle} /></span>
            {event.kind ? <span className="status-pill">{event.kind}</span> : null}
          </div>
          <h3>{event.title || <Bi zh="未命名事件" en="Untitled event" />}</h3>
          <p className="form-hint">{event.summary || <Bi zh="暂无摘要。" en="No summary available." />}</p>
        </article>
      ))}
    </div>
  );
}

function characterConsoleHref(
  tenantSlug: string,
  projectId: string,
  prepareId: string,
  anchorSessionId: string,
) {
  const query = new URLSearchParams();
  query.set("prepare_id", prepareId);
  if (anchorSessionId) {
    query.set("anchor_session_id", anchorSessionId);
  }
  return `/${encodeURIComponent(tenantSlug)}/projects/${encodeURIComponent(projectId)}/character-console?${query.toString()}`;
}

function graphEntitySelectionRef(entity: {
  node_id: string;
  attributes?: Record<string, unknown>;
  canonical_entity_id?: string;
}): string {
  const fromField =
    typeof entity.canonical_entity_id === "string" ? entity.canonical_entity_id.trim() : "";
  const fromAttributes =
    entity.attributes && typeof entity.attributes.canonical_entity_id === "string"
      ? entity.attributes.canonical_entity_id.trim()
      : "";
  // Prefer canonical entity id when the graph view exposes it; otherwise send node_id.
  // Worker resolves story_graph_nodes.node_id -> entities.entity_id when needed.
  return `entity:${fromField || fromAttributes || entity.node_id}`;
}

function SavedPathList({ savedPaths }: { savedPaths: WorldlineSavedPathsSummary }) {
  if (!savedPaths.ok) {
    return (
      <p className="form-hint">
        <FailureText />
      </p>
    );
  }
  if (savedPaths.items.length === 0) {
    return <p className="form-hint"><Bi zh="该项目暂无已保存路径。" en="No saved paths are available for this project." /></p>;
  }

  return (
    <div className="binding-stack">
      {savedPaths.items.map((path) => (
        <article className="reference-card" key={path.path_id}>
          <div className="status-row">
            <span className="status-pill"><StatusValue value={path.lifecycle} /></span>
            <span className="status-pill">{path.selected_event_ids.length} <Bi zh="个事件" en="events" /></span>
          </div>
          <h3>{path.title || <Bi zh="未命名路径" en="Untitled path" />}</h3>
          <p className="form-hint">{path.summary || <Bi zh="暂无摘要。" en="No summary available." />}</p>
          {path.writer_instruction ? (
            <p className="form-hint">{path.writer_instruction}</p>
          ) : null}
        </article>
      ))}
    </div>
  );
}
