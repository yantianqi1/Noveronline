/**
 * book_run runtime status store — single source of truth for the writer
 * StatusBar and BookPlanPanel. Pooled data lands via setFromStatus(); SSE
 * events from a live book_run patch via patchFromEvent().
 *
 * The store also owns the AbortController so multiple subscribers
 * (StatusBar + BookPlanPanel) can observe the SSE without any one of them
 * accidentally aborting the stream on unmount (see docs/plans/2026-04-19-writer-workbench-book-integration-plan.md §1.8.2).
 */

import { create } from "zustand";

export type BookRunStage =
  | "PLAN_INIT"
  | "RETRIEVE"
  | "OUTLINE"
  | "CHAPTER_WRITE"
  | "WORD_AUDIT"
  | "LEXICON_AUDIT"
  | "CHAPTER_COMMIT"
  | "DONE"
  | "";

export interface BookRunChapterRow {
  chapter_order: number;
  chapter_id?: string;
  title?: string;
  status: string;
  word_count: number;
  target: number;
  diff_pct?: number;
  lexicon_hits?: number;
  audit_round?: number;
}

export interface BookRunPlanStatus {
  plan_id: string;
  project_id: string;
  title: string;
  status: string;
  last_stage: string;
  current_chapter_order: number;
  chapter_count: number;
  per_chapter_word_target: number;
  total_word_target: number;
  chapters: Array<{
    chapter_id: string;
    chapter_order: number;
    title: string;
    status: string;
    word_count: number;
  }>;
  words_written_total: number;
  progress_pct: number;
  completed_chapter_count: number;
  in_progress_chapter_order: number | null;
  error_count: number;
  updated_at: string;
}

export interface BookRunStoreState {
  /** The plan id reflected by this store. */
  planId: string | null;
  /** Latest server-side aggregate, from polling. */
  status: BookRunPlanStatus | null;
  /** Latest stage from live SSE (wins over status.last_stage while running). */
  stage: BookRunStage;
  /** Per-chapter live metrics keyed by chapter_order (SSE-sourced). */
  chapters: Record<number, BookRunChapterRow>;
  /** True while a book_run SSE is active (observed by subscribers). */
  running: boolean;
  /** Unix ms of the latest SSE event received. */
  lastEventAt: number | null;
  /** Optional abort controller shared across subscribers. */
  abortController: AbortController | null;
}

export interface BookRunStoreActions {
  setPlanId: (planId: string | null) => void;
  setFromStatus: (status: BookRunPlanStatus | null) => void;
  patchFromEvent: (event: Record<string, unknown>) => void;
  setRunning: (running: boolean) => void;
  setAbortController: (controller: AbortController | null) => void;
  resetRuntime: () => void;
}

const initialState: BookRunStoreState = {
  planId: null,
  status: null,
  stage: "",
  chapters: {},
  running: false,
  lastEventAt: null,
  abortController: null,
};

export const useBookRunStatusStore = create<
  BookRunStoreState & BookRunStoreActions
>()((set, get) => ({
  ...initialState,

  setPlanId: (planId) => {
    const current = get().planId;
    if (current === planId) return;
    // New plan focus: drop stale runtime, keep nothing else.
    set({
      ...initialState,
      planId,
    });
  },

  setFromStatus: (status) => {
    if (!status) {
      set({ status: null });
      return;
    }
    // Only accept status that matches the focused plan id — otherwise
    // stale polling responses could overwrite the current plan's data.
    const { planId } = get();
    if (planId && status.plan_id !== planId) return;
    set({ status });
  },

  patchFromEvent: (event) => {
    const type = event?.type as string | undefined;
    if (!type) return;
    const now = Date.now();
    if (type === "book_run_stage") {
      const stage = (event.stage as BookRunStage) || "";
      const order = typeof event.chapter_order === "number" ? event.chapter_order : null;
      set((s) => ({
        stage,
        lastEventAt: now,
        chapters:
          order !== null
            ? {
                ...s.chapters,
                [order]: {
                  ...(s.chapters[order] || {
                    chapter_order: order,
                    status: "pending",
                    word_count: 0,
                    target: 0,
                  }),
                  status: stage,
                  chapter_order: order,
                },
              }
            : s.chapters,
      }));
    } else if (type === "chapter_progress") {
      const order = typeof event.chapter_order === "number" ? event.chapter_order : null;
      if (order === null) return;
      set((s) => ({
        lastEventAt: now,
        chapters: {
          ...s.chapters,
          [order]: {
            ...(s.chapters[order] || {
              chapter_order: order,
              status: "writing",
              word_count: 0,
              target: 0,
            }),
            chapter_order: order,
            word_count: typeof event.word_count === "number" ? event.word_count : 0,
            target: typeof event.target === "number" ? event.target : 0,
            diff_pct: typeof event.diff_pct === "number" ? event.diff_pct : 0,
          },
        },
      }));
    } else if (type === "audit_hit") {
      const order = typeof event.chapter_order === "number" ? event.chapter_order : null;
      if (order === null) return;
      const details = (event.details as { count?: number } | undefined) || {};
      set((s) => ({
        lastEventAt: now,
        chapters: {
          ...s.chapters,
          [order]: {
            ...(s.chapters[order] || {
              chapter_order: order,
              status: "auditing",
              word_count: 0,
              target: 0,
            }),
            chapter_order: order,
            lexicon_hits: details.count || 0,
          },
        },
      }));
    } else if (type === "audit_fixed") {
      const order = typeof event.chapter_order === "number" ? event.chapter_order : null;
      if (order === null) return;
      set((s) => ({
        lastEventAt: now,
        chapters: {
          ...s.chapters,
          [order]: {
            ...(s.chapters[order] || {
              chapter_order: order,
              status: "auditing",
              word_count: 0,
              target: 0,
            }),
            chapter_order: order,
            lexicon_hits: typeof event.remaining === "number" ? event.remaining : 0,
            audit_round: typeof event.round === "number" ? event.round : 0,
          },
        },
      }));
    } else if (type === "book_run_done") {
      set({ stage: "DONE", lastEventAt: now });
    }
  },

  setRunning: (running) => set({ running }),

  setAbortController: (controller) => set({ abortController: controller }),

  resetRuntime: () =>
    set({
      stage: "",
      chapters: {},
      lastEventAt: null,
      running: false,
      abortController: null,
    }),
}));
