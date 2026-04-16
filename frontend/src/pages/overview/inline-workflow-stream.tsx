/**
 * InlineWorkflowStream — live seed processing workflow with step trace access.
 */

import { useEffect, useMemo, useRef } from "react";

import type { TimelineEvent } from "@/lib/seed-upload-task-state";
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
}

export default function InlineWorkflowStream({
  taskId,
  timeline,
  activeStageKey,
  taskStatus,
  uploadPhase,
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

  return (
    <section className="seed-workflow-shell rounded-lg border border-red-900/10 bg-white/95 p-3 flex flex-col gap-3 shadow-sm">
      {showSummaryBar && (
        <SeedWorkflowSummaryBar chapters={chapters} activeStageKey={activeStageKey} />
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
