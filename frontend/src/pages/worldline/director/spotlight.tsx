import * as React from "react";
import { ArrowRight } from "lucide-react";

import { cn } from "@/lib/utils";
import {
  buildSpotlightData,
  type SpotlightData,
  type ActorActionCard,
} from "./spotlight-view-model";
import { StatusRibbon } from "./status-ribbon";
import { ThinkingOverlay } from "./thinking-overlay";

/* ================================================================ */
/*  Types                                                            */
/* ================================================================ */

interface SpotlightProps {
  currentWorld: Record<string, unknown> | null;
  taskSnapshot: Record<string, unknown> | null;
  timeline: Array<Record<string, unknown>>;
  streamPhase: string;
  thinkingInfo: { agent?: string; question?: string; factors?: string[] } | null;
}

/* ================================================================ */
/*  Component                                                        */
/* ================================================================ */

export function Spotlight({
  currentWorld,
  taskSnapshot,
  timeline,
  streamPhase,
  thinkingInfo,
}: SpotlightProps) {
  const rawSpotlight = React.useMemo(
    () =>
      buildSpotlightData({ currentWorld, taskSnapshot, timeline }),
    [currentWorld, taskSnapshot, timeline],
  );

  // Debounce during streaming to avoid jank from rapid SSE events.
  const [spotlight, setSpotlight] = React.useState<SpotlightData>(rawSpotlight);
  const debounceRef = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(() => {
    if (
      streamPhase === "thinking" ||
      streamPhase === "streaming"
    ) {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => setSpotlight(rawSpotlight), 300);
    } else {
      setSpotlight(rawSpotlight);
    }
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [rawSpotlight, streamPhase]);

  return (
    <section className="mt-3 p-3 rounded-xl bg-gradient-to-br from-amber-50/95 to-orange-50/95 border border-amber-400/40 shadow-md relative">
      {/* Step header bar */}
      <div className="flex items-center gap-2 pb-2 border-b border-amber-300/25">
        <span className="font-mono text-xs text-stone-500 tracking-wider uppercase shrink-0">
          {spotlight.stepLabel}
        </span>
        <h3 className="m-0 text-base font-bold text-stone-800 leading-tight flex-1 min-w-0">
          {spotlight.latestEvent.title}
        </h3>
        <StatusRibbon status="canon" />
      </div>

      {spotlight.latestEvent.summary && (
        <p className="mt-2.5 text-sm text-stone-600 leading-relaxed">
          {spotlight.latestEvent.summary}
        </p>
      )}

      {/* Actor action cards */}
      {spotlight.actorActionCards.length > 0 && (
        <div className="mt-2.5 grid gap-2.5">
          {spotlight.actorActionCards.map((actor) => (
            <ActorCard key={actor.name} actor={actor} />
          ))}
        </div>
      )}

      {/* Empty state */}
      {spotlight.isEmpty && (
        <div className="mt-2.5 p-3 rounded-lg bg-amber-50/80 border border-dashed border-amber-300/50 text-sm text-stone-500 text-center">
          等待推演开始，角色行动会在这里以卡片形式展示。
        </div>
      )}

      {/* Side effects bar */}
      <div className="mt-2.5 p-2 rounded-lg bg-white/55 border border-amber-200/20 flex gap-2.5 flex-wrap items-center">
        {spotlight.latestEvent.variableEffects.length > 0 && (
          <div className="flex gap-1.5 items-center flex-wrap">
            <span className="text-xs font-bold text-stone-500 tracking-wider uppercase">
              变量
            </span>
            {spotlight.latestEvent.variableEffects.map((v) => (
              <span
                key={v.name}
                className="px-2 py-0.5 rounded-full text-xs bg-amber-200/70 text-amber-800"
                title={v.description}
              >
                {v.name}
              </span>
            ))}
          </div>
        )}
        <div className="flex gap-1.5 items-center flex-wrap">
          <span className="text-xs font-bold text-stone-500 tracking-wider uppercase">
            待处理
          </span>
          <span className="px-2 py-0.5 rounded-full text-xs bg-amber-200/60 text-amber-800">
            <strong>{spotlight.pending.variableCount}</strong> 变量
          </span>
          <span className="px-2 py-0.5 rounded-full text-xs bg-amber-200/60 text-amber-800">
            <strong>{spotlight.pending.actionCount}</strong> 动作
          </span>
        </div>
      </div>

      {/* Thinking overlay */}
      <ThinkingOverlay
        visible={streamPhase === "thinking"}
        thinkingInfo={thinkingInfo}
      />
    </section>
  );
}

/* ================================================================ */
/*  Actor Card Sub-component                                         */
/* ================================================================ */

function ActorCard({ actor }: { actor: ActorActionCard }) {
  return (
    <article
      className={cn(
        "border rounded-lg p-2.5 px-3 bg-amber-50/80 transition-all hover:border-amber-500/40",
        "border-amber-200/30",
        actor.isDriver &&
          "border-l-[3px] border-l-amber-500 bg-gradient-to-br from-amber-50/90 to-orange-50/90 shadow-sm",
      )}
    >
      {/* Identity row */}
      <div className="flex items-center gap-2.5">
        <span
          className={cn(
            "w-9 h-9 rounded-full flex items-center justify-center font-bold text-sm shrink-0",
            "bg-amber-500/18 text-amber-800",
            actor.isDriver && "bg-amber-500/25 text-amber-900 ring-2 ring-amber-500/25",
          )}
        >
          {actor.initial}
        </span>
        <div className="flex items-center gap-1.5 flex-wrap flex-1 min-w-0">
          <strong className="text-stone-800 text-[0.95rem]">{actor.name}</strong>
          {actor.role && (
            <span className="px-2 py-0.5 rounded-full text-[0.72rem] bg-stone-200/80 text-stone-600">
              {actor.role}
            </span>
          )}
          {actor.isDriver && (
            <span className="px-2 py-0.5 rounded-full text-[0.72rem] bg-amber-500/18 text-amber-800 font-semibold">
              驱动者
            </span>
          )}
        </div>
        {actor.stateChange && (
          <span className="px-2 py-0.5 rounded-full text-xs bg-stone-200/70 text-stone-600 shrink-0">
            {actor.stateChange.status}
          </span>
        )}
      </div>

      {/* Actions */}
      {actor.actions.map((act, idx) => (
        <div
          key={idx}
          className="mt-2 pl-11 flex flex-wrap gap-1 gap-x-2 items-baseline text-sm text-stone-600 leading-relaxed"
        >
          <span className="text-xs font-bold text-stone-500 tracking-wider uppercase px-1.5 py-px rounded bg-amber-500/10">
            行动
          </span>
          <span className="text-stone-800 font-medium">{act.action}</span>
          {act.intent && (
            <>
              <span className="text-xs font-bold text-stone-500 tracking-wider px-1.5 py-px rounded bg-stone-200/50">
                意图
              </span>
              <span className="italic text-amber-800">{act.intent}</span>
            </>
          )}
          {act.target && (
            <>
              <ArrowRight className="w-3.5 h-3.5 text-amber-600 inline" />
              <span className="text-stone-800 font-medium">{act.target}</span>
            </>
          )}
        </div>
      ))}

      {/* Relation changes */}
      {actor.relationChanges.map((rel) => (
        <div
          key={`${rel.source}_${rel.target}`}
          className="mt-1.5 pl-11 flex gap-1.5 items-center flex-wrap text-sm text-stone-600"
        >
          <span className="text-base text-amber-700">&#10239;</span>
          <span className="text-stone-700 font-medium">
            {rel.source} &rarr; {rel.target}
          </span>
          <span className="px-2 py-0.5 rounded-full text-xs bg-stone-200/80 text-stone-600">
            {rel.label}
          </span>
          {rel.note && (
            <span className="text-xs text-stone-500 italic">{rel.note}</span>
          )}
        </div>
      ))}

      {/* State change reason */}
      {actor.stateChange?.reason && actor.actions.length === 0 && (
        <p className="mt-1.5 pl-11 text-sm text-stone-500 italic">
          {actor.stateChange.reason}
        </p>
      )}

      {/* Drive fallback */}
      {actor.actions.length === 0 &&
        actor.relationChanges.length === 0 &&
        actor.drive && (
          <p className="mt-1.5 pl-11 text-sm text-stone-500 italic">
            {actor.drive}
          </p>
        )}
    </article>
  );
}
