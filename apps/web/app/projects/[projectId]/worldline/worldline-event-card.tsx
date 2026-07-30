"use client";

import { ChevronDown } from "lucide-react";
import { motion } from "motion/react";

import { cn } from "@/lib/utils";
import type { WorldlineEvent } from "@/lib/api/worldline-types";
import { WORLDLINE_CANON } from "@/lib/api/worldline-types";
import { DUR, EASE } from "@/lib/motion";

import { stateChangeView, stepNumeral } from "./worldline-model";

/**
 * One node on the 正史时间线: a canon event card hanging off the vertical ink
 * rail, 步骤印章串联. The timeline only ever shows confirmed history — the
 * current step's seal is filled vermilion and tagged 「此刻」. Cards expand in
 * place (涉及角色 / 状态变化 / kind 标签) instead of opening a side inspector,
 * so the mainline stays one unbroken reading column.
 */
export function WorldlineEventCard({
  event,
  isCurrent = false,
  open = false,
  involvedNames = [],
  onToggle,
}: {
  event: WorldlineEvent;
  /** Whether this is the latest/current step (vermilion seal + 「此刻」). */
  isCurrent?: boolean;
  open?: boolean;
  /** Display names the event involves (resolved by the parent from the roster). */
  involvedNames?: string[];
  onToggle?: (event: WorldlineEvent) => void;
}) {
  const canon =
    event.lifecycle === WORLDLINE_CANON || event.lifecycle === "canon_reference" || event.status === WORLDLINE_CANON;
  // Orchestration markers (queued/admitted bookkeeping) carry no story content,
  // so they render as a static node rather than a card with empty details.
  const isMarker = (event.event_type ?? "").startsWith("workflow.") || (!event.title.trim() && !event.summary.trim());
  const stateChanges = stateChangeView(event.state_changes);
  const kindLabel = event.kind && event.kind !== "event_adoption" ? event.kind : "";
  const hasDetails = involvedNames.length > 0 || stateChanges.summary || stateChanges.entries.length > 0;

  const nodeSeal = (
    <span
      aria-hidden
      className={cn(
        "absolute left-0 top-1 grid size-9 place-items-center rounded-full font-brush text-lg ring-1 ring-inset",
        isCurrent
          ? "bg-accent text-panel ring-accent"
          : canon
            ? "bg-ink/[0.06] text-ink ring-ink/15"
            : "bg-gold/10 text-gold ring-gold/40",
      )}
    >
      {stepNumeral(event.step)}
    </span>
  );
  const connector = (
    <span
      aria-hidden
      className="absolute bottom-[-14px] left-[17px] top-10 w-px bg-gradient-to-b from-line to-transparent"
    />
  );

  if (isMarker) {
    return (
      <li className="relative pl-14">
        {nodeSeal}
        {connector}
        <div className="rounded-modal border border-dashed border-line bg-paper/50 px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <span className="text-caption text-muted">世界线整备就绪，推演开始</span>
            <span className="text-caption tracking-wide text-muted">整备</span>
          </div>
        </div>
      </li>
    );
  }

  return (
    <li className="relative pl-14">
      {nodeSeal}
      {connector}

      <div
        className={cn(
          "rounded-modal border bg-panel p-4 shadow-hairline transition-all",
          isCurrent ? "border-accent/50 ring-1 ring-accent/25" : "border-line hover:border-accent/30 hover:shadow-lift",
        )}
      >
        <button
          type="button"
          onClick={() => onToggle?.(event)}
          aria-expanded={open}
          className="block w-full text-left"
        >
          <div className="flex items-baseline gap-2.5">
            <h4 className="min-w-0 font-serif text-md font-semibold leading-snug text-ink">{event.title}</h4>
            {isCurrent ? (
              <span className="shrink-0 rounded-control border border-accent/30 bg-accent-wash px-1.5 py-0.5 text-caption font-medium text-accent">
                此刻
              </span>
            ) : null}
            {kindLabel ? <span className="shrink-0 text-caption text-muted">{kindLabel}</span> : null}
            <ChevronDown
              aria-hidden
              className={cn(
                "ml-auto size-3.5 shrink-0 self-center text-muted-soft transition-transform",
                open && "rotate-180",
              )}
            />
          </div>
          {event.summary ? <p className="mt-2 font-serif text-sm leading-relaxed text-ink-soft">{event.summary}</p> : null}
          <div className="mt-2.5 flex items-center gap-2 text-caption tracking-wide text-muted">
            <span>{event.step > 0 ? `第 ${event.step} 步` : "正史"}</span>
            <span
              className={cn(
                "rounded-control px-1.5 py-0.5 font-medium",
                canon ? "bg-ink/[0.06] text-ink-soft" : "border border-gold/50 bg-gold/10 text-gold",
              )}
            >
              {canon ? "正史" : "候选"}
            </span>
          </div>
        </button>

        {open && hasDetails ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: DUR.fast, ease: EASE }}
            className="mt-3 flex flex-col gap-2 border-t border-dashed border-line-soft pt-3"
          >
            {involvedNames.length > 0 ? (
              <div className="flex gap-3">
                <span className="w-14 shrink-0 pt-0.5 text-caption text-muted">涉及角色</span>
                <span className="font-serif text-sm leading-relaxed text-ink-soft">{involvedNames.join("、")}</span>
              </div>
            ) : null}
            {stateChanges.summary ? (
              <div className="flex gap-3">
                <span className="w-14 shrink-0 pt-0.5 text-caption text-muted">状态变化</span>
                <span className="font-serif text-sm leading-relaxed text-ink-soft">{stateChanges.summary}</span>
              </div>
            ) : null}
            {stateChanges.entries.length > 0 ? (
              <dl className="flex gap-3">
                <dt className="w-14 shrink-0 pt-0.5 text-caption text-muted">变化明细</dt>
                <dd className="min-w-0 flex-1 space-y-1">
                  {stateChanges.entries.map((entry) => (
                    <div key={entry.key} className="flex items-baseline justify-between gap-3 text-caption">
                      <span className="text-muted">{entry.key}</span>
                      <span className="min-w-0 truncate text-right text-ink-soft">{entry.value}</span>
                    </div>
                  ))}
                </dd>
              </dl>
            ) : null}
          </motion.div>
        ) : null}
      </div>
    </li>
  );
}
