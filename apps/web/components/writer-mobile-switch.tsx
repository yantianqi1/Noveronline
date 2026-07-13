"use client";

import { Bot, ListTree, PenLine } from "lucide-react";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

import { type Locale, tx } from "../lib/locale";

type WriterMobileView = "structure" | "manuscript" | "agent";

type WriterMobileSwitchProps = {
  locale: Locale;
  hasStructure: boolean;
};

/**
 * Mobile-only region switch for the manuscript-primary writer layout.
 *
 * The three regions (`writer-structure-rail`, `writer-artifact-canvas`,
 * `writer-agent-dock`) are server-rendered in the shell. On desktop this
 * control is hidden and the CSS grid shows every region, so the established
 * layout is untouched. On narrow screens it drives `data-mobile-view` on the
 * sibling `.writer-agent-layout`, and the CSS shows only the selected region —
 * turning a long triple-stacked scroll into focused, switchable panes.
 */
export function WriterMobileSwitch({ locale, hasStructure }: WriterMobileSwitchProps) {
  const [view, setView] = useState<WriterMobileView>("manuscript");
  const navRef = useRef<HTMLElement>(null);

  const layoutElement = useCallback(() => {
    const nav = navRef.current;
    if (!nav) {
      return null;
    }
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

  const views: { id: WriterMobileView; label: string; icon: ReactNode; show: boolean }[] = [
    { id: "structure", label: tx(locale, "结构", "Structure"), icon: <ListTree aria-hidden="true" size={17} />, show: hasStructure },
    { id: "manuscript", label: tx(locale, "手稿", "Manuscript"), icon: <PenLine aria-hidden="true" size={17} />, show: true },
    { id: "agent", label: tx(locale, "写作 Agent", "Agent"), icon: <Bot aria-hidden="true" size={17} />, show: true },
  ];

  return (
    <nav className="writer-mobile-switch" aria-label={tx(locale, "切换写作区域", "Switch writer region")} ref={navRef}>
      {views
        .filter((entry) => entry.show)
        .map((entry) => (
          <button
            aria-pressed={view === entry.id}
            className="writer-mobile-switch-tab"
            data-active={view === entry.id ? "true" : "false"}
            key={entry.id}
            onClick={() => setView(entry.id)}
            type="button"
          >
            {entry.icon}
            <span>{entry.label}</span>
          </button>
        ))}
    </nav>
  );
}
