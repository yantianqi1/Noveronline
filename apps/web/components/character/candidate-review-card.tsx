"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";

/**
 * CandidateReviewCard — the gold-dashed 「候选 → 采纳」 card shared by both
 * workbenches. It is the visual contract for the safety rule "simulation only
 * produces candidates": anything proposed (a worldline candidate event, a
 * character proposal) shows in gold with a 候选 corner tag; the vermilion
 * 「采纳」 button is the explicit author action that promotes it to canon.
 *
 * The card is presentation + explicit actions only. It never invents content —
 * title/summary/meta come from the record, and the adopt/edit/reject handlers
 * are owned by the parent workbench.
 */

export type CandidateMeta = { label: string; value: string };

export function CandidateReviewCard({
  title,
  summary,
  metas = [],
  sourceLabel,
  busy = false,
  onAdopt,
  onReject,
  onEdit,
  className,
}: {
  title: string;
  summary: string;
  /** Small key/value rows (e.g. confidence, involved agents, state changes). */
  metas?: CandidateMeta[];
  /** Where this candidate came from (档案驱动 / 目标驱动 / 变量触发 / 角色主动). */
  sourceLabel?: string;
  busy?: boolean;
  onAdopt?: () => void;
  onReject?: () => void;
  /** Edit the candidate's consequences before adopting (expands inline). */
  onEdit?: (draft: string) => void;
  className?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(summary);

  return (
    <article
      className={cn(
        "relative rounded-[12px] border border-dashed border-gold/60 bg-gold/[0.05] p-4",
        className,
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <h4 className="font-serif text-[15px] font-semibold leading-snug text-ink">{title}</h4>
        <span className="shrink-0 rounded-[5px] border border-gold/50 bg-gold/10 px-1.5 py-0.5 text-[10px] font-medium tracking-[0.12em] text-gold">
          候选
        </span>
      </div>

      {sourceLabel ? (
        <p className="mt-1 text-[11px] tracking-wide text-muted">{sourceLabel}</p>
      ) : null}

      <p className="mt-2 font-serif text-[13.5px] leading-[1.85] text-ink-soft">{summary}</p>

      {metas.length > 0 ? (
        <dl className="mt-3 space-y-1.5 border-t border-gold/25 pt-3">
          {metas.map((meta) => (
            <div key={meta.label} className="flex items-baseline justify-between gap-3 text-[12px]">
              <dt className="shrink-0 text-muted">{meta.label}</dt>
              <dd className="min-w-0 truncate text-right text-ink-soft">{meta.value}</dd>
            </div>
          ))}
        </dl>
      ) : null}

      {editing ? (
        <div className="mt-3 border-t border-gold/25 pt-3">
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            rows={3}
            className="w-full resize-none rounded-[8px] border border-line bg-panel px-3 py-2 font-serif text-[13px] leading-relaxed text-ink outline-none focus:border-accent/50"
            placeholder="修正这条候选的走向…"
          />
          <div className="mt-2 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => {
                setEditing(false);
                setDraft(summary);
              }}
              className="rounded-[8px] border border-line bg-panel px-3 py-1.5 text-[12px] text-muted transition-colors hover:text-ink"
            >
              取消
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                onEdit?.(draft);
                setEditing(false);
              }}
              className="rounded-[8px] border border-accent/40 bg-accent-wash px-3 py-1.5 text-[12px] font-medium text-accent transition-colors hover:bg-accent/15 disabled:opacity-50"
            >
              保存修改
            </button>
          </div>
        </div>
      ) : null}

      {(onAdopt || onReject || onEdit) && !editing ? (
        <div className="mt-3 flex items-center gap-2 border-t border-gold/25 pt-3">
          {onAdopt ? (
            <button
              type="button"
              disabled={busy}
              onClick={onAdopt}
              className="rounded-[8px] bg-accent px-3.5 py-1.5 text-[12.5px] font-medium text-panel shadow-sm transition-colors hover:bg-accent-strong disabled:opacity-50"
            >
              采纳
            </button>
          ) : null}
          {onEdit ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setDraft(summary);
                setEditing(true);
              }}
              className="rounded-[8px] border border-line bg-panel px-3 py-1.5 text-[12px] text-ink transition-colors hover:border-accent/40 hover:text-accent disabled:opacity-50"
            >
              编辑后果
            </button>
          ) : null}
          {onReject ? (
            <button
              type="button"
              disabled={busy}
              onClick={onReject}
              className="ml-auto rounded-[8px] px-3 py-1.5 text-[12px] text-muted transition-colors hover:text-accent disabled:opacity-50"
            >
              拒绝
            </button>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
