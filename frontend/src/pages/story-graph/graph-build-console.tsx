import * as React from "react";
import { AlertTriangle, ChevronDown, RotateCcw } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";

import {
  BUILD_STAGE_ORDER,
  describeStage,
  formatCounts,
  formatElapsed,
} from "./build-stage-meta";
import { formatStageSampleLabel, sanitizeDisplayText } from "./display-text";
import type { TaskData, StageEvent } from "./graph-build-task-poller";

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

interface GraphBuildConsoleProps {
  task: TaskData | null;
  onRetry: () => void;
}

/* ------------------------------------------------------------------ */
/*  Component                                                          */
/* ------------------------------------------------------------------ */

export function GraphBuildConsole({ task, onRetry }: GraphBuildConsoleProps) {
  const [showTrace, setShowTrace] = React.useState(false);

  const stages: StageEvent[] = React.useMemo(() => {
    const meta = task?.metadata || {};
    return Array.isArray(meta.stages) ? meta.stages : [];
  }, [task]);

  const failedEvent = React.useMemo(
    () => [...stages].reverse().find((e) => e.stage === "failed") || null,
    [stages],
  );

  const hasFailed = failedEvent !== null || task?.status === "failed";

  const lastSuccessfulStage = React.useMemo(() => {
    const list = stages.filter((e) => e.stage !== "failed");
    return list.length ? list[list.length - 1]! : null;
  }, [stages]);

  const currentStage = lastSuccessfulStage;

  const currentMeta = describeStage(currentStage?.stage || "");

  const currentCountsLabel = formatCounts(currentStage?.counts || {});

  const currentSampleLabels = React.useMemo(() => {
    const sample = currentStage?.sample || [];
    return (sample as unknown[])
      .map(formatStageSampleLabel)
      .filter(Boolean)
      .slice(0, 3);
  }, [currentStage]);

  const progressValue = React.useMemo(() => {
    if (hasFailed) return Math.min(100, currentStage?.progress || 0);
    if (task?.status === "completed") return 100;
    return Math.max(0, Math.min(100, currentStage?.progress || task?.progress || 0));
  }, [hasFailed, task, currentStage]);

  const totalElapsedLabel = React.useMemo(() => {
    const last = stages.length ? stages[stages.length - 1]! : null;
    return formatElapsed(last?.elapsed_ms || 0);
  }, [stages]);

  const headIcon = hasFailed ? "⚠" : task?.status === "completed" ? "✅" : "⚙";
  const headTitle = hasFailed
    ? "图谱构建中断"
    : task?.status === "completed"
      ? "图谱构建完成"
      : "图谱构建中…";
  const headSub = currentStage
    ? `当前阶段：${describeStage(currentStage.stage).title}`
    : "正在准备…";

  const failedAfterLabel = React.useMemo(() => {
    const after = failedEvent?.failed_after || lastSuccessfulStage?.stage || "";
    return describeStage(after).title;
  }, [failedEvent, lastSuccessfulStage]);

  const failedSummary = React.useMemo(
    () => sanitizeDisplayText(failedEvent?.error_summary || "构建失败", { emptyLabel: "构建失败" }),
    [failedEvent],
  );

  const timelineEntries = React.useMemo(() => {
    const eventByStage: Record<string, StageEvent> = {};
    for (const evt of stages) {
      if (evt.stage === "failed") continue;
      eventByStage[evt.stage] = evt;
    }
    const currentKey = currentStage?.stage || "";
    let reachedCurrent = false;
    return BUILD_STAGE_ORDER.map((key) => {
      const meta = describeStage(key);
      const evt = eventByStage[key];
      let statusClass: string;
      let dot: string;
      if (evt) {
        const isCurrent = key === currentKey && !((evt.progress || 0) >= 100);
        if (isCurrent) {
          statusClass = "text-amber-600 font-semibold animate-pulse";
          dot = "▶";
          reachedCurrent = true;
        } else {
          statusClass = "text-green-700";
          dot = "✓";
        }
      } else if (!reachedCurrent && hasFailed && failedEvent?.failed_after === key) {
        statusClass = "text-red-700 font-semibold";
        dot = "✕";
      } else {
        statusClass = "text-muted-foreground";
        dot = "○";
      }
      return {
        key,
        title: meta.title,
        dot,
        statusClass,
        meta: evt
          ? `${formatElapsed(evt.elapsed_ms || 0)}　${formatCounts(evt.counts || {})}`
          : "—",
      };
    });
  }, [stages, currentStage, hasFailed, failedEvent]);

  return (
    <Card
      className={cn(
        "flex flex-col gap-2.5 p-3.5",
        hasFailed && "border-red-300 bg-red-50/40",
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="text-xl">{headIcon}</span>
          <div>
            <div className="text-[15px] font-semibold">{headTitle}</div>
            <div className="text-xs text-muted-foreground">{headSub}</div>
          </div>
        </div>
        <div className="flex gap-3 font-mono text-xs text-muted-foreground">
          <span>已用时 {totalElapsedLabel}</span>
          <span>{progressValue}%</span>
        </div>
      </div>

      {/* Progress bar */}
      <div className="relative h-1.5 overflow-hidden rounded-full bg-muted">
        <div
          className="absolute inset-y-0 left-0 bg-gradient-to-r from-amber-500 to-amber-400 transition-all duration-400"
          style={{ width: `${progressValue}%` }}
        />
      </div>

      {/* Current stage detail */}
      {currentStage && (
        <div className="flex flex-col gap-1 rounded-lg border border-dashed border-amber-300/60 bg-amber-50/30 p-2.5">
          <div className="flex items-baseline gap-2">
            <span className="text-base">{currentMeta.icon}</span>
            <span className="font-semibold">{currentMeta.title}</span>
            <span className="ml-auto font-mono text-[11px] text-muted-foreground">
              {currentCountsLabel}
            </span>
          </div>
          {currentMeta.description && (
            <div className="text-xs text-muted-foreground">{currentMeta.description}</div>
          )}
          {currentSampleLabels.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5 text-xs">
              <span className="text-muted-foreground">示例：</span>
              {currentSampleLabels.map((item, idx) => (
                <span
                  key={idx}
                  className="rounded-full bg-amber-100/60 px-2 py-0.5 text-amber-800"
                >
                  {item}
                </span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Stage timeline grid */}
      <ol className="m-0 grid list-none grid-cols-[repeat(auto-fit,minmax(220px,1fr))] gap-x-3 gap-y-1 p-0">
        {timelineEntries.map((entry) => (
          <li key={entry.key} className={cn("flex items-baseline gap-1.5 text-xs", entry.statusClass)}>
            <span className="w-3.5 text-center">{entry.dot}</span>
            <span className="shrink-0">{entry.title}</span>
            <span className="ml-auto font-mono text-[11px] opacity-80">{entry.meta}</span>
          </li>
        ))}
      </ol>

      {/* Failure box */}
      {hasFailed && (
        <div className="flex flex-col gap-2 rounded-lg border border-red-200 bg-white p-2.5">
          <div className="flex items-center gap-1.5 text-[13px] text-red-700">
            <AlertTriangle className="h-3.5 w-3.5" />
            出错于「{failedAfterLabel}」：{failedSummary}
          </div>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={() => setShowTrace(!showTrace)}>
              <ChevronDown className={cn("mr-1 h-3 w-3 transition-transform", showTrace && "rotate-180")} />
              {showTrace ? "收起技术详情" : "展开技术详情"}
            </Button>
            <Button size="sm" onClick={onRetry}>
              <RotateCcw className="mr-1 h-3 w-3" />
              重试构建
            </Button>
          </div>
          {showTrace && (
            <pre className="max-h-[200px] overflow-auto whitespace-pre-wrap rounded bg-muted/40 p-2 font-mono text-[11px]">
              {failedEvent?.traceback || ""}
            </pre>
          )}
        </div>
      )}
    </Card>
  );
}
