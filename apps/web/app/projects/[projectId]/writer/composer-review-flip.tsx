"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { fetchAssetProposals } from "@/lib/api/asset-proposal-client";

/**
 * The conversation dock is one tabbed panel.
 *
 * 对话: the complete co-writer interface (durable thread + composer).
 * 待审资产: the complete manuscript-asset review queue. The dock-head tabs own
 * switching (⌘J toggles as well); both faces stay mounted and crossfade, so
 * thread scroll and queue state survive every switch.
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
  conversation: (reviewTrigger: ReactNode) => ReactNode;
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

  // ⌘J toggles the two dock faces from anywhere in the workbench.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "j") {
        event.preventDefault();
        setFlipped((value) => !value);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div className="flex h-full w-full min-h-0 flex-col">
      <div className="flex h-12 shrink-0 items-center border-b border-line px-3.5">
        <div role="tablist" aria-label="对话与待审资产切换" className="flex h-full items-center gap-3.5">
          <DockTab active={!flipped} onClick={() => setFlipped(false)}>
            对话
          </DockTab>
          <DockTab active={flipped} onClick={() => setFlipped(true)}>
            待审资产
            {pendingCount > 0 ? (
              <span
                key={pendingCount}
                className="animate-count-up rounded-full bg-paper-deep px-1.5 font-mono text-micro leading-4 text-ink-soft tabular-nums"
              >
                {pendingCount}
              </span>
            ) : null}
            {hasNew ? <span className="size-1.5 rounded-full bg-accent" aria-hidden /> : null}
          </DockTab>
        </div>
        <kbd className="kbd ml-auto">⌘J</kbd>
      </div>

      <div className="relative min-h-0 flex-1">
        <section
          className={`absolute inset-0 flex min-h-0 flex-col bg-paper/40 transition-opacity duration-[160ms] motion-reduce:transition-none ${
            flipped ? "pointer-events-none opacity-0" : "opacity-100"
          }`}
          aria-hidden={flipped}
          inert={flipped}
          aria-label="合著者对话"
        >
          {/* The dock-head tabs own switching now, so nothing is injected into
              the rail header — the render-prop slot stays for the workspace's
              wiring and simply receives no node. */}
          <div className="min-h-0 flex-1">{conversation(null)}</div>
        </section>

        <section
          className={`absolute inset-0 flex min-h-0 flex-col bg-paper/40 transition-opacity duration-[160ms] motion-reduce:transition-none ${
            !flipped ? "pointer-events-none opacity-0" : "opacity-100"
          }`}
          aria-hidden={!flipped}
          inert={!flipped}
          aria-label="待审资产审核台"
        >
          <div className="min-h-0 flex-1">{review(handleCountChange)}</div>
        </section>
      </div>
    </div>
  );
}

/** A dock-head tab: quiet muted text that gains ink weight + a 2px ink
    underline when active — the active marker stays neutral ink, never
    vermilion. */
function DockTab({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`relative flex h-full items-center gap-1.5 text-sm transition-colors ${
        active
          ? "font-semibold text-ink after:absolute after:inset-x-0 after:-bottom-px after:h-0.5 after:bg-ink after:content-['']"
          : "text-muted hover:text-ink-soft"
      }`}
    >
      {children}
    </button>
  );
}
