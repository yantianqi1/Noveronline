/**
 * Worldline workbench layout store — persists pane widths and collapse
 * state to localStorage via Zustand `persist` middleware.
 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

const STORAGE_KEY = "novelwork.worldlineLayout";

const DEFAULT_LEFT_WIDTH = 300;
const DEFAULT_CENTER_WIDTH = 480;
const DEFAULT_RIGHT_WIDTH = 360;
const MIN_PANE_WIDTH = 180;
const MAX_PANE_RATIO = 0.45;

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function clampPaneWidth(value: number): number {
  const maxWidth =
    typeof window !== "undefined"
      ? Math.round(window.innerWidth * MAX_PANE_RATIO)
      : 800;
  return clamp(value, MIN_PANE_WIDTH, maxWidth);
}

/* ---------- Store shape ---------- */

export interface LayoutState {
  leftWidth: number;
  centerWidth: number;
  rightWidth: number;
  leftCollapsed: boolean;
  rightCollapsed: boolean;
}

export interface LayoutActions {
  setLeftWidth: (width: number) => void;
  setCenterWidth: (width: number) => void;
  setRightWidth: (width: number) => void;
  toggleLeft: () => void;
  toggleRight: () => void;
  resetLayout: () => void;
}

const initialState: LayoutState = {
  leftWidth: DEFAULT_LEFT_WIDTH,
  centerWidth: DEFAULT_CENTER_WIDTH,
  rightWidth: DEFAULT_RIGHT_WIDTH,
  leftCollapsed: false,
  rightCollapsed: false,
};

export const useLayoutStore = create<LayoutState & LayoutActions>()(
  persist(
    (set) => ({
      ...initialState,

      setLeftWidth: (width: number) =>
        set({ leftWidth: clampPaneWidth(width) }),

      setCenterWidth: (width: number) =>
        set({ centerWidth: clampPaneWidth(width) }),

      setRightWidth: (width: number) =>
        set({ rightWidth: clampPaneWidth(width) }),

      toggleLeft: () =>
        set((s) => ({ leftCollapsed: !s.leftCollapsed })),

      toggleRight: () =>
        set((s) => ({ rightCollapsed: !s.rightCollapsed })),

      resetLayout: () => set(initialState),
    }),
    { name: STORAGE_KEY },
  ),
);
