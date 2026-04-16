/**
 * Archive Library API client — archive browsing, memory management, adoption/rejection.
 */

import { get, post } from "@/api/http";
import type { ApiResponse } from "@/api/http";

/* ---------- Path helpers ---------- */

export interface ArchiveLibraryListFilters {
  q?: string;
  projectId?: string;
  entityType?: string;
  importanceTier?: string;
  limit?: number;
  offset?: number;
}

export function buildArchiveLibraryListPath({
  q = "",
  projectId = "",
  entityType = "",
  importanceTier = "",
  limit,
  offset,
}: ArchiveLibraryListFilters = {}): string {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (projectId) params.set("project_id", projectId);
  if (entityType) params.set("entity_type", entityType);
  if (importanceTier) params.set("importance_tier", importanceTier);
  if (limit !== undefined) params.set("limit", String(limit));
  if (offset !== undefined) params.set("offset", String(offset));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/api/archive/library${suffix}`;
}

export function buildArchiveLibraryDetailPath(archiveId: string): string {
  return `/api/archive/library/${archiveId}`;
}

export interface ArchiveMemoryFilters {
  includeCandidates?: boolean;
  include_candidates?: boolean;
  layer?: string;
  status?: string;
}

export function buildArchiveMemoryPath(
  archiveId: string,
  filters: ArchiveMemoryFilters = {},
): string {
  const params = new URLSearchParams();
  const resolvedIncludeCandidates =
    filters.includeCandidates ?? filters.include_candidates;
  if (resolvedIncludeCandidates !== undefined) {
    params.set("include_candidates", String(Boolean(resolvedIncludeCandidates)));
  }
  if (filters.layer) {
    params.set("layer", filters.layer);
  }
  if (filters.status) {
    params.set("status", filters.status);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/api/archive/library/${archiveId}/memory${suffix}`;
}

export interface ArchiveMemoryTimelineFilters {
  memoryId?: string;
  memory_id?: string;
  normalizedSubject?: string;
  normalized_subject?: string;
}

export function buildArchiveMemoryTimelinePath(
  archiveId: string,
  filters: ArchiveMemoryTimelineFilters = {},
): string {
  const params = new URLSearchParams();
  const resolvedMemoryId = filters.memoryId || filters.memory_id;
  const resolvedSubject = filters.normalizedSubject || filters.normalized_subject;
  if (resolvedMemoryId) params.set("memory_id", resolvedMemoryId);
  if (resolvedSubject) params.set("normalized_subject", resolvedSubject);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/api/archive/library/${archiveId}/memory/timeline${suffix}`;
}

/* ---------- Library CRUD ---------- */

export function listArchiveLibrary(
  filters: ArchiveLibraryListFilters = {},
): Promise<ApiResponse> {
  return get(buildArchiveLibraryListPath(filters));
}

export function getArchiveLibraryDetail(archiveId: string): Promise<ApiResponse> {
  return get(buildArchiveLibraryDetailPath(archiveId));
}

/* ---------- Memory ---------- */

export function listArchiveMemory(
  archiveId: string,
  filters: ArchiveMemoryFilters = {},
): Promise<ApiResponse> {
  return get(buildArchiveMemoryPath(archiveId, filters));
}

export function getArchiveMemoryTimeline(
  archiveId: string,
  filters: ArchiveMemoryTimelineFilters = {},
): Promise<ApiResponse> {
  return get(buildArchiveMemoryTimelinePath(archiveId, filters));
}

/* ---------- Memory actions ---------- */

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

/* ---------- Reindex ---------- */

export function reindexArchiveLibrary(): Promise<ApiResponse> {
  return post("/api/archive/library/reindex", {});
}
