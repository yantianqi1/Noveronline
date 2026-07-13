"use client";

import { Check, X } from "lucide-react";

import type { ApplyHunkDecision, DiffHunk } from "../lib/writer-diff";
import { type Locale, tx } from "../lib/locale";
import { Bi } from "./bilingual-text";

type WriterRevisionDiffProps = {
  locale: Locale;
  hunks: DiffHunk[];
  decisions: Readonly<Record<string, ApplyHunkDecision>>;
  onDecide: (hunkId: string, decision: ApplyHunkDecision) => void;
  onAcceptAll: () => void;
  onRejectAll: () => void;
  onApplyPartial: () => void;
};

/**
 * Hunk list for manuscript revisions.
 * Insert = antique gold wash; delete = ink strike-through; per-hunk + bulk actions.
 */
export function WriterRevisionDiff({
  locale,
  hunks,
  decisions,
  onDecide,
  onAcceptAll,
  onRejectAll,
  onApplyPartial,
}: WriterRevisionDiffProps) {
  if (hunks.length === 0) {
    return null;
  }

  const decided = hunks.filter((hunk) => decisions[hunk.id]).length;

  return (
    <section className="writer-revision-diff" aria-labelledby="writer-revision-diff-heading">
      <header className="writer-revision-diff-head">
        <div>
          <p className="eyebrow"><Bi zh="修订建议" en="Revision" /></p>
          <h3 id="writer-revision-diff-heading">
            <Bi zh="行内差异" en="Inline diff" />
            <small>
              {decided}/{hunks.length} <Bi zh="已决定" en="decided" />
            </small>
          </h3>
        </div>
        <div className="writer-revision-bulk">
          <button type="button" className="writer-revision-bulk-accept" onClick={onAcceptAll}>
            <Check aria-hidden="true" size={14} />
            <Bi zh="全部接受" en="Accept all" />
          </button>
          <button type="button" onClick={onRejectAll}>
            <X aria-hidden="true" size={14} />
            <Bi zh="全部拒绝" en="Reject all" />
          </button>
          {decided > 0 && decided < hunks.length ? (
            <button type="button" data-tone="primary" onClick={onApplyPartial}>
              <Bi zh="应用已决定项" en="Apply decided" />
            </button>
          ) : null}
        </div>
      </header>
      <ol className="writer-revision-hunk-list">
        {hunks.map((hunk, index) => {
          const decision = decisions[hunk.id];
          return (
            <li
              key={hunk.id}
              className="writer-revision-hunk"
              data-op={hunk.op}
              data-decision={decision || "pending"}
            >
              <div className="writer-revision-hunk-meta">
                <span>
                  #{index + 1} · {hunkOpLabel(locale, hunk.op)}
                </span>
                <div className="writer-revision-hunk-actions">
                  <button
                    type="button"
                    aria-pressed={decision === "accept"}
                    className="writer-hunk-accept"
                    onClick={() => onDecide(hunk.id, "accept")}
                  >
                    <Check aria-hidden="true" size={13} />
                    <Bi zh="接受" en="Accept" />
                  </button>
                  <button
                    type="button"
                    aria-pressed={decision === "reject"}
                    className="writer-hunk-reject"
                    onClick={() => onDecide(hunk.id, "reject")}
                  >
                    <X aria-hidden="true" size={13} />
                    <Bi zh="拒绝" en="Reject" />
                  </button>
                </div>
              </div>
              {hunk.op === "delete" || hunk.baseText ? (
                <p className="writer-revision-delete" aria-label={tx(locale, "删除", "Deleted")}>
                  {hunk.baseText || "∅"}
                </p>
              ) : null}
              {hunk.op === "insert" || hunk.proposedText ? (
                <p className="writer-revision-insert" aria-label={tx(locale, "插入", "Inserted")}>
                  {hunk.proposedText || "∅"}
                </p>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function hunkOpLabel(locale: Locale, op: DiffHunk["op"]) {
  if (op === "insert") return tx(locale, "插入", "Insert");
  if (op === "delete") return tx(locale, "删除", "Delete");
  return tx(locale, "保持", "Equal");
}
