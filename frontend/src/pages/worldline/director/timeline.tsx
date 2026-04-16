import * as React from "react";

import { cn } from "@/lib/utils";
import {
  buildTimelineEntries,
  type TimelineData,
} from "./timeline-view-model";
import { StepCard } from "./step-card";

/* ================================================================ */
/*  Types                                                            */
/* ================================================================ */

interface DirectorTimelineProps {
  timeline: Array<Record<string, unknown>>;
}

/* ================================================================ */
/*  Component                                                        */
/* ================================================================ */

export function DirectorTimeline({ timeline }: DirectorTimelineProps) {
  const timelineData: TimelineData = React.useMemo(
    () => buildTimelineEntries(timeline),
    [timeline],
  );

  const [expandedSteps, setExpandedSteps] = React.useState<Set<string | number>>(
    new Set(),
  );

  function toggleExpand(key: string | number) {
    setExpandedSteps((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  return (
    <section className="mt-3">
      {/* Head */}
      <div className="flex justify-between items-start gap-2">
        <div>
          <p className="font-mono text-xs text-stone-500 tracking-wider uppercase">
            演化时间线
          </p>
          <h3 className="mt-0.5 text-base font-bold text-stone-800">
            局势如何被改写
          </h3>
        </div>
        {timelineData.items.length > 0 && (
          <span className="font-mono text-sm text-stone-500">
            {timelineData.items.length} 步
          </span>
        )}
      </div>

      {/* Track */}
      {timelineData.items.length > 0 ? (
        <div className="mt-3 pl-4 border-l-2 border-amber-500/25 grid gap-2">
          {timelineData.items.map((entry) => {
            const key = entry.eventId || entry.step;
            return (
              <article key={key} className="relative">
                {/* Dot */}
                <div
                  className={cn(
                    "absolute -left-[26px] top-4 w-2.5 h-2.5 rounded-full border-2 border-amber-50",
                    entry.isLatest
                      ? "bg-amber-500 ring-[3px] ring-amber-500/20"
                      : "bg-amber-500/45",
                  )}
                />
                <StepCard
                  step={entry.step}
                  stepLabel={entry.stepLabel}
                  title={entry.title}
                  summary={entry.summary}
                  drivers={entry.drivers}
                  variableEffects={entry.variableEffects}
                  actionEffects={entry.actionEffects}
                  relationChanges={entry.relationChanges}
                  actorSummaries={entry.actorSummaries}
                  status="canon"
                  expanded={expandedSteps.has(key)}
                  isLatest={entry.isLatest}
                  onToggleExpand={() => toggleExpand(key)}
                />
              </article>
            );
          })}
        </div>
      ) : (
        <div className="mt-2.5 p-3 rounded-lg bg-amber-50/80 border border-dashed border-amber-300/50 text-sm text-stone-500 text-center">
          {timelineData.emptyMessage}
        </div>
      )}

      {/* Footer */}
      {timelineData.items.length > 0 && (
        <p className="mt-2.5 px-2.5 py-2 rounded-lg bg-amber-50/60 text-xs text-stone-500 text-center tracking-wide">
          所有演化数据已归档，可供写手 Agent 参考
        </p>
      )}
    </section>
  );
}
