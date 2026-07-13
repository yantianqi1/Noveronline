import { devActorUserId } from "./dev-access";
import { currentRequestSessionCookie } from "./request-session";

const DEFAULT_API_BASE_URL = "http://127.0.0.1:3888";

export type AssetDetail = {
  asset_id: string;
  project_id: string;
  asset_type: string;
  category?: string | null;
  lifecycle: string;
  title: string;
  summary?: string | null;
  payload?: unknown;
  tags: string[];
  source: { kind: string; ref: string };
  enabled: boolean;
  pinned: boolean;
  current_version: number;
  collections: CollectionRef[];
  private?: { content_text?: string | null };
  capabilities: { read_private: boolean; mutate: boolean; manage_collections: boolean };
  created_at: string;
  updated_at: string;
};

export type AssetVersion = {
  version_id: string;
  version_number: number;
  title?: string | null;
  summary?: string | null;
  source: { kind: string; ref: string };
  created_by?: string | null;
  created_at: string;
};

export type CollectionRef = { collection_id: string; title: string; lifecycle: string; position: number };
export type AssetCollection = {
  collection_id: string;
  project_id: string;
  title: string;
  summary?: string | null;
  lifecycle: string;
  metadata: unknown;
  items: Array<{ asset_id: string; title: string; asset_type: string; position: number; created_at: string }>;
  created_at: string;
  updated_at: string;
};

export type AssetCatalogFailure = { ok: false; code: string; message: string };
export type AssetCatalogResult<T> = ({ ok: true; value: T } | AssetCatalogFailure);

type RequestContext = { tenantId: string; projectId: string };

function apiBaseUrl() { return process.env.MIROFISH_API_BASE_URL ?? DEFAULT_API_BASE_URL; }
function catalogUrl(projectId: string, path: string) {
  return `${apiBaseUrl()}/v1/projects/${encodeURIComponent(projectId)}/asset-catalog${path}`;
}

async function authHeaders(tenantId: string, mutate: boolean): Promise<HeadersInit> {
  const headers: Record<string, string> = { Accept: "application/json", "X-Tenant-Id": tenantId };
  const cookie = currentRequestSessionCookie();
  if (cookie) {
    headers.Cookie = `mirofish_session=${encodeURIComponent(cookie)}`;
    if (mutate) {
      const response = await fetch(`${apiBaseUrl()}/v1/auth/csrf-token`, { headers: { Cookie: headers.Cookie }, cache: "no-store" });
      const body = await response.json().catch(() => ({})) as { csrf_token?: string };
      if (!response.ok || !body.csrf_token) throw new Error("ASSET_CATALOG_CSRF_UNAVAILABLE");
      headers["X-CSRF-Token"] = body.csrf_token;
    }
  } else {
    const actor = devActorUserId();
    if (actor) headers["X-User-Id"] = actor;
  }
  if (mutate) headers["Content-Type"] = "application/json";
  return headers;
}

async function request<T>(context: RequestContext, path: string, init: RequestInit = {}): Promise<AssetCatalogResult<T>> {
  try {
    const response = await fetch(catalogUrl(context.projectId, path), {
      ...init,
      headers: { ...(await authHeaders(context.tenantId, init.method !== undefined && init.method !== "GET")), ...init.headers },
      cache: "no-store",
    });
    const body = await response.json().catch(() => ({})) as T & { error?: { code?: string; message?: string } };
    if (!response.ok) return { ok: false, code: body.error?.code ?? `HTTP_${response.status}`, message: body.error?.message ?? "Asset catalog request failed" };
    return { ok: true, value: body };
  } catch (error) {
    return { ok: false, code: "ASSET_CATALOG_UNAVAILABLE", message: error instanceof Error ? error.message : "Asset catalog is unavailable" };
  }
}

export function getAssetDetail(context: RequestContext & { assetId: string }) {
  return request<AssetDetail>(context, `/assets/${encodeURIComponent(context.assetId)}`);
}
export async function getAssetVersions(context: RequestContext & { assetId: string }) {
  const result = await request<{ versions: AssetVersion[] }>(context, `/assets/${encodeURIComponent(context.assetId)}/versions`);
  return result.ok ? { ok: true as const, value: result.value.versions } : result;
}
export async function getAssetCollections(context: RequestContext) {
  const result = await request<{ collections: AssetCollection[] }>(context, "/collections");
  return result.ok ? { ok: true as const, value: result.value.collections } : result;
}
export function updateAssetDetail(context: RequestContext & { assetId: string }, input: Record<string, unknown>) {
  return request<AssetDetail>(context, `/assets/${encodeURIComponent(context.assetId)}`, { method: "PATCH", body: JSON.stringify(input) });
}
export function restoreAssetVersion(context: RequestContext & { assetId: string }, input: { expected_version: number; version_number: number }) {
  return request<AssetDetail>(context, `/assets/${encodeURIComponent(context.assetId)}/restore`, { method: "POST", body: JSON.stringify(input) });
}
export function createAssetCollection(context: RequestContext, input: Record<string, unknown>) {
  return request<AssetCollection>(context, "/collections", { method: "POST", body: JSON.stringify(input) });
}
export function deleteAssetCollection(context: RequestContext, collectionId: string) {
  return request<never>(context, `/collections/${encodeURIComponent(collectionId)}`, { method: "DELETE" });
}
export function setAssetMembership(context: RequestContext & { assetId: string }, collectionId: string, position?: number) {
  return request<AssetCollection>(context, `/collections/${encodeURIComponent(collectionId)}/items/${encodeURIComponent(context.assetId)}`, { method: "PUT", body: JSON.stringify(position === undefined ? {} : { position }) });
}
export function removeAssetMembership(context: RequestContext & { assetId: string }, collectionId: string) {
  return request<AssetCollection>(context, `/collections/${encodeURIComponent(collectionId)}/items/${encodeURIComponent(context.assetId)}`, { method: "DELETE" });
}
export function reorderAssetCollection(context: RequestContext, collectionId: string, assetIds: string[]) {
  return request<AssetCollection>(context, `/collections/${encodeURIComponent(collectionId)}/order`, { method: "PUT", body: JSON.stringify({ asset_ids: assetIds }) });
}
