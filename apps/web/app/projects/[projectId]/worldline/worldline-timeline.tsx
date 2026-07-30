"use client";

import { ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import { motion } from "motion/react";
import type { WorldlineEvent } from "@/lib/api/worldline-types";
import { WorldlineEventCard } from "./worldline-event-card";
import { DUR, EASE, useFadeUp } from "@/lib/motion";

/**
 * The 正史时间线 — the main reading column of the Worldline workbench. A
 * vertical ink rail of canon event cards, oldest at top, the current step's
 * seal filled vermilion. Candidate events never land here; they wait in the
 * right 待定夺 queue until adopted, which keeps "the timeline is always
 * confirmed history" visually true.
 *
 * Cards expand in place and only one stays open at a time (方案A accordion),
 * so reading the mainline never splits into a side panel. Long runs fold into
 * an in-place 展开更早 divider that stays exactly where those steps belong.
 */

/** Keep this many trailing events on screen; fold the rest behind the accordion. */
const VISIBLE_TAIL = 4;

/** Fold-divider range label. Orchestration markers carry no domain step (0),
 * so the range only ever speaks in real steps: "第 1 – 5 步". */
function stepRangeLabel(first: number, last: number): string {
  const from = Math.max(first, 1);
  const to = Math.max(last, from);
  return `第 ${from} – ${to} 步`;
}

export function WorldlineTimeline({
  events,
  involvedNames,
}: {
  /** Canon events in chronological (step) order. */
  events: WorldlineEvent[];
  /** Resolve an event's involved agents to display names for the details. */
  involvedNames?: (event: WorldlineEvent) => string[];
}) {
  const fadeUp = useFadeUp();
  const [expanded, setExpanded] = useState(false);
  const [openId, setOpenId] = useState<string | null>(null);
  const currentStep = events.length > 0 ? Math.max(...events.map((e) => e.step)) : 0;

  if (events.length === 0) {
    return (
      <motion.div
        initial={fadeUp.initial}
        animate={fadeUp.animate}
        transition={{ duration: DUR.med, ease: EASE }}
        className="flex h-full flex-col items-center justify-center px-8 py-16 text-center"
      >
        <p className="font-serif text-lg font-medium text-ink">时间线还没有落下第一笔</p>
        <p className="mt-1.5 max-w-[320px] text-sm leading-relaxed text-muted">
          推进一步，让世界自己走下去。走出来的事件会在这里沉淀成正史。
        </p>
      </motion.div>
    );
  }

  const foldable = events.length > VISIBLE_TAIL;
  const hiddenCount = foldable ? events.length - VISIBLE_TAIL : 0;
  const hidden = foldable ? events.slice(0, hiddenCount) : [];
  const tail = foldable ? events.slice(hiddenCount) : events;
  const visible = expanded ? events : tail;

  return (
    <div>
      {foldable ? (
        expanded ? (
          /* expanded: the collapse control sits in the same spot the divider was */
          <button
            type="button"
            onClick={() => setExpanded(false)}
            className="group mb-4 flex w-full items-center gap-3 rounded-panel border border-line bg-panel px-4 py-2.5 text-left transition-colors hover:border-accent/50"
          >
            <span className="text-caption text-muted transition-colors group-hover:text-accent">
              收起更早的 {hiddenCount} 段正史
            </span>
            <span className="ml-auto text-caption tabular-nums text-muted-soft">
              {stepRangeLabel(hidden[0].step, hidden[hidden.length - 1].step)}
            </span>
            <ChevronUp aria-hidden className="size-3.5 text-muted transition-colors group-hover:text-accent" />
          </button>
        ) : (
          /* collapsed: the divider shows exactly which steps are folded away */
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="group mb-3 w-full rounded-panel border border-dashed border-line bg-paper/50 px-4 py-2.5 text-left transition-colors hover:border-accent/50 hover:bg-accent-wash/40"
          >
            <span className="flex items-center gap-3">
              <span className="text-caption font-medium text-muted transition-colors group-hover:text-accent">
                展开更早的 {hiddenCount} 段正史
              </span>
              <span className="ml-auto text-caption tabular-nums text-muted-soft">
                {stepRangeLabel(hidden[0].step, hidden[hidden.length - 1].step)}
              </span>
              <ChevronDown aria-hidden className="size-3.5 text-muted transition-colors group-hover:text-accent" />
            </span>
            {/* preview which events are folded, so expanding is never a surprise */}
            <span className="mt-2 block space-y-1">
              {hidden.map((event) => (
                <span key={event.event_id} className="flex items-baseline gap-2.5 text-caption">
                  <span className="shrink-0 tabular-nums text-muted-soft">
                    {event.step > 0 ? `第 ${event.step} 步` : "整备"}
                  </span>
                  <span className="min-w-0 truncate font-serif text-muted">{event.title || "（无标题）"}</span>
                </span>
              ))}
            </span>
          </button>
        )
      ) : null}

      <ol className="flex flex-col gap-4">
        {visible.map((event, index) => (
          <motion.div
            key={event.event_id}
            initial={fadeUp.initial}
            animate={fadeUp.animate}
            transition={{ delay: Math.min(index * 0.04, 0.3), duration: DUR.med, ease: EASE }}
          >
            <WorldlineEventCard
              event={event}
              isCurrent={event.step === currentStep}
              open={openId === event.event_id}
              involvedNames={involvedNames?.(event) ?? []}
              onToggle={(e) => setOpenId((current) => (current === e.event_id ? null : e.event_id))}
            />
          </motion.div>
        ))}
      </ol>
    </div>
  );
}
