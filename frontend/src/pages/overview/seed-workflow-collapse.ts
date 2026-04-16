import { useCallback, useRef, useState, type MutableRefObject } from "react";

const STEP_AUTO_COLLAPSE_MS = 3500;
const CHAPTER_AUTO_COLLAPSE_MS = 4500;
const STEP_LOCK_DURATION_MS = 10_000;

type StepState = { collapsed: boolean; lockedUntil: number };
type ChapterState = { collapsed: boolean; manuallyExpanded: boolean };
type TimerRef = MutableRefObject<Map<string, ReturnType<typeof setTimeout>>>;

export interface SeedWorkflowCollapse {
  isStepCollapsed: (stepId: string) => boolean;
  isChapterCollapsed: (key: string) => boolean;
  expandStep: (stepId: string) => void;
  collapseStep: (stepId: string) => void;
  expandChapter: (key: string) => void;
  collapseChapter: (key: string) => void;
  onStepCompleted: (stepId: string, chapterKey: string) => void;
  reset: () => void;
}

export function useSeedWorkflowCollapse(): SeedWorkflowCollapse {
  const steps = useRef(new Map<string, StepState>());
  const chapters = useRef(new Map<string, ChapterState>());
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const [, forceRender] = useState(0);
  const bump = useCallback(() => forceRender((n) => n + 1), []);

  const expandStep = useCallback((stepId: string) => {
    const state = ensureStep(steps.current, stepId);
    state.collapsed = false;
    state.lockedUntil = Date.now() + STEP_LOCK_DURATION_MS;
    clearTimer(timers, stepId);
    bump();
  }, [bump]);

  const collapseStep = useCallback((stepId: string) => {
    const state = ensureStep(steps.current, stepId);
    state.collapsed = true;
    state.lockedUntil = 0;
    clearTimer(timers, stepId);
    bump();
  }, [bump]);

  const expandChapter = useCallback((key: string) => {
    const state = ensureChapter(chapters.current, key);
    state.collapsed = false;
    state.manuallyExpanded = true;
    bump();
  }, [bump]);

  const collapseChapter = useCallback((key: string) => {
    const state = ensureChapter(chapters.current, key);
    state.collapsed = true;
    state.manuallyExpanded = false;
    bump();
  }, [bump]);

  return {
    isStepCollapsed: (stepId) => ensureStep(steps.current, stepId).collapsed,
    isChapterCollapsed: (key) => ensureChapter(chapters.current, key).collapsed,
    expandStep,
    collapseStep,
    expandChapter,
    collapseChapter,
    onStepCompleted: (stepId, chapterKey) => scheduleStepCollapse({ steps, chapters, timers, bump, stepId, chapterKey }),
    reset: () => resetCollapseState({ steps, chapters, timers, bump }),
  };
}

function scheduleStepCollapse(opts: {
  steps: MutableRefObject<Map<string, StepState>>;
  chapters: MutableRefObject<Map<string, ChapterState>>;
  timers: TimerRef;
  bump: () => void;
  stepId: string;
  chapterKey: string;
}) {
  const state = ensureStep(opts.steps.current, opts.stepId);
  if (Date.now() < state.lockedUntil) return;
  clearTimer(opts.timers, opts.stepId);
  const timer = setTimeout(() => collapseUnlockedStep(opts), STEP_AUTO_COLLAPSE_MS);
  opts.timers.current.set(opts.stepId, timer);
}

function collapseUnlockedStep(opts: Parameters<typeof scheduleStepCollapse>[0]) {
  const state = ensureStep(opts.steps.current, opts.stepId);
  if (Date.now() < state.lockedUntil) return;
  state.collapsed = true;
  opts.timers.current.delete(opts.stepId);
  scheduleChapterCollapse(opts);
  opts.bump();
}

function scheduleChapterCollapse(opts: Parameters<typeof scheduleStepCollapse>[0]) {
  const state = ensureChapter(opts.chapters.current, opts.chapterKey);
  if (state.manuallyExpanded) return;
  const timerKey = `ch:${opts.chapterKey}`;
  clearTimer(opts.timers, timerKey);
  const timer = setTimeout(() => {
    const next = ensureChapter(opts.chapters.current, opts.chapterKey);
    if (!next.manuallyExpanded) next.collapsed = true;
    opts.timers.current.delete(timerKey);
    opts.bump();
  }, CHAPTER_AUTO_COLLAPSE_MS);
  opts.timers.current.set(timerKey, timer);
}

function resetCollapseState(opts: {
  steps: MutableRefObject<Map<string, StepState>>;
  chapters: MutableRefObject<Map<string, ChapterState>>;
  timers: TimerRef;
  bump: () => void;
}) {
  for (const timer of opts.timers.current.values()) clearTimeout(timer);
  opts.timers.current.clear();
  opts.steps.current.clear();
  opts.chapters.current.clear();
  opts.bump();
}

function ensureStep(map: Map<string, StepState>, stepId: string): StepState {
  if (!map.has(stepId)) map.set(stepId, { collapsed: false, lockedUntil: 0 });
  return map.get(stepId)!;
}

function ensureChapter(map: Map<string, ChapterState>, key: string): ChapterState {
  if (!map.has(key)) map.set(key, { collapsed: false, manuallyExpanded: false });
  return map.get(key)!;
}

function clearTimer(timers: TimerRef, key: string) {
  const timer = timers.current.get(key);
  if (!timer) return;
  clearTimeout(timer);
  timers.current.delete(key);
}
