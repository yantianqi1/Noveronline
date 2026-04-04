import { get, post, put, del } from "./http.js";
import { postSSE } from "./sse.js";

// Core writing
export function runWriterAgent(payload, handlers, signal) {
  return postSSE("/api/writer-agent/run", payload, handlers, signal);
}

// Scene CRUD
export function getScenes(chapterId, projectId) {
  return get(`/api/writer-agent/scenes/${chapterId}?project_id=${projectId}`);
}

export function getSceneDetail(sceneId, projectId) {
  return get(`/api/writer-agent/scenes/detail/${sceneId}?project_id=${projectId}`);
}

export function updateScene(sceneId, payload) {
  return put(`/api/writer-agent/scenes/${sceneId}`, payload);
}

export function deleteScene(sceneId, projectId) {
  return del(`/api/writer-agent/scenes/${sceneId}?project_id=${projectId}`);
}

export function reorderScenes(chapterId, payload) {
  return post(`/api/writer-agent/scenes/${chapterId}/reorder`, payload);
}

export function compileChapter(chapterId, payload) {
  return post(`/api/writer-agent/scenes/${chapterId}/compile`, payload);
}

// Preset CRUD
export function getPresets(projectId) {
  return get(`/api/writer-agent/presets?project_id=${projectId || ""}`);
}

export function createPreset(payload) {
  return post("/api/writer-agent/presets", payload);
}

export function updatePreset(presetId, payload) {
  return put(`/api/writer-agent/presets/${presetId}`, payload);
}

export function deletePreset(presetId, projectId) {
  return del(`/api/writer-agent/presets/${presetId}?project_id=${projectId || ""}`);
}

// Chapter CRUD
export function getChapters(projectId) {
  return get(`/api/writer-agent/chapters/${projectId}`);
}

export function createChapter(projectId, payload) {
  return post(`/api/writer-agent/chapters/${projectId}`, payload);
}

export function updateChapter(chapterId, payload) {
  return put(`/api/writer-agent/chapters/detail/${chapterId}`, payload);
}

export function deleteChapter(chapterId, projectId) {
  return del(`/api/writer-agent/chapters/detail/${chapterId}?project_id=${projectId}`);
}

// Manuscript
export function commitToManuscript(projectId, payload) {
  return post(`/api/writer-agent/manuscript/${projectId}/commit`, payload);
}

export function getManuscript(projectId, includeContent = true) {
  return get(`/api/writer-agent/manuscript/${projectId}?include_content=${includeContent}`);
}

export function updateManuscriptBlock(blockId, payload) {
  return put(`/api/writer-agent/manuscript/block/${blockId}`, payload);
}

export function deleteManuscriptBlock(blockId, projectId) {
  return del(`/api/writer-agent/manuscript/block/${blockId}?project_id=${projectId}`);
}

export function reorderManuscriptBlocks(projectId, blockIds) {
  return put(`/api/writer-agent/manuscript/${projectId}/reorder`, { block_ids: blockIds });
}

export function tagManuscriptBlocks(projectId, payload) {
  return put(`/api/writer-agent/manuscript/${projectId}/tag`, payload);
}

export async function exportManuscript(projectId, format = "txt") {
  const response = await fetch(`/api/writer-agent/manuscript/${projectId}/export?format=${format}`);
  if (!response.ok) throw new Error(`导出失败: ${response.status}`);
  return response.blob();
}

export function getContinuationContext(projectId, { tokenBudget = 8000, lastBlockId = "" } = {}) {
  let url = `/api/writer-agent/manuscript/${projectId}/continuation-context?token_budget=${tokenBudget}`;
  if (lastBlockId) url += `&last_block_id=${encodeURIComponent(lastBlockId)}`;
  return get(url);
}

// Migration
export function migrateProject(projectId) {
  return post(`/api/writer-agent/migrate/${projectId}`);
}
