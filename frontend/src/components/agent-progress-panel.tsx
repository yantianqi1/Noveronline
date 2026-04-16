import * as React from "react";
import {
  Check,
  X,
  Loader2,
  ChevronDown,
  ChevronUp,
  Search,
  BrainCircuit,
  PenLine,
  CheckCircle2,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import type { AgentTraceState } from "@/components/agent-trace-panel";

/* ---------- types ---------- */

type StepStatus = "pending" | "running" | "done" | "error";

interface PipelineStep {
  key: string;
  label: string;
  icon: React.ReactNode;
  status: StepStatus;
}

export type DraftPhase = "idle" | "collecting" | "writing" | "done";

export interface AgentProgressPanelProps {
  traceState: AgentTraceState;
  draftPhase: DraftPhase;
  className?: string;
}

/* ---------- helpers ---------- */

function fmtSeconds(ms: number): string {
  return (ms / 1000).toFixed(1) + "s";
}

function deriveSteps(
  traceState: AgentTraceState,
  draftPhase: DraftPhase,
): PipelineStep[] {
  const orch = traceState.orchestrator;
  const writer = traceState.writer;
  const hasError = !!traceState.error;

  // Step 1: Retrieval Plan
  let retrievalStatus: StepStatus = "pending";
  if (draftPhase === "collecting" && orch.rounds.length === 0) {
    retrievalStatus = "running";
  } else if (draftPhase !== "idle" && orch.status !== "idle") {
    retrievalStatus = "done";
  }
  if (hasError && retrievalStatus === "running") retrievalStatus = "error";

  // Step 2: Orchestrator
  let orchStatus: StepStatus = "pending";
  if (orch.status === "running") orchStatus = "running";
  else if (orch.status === "done" || orch.status === "error")
    orchStatus = orch.status;
  else if (orch.rounds.length > 0) orchStatus = "running";
  if (hasError && orchStatus === "running") orchStatus = "error";

  // Step 3: Writer
  let writerStatus: StepStatus = "pending";
  if (writer.status === "running") writerStatus = "running";
  else if (writer.status === "done" || writer.status === "error")
    writerStatus = writer.status;
  if (hasError && writerStatus === "running") writerStatus = "error";

  // Step 4: Done
  let doneStatus: StepStatus = "pending";
  if (draftPhase === "done" && writer.status === "done") doneStatus = "done";
  if (hasError) doneStatus = "error";

  return [
    {
      key: "retrieval",
      label: "检索规划",
      icon: <Search className="h-3 w-3" />,
      status: retrievalStatus,
    },
    {
      key: "orchestrator",
      label: "编排收集",
      icon: <BrainCircuit className="h-3 w-3" />,
      status: orchStatus,
    },
    {
      key: "writer",
      label: "创作生成",
      icon: <PenLine className="h-3 w-3" />,
      status: writerStatus,
    },
    {
      key: "done",
      label: "完成",
      icon: <CheckCircle2 className="h-3 w-3" />,
      status: doneStatus,
    },
  ];
}

function StepIndicator({ step }: { step: PipelineStep }) {
  return (
    <div className="flex items-center gap-1">
      <span
        className={cn(
          "flex h-5 w-5 items-center justify-center rounded-full transition-colors",
          step.status === "running" &&
            "bg-blue-500/20 text-blue-400 animate-pulse",
          step.status === "done" && "bg-green-500/20 text-green-400",
          step.status === "error" && "bg-red-500/20 text-red-400",
          step.status === "pending" &&
            "bg-muted-foreground/10 text-muted-foreground/40",
        )}
      >
        {step.status === "done" ? (
          <Check className="h-3 w-3" />
        ) : step.status === "error" ? (
          <X className="h-3 w-3" />
        ) : step.status === "running" ? (
          <Loader2 className="h-3 w-3 animate-spin" />
        ) : (
          step.icon
        )}
      </span>
      <span
        className={cn(
          "text-[11px] font-medium transition-colors",
          step.status === "running" && "text-blue-400",
          step.status === "done" && "text-green-400",
          step.status === "error" && "text-red-400",
          step.status === "pending" && "text-muted-foreground/40",
        )}
      >
        {step.label}
      </span>
    </div>
  );
}

function StepConnector({ done }: { done: boolean }) {
  return (
    <div
      className={cn(
        "h-px w-3 transition-colors",
        done ? "bg-green-400/50" : "bg-muted-foreground/20",
      )}
    />
  );
}

/* ---------- main component ---------- */

export function AgentProgressPanel({
  traceState,
  draftPhase,
  className,
}: AgentProgressPanelProps) {
  const [collapsed, setCollapsed] = React.useState(false);

  const steps = deriveSteps(traceState, draftPhase);
  const allDone = draftPhase === "done" && traceState.writer.status === "done";
  const hasError = !!traceState.error;
  const isIdle = draftPhase === "idle";

  // Auto-collapse 2s after completion
  const autoCollapsedRef = React.useRef(false);
  React.useEffect(() => {
    if (allDone && !autoCollapsedRef.current) {
      const timer = setTimeout(() => {
        setCollapsed(true);
        autoCollapsedRef.current = true;
      }, 2000);
      return () => clearTimeout(timer);
    }
    if (!allDone) {
      autoCollapsedRef.current = false;
      setCollapsed(false);
    }
  }, [allDone]);

  // Don't render when idle
  if (isIdle) return null;

  // Stats
  const orch = traceState.orchestrator;
  const writer = traceState.writer;
  const totalTools = orch.rounds.reduce(
    (sum, r) => sum + r.toolCalls.length,
    0,
  );
  const roundCount = orch.rounds.length;
  const lastRound = orch.rounds.length > 0 ? orch.rounds[orch.rounds.length - 1] : undefined;
  const elapsedMs = orch.summary?.elapsedMs ?? lastRound?.elapsedMs;

  /* ── Collapsed summary bar ── */
  if (collapsed) {
    return (
      <button
        type="button"
        onClick={() => setCollapsed(false)}
        className={cn(
          "flex w-full items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-left font-mono text-xs transition-colors hover:bg-foreground/4",
          hasError
            ? "border-red-400/30 bg-red-400/5"
            : "border-green-400/30 bg-green-400/5",
          className,
        )}
      >
        {hasError ? (
          <X className="h-3.5 w-3.5 shrink-0 text-red-400" />
        ) : (
          <Check className="h-3.5 w-3.5 shrink-0 text-green-400" />
        )}
        <span
          className={cn(
            "flex-1 text-[11px] font-semibold",
            hasError ? "text-red-400" : "text-green-400",
          )}
        >
          {hasError ? "创作异常" : "创作完成"}
          {totalTools > 0 && <> &middot; {totalTools} 工具调用</>}
          {roundCount > 0 && <> &middot; {roundCount} 轮</>}
          {writer.wordCount > 0 && (
            <> &middot; {writer.wordCount.toLocaleString()} 字</>
          )}
          {(() => {
            const t = writer.elapsedMs ?? elapsedMs;
            return t != null ? <> &middot; {fmtSeconds(t)}</> : null;
          })()}
        </span>
        <ChevronDown className="h-3 w-3 shrink-0 text-muted-foreground" />
      </button>
    );
  }

  /* ── Expanded view ── */
  return (
    <div
      className={cn(
        "flex flex-col gap-2 rounded-lg border border-border/40 p-2.5 font-mono text-xs",
        className,
      )}
    >
      {/* Step indicators */}
      <div className="flex flex-wrap items-center gap-1">
        {steps.map((step, i) => (
          <React.Fragment key={step.key}>
            <StepIndicator step={step} />
            {i < steps.length - 1 && (
              <StepConnector done={step.status === "done"} />
            )}
          </React.Fragment>
        ))}
      </div>

      {/* Live stats */}
      <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
        {orch.status === "running" && roundCount > 0 && (
          <Badge variant="secondary" className="text-[10px]">
            Round {roundCount}/15
          </Badge>
        )}
        {totalTools > 0 && (
          <span>{totalTools} 工具调用</span>
        )}
        {elapsedMs != null && <span>{fmtSeconds(elapsedMs)}</span>}
        {writer.status === "running" && writer.wordCount > 0 && (
          <span className="text-blue-400">
            {writer.wordCount.toLocaleString()} 字生成中...
          </span>
        )}
        {writer.status === "done" && writer.wordCount > 0 && (
          <span className="text-green-400">
            {writer.wordCount.toLocaleString()} 字
            {writer.elapsedMs != null && <> &middot; {fmtSeconds(writer.elapsedMs)}</>}
          </span>
        )}
      </div>

      {/* Collapse trigger */}
      {(allDone || hasError) && (
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          className="flex items-center justify-center gap-1 rounded py-0.5 text-[10px] text-muted-foreground/60 transition-colors hover:bg-foreground/4 hover:text-muted-foreground"
        >
          收起
          <ChevronUp className="h-3 w-3" />
        </button>
      )}
    </div>
  );
}
