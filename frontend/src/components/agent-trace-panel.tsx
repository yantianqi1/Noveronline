import * as React from "react";
import {
  ArrowUpRight,
  Check,
  X,
  Loader2,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  MessageCircle,
  PenLine,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

/* ---------- types ---------- */

export interface AgentToolCall {
  name: string;
  display?: string;
  status: "pending" | "done" | "error";
  fullResult?: string;
  toolElapsedMs?: number;
}

export interface PromptMessage {
  role: string;
  content: string;
}

export interface PromptSnapshot {
  charCount: number;
  messages: PromptMessage[];
}

export interface AgentRound {
  roundNum: number;
  status: "pending" | "running" | "done";
  elapsedMs?: number;
  thinking?: string;
  toolCalls: AgentToolCall[];
  promptSnapshot?: PromptSnapshot;
}

export interface OrchestratorSummary {
  toolCount: number;
  roundCount: number;
  elapsedMs: number;
  tokenUsage?: { total_tokens?: number };
}

export interface AgentTraceState {
  orchestrator: {
    status: "idle" | "running" | "done" | "error";
    model?: string;
    rounds: AgentRound[];
    summary?: OrchestratorSummary;
  };
  writer: {
    status: "idle" | "running" | "done" | "error";
    model?: string;
    wordCount: number;
    elapsedMs?: number;
  };
  error?: string;
}

export interface AgentTracePanelProps {
  state: AgentTraceState;
  className?: string;
}

/* ---------- helpers ---------- */

function truncate(text: string, maxLen: number): string {
  if (!text || text.length <= maxLen) return text;
  return text.slice(0, maxLen) + "...";
}

function statusDotClass(status: string): string {
  switch (status) {
    case "running":
      return "bg-blue-400 animate-pulse";
    case "done":
      return "bg-green-400";
    case "error":
      return "bg-red-400";
    default:
      return "bg-muted-foreground/40";
  }
}

/* ---------- sub-components ---------- */

function ToolCallItem({ tc }: { tc: AgentToolCall }) {
  const [expanded, setExpanded] = React.useState(false);

  return (
    <div className="flex flex-col">
      <button
        type="button"
        className="flex items-center gap-1.5 rounded px-1 py-0.5 transition-colors hover:bg-foreground/4"
        onClick={() => tc.fullResult && setExpanded(!expanded)}
      >
        <ArrowUpRight className="h-3.5 w-3.5 shrink-0 text-blue-400" />
        <span className="min-w-0 flex-1 truncate text-left">
          {tc.display || tc.name}
        </span>
        <span className="shrink-0">
          {tc.status === "done" && (
            <Check className="h-3 w-3 text-green-400" />
          )}
          {tc.status === "error" && <X className="h-3 w-3 text-red-400" />}
          {tc.status === "pending" && (
            <Loader2 className="h-3 w-3 animate-spin text-blue-400" />
          )}
        </span>
        {tc.toolElapsedMs != null && (
          <span className="w-9 shrink-0 text-right text-[11px] text-muted-foreground">
            {(tc.toolElapsedMs / 1000).toFixed(1)}s
          </span>
        )}
        {tc.fullResult && (
          <span className="shrink-0 text-[10px] text-muted-foreground">
            {expanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
          </span>
        )}
      </button>
      {expanded && tc.fullResult && (
        <div className="ml-5 mt-1 max-h-[300px] overflow-y-auto rounded-md border border-border/40 bg-black/20">
          <pre className="whitespace-pre-wrap break-all p-2 font-mono text-[11px] leading-relaxed">
            {tc.fullResult}
          </pre>
        </div>
      )}
    </div>
  );
}

function ThinkingBlock({ text }: { text: string }) {
  const [expanded, setExpanded] = React.useState(false);

  return (
    <div className="flex items-start gap-1.5">
      <MessageCircle className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        {!expanded ? (
          <>
            <span className="text-muted-foreground italic">
              {truncate(text, 120)}
            </span>
            {text.length > 120 && (
              <button
                type="button"
                className="ml-1 text-[11px] text-blue-400 hover:underline"
                onClick={() => setExpanded(true)}
              >
                [more]
              </button>
            )}
          </>
        ) : (
          <>
            <pre className="whitespace-pre-wrap break-all font-mono text-xs text-muted-foreground italic">
              {text}
            </pre>
            <button
              type="button"
              className="text-[11px] text-blue-400 hover:underline"
              onClick={() => setExpanded(false)}
            >
              [collapse]
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function PromptSnapshotToggle({ snapshot }: { snapshot: PromptSnapshot }) {
  const [expanded, setExpanded] = React.useState(false);

  return (
    <div className="mt-0.5">
      <button
        type="button"
        className="flex items-center gap-1.5 rounded px-1 py-0.5 transition-colors hover:bg-foreground/4"
        onClick={() => setExpanded(!expanded)}
      >
        <ClipboardList className="h-3.5 w-3.5 shrink-0 text-amber-600" />
        <span className="text-[11px] font-medium text-amber-600">
          Prompt snapshot ({snapshot.charCount.toLocaleString()} chars)
        </span>
        {expanded ? (
          <ChevronDown className="h-3 w-3 text-muted-foreground" />
        ) : (
          <ChevronRight className="h-3 w-3 text-muted-foreground" />
        )}
      </button>
      {expanded && (
        <div className="ml-5 mt-1 max-h-[400px] overflow-y-auto rounded-md border border-border/40">
          {snapshot.messages.map((msg, mIdx) => (
            <div
              key={mIdx}
              className="border-b border-border/40 p-2 last:border-b-0"
            >
              <div className="mb-1 text-[10px] font-bold uppercase tracking-wider text-blue-400">
                {msg.role}
              </div>
              <pre className="whitespace-pre-wrap break-all font-mono text-xs leading-relaxed">
                {msg.content}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RoundCard({ round }: { round: AgentRound }) {
  return (
    <div
      className={cn(
        "flex flex-col gap-2 rounded-lg border border-border/40 bg-card p-2.5",
        round.status === "running" && "border-l-[3px] border-l-blue-400",
      )}
    >
      {/* Round header */}
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
          Round {round.roundNum + 1}
        </span>
        {round.elapsedMs != null && (
          <span className="text-[11px] text-muted-foreground">
            {(round.elapsedMs / 1000).toFixed(1)}s
          </span>
        )}
      </div>

      {/* Thinking */}
      {round.thinking && <ThinkingBlock text={round.thinking} />}

      {/* Tool calls */}
      {round.toolCalls.length > 0 && (
        <div className="flex flex-col gap-0.5">
          {round.toolCalls.map((tc, idx) => (
            <ToolCallItem key={idx} tc={tc} />
          ))}
        </div>
      )}

      {/* Prompt snapshot */}
      {round.promptSnapshot && (
        <PromptSnapshotToggle snapshot={round.promptSnapshot} />
      )}
    </div>
  );
}

/* ---------- main component ---------- */

export function AgentTracePanel({ state, className }: AgentTracePanelProps) {
  const scrollRef = React.useRef<HTMLDivElement>(null);

  // Auto-scroll when new content arrives
  React.useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [
    state.orchestrator.rounds.length,
    state.writer.wordCount,
    state.writer.status,
  ]);

  return (
    <ScrollArea className={cn("font-mono text-xs leading-relaxed", className)}>
      <div ref={scrollRef} className="flex flex-col gap-3">
        {/* Orchestrator section */}
        {state.orchestrator.status !== "idle" && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 py-1">
              <span className="text-[13px] font-bold">Orchestrator</span>
              {state.orchestrator.model && (
                <Badge variant="secondary" className="text-[10px]">
                  {state.orchestrator.model}
                </Badge>
              )}
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  statusDotClass(state.orchestrator.status),
                )}
              />
            </div>

            {/* Rounds */}
            {state.orchestrator.rounds.map((round) => (
              <RoundCard key={round.roundNum} round={round} />
            ))}

            {/* Summary bar */}
            {state.orchestrator.summary && (
              <div className="flex items-center gap-1.5 rounded-md border border-primary/20 bg-primary/8 px-2 py-1.5">
                <span className="text-primary">&#9632;</span>
                <span className="text-xs font-semibold text-primary">
                  Collection complete &middot;{" "}
                  {state.orchestrator.summary.toolCount} tool calls &middot;{" "}
                  {state.orchestrator.summary.roundCount} rounds &middot;{" "}
                  {(state.orchestrator.summary.elapsedMs / 1000).toFixed(1)}s
                  {state.orchestrator.summary.tokenUsage?.total_tokens != null &&
                    ` · ~${state.orchestrator.summary.tokenUsage.total_tokens.toLocaleString()} tokens`}
                </span>
              </div>
            )}
          </div>
        )}

        {/* Writer section */}
        {state.writer.status !== "idle" && (
          <div className="flex flex-col gap-2">
            <div className="flex items-center gap-2 py-1">
              <span className="text-[13px] font-bold">Writer</span>
              {state.writer.model && (
                <Badge variant="secondary" className="text-[10px]">
                  {state.writer.model}
                </Badge>
              )}
              <span
                className={cn(
                  "h-2 w-2 rounded-full",
                  statusDotClass(state.writer.status),
                )}
              />
            </div>
            <div className="flex items-center gap-1.5 px-2 py-1.5">
              <PenLine
                className={cn(
                  "h-3.5 w-3.5",
                  state.writer.status === "running" && "animate-pulse",
                )}
              />
              {state.writer.status === "running" && (
                <span>
                  Writing... {state.writer.wordCount.toLocaleString()} chars
                </span>
              )}
              {state.writer.status === "done" && (
                <span>
                  Writing complete &middot;{" "}
                  {state.writer.wordCount.toLocaleString()} chars
                  {state.writer.elapsedMs != null &&
                    ` · ${(state.writer.elapsedMs / 1000).toFixed(1)}s`}
                </span>
              )}
              {state.writer.status === "error" && <span>Writing failed</span>}
            </div>
          </div>
        )}

        {/* Error */}
        {state.error && (
          <div className="flex items-center gap-1.5 rounded-md border border-red-400/30 bg-red-400/10 px-2 py-1.5">
            <X className="h-3.5 w-3.5 font-bold text-red-400" />
            <span className="text-red-400">{state.error}</span>
          </div>
        )}
      </div>
    </ScrollArea>
  );
}
