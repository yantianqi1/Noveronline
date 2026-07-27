"use client";

import { X } from "lucide-react";

import { CandidateReviewCard } from "@/components/character";
import { IconButton } from "@/components/ui/icon-button";
import type { WorldlineEvent } from "@/lib/api/worldline-types";
import { cn } from "@/lib/utils";

/**
 * The right 候选 rail — the gold-dashed queue of events the simulation offered
 * but the author has not confirmed. Each card carries the shared 「候选 → 采纳」
 * contract: adopt (vermilion), edit consequences, or reject. Adopting a card
 * here is what moves an event onto the timeline as canon.
 *
 * Inline at the wide band; an overlay drawer below it, because pinning three
 * fixed columns used to crush the timeline between them — at an 883px viewport
 * the centre measured 65px and the run button wrapped one glyph per line.
 */

export function WorldlineCandidateRail({
  candidates,
  busyId,
  open = false,
  onClose,
  onAdopt,
  onEdit,
  onReject,
}: {
  candidates: WorldlineEvent[];
  /** event_id currently being adopted/edited (disables its card). */
  busyId?: string | null;
  /** Drawer visibility below the wide band. Always inline at wide. */
  open?: boolean;
  onClose?: () => void;
  onAdopt?: (event: WorldlineEvent) => void;
  onEdit?: (event: WorldlineEvent, draft: string) => void;
  onReject?: (event: WorldlineEvent) => void;
}) {
  return (
    <>
      {open ? (
        <div aria-hidden onClick={onClose} className="fixed inset-0 z-30 bg-ink/45 wide:hidden" />
      ) : null}
      <aside
        className={cn(
          "h-full w-rail-inspector shrink-0 flex-col overflow-hidden border-l border-line bg-paper/40",
          "max-wide:fixed max-wide:inset-y-0 max-wide:right-0 max-wide:z-40 max-wide:w-full max-wide:max-w-[420px] max-wide:bg-panel max-wide:shadow-panel",
          open ? "flex" : "hidden wide:flex",
        )}
      >
      <header className="flex shrink-0 items-start justify-between gap-2 border-b border-line-soft px-5 py-4">
        <div className="min-w-0">
          <h3 className="text-caption font-medium tracking-label text-muted">候选事件</h3>
          <p className="mt-1 text-caption text-muted">
            {candidates.length === 0 ? "推演出来的事件会先落在这里待审。" : `${candidates.length} 条待审`}
          </p>
        </div>
        <IconButton label="关闭候选" size="sm" onClick={onClose} className="wide:hidden">
          <X className="size-4" aria-hidden />
        </IconButton>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {candidates.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center px-4 text-center">
            <p className="font-serif text-base text-ink">还没有候选事件</p>
            <p className="mt-1.5 max-w-[220px] text-caption leading-relaxed text-muted">
              推进一步或注入变量，世界会提出新的走向。
            </p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {candidates.map((event) => (
              <CandidateReviewCard
                key={event.event_id}
                title={event.title}
                summary={event.summary}
                sourceLabel={sourceLabelFor(event)}
                metas={metasFor(event)}
                busy={busyId === event.event_id}
                onAdopt={onAdopt ? () => onAdopt(event) : undefined}
                onEdit={onEdit ? (draft) => onEdit(event, draft) : undefined}
                onReject={onReject ? () => onReject(event) : undefined}
              />
            ))}
          </div>
        )}
      </div>
      </aside>
    </>
  );
}

function sourceLabelFor(event: WorldlineEvent): string | undefined {
  if (!event.kind) return undefined;
  return `来源 · ${event.kind}`;
}

function metasFor(event: WorldlineEvent): { label: string; value: string }[] {
  const metas: { label: string; value: string }[] = [];
  if (event.confidence) metas.push({ label: "置信度", value: event.confidence });
  if (event.involved_agent_ids && event.involved_agent_ids.length > 0) {
    metas.push({ label: "涉及角色", value: `${event.involved_agent_ids.length} 位` });
  }
  return metas;
}
