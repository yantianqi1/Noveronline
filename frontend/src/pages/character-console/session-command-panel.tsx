import * as React from "react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

import {
  buildSelectedAgentSummaryLines,
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

const SCOPE_LABELS: Record<string, string> = {
  global: "全局会话",
  project: "卷宗会话",
};

function formatAgentKind(kind: string): string {
  return KIND_LABELS[kind] || kind || "未知";
}

function formatAgentStatus(status: string): string {
  return STATUS_LABELS[status] || status || "未知";
}

function formatSessionScope(scope: string): string {
  return SCOPE_LABELS[scope] || scope || "未知会话";
}

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface SessionOption {
  value: string;
  label: string;
}

interface SessionData {
  session_id: string;
  session_scope?: string;
  simulation_goal?: string;
  [key: string]: unknown;
}

interface SessionCommandPanelProps {
  projectFilter: string;
  projectSessionOptions: SessionOption[];
  sessions: SessionData[];
  sessionId: string;
  sessionLabel: (session: SessionData) => string;
  activeSession: SessionData | null;
  selectedAgent: AgentData | null;
  action: string;
  busy: boolean;
  error: string;
  message: string;
  onUpdateProjectFilter: (value: string) => void;
  onUpdateSessionId: (value: string) => void;
  onUpdateAction: (value: string) => void;
  onSubmitAction: () => void;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function SessionCommandPanel({
  projectFilter,
  projectSessionOptions,
  sessions,
  sessionId,
  sessionLabel,
  activeSession,
  selectedAgent,
  action,
  busy,
  error,
  message,
  onUpdateProjectFilter,
  onUpdateSessionId,
  onUpdateAction,
  onSubmitAction,
}: SessionCommandPanelProps) {
  const summaryLines = React.useMemo(
    () => buildSelectedAgentSummaryLines(selectedAgent),
    [selectedAgent],
  );

  const sessionSelectOptions = React.useMemo(
    () => sessions.map((item) => ({ label: sessionLabel(item), value: item.session_id })),
    [sessions, sessionLabel],
  );

  return (
    <Card className="flex flex-col gap-2.5 p-2.5">
      <h2 className="text-sm font-semibold">角色与关系控制台</h2>
      <p className="text-xs text-muted-foreground">
        先选择世界线会话，再从右侧名册点选对象并下达动作或发起对话。
      </p>

      {/* Session scope selector */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-muted-foreground">会话范围</label>
        <Select value={projectFilter} onValueChange={(v) => onUpdateProjectFilter(v ?? "")}>
          <SelectTrigger>
            <SelectValue placeholder="全部会话" />
          </SelectTrigger>
          <SelectContent>
            {projectSessionOptions.map((opt) => (
              <SelectItem key={opt.value} value={opt.value || "__all__"}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Session selector */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-muted-foreground">世界线会话</label>
        <Select value={sessionId} onValueChange={(v) => onUpdateSessionId(v ?? "")}>
          <SelectTrigger>
            <SelectValue placeholder="请选择会话" />
          </SelectTrigger>
          <SelectContent>
            {sessionSelectOptions.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Active session summary */}
      {activeSession && (
        <div className="rounded-lg border bg-muted/20 p-2.5">
          <strong className="text-xs">{formatSessionScope(activeSession.session_scope || "")}</strong>
          <div className="font-mono text-[10px] text-muted-foreground">{activeSession.session_id}</div>
          <p className="mt-1 text-xs text-muted-foreground">
            {activeSession.simulation_goal || "暂无会话目标"}
          </p>
        </div>
      )}

      {/* Selected agent summary */}
      {selectedAgent && (
        <div className="rounded-lg border bg-muted/20 p-2.5">
          <strong className="text-sm">{selectedAgent.display_name}</strong>
          <div className="font-mono text-[10px] text-muted-foreground">
            {formatAgentKind(selectedAgent.agent_kind || "")} · {formatAgentStatus(selectedAgent.status || "")}
          </div>
          <p className="mt-1 text-xs text-muted-foreground">{selectedAgent.summary}</p>
          {summaryLines.length > 0 && (
            <div className="mt-1.5 flex flex-col gap-0.5 text-xs">
              {summaryLines.map((line) => (
                <div key={line}>{line}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Action input */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-muted-foreground">动作指令</label>
        <Textarea
          value={action}
          onChange={(e) => onUpdateAction(e.target.value)}
          placeholder="例如：以家族名义公开承认旧约，要求盟友在 3 天内给出立场。"
          className="min-h-[60px] text-sm"
        />
      </div>

      <Button
        disabled={busy || !sessionId || !selectedAgent}
        onClick={onSubmitAction}
      >
        执行动作
      </Button>

      {error ? (
        <Badge variant="destructive" className="self-start">{error}</Badge>
      ) : (
        <p className="text-xs text-muted-foreground">{message}</p>
      )}
    </Card>
  );
}
