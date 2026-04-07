import { get, post, put, del } from "./http.js";

export function listAssets({
  scope = "all",
  projectId = "",
  assetType = "",
  category,
  enabledOnly = false,
  limit = 200,
  offset = 0,
} = {}) {
  const params = new URLSearchParams();
  params.set("scope", scope);
  if (projectId) params.set("project_id", projectId);
  if (assetType) params.set("asset_type", assetType);
  if (category !== undefined && category !== null) params.set("category", category);
  if (enabledOnly) params.set("enabled_only", "true");
  params.set("limit", String(limit));
  params.set("offset", String(offset));
  return get(`/api/assets?${params.toString()}`);
}

export function searchAssets(payload) {
  return post(`/api/assets/search`, payload);
}

export function getAsset(assetId, { projectId } = {}) {
  const qs = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return get(`/api/assets/${assetId}${qs}`);
}

export function createAsset(payload) {
  return post(`/api/assets`, payload);
}

export function updateAsset(assetId, payload) {
  return put(`/api/assets/${assetId}`, payload);
}

export function deleteAsset(assetId, { scope = "global", projectId = "" } = {}) {
  const params = new URLSearchParams({ scope });
  if (projectId) params.set("project_id", projectId);
  return del(`/api/assets/${assetId}?${params.toString()}`);
}

export function batchToggleAssets(payload) {
  return post(`/api/assets/batch-toggle`, payload);
}

export function batchCategorizeAssets(payload) {
  return post(`/api/assets/batch-categorize`, payload);
}

export function startStyleExtraction(payload) {
  return post(`/api/assets/style-extract`, payload);
}

export function getStyleExtractionStatus(taskId) {
  return get(`/api/assets/style-extract/${taskId}`);
}

// ---- 入库 Agent ----
export function startAssetIngestion(payload) {
  return post(`/api/assets/ingest`, payload);
}

export function getAssetIngestionStatus(taskId) {
  return get(`/api/assets/ingest/${taskId}`);
}

// ---- 统一聚合视图（跨 silo） ----
export function listUnifiedAssets({
  projectId = "",
  sources = [],
  entityTypes = [],
  scope = "",
  q = "",
  page = 1,
  pageSize = 50,
} = {}) {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  if (sources.length) params.set("source", sources.join(","));
  if (entityTypes.length) params.set("entity_type", entityTypes.join(","));
  if (scope) params.set("scope", scope);
  if (q) params.set("q", q);
  params.set("page", String(page));
  params.set("page_size", String(pageSize));
  return get(`/api/unified-assets?${params.toString()}`);
}

export function getUnifiedFacets(projectId = "") {
  const qs = projectId ? `?project_id=${encodeURIComponent(projectId)}` : "";
  return get(`/api/unified-assets/facets${qs}`);
}

export function searchGlobalAssets({ q, projectId = "", sources = [], entityTypes = [], limit = 50 } = {}) {
  const params = new URLSearchParams({ q });
  if (projectId) params.set("project_id", projectId);
  if (sources.length) params.set("source", sources.join(","));
  if (entityTypes.length) params.set("entity_type", entityTypes.join(","));
  params.set("limit", String(limit));
  return get(`/api/unified-assets/search?${params.toString()}`);
}

export function reindexUnifiedAssets(projectId) {
  return post(`/api/unified-assets/reindex`, { project_id: projectId });
}
