"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type WriterDrawer = "structure" | "tools" | "library" | null;
export type WriterMobileView = "conversation" | "artifact";
export type WriterSaveState = "idle" | "dirty" | "saving" | "saved";
export type WriterSaveStatus = { state: WriterSaveState; at: number };
export type WriterFocus = {
  chapterId: string;
  sceneId: string;
  blockId: string;
};

type WriterWorkbenchContextValue = {
  paletteOpen: boolean;
  setPaletteOpen: (open: boolean) => void;
  openPalette: () => void;
  closePalette: () => void;
  mobileView: WriterMobileView;
  setMobileView: (view: WriterMobileView) => void;
  /** Soft pulse on the artifact tab when a new candidate is ready. */
  artifactBadge: boolean;
  clearArtifactBadge: () => void;
  /** Switch to artifact pane on phone and optionally show a badge. */
  revealArtifact: (options?: { badge?: boolean }) => void;
  /** Latest manuscript edit save state, surfaced in the canvas header. */
  saveStatus: WriterSaveStatus;
  setSaveStatus: (state: WriterSaveState) => void;
  /** Bottom drawer system (structure / tools / library). */
  drawer: WriterDrawer;
  setDrawer: (drawer: WriterDrawer) => void;
  toggleDrawer: (drawer: Exclude<WriterDrawer, null>) => void;
  /**
   * Live paper focus mirrored from WriterSelectionProvider so the agent dock
   * (a shell sibling) admits runs against the chapter the author is viewing.
   */
  focus: WriterFocus;
  setFocus: (next: WriterFocus) => void;
};

const WriterWorkbenchContext = createContext<WriterWorkbenchContextValue | null>(null);

const WRITER_MOBILE_VIEW_KEY = "mirofish-writer-mobile-view";

function migrateStoredView(raw: string | null): WriterMobileView {
  if (raw === "conversation" || raw === "agent") return "conversation";
  if (raw === "artifact" || raw === "manuscript" || raw === "structure") return "artifact";
  return "conversation";
}

function readStoredMobileView(): WriterMobileView {
  if (typeof window === "undefined") return "conversation";
  try {
    return migrateStoredView(window.localStorage.getItem(WRITER_MOBILE_VIEW_KEY));
  } catch {
    return "conversation";
  }
}

/**
 * Shared client state for conversation-first Writer: ⌘K palette, phone
 * conversation|artifact pane, save status, and bottom drawers.
 */
export function WriterWorkbenchProvider({ children }: { children: ReactNode }) {
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [mobileView, setMobileViewState] = useState<WriterMobileView>("conversation");
  const [artifactBadge, setArtifactBadge] = useState(false);
  const [saveStatus, setSaveStatusState] = useState<WriterSaveStatus>({ state: "idle", at: 0 });
  const [drawer, setDrawer] = useState<WriterDrawer>(null);
  const [focus, setFocusState] = useState<WriterFocus>({ chapterId: "", sceneId: "", blockId: "" });
  const openPalette = useCallback(() => setPaletteOpen(true), []);
  const closePalette = useCallback(() => setPaletteOpen(false), []);
  const clearArtifactBadge = useCallback(() => setArtifactBadge(false), []);
  const setSaveStatus = useCallback((state: WriterSaveState) => {
    setSaveStatusState({ state, at: Date.now() });
  }, []);
  const toggleDrawer = useCallback((target: Exclude<WriterDrawer, null>) => {
    setDrawer((current) => (current === target ? null : target));
  }, []);
  const setFocus = useCallback((next: WriterFocus) => {
    setFocusState((current) =>
      current.chapterId === next.chapterId &&
      current.sceneId === next.sceneId &&
      current.blockId === next.blockId
        ? current
        : next,
    );
  }, []);

  useEffect(() => {
    setMobileViewState(readStoredMobileView());
  }, []);

  const setMobileView = useCallback((view: WriterMobileView) => {
    setMobileViewState(view);
    if (view === "artifact") {
      setArtifactBadge(false);
    }
    try {
      window.localStorage.setItem(WRITER_MOBILE_VIEW_KEY, view);
    } catch {
      // ignore storage failures
    }
  }, []);

  const revealArtifact = useCallback(
    (options?: { badge?: boolean }) => {
      const narrow = typeof window !== "undefined" && window.matchMedia("(max-width: 960px)").matches;
      if (narrow) {
        setMobileViewState("artifact");
        try {
          window.localStorage.setItem(WRITER_MOBILE_VIEW_KEY, "artifact");
        } catch {
          // ignore
        }
      }
      if (options?.badge !== false) {
        setArtifactBadge(true);
      }
    },
    [],
  );

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && (event.key === "k" || event.key === "K")) {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
      if (event.key === "Escape") {
        setDrawer(null);
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const value = useMemo<WriterWorkbenchContextValue>(
    () => ({
      paletteOpen,
      setPaletteOpen,
      openPalette,
      closePalette,
      mobileView,
      setMobileView,
      artifactBadge,
      clearArtifactBadge,
      revealArtifact,
      saveStatus,
      setSaveStatus,
      drawer,
      setDrawer,
      toggleDrawer,
      focus,
      setFocus,
    }),
    [
      paletteOpen,
      openPalette,
      closePalette,
      mobileView,
      setMobileView,
      artifactBadge,
      clearArtifactBadge,
      revealArtifact,
      saveStatus,
      setSaveStatus,
      drawer,
      toggleDrawer,
      focus,
      setFocus,
    ],
  );

  return <WriterWorkbenchContext.Provider value={value}>{children}</WriterWorkbenchContext.Provider>;
}

export function useWriterWorkbench(): WriterWorkbenchContextValue | null {
  return useContext(WriterWorkbenchContext);
}
