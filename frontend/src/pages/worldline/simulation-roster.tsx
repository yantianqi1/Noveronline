import * as React from "react";
import { RefreshCw } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { getWorldlineAgents } from "@/api/worldline";

/* ================================================================ */
/*  Types                                                            */
/* ================================================================ */

interface Agent {
  agent_id: string;
  display_name?: string;
  agent_kind?: string;
  role?: string;
  status?: string;
  summary?: string;
  public_profile?: { identity?: string };
  runtime_seed_state?: { role?: string; status?: string; drive?: string };
}

interface SimulationRosterProps {
  sessionId: string;
  agentsOverride: Agent[];
  selectedAgentIds: string[];
  onUpdateSelectedAgentIds: (ids: string[]) => void;
  onFocus: (agent: Agent) => void;
}

/* ================================================================ */
/*  Helpers                                                          */
/* ================================================================ */

const KIND_LABELS: Record<string, string> = {
  character: "角色",
  organization: "组织",
  relationship: "关系",
};

function formatAgentKind(kind: string): string {
  return KIND_LABELS[kind] || kind || "";
}

function formatMeta(agent: Agent): string {
  const role = agent.role || agent.runtime_seed_state?.role || "";
  const status = agent.status || agent.runtime_seed_state?.status || "";
  return [role, status].filter(Boolean).join(" - ");
}

function resolveSummary(agent: Agent): string {
  if (agent.summary) return agent.summary;
  if (agent.public_profile?.identity) return agent.public_profile.identity;
  return agent.runtime_seed_state?.drive || "";
}

/* ================================================================ */
/*  Component                                                        */
/* ================================================================ */

export function SimulationRoster({
  sessionId,
  agentsOverride,
  selectedAgentIds,
  onUpdateSelectedAgentIds,
  onFocus,
}: SimulationRosterProps) {
  const [agents, setAgents] = React.useState<Agent[]>([]);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState("");

  const selectedIdSet = React.useMemo(
    () => new Set(selectedAgentIds),
    [selectedAgentIds],
  );
  const hasOverride =
    Array.isArray(agentsOverride) && agentsOverride.length > 0;

  const groups = React.useMemo(() => {
    const all = [
      {
        kind: "character",
        label: "角色",
        items: agents.filter((a) => a.agent_kind === "character"),
      },
      {
        kind: "organization",
        label: "组织",
        items: agents.filter((a) => a.agent_kind === "organization"),
      },
      {
        kind: "relationship",
        label: "关系",
        items: agents.filter((a) => a.agent_kind === "relationship"),
      },
    ];
    return all.filter((g) => g.items.length > 0);
  }, [agents]);

  const loadRoster = React.useCallback(async () => {
    if (hasOverride) {
      setAgents(agentsOverride);
      return;
    }
    if (!sessionId) {
      setAgents([]);
      return;
    }
    try {
      setBusy(true);
      setError("");
      const res = await getWorldlineAgents(sessionId);
      const data = res.data as { agents?: Agent[] } | undefined;
      setAgents(data?.agents || []);
    } catch (err: unknown) {
      setAgents([]);
      setError((err as Error).message || "读取对象名册失败");
    } finally {
      setBusy(false);
    }
  }, [sessionId, hasOverride, agentsOverride]);

  React.useEffect(() => {
    setAgents([]);
    setError("");
    if (hasOverride) {
      setAgents(agentsOverride);
      return;
    }
    if (sessionId) {
      void loadRoster();
    }
  }, [sessionId, hasOverride, agentsOverride, loadRoster]);

  function toggleAgent(agent: Agent) {
    const id = agent.agent_id;
    const currentSet = new Set(selectedAgentIds);
    if (currentSet.has(id)) currentSet.delete(id);
    else currentSet.add(id);
    onUpdateSelectedAgentIds([...currentSet]);
    onFocus(agent);
  }

  return (
    <div className="flex flex-col gap-2">
      {/* Toolbar */}
      <div className="flex justify-between items-center gap-2">
        <div className="flex items-center gap-2">
          <p className="font-mono text-xs text-amber-700 tracking-widest m-0">
            AGENTS
          </p>
          {agents.length > 0 && (
            <p className="font-mono text-xs text-stone-400 m-0">
              {agents.length} 对象
            </p>
          )}
        </div>
        <Button
          size="icon"
          variant="ghost"
          className="h-7 w-7"
          disabled={busy}
          title="刷新名册"
          onClick={() => void loadRoster()}
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </Button>
      </div>

      {error && <p className="text-sm text-red-700 m-0">{error}</p>}
      {!agents.length && !busy && !error && (
        <div className="text-sm text-stone-500 text-center py-4">
          当前世界还没有可用对象，推进后会自动加载。
        </div>
      )}

      {/* Groups */}
      {groups.map((group) => (
        <div key={group.kind} className="mt-1">
          <div className="font-mono text-[0.68rem] text-stone-400 tracking-widest uppercase mb-1.5">
            {group.label} - {group.items.length}
          </div>
          {group.items.map((agent) => {
            const selected = selectedIdSet.has(agent.agent_id);
            const meta = formatMeta(agent);
            const summary = resolveSummary(agent);
            return (
              <button
                key={agent.agent_id}
                type="button"
                className={cn(
                  "w-full mt-1.5 border rounded-lg p-2.5 px-3 text-left cursor-pointer flex flex-col gap-1 transition-all",
                  "border-stone-200 bg-amber-50/60 hover:border-amber-500/40 hover:bg-amber-50/90",
                  selected && "border-amber-500 bg-amber-100/80",
                )}
                onClick={() => toggleAgent(agent)}
              >
                <div className="flex items-center gap-2">
                  <div className="shrink-0">
                    <span
                      className={cn(
                        "flex items-center justify-center w-5 h-5 border-[1.5px] rounded text-xs font-bold transition-all",
                        selected
                          ? "border-amber-500 bg-amber-500 text-white"
                          : "border-stone-300 bg-white/90 text-transparent",
                      )}
                    >
                      {selected ? "\u2713" : ""}
                    </span>
                  </div>
                  <div className="flex items-center justify-between gap-2 flex-1 min-w-0">
                    <strong className="truncate text-sm">
                      {agent.display_name || agent.agent_id}
                    </strong>
                    <span className="font-mono text-[0.68rem] text-stone-400 shrink-0">
                      {formatAgentKind(agent.agent_kind || "")}
                    </span>
                  </div>
                </div>
                {meta && (
                  <div className="text-xs text-stone-500 pl-7">{meta}</div>
                )}
                {summary && (
                  <div className="text-xs text-stone-500 pl-7 line-clamp-2">
                    {summary}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      ))}
    </div>
  );
}
