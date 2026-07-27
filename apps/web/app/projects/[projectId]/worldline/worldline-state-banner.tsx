"use client";

import { ChevronDown, Lock } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import type { WorldlineSession } from "@/lib/api/worldline-types";

/**
 * The world-state strip pinned to the top of the timeline. Collapsed by default
 * to one calm line — step · status · the goal (truncated) · locked variables —
 * so it stops crowding the events beneath. Tap to unfold the full goal; it
 * folds itself back when you move on.
 */
export function WorldlineStateBanner({
  session,
  currentStep,
  variableNames,
}: {
  session: WorldlineSession;
  currentStep: number;
  variableNames: string[];
}) {
  const [expanded, setExpanded] = useState(false);
  const goal = session.goal_summary?.trim() ?? "";
  const collapsible = goal.length > 0;

  return (
    <div className="rounded-modal border border-line bg-panel shadow-hairline">
      <button
        type="button"
        onClick={() => collapsible && setExpanded((open) => !open)}
        disabled={!collapsible}
        aria-expanded={expanded}
        className={cn(
          "flex w-full items-center gap-3 px-4 py-2.5 text-left",
          collapsible ? "transition-colors hover:bg-paper/60" : "cursor-default",
        )}
      >
        <span className="shrink-0 font-brush text-lg text-accent">{stepLabel(currentStep)}</span>
        <span className="shrink-0 rounded-control border border-accent/30 bg-accent-wash px-1.5 py-0.5 text-caption text-accent">
          {statusLabel(session.status)}
        </span>
        {goal ? (
          <span className="min-w-0 flex-1 truncate font-serif text-caption text-muted">
            <span className="text-ink-soft/70">目标 · </span>
            {goal}
          </span>
        ) : (
          <span className="min-w-0 flex-1" />
        )}
        {variableNames.length > 0 ? (
          <span className="flex shrink-0 items-center gap-1 text-caption text-muted">
            <Lock className="size-3" aria-hidden />
            {variableNames.length}
          </span>
        ) : null}
        {collapsible ? (
          <ChevronDown
            aria-hidden
            className={cn("size-3.5 shrink-0 text-muted transition-transform", expanded && "rotate-180")}
          />
        ) : null}
      </button>

      {expanded ? (
        <div className="border-t border-line-soft px-4 pb-3.5 pt-3">
          <p className="font-serif text-sm text-ink-soft">
            <span className="text-muted">推演目标 · </span>
            {goal}
          </p>
          {variableNames.length > 0 ? (
            <p className="mt-2 text-caption text-muted">
              <span className="text-ink-soft">注入变量 · </span>
              {variableNames.join("、")}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function stepLabel(step: number): string {
  return step > 0 ? `第 ${step} 步` : "未启程";
}

function statusLabel(status: string): string {
  switch (status) {
    case "queued":
      return "整备中";
    case "running":
      return "推演中";
    case "ready":
      return "就绪";
    case "paused":
      return "已暂停";
    case "failed":
      return "中断";
    default:
      return status || "待命";
  }
}
