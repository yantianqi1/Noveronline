import * as React from "react";

import { cn } from "@/lib/utils";
import { Spotlight } from "./director/spotlight";
import { CandidateReview } from "./director/candidate-review";
import { DirectorTimeline } from "./director/timeline";

/* ================================================================ */
/*  Types                                                            */
/* ================================================================ */

interface CandidateEvent {
  event_id: string;
  step: number;
  title: string;
  summary: string;
  driving_entities: string[];
  confidence: string;
  confidence_reason: string;
  event_source: string;
  status: string;
}

interface DirectorPanelProps {
  sessionId: string;
  currentWorld: Record<string, unknown> | null;
  timeline: Array<Record<string, unknown>>;
  taskSnapshot: Record<string, unknown> | null;
  candidateEvents: CandidateEvent[];
  streamPhase: string;
  thinkingInfo: { agent?: string; question?: string; factors?: string[] } | null;
  onAdoptEvent: (payload: { eventId: string }) => void;
  onRejectEvent: (payload: { eventId: string }) => void;
  onEditEvent: (payload: { eventId: string; consequence: string }) => void;
  onAdoptAll: () => void;
  onRejectAll: () => void;
}

/* ================================================================ */
/*  Component                                                        */
/* ================================================================ */

export function DirectorPanel({
  currentWorld,
  timeline,
  taskSnapshot,
  candidateEvents,
  streamPhase,
  thinkingInfo,
  onAdoptEvent,
  onRejectEvent,
  onEditEvent,
  onAdoptAll,
  onRejectAll,
}: DirectorPanelProps) {
  const headerStepLabel = `STEP ${(currentWorld?.current_step as number) ?? 0}`;
  const headerTitle = (currentWorld?.title as string) || "当前世界";

  const showCandidates =
    candidateEvents.length > 0 ||
    streamPhase === "thinking" ||
    streamPhase === "streaming";

  return (
    <article className="p-4 rounded-lg border border-stone-200 bg-gradient-to-b from-amber-50/98 to-orange-50/98 shadow-sm">
      {/* Header */}
      <header className="flex justify-between gap-3 items-start pb-4 border-b border-amber-300/40">
        <div>
          <p className="font-mono text-xs text-stone-500 tracking-wider uppercase">
            DIRECTOR CONSOLE
          </p>
          <h2 className="text-lg font-bold text-stone-800 mt-0.5">
            世界线导演台
          </h2>
        </div>
        <div className="min-w-[160px] p-3 px-3.5 bg-gradient-to-b from-amber-100/95 to-amber-200/95 border border-amber-500/25 rounded-full grid gap-1">
          <span className="font-mono text-xs text-stone-500">{headerStepLabel}</span>
          <strong className="text-sm text-stone-800">{headerTitle}</strong>
        </div>
      </header>

      {/* Spotlight */}
      <Spotlight
        currentWorld={currentWorld}
        taskSnapshot={taskSnapshot}
        timeline={timeline}
        streamPhase={streamPhase}
        thinkingInfo={thinkingInfo}
      />

      {/* Candidate review */}
      {showCandidates && (
        <CandidateReview
          candidateEvents={candidateEvents}
          streamPhase={streamPhase}
          onAdoptEvent={onAdoptEvent}
          onRejectEvent={onRejectEvent}
          onEditEvent={onEditEvent}
          onAdoptAll={onAdoptAll}
          onRejectAll={onRejectAll}
        />
      )}

      {/* Director timeline */}
      <DirectorTimeline timeline={timeline} />
    </article>
  );
}
