import * as React from "react";
import { Hourglass } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";

import {
  adoptWorldlineEvents,
  advanceWorldlineStep,
  editWorldlineEvent,
  generatePlotInspiration,
  getPreparedWorldlineAgents,
  getPreparedWorldlineSession,
  getWorldlineAgentDetail,
  getWorldlineSession,
  getWorldlineTimeline,
  injectWorldlineVariable,
  prepareWorldlineSession,
  resumeWorldlinePrepare,
  startPreparedWorldlineSession,
} from "@/api/worldline";
import { getTask } from "@/api/project";
import { useWorldlineAutoEvolution } from "@/hooks/use-worldline-auto-evolution";
import { createWorldlinePrepareTaskPoller, type PrepareSnapshot } from "./prepare-task-poller";
import { resolvePrepareTaskMessage } from "./control-panel-view-model";
import { WORLDLINE_PANEL_LAYOUT } from "./layout";

import { SelectionPanel } from "./selection-panel";
import { ControlPanel } from "./control-panel";
import { InspirationPanel } from "./inspiration-panel";
import { DirectorPanel } from "./director-panel";

/* ================================================================
 * Types
 * ================================================================ */

interface Archive {
  archive_id: string;
  entity_name?: string;
  [key: string]: unknown;
}

interface Agent {
  agent_id: string;
  display_name?: string;
  agent_kind?: string;
  public_profile?: Record<string, unknown>;
  private_profile?: Record<string, unknown>;
  runtime_seed_state?: Record<string, unknown>;
  relationship_view?: unknown;
  memory_seed_summary?: unknown;
  [key: string]: unknown;
}

interface WorldVariable {
  variable_id: string;
  name: string;
  description: string;
  impact_axis?: string;
  source?: string;
}

/* ================================================================
 * Poller singleton
 * ================================================================ */

const pollPrepareTask = createWorldlinePrepareTaskPoller({
  getTask,
  getPreparedSession: getPreparedWorldlineSession,
});

/* ================================================================
 * Main Page Component
 * ================================================================ */

export default function WorldlinePage() {
  /* ---- selection state ---- */
  const [selectedArchives, setSelectedArchives] = React.useState<Archive[]>([]);
  const [archiveProjectFilter, setArchiveProjectFilter] = React.useState("");

  /* ---- session lifecycle state ---- */
  const [sessionLabel, setSessionLabel] = React.useState("");
  const [variablesText, setVariablesText] = React.useState(
    "主要势力 A 提前结盟\n主角亲族在第 3 节点失踪",
  );
  const [singleVariable, setSingleVariable] = React.useState("");
  const [sessionId, setSessionId] = React.useState("");
  const [sessionScope, setSessionScope] = React.useState("");
  const [prepareId, setPrepareId] = React.useState("");
  const [prepareTaskId, setPrepareTaskId] = React.useState("");
  const [prepareSnapshot, setPrepareSnapshot] =
    React.useState<PrepareSnapshot | null>(null);
  const [preparedAgents, setPreparedAgents] = React.useState<Agent[]>([]);
  const [currentWorld, setCurrentWorld] =
    React.useState<Record<string, unknown> | null>(null);
  const [worldVariables, setWorldVariables] = React.useState<WorldVariable[]>(
    [],
  );
  const [lockedVariableIds, setLockedVariableIds] = React.useState<
    Set<string>
  >(new Set());
  const [timeline, setTimeline] = React.useState<
    Array<Record<string, unknown>>
  >([]);
  const [feedback, setFeedback] = React.useState("等待操作");
  const [error, setError] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  /* ---- inspiration state ---- */
  const [inspirationPrompt, setInspirationPrompt] = React.useState(
    "希望在下一幕引入关键误判，引发阵营站队重组。",
  );
  const [inspirationBusy, setInspirationBusy] = React.useState(false);
  const [inspirationResult, setInspirationResult] = React.useState<Record<
    string,
    unknown
  > | null>(null);
  const [inspirationError, setInspirationError] = React.useState("");

  /* ---- agent focus state ---- */
  const [focusedAgent, setFocusedAgent] = React.useState<Agent | null>(null);
  const [runtimeAgentDetail, setRuntimeAgentDetail] = React.useState<Record<
    string,
    unknown
  > | null>(null);

  /* ---- left pane collapse ---- */
  const [leftCollapsed, setLeftCollapsed] = React.useState(false);

  /* ---- hooks ---- */
  const autoEvolution = useWorldlineAutoEvolution({
    refreshWorldline: () => {
      void loadWorldline();
    },
    setFeedback: (msg: string) => setFeedback(msg),
    setError: (msg: string) => setError(msg),
  });

  // Auto-collapse left pane during evolution
  React.useEffect(() => {
    if (
      autoEvolution.streamPhase === "connecting" ||
      autoEvolution.streamPhase === "thinking"
    ) {
      setLeftCollapsed(true);
    }
  }, [autoEvolution.streamPhase]);

  /* ---- derived ---- */
  const prepareTaskProgress = Number(prepareSnapshot?.task_progress || 0);
  const prepareTaskMessage = resolvePrepareTaskMessage({
    prepareSnapshot,
    error,
  });
  const preparedInspector = React.useMemo(() => {
    if (!preparedAgents.length) return null;
    if (!focusedAgent)
      return preparedAgents[0]!;
    return (
      preparedAgents.find((a) => a.agent_id === focusedAgent.agent_id) ||
      preparedAgents[0]!
    );
  }, [preparedAgents, focusedAgent]);
  const canStartPreparedSession = Boolean(
    prepareId && prepareSnapshot?.can_start,
  );
  const inspectorTitle =
    (preparedInspector?.display_name as string) || "等待整备完成";
  const panelLayout = leftCollapsed
    ? WORLDLINE_PANEL_LAYOUT.collapsed.panels
    : WORLDLINE_PANEL_LAYOUT.expanded.panels;

  /* ---- helpers ---- */

  function parseVariables(text: string): string[] {
    return text
      .split("\n")
      .map((v) => v.trim())
      .filter(Boolean);
  }

  async function loadWorldline() {
    if (!sessionId) return;
    try {
      const [sessionRes, timelineRes] = await Promise.all([
        getWorldlineSession(sessionId),
        getWorldlineTimeline(sessionId),
      ]);
      const sData = sessionRes.data as Record<string, unknown> | undefined;
      setSessionScope((sData?.session_scope as string) || "");
      setCurrentWorld((sData?.current_world as Record<string, unknown>) || null);
      setWorldVariables(
        (sData?.world_variables as WorldVariable[]) || [],
      );
      const tData = timelineRes.data as Record<string, unknown> | undefined;
      setTimeline(
        (tData?.events as Array<Record<string, unknown>>) || [],
      );
    } catch (err: unknown) {
      setError((err as Error).message);
    }
  }

  async function loadAgentDetail(agentId: string) {
    if (!sessionId || !agentId) {
      setRuntimeAgentDetail(null);
      return;
    }
    try {
      const response = await getWorldlineAgentDetail(sessionId, agentId);
      setRuntimeAgentDetail(
        (response.data as Record<string, unknown>) || null,
      );
    } catch (err: unknown) {
      setError((err as Error).message);
    }
  }

  async function loadPreparedAgents(nextPrepareId = prepareId) {
    const [snapshot, agents] = await Promise.all([
      getPreparedWorldlineSession(nextPrepareId),
      getPreparedWorldlineAgents(nextPrepareId),
    ]);
    const sData = (snapshot.data || {}) as Record<string, unknown>;
    setPrepareSnapshot({
      ...sData,
      task_progress: prepareSnapshot?.task_progress || 0,
      task_message: prepareSnapshot?.task_message || "",
    } as PrepareSnapshot);
    const aData = (agents.data || {}) as Record<string, unknown>;
    const agentList = (aData.agents as Agent[]) || [];
    setPreparedAgents(agentList);
    setFocusedAgent(agentList[0] || null);
  }

  async function waitForPreparedSession(
    taskId: string,
    nextPrepareId: string,
  ) {
    const snapshot = await pollPrepareTask(
      taskId,
      nextPrepareId,
      (value) => setPrepareSnapshot(value),
    );
    setPrepareSnapshot(snapshot);
    await loadPreparedAgents(nextPrepareId);

    if (autoEvolution.createMode === "manual") {
      setFeedback("LLM 整备已完成，请检查 agent 形态后开始推演。");
      return;
    }
    setFeedback("LLM 整备已完成，正在进入自动推演。");
    await startPreparedSessionFlow();
  }

  /* ---- event handlers ---- */

  async function createSession() {
    if (!selectedArchives.length) {
      setError("请先选择至少一个角色档案。");
      return;
    }
    try {
      setBusy(true);
      setError("");
      setRuntimeAgentDetail(null);
      setSessionId("");
      setSessionScope("");
      setPrepareSnapshot(null);
      setPrepareId("");
      setPrepareTaskId("");
      setPreparedAgents([]);
      const res = await prepareWorldlineSession({
        label: sessionLabel.trim(),
        archive_ids: selectedArchives.map((a) => a.archive_id),
        variables: parseVariables(variablesText),
      });
      const data = res.data as Record<string, unknown>;
      setPrepareId(data.prepare_id as string);
      setPrepareTaskId(data.task_id as string);
      setFeedback("已进入 LLM 整备阶段");
      await waitForPreparedSession(
        data.task_id as string,
        data.prepare_id as string,
      );
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function startPreparedSessionFlow() {
    if (!prepareId) return;
    try {
      setBusy(true);
      setError("");
      const res = await startPreparedWorldlineSession(prepareId);
      const data = res.data as Record<string, unknown>;
      setSessionId(data.session_id as string);
      setFeedback("世界线会话已启动");
      await loadWorldline();
      if (focusedAgent?.agent_id) {
        await loadAgentDetail(focusedAgent.agent_id);
      }
      if (autoEvolution.prepareAfterSessionCreate()) {
        await startAutoEvolve();
      }
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function resumePrepareFlow() {
    if (!prepareId) return;
    try {
      setBusy(true);
      setError("");
      const res = await resumeWorldlinePrepare(prepareId);
      const data = res.data as Record<string, unknown>;
      const nextTaskId = (data.task_id as string) || "";
      if (nextTaskId) setPrepareTaskId(nextTaskId);
      setFeedback("已续传 LLM 整备,跳过已完成的 agent");
      if (nextTaskId) {
        await waitForPreparedSession(nextTaskId, prepareId);
      }
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function stepForward() {
    try {
      setBusy(true);
      setError("");
      const res = await advanceWorldlineStep({
        session_id: sessionId,
        steps: 1,
      });
      const data = res.data as Record<string, unknown>;
      setFeedback((data.message as string) || "推进完成");
      await loadWorldline();
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function startAutoEvolve() {
    if (!sessionId) return;
    try {
      setBusy(true);
      setError("");
      const tasks = await autoEvolution.startForSession(sessionId);
      setFeedback(
        tasks.length ? "当前世界自动演化已启动" : "当前模式无需自动演化",
      );
      await loadWorldline();
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function injectVariable() {
    if (!singleVariable.trim()) return;
    try {
      setBusy(true);
      setError("");
      const res = await injectWorldlineVariable({
        session_id: sessionId,
        variable: singleVariable.trim(),
      });
      const data = res.data as Record<string, unknown>;
      setFeedback((data.message as string) || "变量注入成功");
      setSingleVariable("");
      await loadWorldline();
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  /* ---- candidate event handlers ---- */

  async function handleAdoptEvent({ eventId }: { eventId: string }) {
    try {
      setError("");
      await adoptWorldlineEvents({
        session_id: sessionId,
        event_ids: [eventId],
        action: "adopt",
      });
      autoEvolution.removeCandidateEvent(eventId);
      setFeedback("事件已采纳为正史");
      await loadWorldline();
    } catch (err: unknown) {
      setError((err as Error).message);
    }
  }

  async function handleRejectEvent({ eventId }: { eventId: string }) {
    try {
      setError("");
      await adoptWorldlineEvents({
        session_id: sessionId,
        event_ids: [eventId],
        action: "reject",
      });
      autoEvolution.removeCandidateEvent(eventId);
      setFeedback("候选事件已拒绝");
      await loadWorldline();
    } catch (err: unknown) {
      setError((err as Error).message);
    }
  }

  async function handleEditEvent({
    eventId,
    consequence,
  }: {
    eventId: string;
    consequence: string;
  }) {
    try {
      setError("");
      await editWorldlineEvent({
        session_id: sessionId,
        event_id: eventId,
        consequence,
      });
      autoEvolution.removeCandidateEvent(eventId);
      setFeedback("事件已编辑并采纳为正史");
      await loadWorldline();
    } catch (err: unknown) {
      setError((err as Error).message);
    }
  }

  async function handleAdoptAll() {
    const ids = autoEvolution.candidateEvents.map((e) => e.event_id);
    if (!ids.length) return;
    try {
      setError("");
      await adoptWorldlineEvents({
        session_id: sessionId,
        event_ids: ids,
        action: "adopt",
      });
      autoEvolution.removeCandidateEvents(ids);
      setFeedback(`已全部采纳 ${ids.length} 个候选事件`);
      await loadWorldline();
    } catch (err: unknown) {
      setError((err as Error).message);
    }
  }

  async function handleRejectAll() {
    const ids = autoEvolution.candidateEvents.map((e) => e.event_id);
    if (!ids.length) return;
    try {
      setError("");
      await adoptWorldlineEvents({
        session_id: sessionId,
        event_ids: ids,
        action: "reject",
      });
      autoEvolution.removeCandidateEvents(ids);
      setFeedback(`已全部拒绝 ${ids.length} 个候选事件`);
      await loadWorldline();
    } catch (err: unknown) {
      setError((err as Error).message);
    }
  }

  /* ---- lock handlers ---- */

  function handleToggleLock(variableId: string) {
    setLockedVariableIds((prev) => {
      const next = new Set(prev);
      if (next.has(variableId)) next.delete(variableId);
      else next.add(variableId);
      autoEvolution.setConstraints(
        worldVariables
          .filter((v) => next.has(v.variable_id))
          .map((v) => `${v.name}：${v.description}`),
      );
      return next;
    });
  }

  function handleLockAll() {
    const next = new Set(worldVariables.map((v) => v.variable_id));
    setLockedVariableIds(next);
    autoEvolution.setConstraints(
      worldVariables.map((v) => `${v.name}：${v.description}`),
    );
  }

  function handleUnlockAll() {
    setLockedVariableIds(new Set());
    autoEvolution.setConstraints([]);
  }

  async function handleAgentFocus(agent: { agent_id: string }) {
    setFocusedAgent(agent as Agent);
    if (sessionId) {
      await loadAgentDetail(agent.agent_id);
    }
  }

  /* ---- inspiration ---- */

  async function generateInspirationPlan() {
    if (!sessionId) return;
    try {
      setInspirationBusy(true);
      setInspirationError("");
      const res = await generatePlotInspiration({
        session_id: sessionId,
        creator_prompt: inspirationPrompt.trim(),
        focus_question: "下一步走向",
      });
      const data = res.data as Record<string, unknown> | undefined;
      setInspirationResult(
        (data?.result as Record<string, unknown>) || data || null,
      );
    } catch (err: unknown) {
      setInspirationError((err as Error).message);
    } finally {
      setInspirationBusy(false);
    }
  }

  /* ================================================================
   * Render
   * ================================================================ */

  return (
    <ResizablePanelGroup
      key={leftCollapsed ? "worldline-collapsed" : "worldline-expanded"}
      orientation="horizontal"
      className="h-full min-h-0 gap-1"
    >
      {/* LEFT COLUMN: Selection */}
      <ResizablePanel
        defaultSize={panelLayout.left.defaultSize}
        minSize={panelLayout.left.minSize}
        maxSize={panelLayout.left.maxSize}
        className="flex min-w-0 flex-col overflow-hidden"
      >
        <ScrollArea className="flex-1 min-h-0 min-w-0 pr-1">
          {leftCollapsed ? (
            <div
              className="flex flex-col items-center gap-1.5 p-2.5 cursor-pointer h-full rounded-lg bg-amber-50/70 border border-amber-300/20"
              onClick={() => setLeftCollapsed(false)}
            >
              <span className="[writing-mode:vertical-rl] text-xs font-semibold text-stone-500 tracking-widest">
                演员名册
              </span>
              <span className="font-mono text-xs px-1.5 py-0.5 rounded-full bg-amber-200/25 text-amber-800">
                {preparedAgents.length || selectedArchives.length}
              </span>
            </div>
          ) : (
            <SelectionPanel
              selectedArchives={selectedArchives}
              archiveProjectFilter={archiveProjectFilter}
              sessionId={sessionId}
              preparedAgents={preparedAgents}
              busy={busy}
              onUpdateSelectedArchives={setSelectedArchives}
              onUpdateArchiveProjectFilter={setArchiveProjectFilter}
              onSelectAgent={handleAgentFocus}
            />
          )}
        </ScrollArea>
      </ResizablePanel>

      <ResizableHandle withHandle />

      {/* MIDDLE COLUMN: Controls */}
      <ResizablePanel
        defaultSize={panelLayout.center.defaultSize}
        minSize={panelLayout.center.minSize}
        className="flex min-w-0 flex-col overflow-hidden"
      >
        <ScrollArea className="flex-1 min-h-0 min-w-0 px-3">
          <div className="flex min-h-full flex-col gap-3 pb-4 pt-1">
            <ControlPanel
              selectedArchives={selectedArchives}
              archiveProjectFilter={archiveProjectFilter}
              showArchivePicker={false}
              sessionLabel={sessionLabel}
              variablesText={variablesText}
              singleVariable={singleVariable}
              createMode={autoEvolution.createMode}
              goalText={autoEvolution.goalText}
              maxSteps={autoEvolution.maxSteps}
              sessionId={sessionId}
              sessionScope={sessionScope}
              task={autoEvolution.currentTask}
              feedback={feedback}
              error={error}
              busy={busy}
              worldVariables={worldVariables}
              lockedVariableIds={lockedVariableIds}
              onUpdateSelectedArchives={setSelectedArchives}
              onUpdateArchiveProjectFilter={setArchiveProjectFilter}
              onUpdateSessionLabel={setSessionLabel}
              onUpdateVariablesText={setVariablesText}
              onUpdateSingleVariable={setSingleVariable}
              onUpdateCreateMode={autoEvolution.setCreateMode}
              onUpdateGoalText={autoEvolution.setGoalText}
              onUpdateMaxSteps={autoEvolution.setMaxSteps}
              onCreateSession={createSession}
              onStartAutoEvolve={startAutoEvolve}
              onAdvanceStep={stepForward}
              onInjectVariable={injectVariable}
              onToggleLock={handleToggleLock}
              onLockAll={handleLockAll}
              onUnlockAll={handleUnlockAll}
            />

            {/* Prepare status */}
            {prepareId && !sessionId && (
              <article className="border border-amber-300/30 rounded-lg p-3 bg-gradient-to-b from-amber-50/85 to-white/95 shadow-sm">
                <header className="flex justify-between items-start gap-3">
                  <div>
                    <p className="font-mono text-xs text-amber-700 tracking-widest m-0">
                      PREPARE / AGENT 整备
                    </p>
                    <h3 className="text-[0.95rem] font-semibold text-stone-800 mt-0.5">
                      LLM 整备进度
                    </h3>
                  </div>
                  <Badge
                    variant={
                      prepareSnapshot?.status === "ready"
                        ? "default"
                        : "secondary"
                    }
                  >
                    {prepareSnapshot?.status || "preparing"}
                  </Badge>
                </header>
                <p className="text-sm text-stone-500 mt-2 m-0">
                  {prepareTaskMessage}
                </p>
                <Progress value={prepareTaskProgress} className="mt-2" />
                <div className="flex flex-wrap gap-1.5 gap-x-2.5 mt-2 text-xs text-stone-400 font-mono">
                  <span>prepare_id: {prepareId}</span>
                  {prepareTaskId && <span>task: {prepareTaskId}</span>}
                </div>
                {prepareSnapshot?.status === "failed" && (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="secondary"
                      disabled={busy}
                      onClick={resumePrepareFlow}
                      title="保留已生成的 agent dossier,只补跑失败/未跑的部分"
                    >
                      断点续传
                    </Button>
                  </div>
                )}
              </article>
            )}

            {/* Inspiration */}
            {sessionId && (
              <InspirationPanel
                sessionId={sessionId}
                inspirationPrompt={inspirationPrompt}
                inspirationResult={inspirationResult as {
                  overview?: string;
                  next_beats?: string[];
                  conflict_upgrades?: string[];
                } | null}
                inspirationError={inspirationError}
                inspirationBusy={inspirationBusy}
                onUpdatePrompt={setInspirationPrompt}
                onGenerateInspiration={generateInspirationPlan}
              />
            )}
          </div>
        </ScrollArea>
      </ResizablePanel>

      <ResizableHandle withHandle />

      {/* RIGHT COLUMN: Director panel */}
      <ResizablePanel
        defaultSize={panelLayout.right.defaultSize}
        minSize={panelLayout.right.minSize}
        className="flex min-w-0 flex-col overflow-hidden"
      >
        <ScrollArea className="flex-1 min-h-0 min-w-0 px-3">
          {/* Empty state */}
          {!sessionId && !preparedAgents.length && (
            <div className="flex h-full min-h-[420px] flex-col items-center justify-center text-center p-8 border border-dashed border-amber-300/40 rounded-lg bg-gradient-to-b from-amber-50/70 to-white/85">
              <Hourglass className="w-12 h-12 text-amber-400/60 mb-3" />
              <span className="text-lg font-semibold text-amber-900/80 mb-1">
                等待开启世界线
              </span>
              <p className="text-sm text-stone-500 max-w-sm">
                请在左侧选择角色档案，在中栏设定初始变量，以启动当前世界线会话。
              </p>
            </div>
          )}

          {/* Pre-session: agent inspector */}
          {!sessionId && preparedAgents.length > 0 && (
            <article className="border border-stone-200 rounded-lg p-3 bg-white/95">
              <header className="flex justify-between items-start gap-3">
                <div>
                  <p className="font-mono text-xs text-stone-400 tracking-widest m-0">
                    INSPECTION / PREPARED AGENT
                  </p>
                  <h3 className="text-[0.95rem] font-semibold text-stone-800 mt-0.5">
                    {inspectorTitle}
                  </h3>
                </div>
                <Button
                  disabled={busy || !canStartPreparedSession}
                  onClick={() => void startPreparedSessionFlow()}
                >
                  开始推演
                </Button>
              </header>
              {preparedInspector && (
                <>
                  <p className="text-sm text-stone-500 mt-2 m-0">
                    {(preparedInspector.public_profile?.identity as string) ||
                      (preparedInspector.runtime_seed_state?.drive as string) ||
                      "等待选择 agent"}
                  </p>
                  <InspectorSections agent={preparedInspector} />
                </>
              )}
            </article>
          )}

          {/* Active session: Director panel + runtime inspector */}
          {sessionId && (
            <div className="flex min-h-full flex-col gap-3">
              <DirectorPanel
                sessionId={sessionId}
                currentWorld={currentWorld}
                timeline={timeline}
                taskSnapshot={autoEvolution.currentTask as Record<string, unknown> | null}
                candidateEvents={autoEvolution.candidateEvents}
                streamPhase={autoEvolution.streamPhase}
                thinkingInfo={autoEvolution.thinkingInfo as { agent?: string; question?: string; factors?: string[] } | null}
                onAdoptEvent={handleAdoptEvent}
                onRejectEvent={handleRejectEvent}
                onEditEvent={handleEditEvent}
                onAdoptAll={handleAdoptAll}
                onRejectAll={handleRejectAll}
              />
              {runtimeAgentDetail && (
                <RuntimeInspector detail={runtimeAgentDetail} />
              )}
            </div>
          )}
        </ScrollArea>
      </ResizablePanel>
    </ResizablePanelGroup>
  );
}

/* ================================================================
 * Inspector sub-components
 * ================================================================ */

function InspectorSections({ agent }: { agent: Agent }) {
  return (
    <div className="grid gap-2 mt-2">
      {agent.public_profile && (
        <InspectorSection title="公开面">
          <InspectorDl data={agent.public_profile} />
        </InspectorSection>
      )}
      {agent.private_profile && (
        <InspectorSection title="私密面">
          <InspectorDl data={agent.private_profile} />
        </InspectorSection>
      )}
      {agent.runtime_seed_state && (
        <InspectorSection title="运行态基底">
          <InspectorDl data={agent.runtime_seed_state} stringify />
        </InspectorSection>
      )}
      {(agent.relationship_view != null || agent.memory_seed_summary != null) ? (
        <InspectorSection title="关系与记忆">
          {typeof agent.relationship_view === "string" && (
            <p className="text-xs text-stone-600 leading-relaxed m-0">
              {agent.relationship_view}
            </p>
          )}
          {agent.relationship_view != null &&
            typeof agent.relationship_view === "object" &&
            !Array.isArray(agent.relationship_view) && (
              <InspectorDl
                data={agent.relationship_view as Record<string, unknown>}
                stringify
              />
            )}
          {Array.isArray(agent.memory_seed_summary) && (
            <ul className="list-disc pl-4 text-xs text-stone-600 leading-relaxed m-0">
              {(agent.memory_seed_summary as unknown[]).map((item, idx) => (
                <li key={idx} className="mt-1">
                  {typeof item === "string"
                    ? item
                    : (item as Record<string, unknown>).summary
                      ? String((item as Record<string, unknown>).summary)
                      : JSON.stringify(item)}
                </li>
              ))}
            </ul>
          )}
        </InspectorSection>
      ) : null}
    </div>
  );
}

function InspectorSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="p-2 px-2.5 rounded-lg bg-amber-50/85 border border-amber-300/15">
      <h4 className="text-xs font-bold text-stone-400 tracking-wider mb-1 m-0">
        {title}
      </h4>
      {children}
    </section>
  );
}

function InspectorDl({
  data,
  stringify = false,
}: {
  data: Record<string, unknown>;
  stringify?: boolean;
}) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs leading-relaxed m-0">
      {Object.entries(data).map(([key, val]) => (
        <React.Fragment key={key}>
          <dt className="text-stone-400 font-semibold whitespace-nowrap">
            {key}
          </dt>
          <dd className="text-stone-600 break-words m-0">
            {stringify && typeof val === "object"
              ? JSON.stringify(val)
              : String(val ?? "")}
          </dd>
        </React.Fragment>
      ))}
    </dl>
  );
}

function RuntimeInspector({
  detail,
}: {
  detail: Record<string, unknown>;
}) {
  const currentAgent = detail.current_agent as Record<string, unknown> | undefined;
  const baselineDossier = detail.baseline_dossier as Record<string, unknown> | undefined;
  const history = detail.history;
  const relationHistory = detail.relation_history as Array<Record<string, unknown>> | undefined;

  return (
    <article className="border border-stone-200 rounded-lg p-3 bg-white/95">
      <header className="flex justify-between items-start gap-3">
        <div>
          <p className="font-mono text-xs text-stone-400 tracking-widest m-0">
            INSPECTION / RUNTIME AGENT
          </p>
          <h3 className="text-[0.95rem] font-semibold text-stone-800 mt-0.5">
            {(currentAgent?.display_name as string) || "Agent 详情"}
          </h3>
        </div>
      </header>
      <p className="text-sm text-stone-500 mt-2 m-0">
        {(currentAgent?.summary as string) ||
          ((baselineDossier?.public_profile as Record<string, unknown>)
            ?.identity as string) ||
          "当前 agent 的运行态与基线档案对比。"}
      </p>

      <div className="grid gap-2 mt-2">
        {currentAgent && (
          <InspectorSection title="当前运行态">
            <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs leading-relaxed m-0">
              <dt className="text-stone-400 font-semibold">状态</dt>
              <dd className="text-stone-600 m-0">
                {(currentAgent.status as string) || "\u2014"}
              </dd>
              <dt className="text-stone-400 font-semibold">驱动力</dt>
              <dd className="text-stone-600 m-0">
                {(currentAgent.drive as string) ||
                  (currentAgent.core_drive as string) ||
                  "\u2014"}
              </dd>
              <dt className="text-stone-400 font-semibold">张力</dt>
              <dd className="text-stone-600 m-0">
                {(currentAgent.tension as string) || "\u2014"}
              </dd>
              {Boolean(currentAgent.role) && (
                <>
                  <dt className="text-stone-400 font-semibold">角色</dt>
                  <dd className="text-stone-600 m-0">
                    {String(currentAgent.role)}
                  </dd>
                </>
              )}
              {Boolean(currentAgent.last_action) && (
                <>
                  <dt className="text-stone-400 font-semibold">最近行动</dt>
                  <dd className="text-stone-600 m-0">
                    {String(currentAgent.last_action)}
                  </dd>
                </>
              )}
            </dl>
          </InspectorSection>
        )}

        {(baselineDossier?.public_profile as Record<string, unknown>) && (
          <InspectorSection title="准备态档案">
            <InspectorDl
              data={
                baselineDossier!.public_profile as Record<string, unknown>
              }
            />
          </InspectorSection>
        )}

        {history != null && (
          <InspectorSection title="历史记录">
            {Array.isArray(history) ? (
              <ul className="list-disc pl-4 text-xs text-stone-600 leading-relaxed m-0">
                {(history as unknown[]).slice(-6).map((item, idx) => (
                  <li key={idx} className="mt-1">
                    {typeof item === "string"
                      ? item
                      : (item as Record<string, unknown>).summary
                        ? String((item as Record<string, unknown>).summary)
                        : (item as Record<string, unknown>).action
                          ? String((item as Record<string, unknown>).action)
                          : JSON.stringify(item)}
                  </li>
                ))}
              </ul>
            ) : typeof history === "object" ? (
              <InspectorDl
                data={history as Record<string, unknown>}
                stringify
              />
            ) : null}
          </InspectorSection>
        )}

        {relationHistory && relationHistory.length > 0 && (
          <InspectorSection title="关系变化">
            <ul className="list-disc pl-4 text-xs text-stone-600 leading-relaxed m-0">
              {relationHistory.slice(-6).map((rel, idx) => (
                <li key={idx} className="mt-1">
                  <strong>
                    {(rel.source as string) || ""} &rarr;{" "}
                    {(rel.target as string) || ""}
                  </strong>
                  {Boolean(rel.change) && (
                    <span> - {String(rel.change)}</span>
                  )}
                  {Boolean(rel.note) && (
                    <span> -- {String(rel.note)}</span>
                  )}
                </li>
              ))}
            </ul>
          </InspectorSection>
        )}
      </div>
    </article>
  );
}
