"use client";

import { motion } from "motion/react";
import type { WorldlineEvent } from "@/lib/api/worldline-types";
import { WorldlineEventCard } from "./worldline-event-card";
import { DUR, EASE, useFadeUp } from "./worldline-motion";

/**
 * The evolution timeline — the soul of the Worldline workbench. A vertical ink
 * rail of canon event cards, oldest at top, the current step glowing vermilion.
 * Candidate events never land here; they wait in the right rail until adopted,
 * which keeps "the timeline is always confirmed history" visually true.
 */

export function WorldlineTimeline({
  events,
  agents,
  onInspect,
}: {
  /** Canon events in chronological (step) order. */
  events: WorldlineEvent[];
  agents?: ReadonlyMap<string, string>;
  onInspect?: (event: WorldlineEvent) => void;
}) {
  const fadeUp = useFadeUp();
  const currentStep = events.length > 0 ? Math.max(...events.map((e) => e.step)) : 0;

  if (events.length === 0) {
    return (
      <motion.div
        initial={fadeUp.initial}
        animate={fadeUp.animate}
        transition={{ duration: DUR.med, ease: EASE }}
        className="flex h-full flex-col items-center justify-center px-8 py-16 text-center"
      >
        <p className="font-serif text-[17px] font-medium text-ink">时间线还没有落下第一笔</p>
        <p className="mt-1.5 max-w-[320px] text-[13px] leading-relaxed text-muted">
          推进一步，让世界自己走下去。走出来的事件会在这里沉淀成正史。
        </p>
      </motion.div>
    );
  }

  return (
    <ol className="flex flex-col gap-4">
      {events.map((event, index) => (
        <motion.div
          key={event.event_id}
          initial={fadeUp.initial}
          animate={fadeUp.animate}
          transition={{ delay: Math.min(index * 0.04, 0.3), duration: DUR.med, ease: EASE }}
        >
          <WorldlineEventCard
            event={event}
            isCurrent={event.step === currentStep}
            agents={agents}
            onInspect={onInspect}
          />
        </motion.div>
      ))}
    </ol>
  );
}
