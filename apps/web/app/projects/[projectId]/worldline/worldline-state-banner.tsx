"use client";

import type { WorldlineSession } from "@/lib/api/worldline-types";

/**
 * The world-state banner pinned to the top of the timeline — a 榜文 at the
 * head of the scroll. It states the current step, the active injected
 * variables, and the simulation goal, so the author always knows "where the
 * world stands" before reading the events beneath.
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
  return (
    <div className="rounded-[12px] border border-line bg-panel p-5 shadow-sm">
      <div className="flex items-baseline justify-between gap-4">
        <p className="font-brush text-[26px] leading-none text-accent">
          {stepLabel(currentStep)}
        </p>
        <span className="rounded-[6px] border border-accent/30 bg-accent-wash px-2 py-0.5 text-[11px] text-accent">
          {statusLabel(session.status)}
        </span>
      </div>
      {session.goal_summary ? (
        <p className="mt-3 font-serif text-[13.5px] leading-[1.85] text-ink-soft">
          <span className="text-muted">推演目标 · </span>
          {session.goal_summary}
        </p>
      ) : null}
      {variableNames.length > 0 ? (
        <p className="mt-2 text-[12px] text-muted">
          <span className="text-ink-soft">注入变量 · </span>
          {variableNames.join("、")}
        </p>
      ) : null}
    </div>
  );
}

function stepLabel(step: number): string {
  return step > 0 ? `第 ${step} 步` : "未启程";
}

function statusLabel(status: string): string {
  switch (status) {
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
