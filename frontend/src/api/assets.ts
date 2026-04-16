/**
 * Assets & Unified Assets API client — asset CRUD, style extraction,
 * ingestion agent, unified cross-silo view, and global FTS search.
 */

import { del, get, post, put } from "@/api/http";
import type { ApiResponse } from "@/api/http";

/* ---------- Asset list ---------- */

export interface ListAssetsParams {
  scope?: string;
  projectId?: string;
  assetType?: string;
  category?: string | null;
  enabledOnly?: boolean;
  limit?: number;
  offset?: number;
}

export function listAssets({
  scope = "all",
  projectId = "",
  assetType = "",
  category,
  enabledOnly = false,
  limit = 200,
  offset = 0,
}: ListAssetsParams = {}): Promise<ApiResponse> {
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

/* ---------- Asset search ---------- */

export function searchAssets(payload: unknown): Promise<ApiResponse> {
  return post("/api/assets/search", payload);
}

/* ---------- Asset CRUD ---------- */

export function getAsset(
  assetId: string,
  { projectId }: { projectId?: string } = {},
): Promise<ApiResponse> {
  const qs = projectId
    ? `?project_id=${encodeURIComponent(projectId)}`
    : "";
  return get(`/api/assets/${assetId}${qs}`);
}

export function createAsset(payload: unknown): Promise<ApiResponse> {
  return post("/api/assets", payload);
}

export function updateAsset(assetId: string, payload: unknown): Promise<ApiResponse> {
  return put(`/api/assets/${assetId}`, payload);
}

export function deleteAsset(
  assetId: string,
  { scope = "global", projectId = "" }: { scope?: string; projectId?: string } = {},
): Promise<ApiResponse> {
  const params = new URLSearchParams({ scope });
  if (projectId) params.set("project_id", projectId);
  return del(`/api/assets/${assetId}?${params.toString()}`);
}

/* ---------- Batch operations ---------- */

export function batchToggleAssets(payload: unknown): Promise<ApiResponse> {
  return post("/api/assets/batch-toggle", payload);
}

export function batchCategorizeAssets(payload: unknown): Promise<ApiResponse> {
  return post("/api/assets/batch-categorize", payload);
}

/* ---------- Style extraction ---------- */

export function startStyleExtraction(payload: unknown): Promise<ApiResponse> {
  return post("/api/assets/style-extract", payload);
}

export function getStyleExtractionStatus(taskId: string): Promise<ApiResponse> {
  return get(`/api/assets/style-extract/${taskId}`);
}

/* ---------- Ingestion agent ---------- */

export function startAssetIngestion(payload: unknown): Promise<ApiResponse> {
  return post("/api/assets/ingest", payload);
}

export function getAssetIngestionStatus(taskId: string): Promise<ApiResponse> {
  return get(`/api/assets/ingest/${taskId}`);
}

/* ---------- Unified asset view (cross-silo) ---------- */

export interface ListUnifiedAssetsParams {
  projectId?: string;
  sources?: string[];
  entityTypes?: string[];
  scope?: string;
  q?: string;
  page?: number;
  pageSize?: number;
}

export function listUnifiedAssets({
  projectId = "",
  sources = [],
  entityTypes = [],
  scope = "",
  q = "",
  page = 1,
  pageSize = 50,
}: ListUnifiedAssetsParams = {}): Promise<ApiResponse> {
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

export function getUnifiedFacets(projectId = ""): Promise<ApiResponse> {
  const qs = projectId
    ? `?project_id=${encodeURIComponent(projectId)}`
    : "";
  return get(`/api/unified-assets/facets${qs}`);
}

export interface SearchGlobalAssetsParams {
  q: string;
  projectId?: string;
  sources?: string[];
  entityTypes?: string[];
  limit?: number;
}

export function searchGlobalAssets({
  q,
  projectId = "",
  sources = [],
  entityTypes = [],
  limit = 50,
}: SearchGlobalAssetsParams): Promise<ApiResponse> {
  const params = new URLSearchParams({ q });
  if (projectId) params.set("project_id", projectId);
  if (sources.length) params.set("source", sources.join(","));
  if (entityTypes.length) params.set("entity_type", entityTypes.join(","));
  params.set("limit", String(limit));
  return get(`/api/unified-assets/search?${params.toString()}`);
}

export function reindexUnifiedAssets(projectId: string): Promise<ApiResponse> {
  return post("/api/unified-assets/reindex", { project_id: projectId });
}
