/**
 * Seed upload Zustand store — global state for novel seed upload + task polling.
 *
 * Ported from src-vue/composables/useSeedUpload.js
 */

import { create } from "zustand";

import type {
  ActiveStage,
  SeedLlmActivity,
  SequentialReadingRetry,
  TaskMetrics,
  TimelineEvent,
} from "@/lib/seed-upload-task-state";
import {
  DEFAULT_ACTIVE_STAGE,
  DEFAULT_LLM_ACTIVITY,
  DEFAULT_TASK_METRICS,
} from "@/lib/seed-upload-task-state";

/* ---------- Types ---------- */

export type UploadPhase = "idle" | "uploading" | "processing" | "success" | "error";

export interface SeedUploadViewState {
  activeStage: ActiveStage;
  taskMetrics: TaskMetrics;
  llmActivity: SeedLlmActivity;
  timeline: TimelineEvent[];
  taskStartedAt: string;
  sequentialReadingRetry?: SequentialReadingRetry;
}

export interface SeedUploadResult {
  project_id: string;
  project_name: string;
  task_id: string;
  task_result: Record<string, unknown>;
  task_message: string;
}

export interface SeedUploadState extends SeedUploadViewState {
  /* ---- form fields ---- */
  projectName: string;
  analysisGoal: string;
  additionalContext: string;
  segmentTokenLimit: number;
  files: File[];
  dragActive: boolean;
  /* ---- upload / task tracking ---- */
  uploadBusy: boolean;
  uploadPhase: UploadPhase;
  progressPercent: number;
  uploadedBytes: number;
  totalBytes: number;
  taskId: string;
  taskStatus: string;
  result: SeedUploadResult | null;
  error: string;
  completedProjectId: string;
  statusText: string;
  stageLabel: string;
}

export interface SeedUploadActions {
  appendFiles: (files: File[]) => void;
  removeFile: (file: File) => void;
  setField: <K extends keyof SeedUploadState>(key: K, value: SeedUploadState[K]) => void;
  patchState: (patch: Partial<SeedUploadState>) => void;
  patchView: (view: Partial<SeedUploadViewState>) => void;
  reset: () => void;
  clearNotice: () => void;
}

/* ---------- Helpers ---------- */

function fileKey(file: File): string {
  return `${file.name}_${file.size}_${file.lastModified}`;
}

function isSupported(file: File): boolean {
  return /\.(txt|md|markdown|pdf)$/i.test(file.name || "");
}

function hasFile(existing: File[], incoming: File): boolean {
  return existing.some((item) => fileKey(item) === fileKey(incoming));
}

function stemFromFileName(name: string): string {
  const base = name.replace(/^.*[\\/]/, "");
  const idx = base.lastIndexOf(".");
  return (idx > 0 ? base.slice(0, idx) : base).trim();
}

const DEFAULT_GOAL = "提取全部有名角色、组织和关系，用于世界线推演。";
const DEFAULT_PROJECT_NAME = "我的小说项目";

const initialState: SeedUploadState = {
  projectName: DEFAULT_PROJECT_NAME,
  analysisGoal: DEFAULT_GOAL,
  additionalContext: "",
  segmentTokenLimit: 50000,
  files: [],
  dragActive: false,
  uploadBusy: false,
  uploadPhase: "idle",
  progressPercent: 0,
  uploadedBytes: 0,
  totalBytes: 0,
  taskId: "",
  taskStatus: "",
  result: null,
  error: "",
  completedProjectId: "",
  statusText: "等待上传",
  stageLabel: "",
  activeStage: { ...DEFAULT_ACTIVE_STAGE },
  taskMetrics: { ...DEFAULT_TASK_METRICS },
  llmActivity: { ...DEFAULT_LLM_ACTIVITY },
  timeline: [],
  taskStartedAt: "",
  sequentialReadingRetry: undefined,
};

/* ---------- Store ---------- */

export const useSeedUploadStore = create<SeedUploadState & SeedUploadActions>()(
  (set, get) => ({
    ...initialState,

    appendFiles: (nextFiles: File[]) => {
      const current = get().files;
      const merged = [...current];
      for (const file of nextFiles) {
        if (!isSupported(file) || hasFile(merged, file)) continue;
        merged.push(file);
      }
      const patch: Partial<SeedUploadState> = { files: merged };
      const currentName = get().projectName.trim();
      const isPlaceholder = !currentName || currentName === DEFAULT_PROJECT_NAME;
      if (isPlaceholder && merged.length > current.length) {
        const firstNew = merged[current.length];
        if (firstNew) {
          const stem = stemFromFileName(firstNew.name);
          if (stem) patch.projectName = stem;
        }
      }
      set(patch);
    },

    removeFile: (file: File) => {
      set({ files: get().files.filter((item) => fileKey(item) !== fileKey(file)) });
    },

    setField: (key, value) => {
      set({ [key]: value } as Partial<SeedUploadState>);
    },

    patchState: (patch) => set(patch),

    patchView: (view) => set(view),

    reset: () => set(initialState),

    clearNotice: () => {
      if (get().uploadBusy) return;
      set({
        uploadPhase: "idle",
        progressPercent: 0,
        statusText: "等待上传",
        stageLabel: "",
        taskId: "",
        taskStatus: "",
        result: null,
        error: "",
        activeStage: { ...DEFAULT_ACTIVE_STAGE },
        taskMetrics: { ...DEFAULT_TASK_METRICS },
        llmActivity: { ...DEFAULT_LLM_ACTIVITY },
        timeline: [],
        taskStartedAt: "",
        sequentialReadingRetry: undefined,
      });
      clearPersistedActiveTask();
    },
  }),
);

/* ---------- localStorage persistence for active task ---------- */

const ACTIVE_TASK_STORAGE_KEY = "novelwork.seedUpload.activeTask";

export interface PersistedActiveTask {
  taskId: string;
  projectId: string;
  projectName: string;
  taskStartedAt: string;
}

export function loadPersistedActiveTask(): PersistedActiveTask | null {
  if (typeof window === "undefined" || !window.localStorage) return null;
  try {
    const raw = window.localStorage.getItem(ACTIVE_TASK_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedActiveTask;
    if (!parsed || !parsed.taskId) return null;
    return parsed;
  } catch {
    console.warn("[seedUpload] failed to parse persisted active task");
    return null;
  }
}

export function persistActiveTask(payload: PersistedActiveTask): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.setItem(ACTIVE_TASK_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    console.warn("[seedUpload] failed to persist active task");
  }
}

export function clearPersistedActiveTask(): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.removeItem(ACTIVE_TASK_STORAGE_KEY);
  } catch {
    console.warn("[seedUpload] failed to clear persisted active task");
  }
}

/* ---------- Re-export fileKey for consumers ---------- */

export { fileKey };
