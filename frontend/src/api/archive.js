import { get, post } from "./http.js";

export function buildArchiveLibraryListPath({
  q = "",
  projectId = "",
  entityType = "",
  importanceTier = "",
  limit,
  offset,
} = {}) {
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

export function buildArchiveLibraryDetailPath(archiveId) {
  return `/api/archive/library/${archiveId}`;
}

export function buildArchiveMemoryPath(archiveId, {
  includeCandidates,
  include_candidates: rawIncludeCandidates,
  layer,
  status,
} = {}) {
  const params = new URLSearchParams();
  const resolvedIncludeCandidates = includeCandidates ?? rawIncludeCandidates;
  if (resolvedIncludeCandidates !== undefined) {
    params.set("include_candidates", String(Boolean(resolvedIncludeCandidates)));
  }
  if (layer) {
    params.set("layer", layer);
  }
  if (status) {
    params.set("status", status);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/api/archive/library/${archiveId}/memory${suffix}`;
}

export function buildArchiveMemoryTimelinePath(archiveId, {
  memoryId,
  memory_id: rawMemoryId,
  normalizedSubject,
  normalized_subject: rawNormalizedSubject,
} = {}) {
  const params = new URLSearchParams();
  const resolvedMemoryId = memoryId || rawMemoryId;
  const resolvedSubject = normalizedSubject || rawNormalizedSubject;
  if (resolvedMemoryId) params.set("memory_id", resolvedMemoryId);
  if (resolvedSubject) params.set("normalized_subject", resolvedSubject);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/api/archive/library/${archiveId}/memory/timeline${suffix}`;
}

export function listArchiveLibrary(filters = {}) {
  return get(buildArchiveLibraryListPath(filters));
}

export function getArchiveLibraryDetail(archiveId) {
  return get(buildArchiveLibraryDetailPath(archiveId));
}

export function listArchiveMemory(archiveId, filters = {}) {
  return get(buildArchiveMemoryPath(archiveId, filters));
}

export function getArchiveMemoryTimeline(archiveId, filters = {}) {
  return get(buildArchiveMemoryTimelinePath(archiveId, filters));
}

export function adoptArchiveMemory(archiveId, memoryId) {
  return post(`/api/archive/library/${archiveId}/memory/${memoryId}/adopt`, {});
}

export function rejectArchiveMemory(archiveId, memoryId) {
  return post(`/api/archive/library/${archiveId}/memory/${memoryId}/reject`, {});
}

export function reindexArchiveLibrary() {
  return post("/api/archive/library/reindex", {});
}
