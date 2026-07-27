"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { fetchAssetProposals } from "@/lib/api/asset-proposal-client";
import { ArrowLeft, ArrowRight, Feather, ScrollText } from "lucide-react";

/**
 * The entire conversation dock is one two-sided card.
 *
 * Front: complete co-writer interface (header, durable thread and composer).
 * Back: complete manuscript-asset review interface. The small queue row on the
 * front is only the trigger; the transform is applied to the full-height dock,
 * never to the composer or an individual proposal card.
 */
export function ConversationReviewFlip({
  projectId,
  tenantId,
  /** Bump to re-fetch the count + queue (e.g. after a draft adoption). */
  refreshKey,
  conversation,
  review,
}: {
  projectId: string;
  tenantId: string;
  refreshKey: number;
  conversation: ReactNode;
  review: (onCountChange: (count: number) => void) => ReactNode;
}) {
  const [flipped, setFlipped] = useState(false);
  const [pendingCount, setPendingCount] = useState(0);
  const [hasNew, setHasNew] = useState(false);
  const prevCountRef = useRef(0);

  // The mounted queue reports its pending count up, keeping both faces in
  // lockstep as individual review decisions remove candidates.
  const handleCountChange = useCallback((count: number) => setPendingCount(count), []);

  // Refresh eagerly after adoption as well; the queue then remains the live
  // authority while review decisions are made.
  const loadCount = useCallback(async () => {
    if (!tenantId) return;
    try {
      const items = await fetchAssetProposals(projectId, tenantId, "pending");
      setPendingCount(items.length);
    } catch {
      // leave the last known count; the queue body surfaces real errors
    }
  }, [projectId, tenantId]);

  useEffect(() => {
    void loadCount();
  }, [loadCount, refreshKey]);

  // Flag "new" when the count climbs while the author isn't looking at the queue.
  useEffect(() => {
    if (pendingCount > prevCountRef.current && !flipped) setHasNew(true);
    prevCountRef.current = pendingCount;
  }, [pendingCount, flipped]);

  useEffect(() => {
    if (flipped) setHasNew(false);
  }, [flipped]);

  return (
    <div className="h-full w-full [perspective:1800px]">
      <div
        className={`relative h-full w-full transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none ${
          flipped ? "[transform:rotateY(180deg)]" : ""
        }`}
        style={{ transformStyle: "preserve-3d" }}
      >
        <section
          className={`absolute inset-0 flex min-h-0 flex-col bg-paper/40 ${flipped ? "pointer-events-none" : ""}`}
          style={{ backfaceVisibility: "hidden" }}
          aria-hidden={flipped}
          inert={flipped}
          aria-label="合著者对话"
        >
          <div className="min-h-0 flex-1">{conversation}</div>
          <button
            type="button"
            onClick={() => setFlipped(true)}
            aria-label="翻转到待审资产"
            className="group mx-3 mb-3 flex min-h-12 shrink-0 items-center gap-2.5 rounded-modal border border-line bg-panel px-3.5 text-left shadow-panel transition-colors hover:border-gold/50 hover:bg-gold/5 focus-visible:border-gold"
          >
            <span className="relative grid size-7 shrink-0 place-items-center rounded-control bg-gold/15 text-candidate">
              <ScrollText className="size-3.5" aria-hidden />
              {hasNew ? <span className="absolute -right-0.5 -top-0.5 size-2 rounded-full bg-accent" aria-hidden /> : null}
            </span>
            <span>
              <span className="block text-caption font-semibold tracking-label text-ink">待审资产</span>
              <span className="mt-0.5 block text-caption text-muted">
                {pendingCount > 0 ? `${pendingCount} 条蒸馏结果等你审核` : "查看资产蒸馏审核台"}
              </span>
            </span>
            {pendingCount > 0 ? (
              <span key={pendingCount} className="ml-auto animate-count-up rounded-full bg-candidate px-2 py-0.5 text-caption font-medium tabular-nums text-panel">
                {pendingCount}
              </span>
            ) : null}
            <ArrowRight className="size-4 shrink-0 text-muted-soft transition-transform group-hover:translate-x-0.5" aria-hidden />
          </button>
        </section>

        <section
          className={`absolute inset-0 flex min-h-0 flex-col bg-paper/40 ${!flipped ? "pointer-events-none" : ""}`}
          style={{ backfaceVisibility: "hidden", transform: "rotateY(180deg)" }}
          aria-hidden={!flipped}
          inert={!flipped}
          aria-label="待审资产审核台"
        >
          <header className="flex h-12 shrink-0 items-center gap-2 border-b border-line-soft bg-panel/70 px-3">
            <button
              type="button"
              onClick={() => setFlipped(false)}
              className="grid size-8 shrink-0 place-items-center rounded-control text-muted transition-colors hover:bg-paper hover:text-ink"
              aria-label="返回合著者对话"
            >
              <ArrowLeft className="size-4" aria-hidden />
            </button>
            <span className="grid size-6 place-items-center rounded-control bg-gold/15 text-candidate">
              <ScrollText className="size-3" aria-hidden />
            </span>
            <span className="text-sm font-medium text-ink">待审资产</span>
            <span className="text-caption text-muted">逐条核对后才进入资产库</span>
            {pendingCount > 0 ? (
              <span className="ml-auto rounded-full bg-candidate px-2 py-0.5 text-caption font-medium tabular-nums text-panel">
                {pendingCount}
              </span>
            ) : null}
          </header>
          <div className="min-h-0 flex-1">{review(handleCountChange)}</div>
          <button
            type="button"
            onClick={() => setFlipped(false)}
            className="mx-3 mb-3 flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-panel border border-line bg-panel text-caption font-medium text-muted transition-colors hover:border-accent/30 hover:text-ink"
          >
            <Feather className="size-3.5" aria-hidden />
            返回合著者
          </button>
        </section>
      </div>
    </div>
  );
}
