import type {
  AssetRecord,
  AssetVersion,
  CatalogAsset,
  Collection,
  Facets,
  ListResponse,
  SearchCapabilities,
  SearchFilters,
  SearchRecord,
} from "@/lib/api/asset-types";
import { readSelectionFor } from "@/lib/api/writer-client";

/**
 * Browser-side client for the Asset Library (资产库) workbench. All calls go
 * to same-origin BFF routes; the browser supplies the tenant via X-Tenant-Id
 * (from the shelf selection) and a CSRF token + X-Request-Id for mutations.
 * Catalog updates additionally send the `expected_version` optimistic lock.
 */

export class AssetError extends Error {
  constructor(
    message: string,
    readonly code?: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "AssetError";
  }
}

/** The active project/tenant selection, but only when it matches this project. */
export function readAssetSelection(projectId: string) {
  return readSelectionFor(projectId);
}

async function readError(response: Response): Promise<AssetError> {
  let code: string | undefined;
  let message = `请求失败（${response.status}）`;
  try {
    const payload = (await response.json()) as { error?: { code?: string; message?: string } };
    code = payload?.error?.code;
    if (payload?.error?.message) message = payload.error.message;
  } catch {
    // non-JSON body — keep the generic message
  }
  return new AssetError(message, code, response.status);
}

/** Idempotency key for mutations (X-Request-Id). */
function requestId(): string {
  return `assets-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

async function getJson<T>(path: string, tenantId: string): Promise<T> {
  const response = await fetch(path, {
    headers: { Accept: "application/json", "X-Tenant-Id": tenantId },
    cache: "no-store",
  });
  if (!response.ok) throw await readError(response);
  return (await response.json()) as T;
}

async function sendJson<T>(
  method: "POST" | "PATCH" | "PUT" | "DELETE",
  path: string,
  tenantId: string,
  csrfToken: string,
  body?: unknown,
): Promise<T> {
  const response = await fetch(path, {
    method,
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-Tenant-Id": tenantId,
      "X-CSRF-Token": csrfToken,
      "X-Request-Id": requestId(),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw await readError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

// ── Browse: list + facets + search capabilities ────────────────────────────

// The list endpoint paginates at 100/page. The library and overview both need
// the COMPLETE set (client-side filtering/facets and the new-asset diff), so we
// walk offset pages until has_more is false and assemble the full array here —
// the same accumulate-until-done idiom as the writer run event walk.
const ASSET_PAGE_SIZE = 100;

export async function fetchAssets(projectId: string, tenantId: string): Promise<AssetRecord[]> {
  const all: AssetRecord[] = [];
  // Dedupe by asset_id: the list orders by pinned/updated_at, which can shift
  // while we page if an asset is updated mid-walk, so an overlapping row may
  // reappear on a later offset. Seen rows are dropped rather than duplicated;
  // the next reload re-walks from offset 0 and self-heals any skip.
  const seen = new Set<string>();
  let offset = 0;
  for (;;) {
    const data = await getJson<ListResponse<AssetRecord>>(
      `/api/projects/${projectId}/assets?limit=${ASSET_PAGE_SIZE}&offset=${offset}`,
      tenantId,
    );
    const page = data.items ?? [];
    for (const asset of page) {
      if (!seen.has(asset.asset_id)) {
        seen.add(asset.asset_id);
        all.push(asset);
      }
    }
    if (!data.has_more || page.length === 0) break; // short/last page ends the walk
    offset = data.next_offset ?? offset + page.length;
  }
  return all;
}

export function fetchAssetFacets(projectId: string, tenantId: string): Promise<Facets> {
  return getJson<Facets>(`/api/projects/${projectId}/assets/facets`, tenantId);
}

export function fetchSearchCapabilities(projectId: string, tenantId: string): Promise<SearchCapabilities> {
  return getJson<SearchCapabilities>(`/api/projects/${projectId}/assets/search-capabilities`, tenantId);
}

/** Full-text (keyword/vector/hybrid) search across the project's entities. */
export async function searchAssets(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  query: string,
  filters?: SearchFilters,
): Promise<SearchRecord[]> {
  const data = await sendJson<ListResponse<SearchRecord>>(
    "POST",
    `/api/projects/${projectId}/assets/search`,
    tenantId,
    csrfToken,
    { query, mode: "hybrid", filters: filters ?? {} },
  );
  return data.items ?? [];
}

// ── Catalog: detail, versions, restore ─────────────────────────────────────

export function fetchCatalogAsset(
  projectId: string,
  tenantId: string,
  assetId: string,
): Promise<CatalogAsset> {
  return getJson<CatalogAsset>(`/api/projects/${projectId}/asset-catalog/assets/${assetId}`, tenantId);
}

export async function fetchAssetVersions(
  projectId: string,
  tenantId: string,
  assetId: string,
  includePrivate: boolean,
): Promise<AssetVersion[]> {
  const query = includePrivate ? "?include_private=true" : "";
  const data = await getJson<{ versions: AssetVersion[] }>(
    `/api/projects/${projectId}/asset-catalog/assets/${assetId}/versions${query}`,
    tenantId,
  );
  return [...(data.versions ?? [])].sort((a, b) => b.version_number - a.version_number);
}

/**
 * Edit an asset's metadata/content. Requires the current `current_version` as
 * the optimistic-lock `expected_version`; stale writes surface as a conflict.
 */
export function patchAsset(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  assetId: string,
  expectedVersion: number,
  patch: Partial<{
    title: string;
    summary: string;
    category: string;
    tags: string[];
    content_text: string;
    enabled: boolean;
    pinned: boolean;
    always_on: boolean;
    /** Chapter order after which recall may see this; a negative value clears the gate. */
    reveal_after_chapter_order: number;
  }>,
): Promise<CatalogAsset> {
  return sendJson<CatalogAsset>(
    "PATCH",
    `/api/projects/${projectId}/asset-catalog/assets/${assetId}`,
    tenantId,
    csrfToken,
    { expected_version: expectedVersion, ...patch },
  );
}

/** Restore an asset to a prior version (explicit, optimistic-locked). */
export function restoreAssetVersion(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  assetId: string,
  expectedVersion: number,
  versionNumber: number,
): Promise<CatalogAsset> {
  return sendJson<CatalogAsset>(
    "POST",
    `/api/projects/${projectId}/asset-catalog/assets/${assetId}/restore`,
    tenantId,
    csrfToken,
    { expected_version: expectedVersion, version_number: versionNumber },
  );
}

/**
 * Adopt a candidate into canon (候选 → 正典). Goes through the top-level
 * /v1/assets/{id}/adoptions route; the author confirms before this is called.
 */
export function adoptAsset(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  assetId: string,
  targetLifecycle: string,
): Promise<AssetRecord> {
  return sendJson<AssetRecord>(
    "POST",
    `/api/projects/${projectId}/assets/${assetId}/adoptions`,
    tenantId,
    csrfToken,
    { target_lifecycle: targetLifecycle },
  );
}

// ── Catalog: collections ───────────────────────────────────────────────────

export async function fetchCollections(projectId: string, tenantId: string): Promise<Collection[]> {
  const data = await getJson<{ collections: Collection[] }>(
    `/api/projects/${projectId}/asset-catalog/collections`,
    tenantId,
  );
  return data.collections ?? [];
}

export function createCollection(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  input: { title: string; summary?: string },
): Promise<Collection> {
  return sendJson<Collection>(
    "POST",
    `/api/projects/${projectId}/asset-catalog/collections`,
    tenantId,
    csrfToken,
    input,
  );
}

export function deleteCollection(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  collectionId: string,
): Promise<void> {
  return sendJson<void>(
    "DELETE",
    `/api/projects/${projectId}/asset-catalog/collections/${collectionId}`,
    tenantId,
    csrfToken,
  );
}

export function addToCollection(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  collectionId: string,
  assetId: string,
): Promise<Collection> {
  return sendJson<Collection>(
    "PUT",
    `/api/projects/${projectId}/asset-catalog/collections/${collectionId}/items/${assetId}`,
    tenantId,
    csrfToken,
    {},
  );
}

export function removeFromCollection(
  projectId: string,
  tenantId: string,
  csrfToken: string,
  collectionId: string,
  assetId: string,
): Promise<Collection> {
  return sendJson<Collection>(
    "DELETE",
    `/api/projects/${projectId}/asset-catalog/collections/${collectionId}/items/${assetId}`,
    tenantId,
    csrfToken,
  );
}
