/**
 * Assets & Unified Assets API client — asset CRUD, style extraction,
 * ingestion agent, unified cross-silo view, global FTS search, and
 * archive library browsing + memory management.
 *
 * The archive.* helpers (previously in api/archive.ts) still hit
 * /api/archive/* URLs — Phase 5 of the asset-library refactor will
 * merge archive_library into the assets table and retire those URLs.
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
  categories?: string[];
  lifecycles?: string[];
  scope?: string;
  q?: string;
  page?: number;
  pageSize?: number;
}

export function listUnifiedAssets({
  projectId = "",
  sources = [],
  entityTypes = [],
  categories = [],
  lifecycles = [],
  scope = "",
  q = "",
  page = 1,
  pageSize = 50,
}: ListUnifiedAssetsParams = {}): Promise<ApiResponse> {
  const params = new URLSearchParams();
  if (projectId) params.set("project_id", projectId);
  if (sources.length) params.set("source", sources.join(","));
  if (entityTypes.length) params.set("entity_type", entityTypes.join(","));
  if (categories.length) params.set("category", categories.join(","));
  if (lifecycles.length) params.set("lifecycle", lifecycles.join(","));
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

/* ---------- Archive library (legacy /api/archive/*, to be merged into assets in P5) ---------- */

export interface ArchiveLibraryListFilters {
  q?: string;
  projectId?: string;
  entityType?: string;
  agentKind?: string;
  importanceTier?: string;
  limit?: number;
  offset?: number;
}

export function listArchiveLibrary({
  q = "",
  projectId = "",
  entityType = "",
  agentKind = "",
  importanceTier = "",
  limit,
  offset,
}: ArchiveLibraryListFilters = {}): Promise<ApiResponse> {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (projectId) params.set("project_id", projectId);
  if (entityType) params.set("entity_type", entityType);
  if (agentKind) params.set("agent_kind", agentKind);
  if (importanceTier) params.set("importance_tier", importanceTier);
  if (limit !== undefined) params.set("limit", String(limit));
  if (offset !== undefined) params.set("offset", String(offset));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return get(`/api/archive/library${suffix}`);
}

export function getArchiveLibraryDetail(archiveId: string): Promise<ApiResponse> {
  return get(`/api/archive/library/${archiveId}`);
}

/* ---------- Archive memory ---------- */

export interface ArchiveMemoryFilters {
  includeCandidates?: boolean;
  include_candidates?: boolean;
  layer?: string;
  status?: string;
}

export function listArchiveMemory(
  archiveId: string,
  filters: ArchiveMemoryFilters = {},
): Promise<ApiResponse> {
  const params = new URLSearchParams();
  const resolvedIncludeCandidates =
    filters.includeCandidates ?? filters.include_candidates;
  if (resolvedIncludeCandidates !== undefined) {
    params.set("include_candidates", String(Boolean(resolvedIncludeCandidates)));
  }
  if (filters.layer) params.set("layer", filters.layer);
  if (filters.status) params.set("status", filters.status);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return get(`/api/archive/library/${archiveId}/memory${suffix}`);
}

export interface ArchiveMemoryTimelineFilters {
  memoryId?: string;
  memory_id?: string;
  normalizedSubject?: string;
  normalized_subject?: string;
}

export function getArchiveMemoryTimeline(
  archiveId: string,
  filters: ArchiveMemoryTimelineFilters = {},
): Promise<ApiResponse> {
  const params = new URLSearchParams();
  const resolvedMemoryId = filters.memoryId || filters.memory_id;
  const resolvedSubject = filters.normalizedSubject || filters.normalized_subject;
  if (resolvedMemoryId) params.set("memory_id", resolvedMemoryId);
  if (resolvedSubject) params.set("normalized_subject", resolvedSubject);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return get(`/api/archive/library/${archiveId}/memory/timeline${suffix}`);
}

export function adoptArchiveMemory(
  archiveId: string,
  memoryId: string,
): Promise<ApiResponse> {
  return post(`/api/archive/library/${archiveId}/memory/${memoryId}/adopt`, {});
}

export function rejectArchiveMemory(
  archiveId: string,
  memoryId: string,
): Promise<ApiResponse> {
  return post(`/api/archive/library/${archiveId}/memory/${memoryId}/reject`, {});
}
