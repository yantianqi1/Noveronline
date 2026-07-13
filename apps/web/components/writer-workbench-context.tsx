"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type WriterArtifactTab = "manuscript" | "structure" | "review" | "studio";

type WriterWorkbenchContextValue = {
  activeTab: WriterArtifactTab;
  setActiveTab: (tab: WriterArtifactTab) => void;
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
  openPalette: () => void;
  closePalette: () => void;
};

const WriterWorkbenchContext = createContext<WriterWorkbenchContextValue | null>(null);

// Shared client state for the manuscript-primary studio: which artifact tab is active
// and whether the command palette is open. Lets the ⌘K palette drive the canvas tabs.
export function WriterWorkbenchProvider({ children }: { children: ReactNode }) {
  const [activeTab, setActiveTab] = useState<WriterArtifactTab>("manuscript");
  const [paletteOpen, setPaletteOpen] = useState(false);
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && (event.key === "k" || event.key === "K")) {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const value = useMemo<WriterWorkbenchContextValue>(
    () => ({ activeTab, setActiveTab, paletteOpen, setPaletteOpen, openPalette, closePalette }),
    [activeTab, paletteOpen, openPalette, closePalette],
  );

  return <WriterWorkbenchContext.Provider value={value}>{children}</WriterWorkbenchContext.Provider>;
}

export function useWriterWorkbench(): WriterWorkbenchContextValue | null {
  return useContext(WriterWorkbenchContext);
}
