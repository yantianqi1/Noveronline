"use client";

import { useState } from "react";
import { ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";
import { WORLDLINE_CHIP_LABELS, type WorldlineChipState } from "./worldline-model";

/**
 * The 状态行 under the masthead (方案A): 目标 · 第 N 步 · 状态芯片, one calm
 * strip that always answers "推演到哪了、现在轮到我做什么". The goal truncates
 * to a single serif line and unfolds in place; the chip is the three-state
 * 待推进 / 推演中 / 待裁决 from worldlineChipState (never derived locally here).
 */
export function WorldlineStatusRow({
  goal,
  currentStep,
  chip,
}: {
  /** session.goal_summary — the author's question to the world. */
  goal: string;
  /** session.current_step — the domain step, never the orchestration sequence. */
  currentStep: number;
  chip: WorldlineChipState;
}) {
  const [expanded, setExpanded] = useState(false);
  const goalText = goal.trim();
  const collapsible = goalText.length > 0;

  return (
    <div className="shrink-0 border-b border-line-soft bg-paper">
      <div className="flex h-11 items-center gap-3 px-6">
        <span className="shrink-0 text-sm text-muted">目标</span>
        <button
          type="button"
          onClick={() => collapsible && setExpanded((open) => !open)}
          disabled={!collapsible}
          aria-expanded={expanded}
          title={collapsible ? "点击展开完整目标" : undefined}
          className={cn(
            "min-w-0 flex-1 truncate rounded-control px-2 py-1 text-left font-serif text-sm text-ink-soft transition-colors",
            collapsible ? "hover:bg-accent-wash hover:text-ink" : "cursor-default text-muted",
          )}
        >
          {goalText || "（这条世界线还没有写下目标）"}
        </button>
        {collapsible ? (
          <ChevronDown
            aria-hidden
            className={cn("size-3.5 shrink-0 text-muted transition-transform", expanded && "rotate-180")}
          />
        ) : null}
        <span aria-hidden className="shrink-0 text-line">
          ·
        </span>
        <span className="shrink-0 font-brush text-xl leading-none text-ink">
          {currentStep > 0 ? `第 ${currentStep} 步` : "未启程"}
        </span>
        <span aria-hidden className="shrink-0 text-line">
          ·
        </span>
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-line bg-panel px-2.5 py-1 text-caption text-ink-soft">
          <span
            aria-hidden
            className={cn(
              "size-1.5 rounded-full",
              chip === "idle" && "bg-success",
              chip === "judging" && "bg-gold",
              chip === "running" && "animate-pulse bg-gold",
            )}
          />
          {WORLDLINE_CHIP_LABELS[chip]}
        </span>
      </div>

      {expanded && collapsible ? (
        <div className="border-t border-line-soft px-6 pb-3.5 pt-3">
          <p className="font-serif text-sm leading-relaxed text-ink-soft">
            <span className="text-muted">推演目标 · </span>
            {goalText}
          </p>
        </div>
      ) : null}
    </div>
  );
}
