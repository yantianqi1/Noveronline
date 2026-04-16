import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";
import type { ChapterStep, ChapterViewModel } from "./seed-pipeline-chapters";
import type { SeedWorkflowCollapse } from "./seed-workflow-collapse";
import SeedStepTracePanel from "./seed-step-trace-panel";

export default function SeedWorkflowChatContent({
  taskId,
  chapters,
  activeStageKey,
  collapse,
}: {
  taskId: string;
  chapters: ChapterViewModel[];
  activeStageKey: string;
  collapse: SeedWorkflowCollapse;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const prevActiveChapterRef = useRef("");

  useEffect(() => {
    const active = chapters.find((chapter) => chapter.status === "active");
    if (active && active.key !== prevActiveChapterRef.current) {
      prevActiveChapterRef.current = active.key;
    }
  }, [activeStageKey, chapters]);

  return (
    <div ref={containerRef} className="flex flex-col gap-4">
      {chapters.map((chapter) => (
        <ChapterSection key={chapter.key} chapter={chapter} taskId={taskId} collapse={collapse} />
      ))}
    </div>
  );
}

function ChapterSection({
  chapter,
  taskId,
  collapse,
}: {
  chapter: ChapterViewModel;
  taskId: string;
  collapse: SeedWorkflowCollapse;
}) {
  if (chapter.status === "pending") return <PendingChapter label={chapter.label} />;
  if (chapter.status === "completed" && collapse.isChapterCollapsed(chapter.key)) {
    return <ChapterCard chapter={chapter} onExpand={() => collapse.expandChapter(chapter.key)} />;
  }
  return (
    <div className="seed-chapter-in flex flex-col gap-2">
      <ChapterHeader chapter={chapter} onCollapse={() => collapse.collapseChapter(chapter.key)} />
      <div className="flex flex-col gap-2">
        {chapter.steps.map((step) => (
          <StepItem
            key={step.stepId}
            step={step}
            taskId={taskId}
            collapsed={collapse.isStepCollapsed(step.stepId)}
            onToggle={() => toggleStep(collapse, step.stepId)}
          />
        ))}
      </div>
    </div>
  );
}

function ChapterHeader({ chapter, onCollapse }: { chapter: ChapterViewModel; onCollapse: () => void }) {
  return (
    <div className="flex items-center justify-between rounded-md px-1 py-1">
      <span className="font-serif text-sm text-foreground">{chapter.label}</span>
      {chapter.status === "active" && <span className="w-1.5 h-1.5 rounded-full bg-red-700 animate-pulse ml-1.5" />}
      {chapter.status === "completed" && (
        <button className="text-xs text-muted-foreground hover:text-red-700 bg-transparent border-none cursor-pointer" onClick={onCollapse}>
          收起
        </button>
      )}
    </div>
  );
}

function PendingChapter({ label }: { label: string }) {
  return (
    <div className="seed-chapter-in flex items-center rounded-md px-1 py-1 opacity-45">
      <span className="font-serif text-sm text-muted-foreground">{label}</span>
    </div>
  );
}

function ChapterCard({ chapter, onExpand }: { chapter: ChapterViewModel; onExpand: () => void }) {
  return (
    <div
      className="seed-step-card flex items-center gap-2 px-3 py-2 rounded-lg border border-border bg-white cursor-pointer hover:border-red-900/20 hover:bg-zinc-50 transition-colors"
      onClick={onExpand}
    >
      <span className="text-emerald-600 text-sm flex-shrink-0">&#10003;</span>
      <span className="font-serif text-sm text-foreground">{chapter.label}</span>
      <span className="ml-auto font-mono text-[11px] text-muted-foreground whitespace-nowrap">
        {chapter.stepCount}个步骤 &middot; {formatMs(chapter.elapsedMs)} &middot; {chapter.llmCallCount}次LLM调用
      </span>
    </div>
  );
}

function StepItem({
  step,
  taskId,
  collapsed,
  onToggle,
}: {
  step: ChapterStep;
  taskId: string;
  collapsed: boolean;
  onToggle: () => void;
}) {
  return (
    <div className={cn("seed-step-card rounded-lg border border-border bg-white overflow-hidden transition-colors", step.status === "active" && "seed-current-ring border-red-700/50")}>
      <div className="flex items-center gap-2 px-3 py-2.5 cursor-pointer select-none hover:bg-zinc-50" onClick={onToggle}>
        <StatusDot active={step.status === "active"} />
        <span className="text-sm text-foreground flex-1 min-w-0 truncate">{step.title}</span>
        {step.hasTrace && <TraceBadge />}
        {step.status === "completed" && <StepMetrics step={step} />}
        <span className="font-mono text-xs text-muted-foreground flex-shrink-0">{collapsed ? "\u25B8" : "\u25BE"}</span>
      </div>
      {!collapsed && (
        <div className="seed-step-body border-t border-border/70 bg-white px-3 py-3">
          <SeedStepTracePanel taskId={taskId} step={step} />
        </div>
      )}
    </div>
  );
}

function StepMetrics({ step }: { step: ChapterStep }) {
  return (
    <span className="flex items-center gap-1 font-mono text-[11px] text-muted-foreground flex-shrink-0">
      {step.elapsedMs > 0 && <span>{formatMs(step.elapsedMs)}</span>}
      {step.llmCallCount > 0 && (
        <span className="bg-emerald-50 text-emerald-700 border border-emerald-200 px-1.5 py-px rounded-md text-[10px]">
          {step.llmCallCount}次
        </span>
      )}
    </span>
  );
}

function StatusDot({ active }: { active: boolean }) {
  const className = active ? "bg-red-700 animate-pulse" : "bg-emerald-500";
  return <span className={cn("w-2 h-2 rounded-full flex-shrink-0", className)} />;
}

function TraceBadge() {
  return (
    <span className="rounded-md border border-red-900/10 bg-red-50 px-1.5 py-0.5 font-mono text-[10px] text-red-700">
      prompt/response
    </span>
  );
}

function toggleStep(collapse: SeedWorkflowCollapse, stepId: string) {
  if (collapse.isStepCollapsed(stepId)) {
    collapse.expandStep(stepId);
    return;
  }
  collapse.collapseStep(stepId);
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const sec = ms / 1000;
  return sec < 60 ? `${sec.toFixed(1)}s` : `${Math.floor(sec / 60)}m${Math.round(sec % 60)}s`;
}
