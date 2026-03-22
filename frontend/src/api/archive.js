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

export function listArchiveLibrary(filters = {}) {
  return get(buildArchiveLibraryListPath(filters));
}

export function getArchiveLibraryDetail(archiveId) {
  return get(buildArchiveLibraryDetailPath(archiveId));
}

export function reindexArchiveLibrary() {
  return post("/api/archive/library/reindex", {});
}
