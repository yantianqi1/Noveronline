"use client";

import { Bot, PenLine } from "lucide-react";
import { useCallback, useEffect, useRef, type ReactNode } from "react";

import { type Locale, tx } from "../lib/locale";
import { useWriterWorkbench, type WriterMobileView } from "./writer-workbench-context";

type WriterMobileSwitchProps = {
  locale: Locale;
  /** Kept for call-site compatibility; structure rail is retired in doc 36 W4. */
  hasStructure?: boolean;
};

/**
 * Mobile two-pane switch (doc 36 W5): conversation | artifact.
 * Supports horizontal swipe on the writer layout and a badge when a candidate is ready.
 */
export function WriterMobileSwitch({ locale }: WriterMobileSwitchProps) {
  const workbench = useWriterWorkbench();
  const view = workbench?.mobileView ?? "conversation";
  const setView = workbench?.setMobileView;
  const artifactBadge = workbench?.artifactBadge === true;
  const clearArtifactBadge = workbench?.clearArtifactBadge;
  const navRef = useRef<HTMLElement>(null);
  const touchStart = useRef<{ x: number; y: number } | null>(null);

  const layoutElement = useCallback(() => {
    const nav = navRef.current;
    if (!nav) return null;
    let sibling = nav.nextElementSibling;
    while (sibling && !sibling.classList.contains("writer-agent-layout")) {
      sibling = sibling.nextElementSibling;
    }
    return sibling as HTMLElement | null;
  }, []);

  useEffect(() => {
    const layout = layoutElement();
    if (layout) {
      layout.dataset.mobileView = view;
    }
  }, [view, layoutElement]);

  useEffect(() => {
    const layout = layoutElement();
    if (!layout || !setView) return;

    const onTouchStart = (event: Event) => {
      const touchEvent = event as globalThis.TouchEvent;
      const touch = touchEvent.changedTouches[0];
      if (!touch) return;
      touchStart.current = { x: touch.clientX, y: touch.clientY };
    };

    const onTouchEnd = (event: Event) => {
      const start = touchStart.current;
      touchStart.current = null;
      const touchEvent = event as globalThis.TouchEvent;
      const touch = touchEvent.changedTouches[0];
      if (!start || !touch) return;
      const dx = touch.clientX - start.x;
      const dy = touch.clientY - start.y;
      if (Math.abs(dx) < 56 || Math.abs(dx) < Math.abs(dy) * 1.35) return;
      if (dx < 0) {
        setView("artifact");
        clearArtifactBadge?.();
      } else {
        setView("conversation");
      }
    };

    layout.addEventListener("touchstart", onTouchStart, { passive: true });
    layout.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => {
      layout.removeEventListener("touchstart", onTouchStart);
      layout.removeEventListener("touchend", onTouchEnd);
    };
  }, [layoutElement, setView, clearArtifactBadge]);

  const views: { id: WriterMobileView; label: string; icon: ReactNode; badge?: boolean }[] = [
    { id: "conversation", label: tx(locale, "对话", "Chat"), icon: <Bot aria-hidden="true" size={17} /> },
    {
      id: "artifact",
      label: tx(locale, "产物", "Canvas"),
      icon: <PenLine aria-hidden="true" size={17} />,
      badge: artifactBadge,
    },
  ];

  return (
    <nav className="writer-mobile-switch" aria-label={tx(locale, "切换写作区域", "Switch writer region")} ref={navRef}>
      {views.map((entry) => (
        <button
          aria-pressed={view === entry.id}
          className="writer-mobile-switch-tab"
          data-active={view === entry.id ? "true" : "false"}
          key={entry.id}
          onClick={() => {
            setView?.(entry.id);
            if (entry.id === "artifact") clearArtifactBadge?.();
          }}
          type="button"
        >
          {entry.icon}
          <span>{entry.label}</span>
          {entry.badge ? <span aria-hidden="true" className="writer-mobile-switch-badge" /> : null}
        </button>
      ))}
    </nav>
  );
}
