/**
 * Writer workbench layout preferences — persists layout version, panel sizes,
 * outline tree collapse state, and pinned book_plan id to localStorage.
 *
 * Layout version resolution (low → high priority):
 *   1. env VITE_WRITER_LAYOUT_V2_DEFAULT ("true" | "false")
 *   2. localStorage (this store's persist key)
 *   3. URL query ?layout=v1|v2  (session-only, not written back)
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

const STORAGE_KEY = "novelwork.writerLayoutV2";

export type LayoutVersion = "v1" | "v2";

function readEnvDefault(): LayoutVersion {
  const raw = (import.meta as unknown as {
    env?: { VITE_WRITER_LAYOUT_V2_DEFAULT?: string };
  }).env?.VITE_WRITER_LAYOUT_V2_DEFAULT;
  return raw === "true" ? "v2" : "v1";
}

function readUrlOverride(): LayoutVersion | null {
  if (typeof window === "undefined") return null;
  const params = new URLSearchParams(window.location.search);
  const q = params.get("layout");
  return q === "v1" || q === "v2" ? q : null;
}

export interface WriterLayoutState {
  /** Persisted user preference. URL override takes precedence via getEffectiveVersion(). */
  layoutVersion: LayoutVersion;
  /** Whether left outline tree is collapsed (v2 only). */
  outlineTreeCollapsed: boolean;
  /** Panel sizes persisted from ResizablePanelGroup (v2 only). */
  panelSizes: { outline: number; main: number; tools: number };
  /** User-chosen plan to pin at the top StatusBar; overrides activePlanId. */
  pinnedPlanId: string | null;
}

export interface WriterLayoutActions {
  setLayoutVersion: (v: LayoutVersion) => void;
  toggleOutlineTreeCollapsed: () => void;
  setPanelSizes: (sizes: { outline: number; main: number; tools: number }) => void;
  setPinnedPlanId: (planId: string | null) => void;
  /** Compose persisted value with URL override (URL wins, session-only). */
  getEffectiveVersion: () => LayoutVersion;
}

const initialState: WriterLayoutState = {
  layoutVersion: readEnvDefault(),
  outlineTreeCollapsed: false,
  panelSizes: { outline: 26, main: 56, tools: 18 },
  pinnedPlanId: null,
};

export const useWriterLayoutStore = create<
  WriterLayoutState & WriterLayoutActions
>()(
  persist(
    (set, get) => ({
      ...initialState,

      setLayoutVersion: (v) => set({ layoutVersion: v }),

      toggleOutlineTreeCollapsed: () =>
        set((s) => ({ outlineTreeCollapsed: !s.outlineTreeCollapsed })),

      setPanelSizes: (sizes) => set({ panelSizes: sizes }),

      setPinnedPlanId: (planId) => set({ pinnedPlanId: planId }),

      getEffectiveVersion: () => readUrlOverride() ?? get().layoutVersion,
    }),
    {
      name: STORAGE_KEY,
      partialize: (s) => ({
        layoutVersion: s.layoutVersion,
        outlineTreeCollapsed: s.outlineTreeCollapsed,
        panelSizes: s.panelSizes,
        pinnedPlanId: s.pinnedPlanId,
      }),
    },
  ),
);
