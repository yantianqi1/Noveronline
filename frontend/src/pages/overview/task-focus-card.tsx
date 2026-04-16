/**
 * TaskFocusCard — shows current task progress or idle state.
 */

import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import type { ActiveStage, TaskMetrics, TimelineEvent } from "@/lib/seed-upload-task-state";
import { deriveStageProgress } from "@/lib/seed-upload-task-view";
import PipelineVisualization from "./pipeline-visualization";

/* ---------- Props ---------- */

interface TaskFocusCardProps {
  projectName: string;
  uploadPhase: string;
  taskStatus: string;
  activeStage: ActiveStage;
  taskMetrics: TaskMetrics;
  timeline: TimelineEvent[];
  statusText: string;
  errorMessage: string;
}

/* ---------- Component ---------- */

export default function TaskFocusCard({
  projectName,
  uploadPhase,
  taskStatus,
  activeStage,
  taskMetrics,
  timeline,
  statusText,
  errorMessage,
}: TaskFocusCardProps) {
  const hasActiveTask = uploadPhase !== "idle";
  const stageProgress = deriveStageProgress(activeStage, taskMetrics, timeline);
  const focusTitle = hasActiveTask
    ? projectName || "当前卷宗"
    : projectName || "暂无运行中的任务";
  const focusStatus = hasActiveTask ? "运行中" : "待命";
  const focusDescription = hasActiveTask
    ? statusText || "后台正在推进分析流程。"
    : "暂无进行中的分析任务。";
  const stageLabel = activeStage?.label || "等待启动";

  return (
    <Card className="shadow-lg bg-gradient-to-b from-amber-50/80 to-amber-50/40">
      <CardContent className="p-3.5 space-y-2">
        {/* Top */}
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div>
            <div className="font-mono text-[11px] text-muted-foreground">任务焦点</div>
            <h2 className="mt-0.5 font-serif text-base font-semibold leading-snug">
              {focusTitle}
            </h2>
          </div>
          <Badge variant={hasActiveTask ? "secondary" : "outline"} className="text-xs">
            {focusStatus}
          </Badge>
        </div>

        {/* Metrics or idle description */}
        {hasActiveTask ? (
          <div className="flex gap-1.5 mt-2">
            <div className="flex-1 rounded-lg border bg-white/70 p-2">
              <span className="block font-mono text-[10px] text-muted-foreground">
                进度
              </span>
              <Progress value={stageProgress.percent} className="mt-1 h-1.5" />
              <strong className="block mt-1 text-base text-foreground">
                {stageProgress.percent}%
              </strong>
            </div>
            <div className="flex-1 rounded-lg border bg-white/70 p-2">
              <span className="block font-mono text-[10px] text-muted-foreground">
                阶段
              </span>
              <strong className="block mt-1 text-base text-foreground">
                {stageLabel}
              </strong>
            </div>
          </div>
        ) : (
          <p className="mt-2 text-sm text-muted-foreground">{focusDescription}</p>
        )}

        {/* Compact pipeline when active */}
        {hasActiveTask && (
          <PipelineVisualization
            uploadPhase={uploadPhase}
            taskStatus={taskStatus}
            activeStage={activeStage}
            compact
          />
        )}

        {/* Error */}
        {errorMessage && (
          <p className="mt-2 rounded-lg bg-destructive/10 px-3 py-2 text-xs font-mono text-destructive">
            {errorMessage}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
