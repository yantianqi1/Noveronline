"use client";

import { useState } from "react";

import { cn } from "@/lib/utils";
import type { WorldlineEvent } from "@/lib/api/worldline-types";

import { stateChangeView } from "./worldline-model";

/**
 * One 待定夺 gold card in the decision queue (方案A). Carries everything the
 * author needs to judge a step: 把握 badge, kind, title/summary, 涉及 and
 * 状态变化. The three explicit verdicts: 采纳 (vermilion, promotes to canon),
 * 改一改 (PATCH the summary before judging), 暂不采纳 (persisted rejection —
 * the parent calls the rejections endpoint; the card never hides itself).
 */
export function WorldlineCandidateCard({
  event,
  busy = false,
  involvedNames = [],
  onAdopt,
  onEdit,
  onReject,
}: {
  event: WorldlineEvent;
  /** This card's request is in flight — freeze its buttons, never its data. */
  busy?: boolean;
  involvedNames?: string[];
  onAdopt?: (event: WorldlineEvent) => void;
  onEdit?: (event: WorldlineEvent, draft: string) => void;
  onReject?: (event: WorldlineEvent) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(event.summary);
  const stateChanges = stateChangeView(event.state_changes);

  return (
    <article
      className={cn(
        "rounded-panel border border-gold/40 border-l-2 border-l-gold bg-candidate-wash/40 bg-panel p-4 transition-colors",
        busy && "opacity-70",
      )}
    >
      <div className="flex items-center gap-2">
        <span className="shrink-0 rounded-full bg-gold px-2 py-0.5 text-caption font-medium text-panel">待定夺</span>
        {event.confidence ? (
          <span className="shrink-0 rounded-full border border-gold/60 bg-candidate-wash px-2 py-0.5 text-caption text-candidate">
            把握 {event.confidence}
          </span>
        ) : null}
        {event.kind ? <span className="ml-auto shrink-0 text-caption text-muted">{event.kind}</span> : null}
      </div>

      <h4 className="mt-2.5 font-serif text-md font-semibold leading-snug text-ink">{event.title}</h4>
      {event.summary ? <p className="mt-1.5 font-serif text-sm leading-relaxed text-ink-soft">{event.summary}</p> : null}

      {involvedNames.length > 0 ? (
        <p className="mt-2 text-caption leading-relaxed text-muted">
          <span className="text-muted-soft">涉及：</span>
          {involvedNames.join("、")}
        </p>
      ) : null}
      {stateChanges.summary ? (
        <p className="mt-1 text-caption leading-relaxed text-muted">
          <span className="text-muted-soft">状态变化：</span>
          {stateChanges.summary}
        </p>
      ) : null}

      {editing ? (
        <div className="mt-3 border-t border-gold/25 pt-3">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={3}
            className="w-full resize-y rounded-control border border-line bg-panel px-3 py-2 font-serif text-sm leading-relaxed text-ink outline-none focus:border-accent/50"
            placeholder="修正这条候选的走向…"
          />
          <div className="mt-2 flex gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                const next = draft.trim();
                if (next && next !== event.summary) onEdit?.(event, next);
                setEditing(false);
              }}
              className="rounded-control bg-accent px-3 py-1.5 text-caption font-medium text-panel transition-colors hover:bg-accent-strong disabled:opacity-50"
            >
              保存
            </button>
            <button
              type="button"
              onClick={() => {
                setDraft(event.summary);
                setEditing(false);
              }}
              className="rounded-control px-3 py-1.5 text-caption text-muted transition-colors hover:text-ink"
            >
              取消
            </button>
          </div>
        </div>
      ) : null}

      {!editing ? (
        <div className="mt-3 flex items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => onAdopt?.(event)}
            className="rounded-control bg-accent px-3.5 py-1.5 text-caption font-medium text-panel shadow-hairline transition-colors hover:bg-accent-strong disabled:opacity-50"
          >
            采纳
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setDraft(event.summary);
              setEditing(true);
            }}
            className="rounded-control border border-line bg-panel px-3 py-1.5 text-caption text-ink transition-colors hover:border-accent/50 hover:text-accent disabled:opacity-50"
          >
            改一改
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => onReject?.(event)}
            className="ml-auto rounded-control px-3 py-1.5 text-caption text-muted transition-colors hover:text-accent disabled:opacity-50"
          >
            暂不采纳
          </button>
        </div>
      ) : null}
    </article>
  );
}
