import * as React from "react";
import { RefreshCw } from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { ScrollArea } from "@/components/ui/scroll-area";

import { getWorldlineAgents } from "@/api/worldline";
import type { ApiResponse } from "@/api/http";

import {
  buildAgentCardHighlights,
  type AgentData,
} from "./agent-detail-presentation";

/* ------------------------------------------------------------------ */
/*  Display helpers                                                    */
/* ------------------------------------------------------------------ */

const KIND_LABELS: Record<string, string> = {
  character: "角色",
  organization: "组织",
  relationship: "关系",
};

const STATUS_LABELS: Record<string, string> = {
  active: "活跃",
  idle: "闲置",
  eliminated: "淡出",
};

function formatAgentKind(kind: string): string {
  return KIND_LABELS[kind] || kind || "未知";
}

function formatAgentStatus(status: string): string {
  return STATUS_LABELS[status] || status || "未知";
}

function formatRoleText(role: unknown): string {
  return role ? String(role) : "未设定角色";
}

function formatTime(value: unknown): string {
  if (!value) return "--";
  const date = new Date(String(value));
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("zh-CN", { hour12: false });
}

/* ------------------------------------------------------------------ */
/*  Props                                                              */
/* ------------------------------------------------------------------ */

interface WorldlineAgentRosterProps {
  sessionId: string;
  selectedAgentRef: string;
  onSelect: (agent: AgentData) => void;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function WorldlineAgentRoster({
  sessionId,
  selectedAgentRef,
  onSelect,
}: WorldlineAgentRosterProps) {
  const [agents, setAgents] = React.useState<AgentData[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  const groups = React.useMemo(() => {
    return [
      { kind: "character", label: "角色", items: agents.filter((a) => a.agent_kind === "character") },
      { kind: "organization", label: "组织", items: agents.filter((a) => a.agent_kind === "organization") },
      { kind: "relationship", label: "关系", items: agents.filter((a) => a.agent_kind === "relationship") },
    ].filter((g) => g.items.length > 0);
  }, [agents]);

  const loadRoster = React.useCallback(async () => {
    if (!sessionId) {
      setAgents([]);
      return;
    }
    try {
      setBusy(true);
      setError("");
      const res = await getWorldlineAgents(sessionId);
      setAgents(((res as ApiResponse).data as Record<string, unknown>)?.agents as AgentData[] || []);
    } catch (err) {
      setAgents([]);
      setError(err instanceof Error ? err.message : "读取对象名册失败");
    } finally {
      setBusy(false);
    }
  }, [sessionId]);

  React.useEffect(() => {
    void loadRoster();
  }, [loadRoster]);

  return (
    <Card className="flex flex-col gap-2 p-2.5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold">对象名册</h2>
          <p className="text-xs text-muted-foreground">从当前世界线自动读取角色、组织和关系对象。</p>
        </div>
        <Button variant="outline" size="sm" disabled={!sessionId || busy} onClick={loadRoster}>
          <RefreshCw className={cn("mr-1 h-3 w-3", busy && "animate-spin")} />
          刷新
        </Button>
      </div>

      {!sessionId ? (
        <p className="py-4 text-center text-xs text-muted-foreground">
          先在左侧选择世界线会话，再读取当前世界的对象名册。
        </p>
      ) : error ? (
        <Badge variant="destructive" className="self-start">{error}</Badge>
      ) : !agents.length && !busy ? (
        <p className="py-4 text-center text-xs text-muted-foreground">
          当前世界还没有可用对象。
        </p>
      ) : null}

      <ScrollArea className="max-h-[calc(100vh-380px)] min-h-0">
        <div className="flex flex-col gap-2.5">
          {groups.map((group) => (
            <div key={group.kind}>
              <div className="mb-1 text-xs font-semibold text-muted-foreground">
                {group.label} · {group.items.length}
              </div>
              {group.items.map((agent) => {
                const isActive =
                  selectedAgentRef === agent.agent_id ||
                  selectedAgentRef === agent.display_name;
                const highlights = buildAgentCardHighlights(agent);
                return (
                  <button
                    key={agent.agent_id}
                    type="button"
                    className={cn(
                      "mt-1.5 w-full rounded-lg border p-2 text-left transition-colors",
                      isActive
                        ? "border-primary bg-primary/5"
                        : "border-border hover:border-primary/40",
                    )}
                    onClick={() => onSelect(agent)}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <strong className="text-sm">{agent.display_name}</strong>
                      <span className="font-mono text-[10px] text-muted-foreground">
                        {formatAgentKind(agent.agent_kind || "")}
                      </span>
                    </div>
                    <div className="mt-0.5 text-[11px] text-muted-foreground">
                      {formatRoleText(agent.role)} · {formatAgentStatus(agent.status || "")}
                    </div>
                    <div className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                      ID {agent.agent_id} · v{agent.state_version || 0} · {agent.state_source || "unknown"}
                    </div>
                    <div className="mt-0.5 text-[10px] text-muted-foreground">
                      动作 {formatTime(agent.last_action_at)} · 对话 {formatTime(agent.last_dialogue_at)}
                    </div>
                    {agent.summary && (
                      <div className="mt-1 text-xs text-muted-foreground">{agent.summary}</div>
                    )}
                    {highlights.length > 0 && (
                      <div className="mt-1 flex flex-col gap-0.5 text-xs">
                        {highlights.map((line) => (
                          <div key={line}>{line}</div>
                        ))}
                      </div>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </ScrollArea>
    </Card>
  );
}
