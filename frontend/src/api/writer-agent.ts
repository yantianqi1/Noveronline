/**
 * Writer Agent API client — writing workbench, scenes, chapters, manuscripts,
 * presets, outline versioning, and world data updates.
 */

import { del, get, post, put } from "@/api/http";
import type { ApiResponse } from "@/api/http";
import { postSSE } from "@/api/sse";
import type { SSEHandlers } from "@/api/sse";

/* ---------- Core writing (SSE) ---------- */

export interface WriterRunV1 {
  run_id: string;
  tenant_id: string;
  project_id: string;
  status: string;
  mode: string;
  chapter_id?: string | null;
  scene_id?: string | null;
  instruction: string;
  module_key: string;
}

interface WriterRunV1Response {
  success?: boolean;
  data?: WriterRunV1;
  error?: {
    code?: string;
    message?: string;
    details?: Record<string, unknown>;
  };
}

export async function createWriterRunV1(
  projectId: string,
  payload: unknown,
): Promise<ApiResponse<WriterRunV1>> {
  const response = await fetch(`/api/v1/projects/${projectId}/writer-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload ?? {}),
  });
  const data = (await response.json().catch(() => ({}))) as WriterRunV1Response;
  if (!response.ok || data.success === false) {
    const message = data.error?.message || `writer run failed: ${response.status}`;
    const error = new Error(message) as Error & { code?: string; details?: Record<string, unknown> };
    error.code = data.error?.code;
    error.details = data.error?.details;
    throw error;
  }
  return data as ApiResponse<WriterRunV1>;
}

export async function streamWriterRunEventsV1(
  runId: string,
  handlers: SSEHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`/api/v1/writer-runs/${runId}/events`, {
    method: "GET",
    headers: { Accept: "text/event-stream" },
    signal,
  });
  if (!response.ok || !response.body) {
    throw new Error(`writer run stream failed: ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() || "";
    for (const part of parts) {
      const line = part.split("\n").find((item) => item.startsWith("data: "));
      if (!line) continue;
      const event = normalizeWriterRunEvent(JSON.parse(line.slice(6)));
      if (event.type === "done") {
        handlers.onDone?.(event);
      } else if (event.type === "error") {
        handlers.onError?.(event);
      } else {
        handlers.onEvent?.(event);
      }
    }
  }
}

export function adoptWriterDraftV1(draftId: string): Promise<ApiResponse<{ block_id: string }>> {
  return post(`/api/v1/drafts/${draftId}/adoptions`, {});
}

export function normalizeWriterRunEvent(event: Record<string, unknown>): { type: string; [key: string]: unknown } {
  const payload = (event.payload || {}) as Record<string, unknown>;
  switch (event.type) {
    case "writer.run.started":
      return { type: "orchestrator_status", phase: "writing", message: "写作运行已启动" };
    case "writer.token":
      return { type: "writer_token", token: payload.token || "" };
    case "writer.tool.started":
      return { type: "tool_call", name: payload.tool_name, display: payload.tool_name };
    case "writer.tool.completed":
      return {
        type: "tool_result",
        name: payload.tool_name,
        status: payload.is_error ? "error" : "done",
        full_result: JSON.stringify(payload.result ?? {}, null, 2),
      };
    case "writer.draft.saved":
      return { type: "draft_saved", draft_id: payload.draft_id };
    case "writer.run.failed":
      return { type: "error", message: payload.message || "生成失败", code: payload.code };
    case "writer.run.completed":
      return { type: "done", draft_id: payload.draft_id };
    default:
      return { type: String(event.type || "unknown"), ...payload };
  }
}

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
