/**
 * SeedTaskStageCard — shows current active stage with progress bar and metrics.
 */

import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";
import type { ActiveStage, TaskMetrics, TimelineEvent } from "@/lib/seed-upload-task-state";
import {
  deriveStageProgress,
  formatElapsedDuration,
} from "@/lib/seed-upload-task-view";

/* ---------- Display helpers ---------- */

const TASK_STAGE_STATUS_TEXT: Record<string, string> = {
  processing: "进行中",
  completed: "已完成",
  failed: "失败",
  pending: "待开始",
  active: "进行中",
};

function formatTaskStageStatus(value: string): string {
  return TASK_STAGE_STATUS_TEXT[value] || "待开始";
}

/* ---------- Props ---------- */

interface SeedTaskStageCardProps {
  activeStage: ActiveStage;
  taskStatus: string;
  taskMetrics: TaskMetrics;
  timeline: TimelineEvent[];
  startedAt: string;
}

/* ---------- Component ---------- */

export default function SeedTaskStageCard({
  activeStage,
  taskStatus,
  taskMetrics,
  timeline,
  startedAt,
}: SeedTaskStageCardProps) {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  const resolvedStatus = (() => {
    if (activeStage.status === "failed" || taskStatus === "failed") return "failed";
    if (activeStage.status === "completed" || taskStatus === "completed")
      return "completed";
    if (activeStage.status === "processing" || taskStatus === "processing")
      return "processing";
    return "pending";
  })();

  const statusText = formatTaskStageStatus(resolvedStatus);
  const stageProgress = deriveStageProgress(activeStage, taskMetrics, timeline);
  const elapsedText = formatElapsedDuration(startedAt, now);

  const blockSummary = taskMetrics.totalBlocks
    ? `${taskMetrics.completedBlocks}/${taskMetrics.totalBlocks}`
    : "-";
  const chapterSummary = taskMetrics.chapterCount
    ? String(taskMetrics.chapterCount)
    : "-";

  const workMetricLabel =
    activeStage.key === "sequential_reading" ? "阅读段" : "分析块";
  const workMetricValue =
    activeStage.key === "sequential_reading"
      ? stageProgress.detail
      : blockSummary;

  const statusColor: Record<string, string> = {
    processing: "bg-amber-100/70 text-amber-700",
    completed: "bg-emerald-100/70 text-emerald-700",
    failed: "bg-red-100/70 text-red-700",
    pending: "bg-blue-100/70 text-blue-700",
  };

  return (
    <section className="rounded-xl border p-3.5 bg-gradient-to-b from-amber-50/80 to-amber-50/40 shadow-sm space-y-3.5">
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="font-mono text-[11px] tracking-wide text-muted-foreground">
            当前阶段
          </div>
          <h3 className="mt-1 font-serif text-xl font-semibold">
            {activeStage.label || "等待上传"}
          </h3>
        </div>
        <span
          className={cn(
            "rounded-full px-2.5 py-1 text-[11px] font-mono",
            statusColor[resolvedStatus] || statusColor.pending,
          )}
        >
          {statusText}
        </span>
      </div>

      {/* Metric boxes */}
      <div className="flex flex-wrap gap-2.5 mt-3">
        {[
          { label: "进度", value: `${stageProgress.percent}%` },
          { label: "耗时", value: elapsedText },
          { label: workMetricLabel, value: workMetricValue },
          { label: "章节数", value: chapterSummary },
        ].map((m) => (
          <div
            key={m.label}
            className="flex-1 min-w-[7.5rem] rounded-xl border bg-amber-50/50 p-2.5"
          >
            <span className="block font-mono text-[11px] tracking-wide text-muted-foreground">
              {m.label}
            </span>
            <strong className="block mt-1.5 text-lg text-foreground">
              {m.value}
            </strong>
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div className="mt-3 h-2 rounded-full overflow-hidden bg-amber-100">
        <div
          className="h-full rounded-full bg-gradient-to-r from-amber-700 via-amber-500 to-amber-200 transition-[width] duration-200"
          style={{ width: `${stageProgress.percent}%` }}
        />
      </div>
    </section>
  );
}
