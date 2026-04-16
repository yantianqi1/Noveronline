import * as React from "react";
import { Drama } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ApiResponse } from "@/api/http";
import {
  chatWithWorldlineAgent,
  getWorldlineAgentActions,
  getWorldlineAgentDialogues,
  getWorldlineAgentHistory,
  getWorldlineAgentMemory,
  getWorldlineSession,
  issueAgentAction,
  listWorldlineSessions,
} from "@/api/worldline";

import {
  ResizablePanelGroup,
  ResizablePanel,
  ResizableHandle,
} from "@/components/ui/resizable";

import { SessionCommandPanel } from "./session-command-panel";
import { WorldlineAgentRoster } from "./worldline-agent-roster";
import { AgentDialoguePanel } from "./agent-dialogue-panel";
import { AgentDetailPanel } from "./agent-detail-panel";
import { AgentHistoryPanel } from "./agent-history-panel";
import { InteractionLogPanel } from "./interaction-log-panel";
import type { AgentData } from "./agent-detail-presentation";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

interface SessionData {
  session_id: string;
  session_scope?: string;
  project_id?: string;
  simulation_goal?: string;
  [key: string]: unknown;
}

interface LogEntry {
  time: string;
  text: string;
}

function nowTime(): string {
  return new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

function sessionLabel(session: SessionData): string {
  return `${session.session_scope === "global" ? "全局会话" : "卷宗会话"} · ${session.session_id.slice(0, 8)}`;
}

function buildProjectSessionOptions(sessions: SessionData[]) {
  const projectIds = [...new Set(sessions.map((item) => item.project_id).filter(Boolean))].sort();
  const hasGlobal = sessions.some((item) => item.session_scope === "global");
  const options = [{ value: "", label: "全部会话" }];
  for (const projectId of projectIds) {
    options.push({ value: projectId!, label: `项目会话 · ${projectId}` });
  }
  if (hasGlobal) {
    options.push({ value: "__global__", label: "全局混合会话" });
  }
  return options;
}

/* ------------------------------------------------------------------ */
/*  Main page                                                          */
/* ------------------------------------------------------------------ */

export default function CharacterConsolePage() {
  /* -- session & project state -- */
  const [projectFilter, setProjectFilter] = React.useState("");
  const [sessions, setSessions] = React.useState<SessionData[]>([]);
  const [sessionId, setSessionId] = React.useState("");
  const [sessionMap, setSessionMap] = React.useState<Record<string, SessionData>>({});

  /* -- action state -- */
  const [action, setAction] = React.useState("");
  const [busy, setBusy] = React.useState(false);
  const [message, setMessage] = React.useState("等待指令");
  const [error, setError] = React.useState("");

  /* -- chat state -- */
  const [chatMode, setChatMode] = React.useState("template");
  const [chatMessage, setChatMessage] = React.useState("");
  const [chatBusy, setChatBusy] = React.useState(false);
  const [chatReply, setChatReply] = React.useState<Record<string, unknown> | null>(null);
  const [chatError, setChatError] = React.useState("");

  /* -- agent state -- */
  const [selectedAgent, setSelectedAgent] = React.useState<AgentData | null>(null);
  const [chatActor, setChatActor] = React.useState("");

  /* -- history state -- */
  const [agentSnapshots, setAgentSnapshots] = React.useState<unknown[]>([]);
  const [agentActions, setAgentActions] = React.useState<unknown[]>([]);
  const [agentDialogues, setAgentDialogues] = React.useState<unknown[]>([]);
  const [agentSessionMemories, setAgentSessionMemories] = React.useState<unknown[]>([]);
  const [agentLongTermMemories, setAgentLongTermMemories] = React.useState<unknown[]>([]);
  const [historyError, setHistoryError] = React.useState("");

  /* -- logs -- */
  const [logs, setLogs] = React.useState<LogEntry[]>([]);

  /* -- derived -- */
  const activeSession = sessionMap[sessionId] || null;
  const projectSessionOptions = React.useMemo(
    () => buildProjectSessionOptions(sessions),
    [sessions],
  );

  /* -- load sessions -- */
  const loadSessions = React.useCallback(async () => {
    const filters =
      projectFilter && projectFilter !== "__global__"
        ? { projectId: projectFilter }
        : {};
    const response = await listWorldlineSessions(filters);
    let items = ((response as ApiResponse).data as Record<string, unknown>)?.sessions as SessionData[] || [];
    if (projectFilter === "__global__") {
      items = items.filter((item) => item.session_scope === "global");
    }
    setSessions(items);
    setSessionMap(Object.fromEntries(items.map((item) => [item.session_id, item])));
    if (!items.some((item) => item.session_id === sessionId)) {
      const firstId = items[0]?.session_id || "";
      setSessionId(firstId);
      if (firstId) await handleSessionChangeImpl(firstId, items);
    }
  }, [projectFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  async function handleSessionChangeImpl(sid: string, itemsForMap?: SessionData[]) {
    setSelectedAgent(null);
    setChatActor("");
    setChatReply(null);
    clearAgentHistory();
    if (!sid) return;
    const res = await getWorldlineSession(sid);
    const session = (res as ApiResponse).data as SessionData;
    setSessionMap((prev) => {
      const base = itemsForMap
        ? Object.fromEntries(itemsForMap.map((i) => [i.session_id, i]))
        : prev;
      return { ...base, [session.session_id]: session };
    });
  }

  function clearAgentHistory() {
    setHistoryError("");
    setAgentSnapshots([]);
    setAgentActions([]);
    setAgentDialogues([]);
    setAgentSessionMemories([]);
    setAgentLongTermMemories([]);
  }

  async function loadAgentHistory() {
    if (!sessionId || !selectedAgent?.agent_id) {
      clearAgentHistory();
      return;
    }
    try {
      setHistoryError("");
      const filters = { agent_id: selectedAgent.agent_id, limit: 20 };
      const [historyRes, actionRes, dialogueRes, memoryRes] = await Promise.all([
        getWorldlineAgentHistory(sessionId, filters),
        getWorldlineAgentActions(sessionId, filters),
        getWorldlineAgentDialogues(sessionId, filters),
        getWorldlineAgentMemory(sessionId, filters),
      ]);
      setAgentSnapshots(
        ((historyRes as ApiResponse).data as Record<string, unknown>)?.snapshots as unknown[] || [],
      );
      setAgentActions(
        ((actionRes as ApiResponse).data as Record<string, unknown>)?.items as unknown[] || [],
      );
      setAgentDialogues(
        ((dialogueRes as ApiResponse).data as Record<string, unknown>)?.items as unknown[] || [],
      );
      setAgentSessionMemories(
        ((memoryRes as ApiResponse).data as Record<string, unknown>)?.session_memories as unknown[] || [],
      );
      setAgentLongTermMemories(
        ((memoryRes as ApiResponse).data as Record<string, unknown>)?.long_term_memories as unknown[] || [],
      );
    } catch (err) {
      clearAgentHistory();
      setHistoryError(err instanceof Error ? err.message : "读取历史失败");
    }
  }

  /* -- event handlers -- */
  async function updateProjectFilter(value: string) {
    setProjectFilter(value === "__all__" ? "" : value);
  }

  async function updateSessionId(value: string) {
    setSessionId(value);
    await handleSessionChangeImpl(value);
  }

  function handleAgentSelect(agent: AgentData) {
    setSelectedAgent(agent);
    setChatActor(agent.agent_id || "");
  }

  async function submitAction() {
    if (!sessionId || !selectedAgent || !action.trim()) return;
    try {
      setBusy(true);
      setError("");
      const res = await issueAgentAction({
        session_id: sessionId,
        agent_id: selectedAgent.agent_id!,
        action: action.trim(),
      });
      setMessage(((res as ApiResponse).data as Record<string, unknown>)?.message as string || "动作成功");
      setLogs((prev) => [
        { time: nowTime(), text: `[动作][${selectedAgent.display_name}] ${action}` },
        ...prev,
      ]);
      setAction("");
      await loadAgentHistory();
    } catch (err) {
      setError(err instanceof Error ? err.message : "动作失败");
    } finally {
      setBusy(false);
    }
  }

  async function submitChat() {
    if (!sessionId || !selectedAgent || !chatMessage.trim()) return;
    try {
      setChatBusy(true);
      setChatError("");
      const res = await chatWithWorldlineAgent({
        session_id: sessionId,
        agent_id: chatActor,
        message: chatMessage.trim(),
        mode: chatMode,
      });
      const data = (res as ApiResponse).data as Record<string, unknown>;
      setChatReply(data?.result as Record<string, unknown> || data || null);
      setLogs((prev) => [
        { time: nowTime(), text: `[对话][${selectedAgent.display_name}] ${chatMessage}` },
        ...prev,
      ]);
      await loadAgentHistory();
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "对话失败");
    } finally {
      setChatBusy(false);
    }
  }

  /* -- effects -- */
  React.useEffect(() => {
    void loadSessions();
  }, [loadSessions]);

  React.useEffect(() => {
    if (selectedAgent) void loadAgentHistory();
  }, [selectedAgent?.agent_id, sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  /* -- render -- */
  return (
    <div className="h-[calc(100vh-60px)] p-3">
      <ResizablePanelGroup orientation="horizontal" className="h-full gap-1">
        {/* Left panel: session + roster */}
        <ResizablePanel defaultSize="25%" minSize="18%" maxSize="35%">
          <div className="flex h-full flex-col gap-2 overflow-y-auto pr-1">
            <SessionCommandPanel
              projectFilter={projectFilter}
              projectSessionOptions={projectSessionOptions}
              sessions={sessions}
              sessionId={sessionId}
              sessionLabel={sessionLabel}
              activeSession={activeSession}
              selectedAgent={selectedAgent}
              action={action}
              busy={busy}
              error={error}
              message={message}
              onUpdateProjectFilter={updateProjectFilter}
              onUpdateSessionId={updateSessionId}
              onUpdateAction={setAction}
              onSubmitAction={submitAction}
            />
            <WorldlineAgentRoster
              sessionId={sessionId}
              selectedAgentRef={selectedAgent?.agent_id || chatActor}
              onSelect={handleAgentSelect}
            />
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Center panel: dialogue + interaction log */}
        <ResizablePanel defaultSize="50%" minSize="30%">
          <div className="flex h-full flex-col gap-2 overflow-y-auto">
            {!selectedAgent ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-2 rounded-xl border bg-card p-8 text-center">
                <Drama className="h-12 w-12 text-muted-foreground/50" />
                <span className="text-sm font-medium">请选择交互对象</span>
                <span className="text-xs text-muted-foreground">
                  在左侧名录中点选一个角色或组织，开始对话或下达指令。
                </span>
              </div>
            ) : (
              <>
                <AgentDialoguePanel
                  sessionId={sessionId}
                  selectedAgent={selectedAgent}
                  chatMode={chatMode}
                  chatMessage={chatMessage}
                  chatReply={chatReply as Record<string, unknown> | null}
                  dialogues={agentDialogues as Array<{
                    dialogue_id: string;
                    generator_mode: string;
                    message: string;
                    reply: string;
                    created_at?: string;
                  }>}
                  chatError={chatError}
                  busy={chatBusy}
                  onUpdateChatMode={setChatMode}
                  onUpdateChatMessage={setChatMessage}
                  onSubmit={submitChat}
                />
                <InteractionLogPanel logs={logs} />
              </>
            )}
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right panel: detail + history */}
        <ResizablePanel defaultSize="25%" minSize="18%" maxSize="35%">
          <div className="flex h-full flex-col gap-2 overflow-y-auto pl-1">
            <AgentDetailPanel selectedAgent={selectedAgent} />
            <AgentHistoryPanel
              sessionId={sessionId}
              selectedAgent={selectedAgent}
              snapshots={agentSnapshots as Array<{
                snapshot_id: string;
                state_version: number;
                status: string;
                reason: string;
                created_at?: string;
              }>}
              actions={agentActions as Array<{
                action_event_id: string;
                status: string;
                action: string;
                created_at?: string;
              }>}
              dialogues={agentDialogues as Array<{
                dialogue_id: string;
                generator_mode: string;
                message: string;
                reply: string;
                created_at?: string;
              }>}
              sessionMemories={agentSessionMemories as Array<{
                memory_id: string;
                memory_type: string;
                summary: string;
                updated_at?: string;
              }>}
              longTermMemories={agentLongTermMemories as Array<{
                memory_id: string;
                memory_type: string;
                summary: string;
                updated_at?: string;
              }>}
              error={historyError}
            />
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  );
}
