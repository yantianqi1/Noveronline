"use client";

import { cn } from "@/lib/utils";
import { CharacterSeal } from "@/components/character";
import type { WorldlineEvent } from "@/lib/api/worldline-types";
import { WORLDLINE_CANON } from "@/lib/api/worldline-types";

/**
 * One node on the evolution timeline: a canon event card hanging off the
 * vertical ink rail. The timeline only ever shows confirmed history — candidate
 * events live in the right rail until adopted. The current step is highlighted
 * with a vermilion ring so the eye lands on "where the world is now".
 */

const STEP_NUMERALS = ["〇", "壹", "贰", "叁", "肆", "伍", "陆", "柒", "捌", "玖", "拾"];

function stepNumeral(step: number): string {
  if (step > 0 && step < STEP_NUMERALS.length) return STEP_NUMERALS[step];
  if (step > 0) return String(step);
  return "·"; // orchestration marker — no domain step yet
}

export function WorldlineEventCard({
  event,
  isCurrent = false,
  agents,
  onInspect,
}: {
  event: WorldlineEvent;
  /** Whether this is the latest/current step (vermilion highlight). */
  isCurrent?: boolean;
  /** Resolve involved agent ids → display names for the seal cluster. */
  agents?: ReadonlyMap<string, string>;
  onInspect?: (event: WorldlineEvent) => void;
}) {
  const canon = event.lifecycle === WORLDLINE_CANON || event.lifecycle === "canon_reference" || event.status === WORLDLINE_CANON;
  const involvedNames = (event.involved_agent_ids ?? [])
    .map((id) => agents?.get(id) ?? "")
    .filter(Boolean);
  // Orchestration markers (queued/admitted bookkeeping) carry no story content,
  // so they render as a static node rather than a clickable card with an empty inspector.
  const isMarker = (event.event_type ?? "").startsWith("workflow.") || (!event.title.trim() && !event.summary.trim());

  const nodeSeal = (
    <span
      aria-hidden
      className={cn(
        "absolute left-0 top-1 grid size-9 place-items-center rounded-control font-brush text-lg ring-1 ring-inset",
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

      <button
        type="button"
        onClick={() => onInspect?.(event)}
        className={cn(
          "block w-full rounded-modal border bg-panel p-4 text-left shadow-hairline transition-all",
          isCurrent
            ? "border-accent/50 ring-1 ring-accent/25"
            : "border-line hover:border-accent/30 hover:shadow-lift",
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <h4 className="font-serif text-md font-semibold leading-snug text-ink">{event.title}</h4>
          <span
            className={cn(
              "shrink-0 rounded-control px-1.5 py-0.5 text-caption font-medium tracking-wide",
              canon ? "bg-ink/[0.06] text-ink-soft" : "border border-gold/50 bg-gold/10 text-gold",
            )}
          >
            {canon ? "正史" : "候选"}
          </span>
        </div>
        {event.summary ? (
          <p className="mt-2 line-clamp-3 font-serif text-sm text-ink-soft">{event.summary}</p>
        ) : null}
        <div className="mt-3 flex items-center justify-between gap-3">
          <span className="text-caption tracking-wide text-muted">
            {event.step > 0 ? `第 ${event.step} 步` : "正史"}
            {event.kind && event.kind !== "event_adoption" ? ` · ${event.kind}` : ""}
          </span>
          {involvedNames.length > 0 ? (
            <span className="flex -space-x-1.5">
              {involvedNames.slice(0, 4).map((name, index) => (
                <CharacterSeal key={index} name={name} size="sm" tone="ink" className="ring-2 ring-panel" />
              ))}
            </span>
          ) : null}
        </div>
      </button>
    </li>
  );
}
