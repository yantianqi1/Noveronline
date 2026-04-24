/**
 * InlineWorkflowStream — live seed processing workflow with step trace access.
 */

import { useEffect, useMemo, useRef } from "react";
import { RefreshCcw, Radio, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { TaskMetrics, TimelineEvent } from "@/lib/seed-upload-task-state";
import { buildChapterViewModel } from "./seed-pipeline-chapters";
import SeedWorkflowChatContent from "./seed-workflow-chat-content";
import { useSeedWorkflowCollapse } from "./seed-workflow-collapse";
import SeedWorkflowSummaryBar from "./seed-workflow-summary-bar";

interface InlineWorkflowStreamProps {
  taskId: string;
  timeline: TimelineEvent[];
  activeStageKey: string;
  taskStatus: string;
  uploadPhase: string;
  taskMetrics: TaskMetrics;
  errorMessage?: string;
  canResume?: boolean;
  onDismiss?: () => void;
  onContinue?: () => void;
  onRerun?: () => void;
}

export default function InlineWorkflowStream({
  taskId,
  timeline,
  activeStageKey,
  taskStatus,
  uploadPhase,
  taskMetrics,
  errorMessage,
  canResume,
  onDismiss,
  onContinue,
  onRerun,
}: InlineWorkflowStreamProps) {
  const visible = uploadPhase !== "idle";
  const chapters = useMemo(
    () => buildChapterViewModel(timeline, activeStageKey),
    [timeline, activeStageKey],
  );
  const showSummaryBar =
    taskStatus === "processing" || chapters.some((chapter) => chapter.status === "active");
  const collapse = useSeedWorkflowCollapse();
  const prevTaskIdRef = useRef(taskId);

  useEffect(() => {
    if (taskId === prevTaskIdRef.current) return;
    prevTaskIdRef.current = taskId;
    collapse.reset();
  }, [taskId, collapse]);

  useEffect(() => {
    for (const chapter of chapters) {
      for (const step of chapter.steps) {
        if (step.status === "completed") {
          collapse.onStepCompleted(step.stepId, chapter.key);
        }
      }
    }
  }, [timeline.length, chapters, collapse]);

  if (!visible) return null;

  const inErrorState = uploadPhase === "error";
  const hasAnyAction = canResume || !!onDismiss;

  return (
    <section className="seed-workflow-shell rounded-lg border border-red-900/10 bg-white/95 p-3 flex flex-col gap-3 shadow-sm">
      {/* Recovery toolbar — visible whenever the workflow panel is mounted.
          Style switches to destructive red when the task has errored,
          otherwise renders in a neutral subtle form. */}
      {hasAnyAction && (
        <div
          className={`rounded-lg border px-3 py-2 flex flex-wrap items-center gap-2 ${
            inErrorState
              ? "border-destructive/30 bg-destructive/5"
              : "border-zinc-200 bg-zinc-50/70"
          }`}
        >
          <div className="flex-1 min-w-[200px] text-xs">
            {inErrorState ? (
              <>
                <div className="font-semibold text-destructive">工作流已中断</div>
                {errorMessage && (
                  <div className="mt-0.5 font-mono text-[11px] text-destructive/80 break-all">
                    {errorMessage}
                  </div>
                )}
              </>
            ) : (
              <div className="text-muted-foreground">
                如需中止或从头开始，可使用右侧按钮。
              </div>
            )}
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            {canResume && onContinue && (
              <Button
                size="sm"
                variant={inErrorState ? "secondary" : "outline"}
                className="h-7 text-xs"
                onClick={onContinue}
                title="断点续传：先重新接入活着的任务，否则重读失败段落"
              >
                <Radio className="mr-1 h-3 w-3" />
                断点续传
              </Button>
            )}
            {canResume && onRerun && (
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={onRerun}
                title="使用已上传的文件重新从头开始分析"
              >
                <RefreshCcw className="mr-1 h-3 w-3" />
                重新开始
              </Button>
            )}
            {onDismiss && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs text-muted-foreground"
                onClick={onDismiss}
                title="关闭当前工作流显示（不影响后端任务）"
              >
                <X className="mr-1 h-3 w-3" />
                关闭
              </Button>
            )}
          </div>
        </div>
      )}
      {showSummaryBar && (
        <SeedWorkflowSummaryBar
          chapters={chapters}
          activeStageKey={activeStageKey}
          taskMetrics={taskMetrics}
        />
      )}
      <SeedWorkflowChatContent
        taskId={taskId}
        chapters={chapters}
        activeStageKey={activeStageKey}
        collapse={collapse}
      />
    </section>
  );
}
