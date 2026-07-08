import { redirect } from "next/navigation";
import { AssetLibraryShell } from "../../../../../../components/asset-library-shell";
import {
  adoptAsset,
  adoptArchiveMemory,
  bulkActionAssets,
  createAsset,
  deleteAsset,
  getAssetFacets,
  getArchiveAssetMemories,
  getArchiveAssetMemoryEvents,
  getProjectAssets,
  searchAssets,
  rejectArchiveMemory,
  startAssetIngestion,
  startAssetReindex,
  startStyleExtraction,
  updateAsset,
} from "../../../../../../lib/api";
import { webApiContext } from "../../../../../../lib/server-auth";

export const dynamic = "force-dynamic";

export default async function AssetsPage({
  params,
  searchParams,
}: {
  params: Promise<{ tenantSlug: string; projectId: string }>;
  searchParams?: Promise<{
    assetCode?: string;
    assetMessage?: string;
    assetStatus?: string;
    bulkCode?: string;
    bulkMessage?: string;
    bulkStatus?: string;
    ingestionCode?: string;
    ingestionMessage?: string;
    ingestionStatus?: string;
    memoryAssetId?: string;
    memoryCode?: string;
    memoryMessage?: string;
    memoryStatus?: string;
    query?: string;
    reindexCode?: string;
    reindexMessage?: string;
    reindexStatus?: string;
    styleCode?: string;
    styleMessage?: string;
    styleStatus?: string;
  }>;
}) {
  const { tenantSlug, projectId } = await params;
  const query = searchParams ? await searchParams : {};
  const searchQuery = query.query?.trim() || "";
  const memoryAssetId = query.memoryAssetId?.trim() || "";
  const apiContext = await webApiContext({ tenantId: tenantSlug, projectId });

  const [assets, facets, searchResults, archiveMemories, archiveMemoryEvents] = await Promise.all([
    getProjectAssets(apiContext),
    getAssetFacets(apiContext),
    searchQuery ? searchAssets({ ...apiContext, query: searchQuery }) : Promise.resolve(null),
    memoryAssetId ? getArchiveAssetMemories({ ...apiContext, assetId: memoryAssetId }) : Promise.resolve(null),
    memoryAssetId ? getArchiveAssetMemoryEvents({ ...apiContext, assetId: memoryAssetId }) : Promise.resolve(null),
  ]);

  async function searchAction(formData: FormData) {
    "use server";

    const nextQuery = new URLSearchParams();
    const nextSearch = stringFromFormData(formData, "query");
    if (nextSearch) {
      nextQuery.set("query", nextSearch);
    }
    redirect(assetRoute(tenantSlug, projectId, nextQuery));
  }

  async function memoryAssetAction(formData: FormData) {
    "use server";

    const nextQuery = baseAssetQuery(searchQuery);
    const assetId = stringFromFormData(formData, "memoryAssetId");
    if (assetId) {
      nextQuery.set("memoryAssetId", assetId);
    }
    redirect(assetRoute(tenantSlug, projectId, nextQuery));
  }

  async function createAssetAction(formData: FormData) {
    "use server";

    const payload = jsonObjectFromFormData(formData, "payload");
    if (!payload.ok) {
      redirect(assetStatusRoute(tenantSlug, projectId, searchQuery, "error", payload.code, payload.message));
    }
    const result = await createAsset({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      scope: "project",
      assetType: stringFromFormData(formData, "assetType"),
      category: stringFromFormData(formData, "category"),
      lifecycle: stringFromFormData(formData, "lifecycle") || "material",
      title: stringFromFormData(formData, "title"),
      summary: stringFromFormData(formData, "summary"),
      contentText: stringFromFormData(formData, "contentText"),
      payload: payload.value,
      tags: tagsFromFormData(formData, "tags"),
      sourceKind: stringFromFormData(formData, "sourceKind") || "manual",
      sourceRef: stringFromFormData(formData, "sourceRef") || `manual:${Date.now()}`,
      enabled: stringFromFormData(formData, "enabled") === "on",
      pinned: stringFromFormData(formData, "pinned") === "on",
    });
    redirect(
      assetStatusRoute(
        tenantSlug,
        projectId,
        searchQuery,
        result.ok ? "success" : "error",
        result.ok ? "ASSET_CREATED" : result.code,
        result.ok ? `${result.title} created` : result.message,
      ),
    );
  }

  async function updateAssetAction(formData: FormData) {
    "use server";

    const assetId = stringFromFormData(formData, "assetId");
    const payload = optionalJsonObjectFromFormData(formData, "payload");
    if (!payload.ok) {
      redirect(assetStatusRoute(tenantSlug, projectId, searchQuery, "error", payload.code, payload.message));
    }
    const result = await updateAsset({
      ...(await webApiContext({ tenantId: tenantSlug })),
      assetId,
      title: optionalStringFromFormData(formData, "title"),
      summary: optionalStringFromFormData(formData, "summary"),
      lifecycle: optionalStringFromFormData(formData, "lifecycle"),
      contentText: optionalStringFromFormData(formData, "contentText"),
      payload: payload.value,
      tags: optionalTagsFromFormData(formData, "tags"),
      enabled: stringFromFormData(formData, "enabled") === "on",
      pinned: stringFromFormData(formData, "pinned") === "on",
    });
    redirect(
      assetStatusRoute(
        tenantSlug,
        projectId,
        searchQuery,
        result.ok ? "success" : "error",
        result.ok ? "ASSET_UPDATED" : result.code,
        result.ok ? `${result.title || result.asset_id} updated` : result.message,
      ),
    );
  }

  async function deleteAssetAction(formData: FormData) {
    "use server";

    const assetId = stringFromFormData(formData, "assetId");
    const result = await deleteAsset({
      ...(await webApiContext({ tenantId: tenantSlug })),
      assetId,
    });
    redirect(
      assetStatusRoute(
        tenantSlug,
        projectId,
        searchQuery,
        result.ok ? "success" : "error",
        result.ok ? "ASSET_DELETED" : result.code,
        result.ok ? `${result.asset_id} deleted` : result.message,
      ),
    );
  }

  async function adoptAssetAction(formData: FormData) {
    "use server";

    const targetLifecycle = targetLifecycleFromFormData(formData, "targetLifecycle");
    const result = await adoptAsset({
      ...(await webApiContext({ tenantId: tenantSlug })),
      assetId: stringFromFormData(formData, "assetId"),
      targetLifecycle,
    });
    redirect(
      assetStatusRoute(
        tenantSlug,
        projectId,
        searchQuery,
        result.ok ? "success" : "error",
        result.ok ? "ASSET_ADOPTED" : result.code,
        result.ok ? `${result.title || result.asset_id} adopted as ${result.lifecycle}` : result.message,
      ),
    );
  }

  async function adoptArchiveMemoryAction(formData: FormData) {
    "use server";

    const memoryId = stringFromFormData(formData, "memoryId");
    const result = await adoptArchiveMemory({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      memoryId,
    });
    redirect(
      memoryStatusRoute(
        tenantSlug,
        projectId,
        searchQuery,
        memoryAssetId,
        result.ok ? "success" : "error",
        result.ok ? "ARCHIVE_MEMORY_ADOPTED" : result.code,
        result.ok ? `${result.memory_id} adopted` : result.message,
      ),
    );
  }

  async function rejectArchiveMemoryAction(formData: FormData) {
    "use server";

    const memoryId = stringFromFormData(formData, "memoryId");
    const result = await rejectArchiveMemory({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      memoryId,
    });
    redirect(
      memoryStatusRoute(
        tenantSlug,
        projectId,
        searchQuery,
        memoryAssetId,
        result.ok ? "success" : "error",
        result.ok ? "ARCHIVE_MEMORY_REJECTED" : result.code,
        result.ok ? `${result.memory_id} rejected` : result.message,
      ),
    );
  }

  async function bulkAssetAction(formData: FormData) {
    "use server";

    const action = stringFromFormData(formData, "bulkAction") || "disable";
    const assetIds = assetIdsFromFormData(formData, "assetIds");
    const result = await bulkActionAssets({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      action,
      assetIds,
      targetLifecycle: optionalStringFromFormData(formData, "targetLifecycle"),
      category: optionalStringFromFormData(formData, "category"),
      enabled: optionalBooleanFromFormData(formData, "enabled"),
      pinned: optionalBooleanFromFormData(formData, "pinned"),
    });
    redirect(
      bulkStatusRoute(
        tenantSlug,
        projectId,
        searchQuery,
        result.ok ? "success" : "error",
        result.ok ? "ASSET_BULK_ACTION_ACCEPTED" : result.code,
        result.ok ? `${result.action} ${result.status}: ${result.updated_count}/${result.matched_count}` : result.message,
      ),
    );
  }

  async function ingestAssetAction(formData: FormData) {
    "use server";

    const result = await startAssetIngestion({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      materialText: stringFromFormData(formData, "materialText"),
      hintType: stringFromFormData(formData, "hintType") || "note",
      scope: stringFromFormData(formData, "scope") || "project",
      options: {},
    });
    redirect(
      ingestionStatusRoute(
        tenantSlug,
        projectId,
        searchQuery,
        result.ok ? "success" : "error",
        result.ok ? "ASSET_INGESTION_QUEUED" : result.code,
        result.ok ? `${result.run_id} queued` : result.message,
      ),
    );
  }

  async function reindexAssetsAction(formData: FormData) {
    "use server";

    const result = await startAssetReindex({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      scope: stringFromFormData(formData, "scope") || "project",
      mode: stringFromFormData(formData, "mode") || "keyword",
      options: {},
    });
    redirect(
      reindexStatusRoute(
        tenantSlug,
        projectId,
        searchQuery,
        result.ok ? "success" : "error",
        result.ok ? "ASSET_REINDEX_QUEUED" : result.code,
        result.ok ? `${result.run_id} queued` : result.message,
      ),
    );
  }

  async function extractStyleAction(formData: FormData) {
    "use server";

    const result = await startStyleExtraction({
      ...(await webApiContext({ tenantId: tenantSlug, projectId })),
      projectId,
      materialText: stringFromFormData(formData, "materialText"),
      sourceAssetId: optionalStringFromFormData(formData, "sourceAssetId"),
      scope: stringFromFormData(formData, "scope") || "project",
      options: {},
    });
    redirect(
      styleStatusRoute(
        tenantSlug,
        projectId,
        searchQuery,
        result.ok ? "success" : "error",
        result.ok ? "STYLE_EXTRACTION_QUEUED" : result.code,
        result.ok ? `${result.run_id} queued` : result.message,
      ),
    );
  }

  return (
    <AssetLibraryShell
      tenantSlug={tenantSlug}
      projectId={projectId}
      searchQuery={searchQuery}
      assetStatus={query.assetStatus?.trim() || ""}
      assetCode={query.assetCode?.trim() || ""}
      assetMessage={query.assetMessage?.trim() || ""}
      bulkStatus={query.bulkStatus?.trim() || ""}
      bulkCode={query.bulkCode?.trim() || ""}
      bulkMessage={query.bulkMessage?.trim() || ""}
      ingestionStatus={query.ingestionStatus?.trim() || ""}
      ingestionCode={query.ingestionCode?.trim() || ""}
      ingestionMessage={query.ingestionMessage?.trim() || ""}
      memoryStatus={query.memoryStatus?.trim() || ""}
      memoryCode={query.memoryCode?.trim() || ""}
      memoryMessage={query.memoryMessage?.trim() || ""}
      reindexStatus={query.reindexStatus?.trim() || ""}
      reindexCode={query.reindexCode?.trim() || ""}
      reindexMessage={query.reindexMessage?.trim() || ""}
      styleStatus={query.styleStatus?.trim() || ""}
      styleCode={query.styleCode?.trim() || ""}
      styleMessage={query.styleMessage?.trim() || ""}
      assets={assets}
      facets={facets}
      searchResults={searchResults}
      memoryAssetId={memoryAssetId}
      archiveMemories={archiveMemories}
      archiveMemoryEvents={archiveMemoryEvents}
      searchAction={searchAction}
      memoryAssetAction={memoryAssetAction}
      createAssetAction={createAssetAction}
      updateAssetAction={updateAssetAction}
      deleteAssetAction={deleteAssetAction}
      adoptAssetAction={adoptAssetAction}
      adoptArchiveMemoryAction={adoptArchiveMemoryAction}
      rejectArchiveMemoryAction={rejectArchiveMemoryAction}
      bulkAssetAction={bulkAssetAction}
      ingestAssetAction={ingestAssetAction}
      reindexAssetsAction={reindexAssetsAction}
      extractStyleAction={extractStyleAction}
    />
  );
}

function assetStatusRoute(
  tenantSlug: string,
  projectId: string,
  searchQuery: string,
  status: string,
  code: string,
  message: string,
) {
  const params = baseAssetQuery(searchQuery);
  params.set("assetStatus", status);
  params.set("assetCode", code);
  params.set("assetMessage", message);
  return assetRoute(tenantSlug, projectId, params);
}

function ingestionStatusRoute(
  tenantSlug: string,
  projectId: string,
  searchQuery: string,
  status: string,
  code: string,
  message: string,
) {
  const params = baseAssetQuery(searchQuery);
  params.set("ingestionStatus", status);
  params.set("ingestionCode", code);
  params.set("ingestionMessage", message);
  return assetRoute(tenantSlug, projectId, params);
}

function memoryStatusRoute(
  tenantSlug: string,
  projectId: string,
  searchQuery: string,
  memoryAssetId: string,
  status: string,
  code: string,
  message: string,
) {
  const params = baseAssetQuery(searchQuery);
  if (memoryAssetId) {
    params.set("memoryAssetId", memoryAssetId);
  }
  params.set("memoryStatus", status);
  params.set("memoryCode", code);
  params.set("memoryMessage", message);
  return assetRoute(tenantSlug, projectId, params);
}

function bulkStatusRoute(
  tenantSlug: string,
  projectId: string,
  searchQuery: string,
  status: string,
  code: string,
  message: string,
) {
  const params = baseAssetQuery(searchQuery);
  params.set("bulkStatus", status);
  params.set("bulkCode", code);
  params.set("bulkMessage", message);
  return assetRoute(tenantSlug, projectId, params);
}

function reindexStatusRoute(
  tenantSlug: string,
  projectId: string,
  searchQuery: string,
  status: string,
  code: string,
  message: string,
) {
  const params = baseAssetQuery(searchQuery);
  params.set("reindexStatus", status);
  params.set("reindexCode", code);
  params.set("reindexMessage", message);
  return assetRoute(tenantSlug, projectId, params);
}

function styleStatusRoute(
  tenantSlug: string,
  projectId: string,
  searchQuery: string,
  status: string,
  code: string,
  message: string,
) {
  const params = baseAssetQuery(searchQuery);
  params.set("styleStatus", status);
  params.set("styleCode", code);
  params.set("styleMessage", message);
  return assetRoute(tenantSlug, projectId, params);
}

function assetRoute(tenantSlug: string, projectId: string, params: URLSearchParams) {
  const query = params.toString();
  return `/${tenantSlug}/projects/${projectId}/assets${query ? `?${query}` : ""}`;
}

function baseAssetQuery(searchQuery: string) {
  const params = new URLSearchParams();
  if (searchQuery) {
    params.set("query", searchQuery);
  }
  return params;
}

function stringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function optionalStringFromFormData(formData: FormData, key: string) {
  const value = stringFromFormData(formData, key);
  return value || undefined;
}

function tagsFromFormData(formData: FormData, key: string) {
  return stringFromFormData(formData, key)
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

function optionalTagsFromFormData(formData: FormData, key: string) {
  const tags = tagsFromFormData(formData, key);
  return tags.length > 0 ? tags : undefined;
}

function assetIdsFromFormData(formData: FormData, key: string) {
  return stringFromFormData(formData, key)
    .split(/[\n,]/)
    .map((assetId) => assetId.trim())
    .filter(Boolean);
}

function optionalBooleanFromFormData(formData: FormData, key: string) {
  const value = stringFromFormData(formData, key);
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  return undefined;
}

function jsonObjectFromFormData(formData: FormData, key: string) {
  const raw = stringFromFormData(formData, key) || "{}";
  return parseJsonObject(raw);
}

function optionalJsonObjectFromFormData(formData: FormData, key: string) {
  const raw = stringFromFormData(formData, key);
  return raw ? parseJsonObject(raw) : { ok: true as const, value: undefined };
}

function parseJsonObject(raw: string) {
  try {
    const value = JSON.parse(raw) as unknown;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return { ok: true as const, value: value as Record<string, unknown> };
    }
    return { ok: false as const, code: "ASSET_PAYLOAD_INVALID", message: "payload must be a JSON object" };
  } catch {
    return { ok: false as const, code: "ASSET_PAYLOAD_INVALID", message: "payload must be valid JSON" };
  }
}

function targetLifecycleFromFormData(formData: FormData, key: string): "canon" | "material" {
  return stringFromFormData(formData, key) === "material" ? "material" : "canon";
}
