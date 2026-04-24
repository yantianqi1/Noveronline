/**
 * Writer Agent API client — writing workbench, scenes, chapters, manuscripts,
 * presets, outline versioning, and world data updates.
 */

import { del, get, post, put } from "@/api/http";
import type { ApiResponse } from "@/api/http";
import { postSSE } from "@/api/sse";
import type { SSEHandlers } from "@/api/sse";

/* ---------- Core writing (SSE) ---------- */

export function runWriterAgent(
  payload: unknown,
  handlers: SSEHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return postSSE("/api/writer-agent/run", payload, handlers, signal);
}

export function updateWorldData(
  payload: unknown,
  handlers: SSEHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return postSSE("/api/writer-agent/world-update", payload, handlers, signal);
}

/** Apply user-selected reviewer suggestions — SSE stream of the rewrite. */
export function applyReviewer(
  payload: unknown,
  handlers: SSEHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return postSSE("/api/writer-agent/apply-reviewer", payload, handlers, signal);
}

/* ---------- One-click buttons (W-3 §4.4) ---------- */

export function oneClickCompleteOutline(
  payload: { project_id: string; chapter_id: string; chapter_order?: number },
  handlers: SSEHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return postSSE(
    "/api/writer-agent/one-click/complete-outline",
    payload,
    handlers,
    signal,
  );
}

export function oneClickAlignWords(
  payload: {
    project_id: string;
    chapter_id: string;
    chapter_order?: number;
    target_word_count: number;
    tolerance_pct?: number;
  },
  handlers: SSEHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return postSSE(
    "/api/writer-agent/one-click/align-words",
    payload,
    handlers,
    signal,
  );
}

export function oneClickScanLexicon(
  payload: {
    project_id: string;
    chapter_id: string;
    chapter_order?: number;
    lexicon_asset_ids?: string[];
  },
  handlers: SSEHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return postSSE(
    "/api/writer-agent/one-click/scan-lexicon",
    payload,
    handlers,
    signal,
  );
}

export function oneClickFillRelationships(
  payload: { project_id: string; chapter_id: string; chapter_order?: number },
  handlers: SSEHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return postSSE(
    "/api/writer-agent/one-click/fill-relationships",
    payload,
    handlers,
    signal,
  );
}

export function oneClickContinueChapter(
  payload: {
    project_id: string;
    chapter_id: string;
    chapter_order?: number;
    last_block_id?: string;
    target_word_count?: number;
    preset_id?: string;
  },
  handlers: SSEHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return postSSE(
    "/api/writer-agent/one-click/continue-chapter",
    payload,
    handlers,
    signal,
  );
}

/* ---------- Scene CRUD ---------- */

export function getScenes(chapterId: string, projectId: string): Promise<ApiResponse> {
  return get(`/api/writer-agent/scenes/${chapterId}?project_id=${projectId}`);
}

export function createScene(chapterId: string, payload: unknown): Promise<ApiResponse> {
  return post(`/api/writer-agent/scenes/${chapterId}`, payload);
}

export function getSceneDetail(sceneId: string, projectId: string): Promise<ApiResponse> {
  return get(`/api/writer-agent/scenes/detail/${sceneId}?project_id=${projectId}`);
}

export function updateScene(sceneId: string, payload: unknown): Promise<ApiResponse> {
  return put(`/api/writer-agent/scenes/${sceneId}`, payload);
}

export function deleteScene(sceneId: string, projectId: string): Promise<ApiResponse> {
  return del(`/api/writer-agent/scenes/${sceneId}?project_id=${projectId}`);
}

export function reorderScenes(chapterId: string, payload: unknown): Promise<ApiResponse> {
  return post(`/api/writer-agent/scenes/${chapterId}/reorder`, payload);
}

export function compileChapter(chapterId: string, payload: unknown): Promise<ApiResponse> {
  return post(`/api/writer-agent/scenes/${chapterId}/compile`, payload);
}

/* ---------- Preset CRUD ---------- */

export function getPresets(projectId?: string): Promise<ApiResponse> {
  return get(`/api/writer-agent/presets?project_id=${projectId || ""}`);
}

export function createPreset(payload: unknown): Promise<ApiResponse> {
  return post("/api/writer-agent/presets", payload);
}

export function updatePreset(presetId: string, payload: unknown): Promise<ApiResponse> {
  return put(`/api/writer-agent/presets/${presetId}`, payload);
}

export function deletePreset(presetId: string, projectId?: string): Promise<ApiResponse> {
  return del(`/api/writer-agent/presets/${presetId}?project_id=${projectId || ""}`);
}

/* ---------- Chapter CRUD ---------- */

export function getChapters(projectId: string): Promise<ApiResponse> {
  return get(`/api/writer-agent/chapters/${projectId}`);
}

export function createChapter(projectId: string, payload: unknown): Promise<ApiResponse> {
  return post(`/api/writer-agent/chapters/${projectId}`, payload);
}

export function updateChapter(chapterId: string, payload: unknown): Promise<ApiResponse> {
  return put(`/api/writer-agent/chapters/detail/${chapterId}`, payload);
}

export function deleteChapter(chapterId: string, projectId: string): Promise<ApiResponse> {
  return del(`/api/writer-agent/chapters/detail/${chapterId}?project_id=${projectId}`);
}

/* ---------- Manuscript ---------- */

export function commitToManuscript(
  projectId: string,
  payload: unknown,
): Promise<ApiResponse> {
  return post(`/api/writer-agent/manuscript/${projectId}/commit`, payload);
}

export function getManuscript(
  projectId: string,
  includeContent = true,
): Promise<ApiResponse> {
  return get(
    `/api/writer-agent/manuscript/${projectId}?include_content=${includeContent}`,
  );
}

export function updateManuscriptBlock(
  blockId: string,
  payload: unknown,
): Promise<ApiResponse> {
  return put(`/api/writer-agent/manuscript/block/${blockId}`, payload);
}

export function deleteManuscriptBlock(
  blockId: string,
  projectId: string,
): Promise<ApiResponse> {
  return del(`/api/writer-agent/manuscript/block/${blockId}?project_id=${projectId}`);
}

export function reorderManuscriptBlocks(
  projectId: string,
  blockIds: string[],
): Promise<ApiResponse> {
  return put(`/api/writer-agent/manuscript/${projectId}/reorder`, {
    block_ids: blockIds,
  });
}

export function tagManuscriptBlocks(
  projectId: string,
  payload: unknown,
): Promise<ApiResponse> {
  return put(`/api/writer-agent/manuscript/${projectId}/tag`, payload);
}

export function moveManuscriptBlock(
  blockId: string,
  payload: unknown,
): Promise<ApiResponse> {
  return put(`/api/writer-agent/manuscript/block/${blockId}/move`, payload);
}

/**
 * Export manuscript as a downloadable Blob.
 * Uses raw fetch() — does NOT go through the http wrapper.
 */
export async function exportManuscript(
  projectId: string,
  format = "txt",
): Promise<Blob> {
  const response = await fetch(
    `/api/writer-agent/manuscript/${projectId}/export?format=${format}`,
  );
  if (!response.ok) throw new Error(`导出失败: ${response.status}`);
  return response.blob();
}

/* ---------- Continuation context ---------- */

export interface ContinuationContextOptions {
  tokenBudget?: number;
  lastBlockId?: string;
}

export function getContinuationContext(
  projectId: string,
  { tokenBudget = 8000, lastBlockId = "" }: ContinuationContextOptions = {},
): Promise<ApiResponse> {
  let url = `/api/writer-agent/manuscript/${projectId}/continuation-context?token_budget=${tokenBudget}`;
  if (lastBlockId) url += `&last_block_id=${encodeURIComponent(lastBlockId)}`;
  return get(url);
}

/* ---------- Outline versions ---------- */

export function getOutlineVersions(
  chapterId: string,
  projectId: string,
): Promise<ApiResponse> {
  return get(
    `/api/writer-agent/chapters/detail/${chapterId}/outline-versions?project_id=${projectId}`,
  );
}

export function getOutlineVersion(
  chapterId: string,
  versionId: string,
  projectId: string,
): Promise<ApiResponse> {
  return get(
    `/api/writer-agent/chapters/detail/${chapterId}/outline-versions/${versionId}?project_id=${projectId}`,
  );
}

export function restoreOutlineVersion(
  chapterId: string,
  versionId: string,
  projectId: string,
): Promise<ApiResponse> {
  return post(
    `/api/writer-agent/chapters/detail/${chapterId}/outline-versions/${versionId}/restore`,
    { project_id: projectId },
  );
}

/* ---------- Migration ---------- */

export function migrateProject(projectId: string): Promise<ApiResponse> {
  return post(`/api/writer-agent/migrate/${projectId}`);
}

/* ---------- Book-run (multi-chapter agent task) ---------- */

export interface BookPlanInput {
  project_id: string;
  title: string;
  chapter_count: number;
  per_chapter_word_target: number;
  word_tolerance_pct?: number;
  overall_direction?: string;
  global_brief?: string;
  start_chapter_order?: number;
  forbidden_lexicon_asset_ids?: string[];
  style_asset_ids?: string[];
  preset_id?: string | null;
}

export function listBookPlans(projectId: string): Promise<ApiResponse> {
  return get(`/api/writer-agent/book-plans?project_id=${encodeURIComponent(projectId)}`);
}

export function createBookPlan(payload: BookPlanInput): Promise<ApiResponse> {
  return post("/api/writer-agent/book-plans", payload);
}

export function getBookPlan(planId: string): Promise<ApiResponse> {
  return get(`/api/writer-agent/book-plans/${planId}`);
}

export function updateBookPlan(planId: string, payload: Partial<BookPlanInput>): Promise<ApiResponse> {
  return put(`/api/writer-agent/book-plans/${planId}`, payload);
}

export function deleteBookPlan(planId: string): Promise<ApiResponse> {
  return del(`/api/writer-agent/book-plans/${planId}`);
}

export function getBookPlanStatus(planId: string): Promise<ApiResponse> {
  return get(`/api/writer-agent/book-plans/${planId}/status`);
}

export function getActiveBookPlan(projectId: string): Promise<ApiResponse> {
  return get(`/api/writer-agent/book-plans/active/by-project?project_id=${encodeURIComponent(projectId)}`);
}

export function runBookRun(
  planId: string,
  handlers: SSEHandlers,
  signal?: AbortSignal,
): Promise<void> {
  return postSSE("/api/writer-agent/book-run", { plan_id: planId }, handlers, signal);
}

export function abortBookRun(planId: string): Promise<ApiResponse> {
  return post("/api/writer-agent/book-run/abort", { plan_id: planId });
}

/* ---------- Forbidden lexicon ---------- */

export interface ForbiddenLexiconEntry {
  pattern: string;
  match_type?: "literal" | "regex" | "phrase";
  category?: "word" | "sentence" | "stylistic";
  severity?: "block" | "warn";
  note?: string;
  whitelist_contexts?: string[];
}

export function listForbiddenLexicons(
  projectId: string,
  includeEntries = false,
): Promise<ApiResponse> {
  return get(
    `/api/writer-agent/forbidden-lexicons?project_id=${encodeURIComponent(projectId)}&include_entries=${includeEntries}`,
  );
}

export function upsertForbiddenLexicon(payload: {
  project_id: string;
  asset_id?: string | null;
  title?: string;
  entries: ForbiddenLexiconEntry[] | string[];
}): Promise<ApiResponse> {
  return post("/api/writer-agent/forbidden-lexicons", payload);
}

export function deleteForbiddenLexicon(
  assetId: string,
  projectId: string,
): Promise<ApiResponse> {
  return del(
    `/api/writer-agent/forbidden-lexicons/${assetId}?project_id=${encodeURIComponent(projectId)}`,
  );
}
