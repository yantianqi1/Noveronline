import { redirect } from "next/navigation";
import { AssetLibraryShell } from "../../../../../../components/asset-library-shell";
import {
  adoptAsset,
  adoptArchiveMemory,
  bulkActionAssets,
  createAsset,
  deleteAsset,
  getAssetFacets,
  getAssetSearchCapabilities,
  getArchiveAssetMemories,
  getArchiveAssetMemoryEvents,
  getProjectAssets,
  getWorkflowRunSummary,
  searchAssets,
  rejectArchiveMemory,
  startAssetIngestion,
  startAssetReindex,
  startStyleExtraction,
  updateAsset,
} from "../../../../../../lib/api";
import { type Locale, tx } from "../../../../../../lib/locale";
import { currentRequestLocale } from "../../../../../../lib/request-locale";
import { webApiContext, webReadApiContext } from "../../../../../../lib/server-auth";

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
    assetType?: string;
    bulkCode?: string;
    bulkMessage?: string;
    bulkStatus?: string;
    category?: string;
    ingestionCode?: string;
    ingestionMessage?: string;
    ingestionStatus?: string;
    lifecycle?: string;
    memoryAssetId?: string;
    memoryCode?: string;
    memoryMessage?: string;
    memoryStatus?: string;
    mode?: string;
    pinned?: string;
    query?: string;
    reindexCode?: string;
    reindexMessage?: string;
    reindexRunId?: string;
    reindexStatus?: string;
    source?: string;
    styleCode?: string;
    styleMessage?: string;
    styleStatus?: string;
    tag?: string;
  }>;
}) {
  const { tenantSlug, projectId } = await params;
  const locale = await currentRequestLocale();
  const query = searchParams ? await searchParams : {};
  const searchQuery = query.query?.trim() || "";
  const searchMode = normalizeSearchMode(query.mode);
  const searchFilters = {
    asset_types: optionalFilterValues(query.assetType),
    categories: optionalFilterValues(query.category),
    lifecycles: optionalFilterValues(query.lifecycle),
    sources: optionalFilterValues(query.source),
    tags: optionalFilterValues(query.tag),
    pinned: optionalBooleanQuery(query.pinned),
  };
  const searchState: AssetSearchState = { query: searchQuery, mode: searchMode, ...searchFilters };
  const memoryAssetId = query.memoryAssetId?.trim() || "";
  const reindexRunId = query.reindexRunId?.trim() || "";
  const apiContext = webReadApiContext({ tenantId: tenantSlug, projectId });

  const [assets, facets, searchCapabilities, searchResults, archiveMemories, archiveMemoryEvents, reindexRun] = await Promise.all([
    getProjectAssets(apiContext),
    getAssetFacets(apiContext),
    getAssetSearchCapabilities(apiContext),
    searchQuery
      ? searchAssets({ ...apiContext, query: searchQuery, mode: searchMode, filters: compactSearchFilters(searchFilters) })
      : Promise.resolve(null),
    memoryAssetId ? getArchiveAssetMemories({ ...apiContext, assetId: memoryAssetId }) : Promise.resolve(null),
    memoryAssetId ? getArchiveAssetMemoryEvents({ ...apiContext, assetId: memoryAssetId }) : Promise.resolve(null),
    reindexRunId ? getWorkflowRunSummary({ ...apiContext, runId: reindexRunId }) : Promise.resolve(null),
  ]);

  async function searchAction(formData: FormData) {
    "use server";

    const nextQuery = new URLSearchParams();
    const nextSearch = stringFromFormData(formData, "query");
    if (nextSearch) {
      nextQuery.set("query", nextSearch);
    }
    nextQuery.set("mode", normalizeSearchMode(stringFromFormData(formData, "mode")));
    setOptionalQuery(nextQuery, "assetType", stringFromFormData(formData, "assetType"));
    setOptionalQuery(nextQuery, "category", stringFromFormData(formData, "category"));
    setOptionalQuery(nextQuery, "lifecycle", stringFromFormData(formData, "lifecycle"));
    setOptionalQuery(nextQuery, "source", stringFromFormData(formData, "source"));
    setOptionalQuery(nextQuery, "tag", stringFromFormData(formData, "tag"));
    setOptionalQuery(nextQuery, "pinned", stringFromFormData(formData, "pinned"));
    redirect(assetRoute(tenantSlug, projectId, nextQuery));
  }

  async function memoryAssetAction(formData: FormData) {
    "use server";

    const nextQuery = baseAssetQuery(searchState);
    const assetId = stringFromFormData(formData, "memoryAssetId");
    if (assetId) {
      nextQuery.set("memoryAssetId", assetId);
    }
    redirect(assetRoute(tenantSlug, projectId, nextQuery));
  }

  async function createAssetAction(formData: FormData) {
    "use server";

    const payload = jsonObjectFromFormData(formData, "payload", locale);
    if (!payload.ok) {
      redirect(assetStatusRoute(tenantSlug, projectId, searchState, "error", payload.code, payload.message));
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
        searchState,
        result.ok ? "success" : "error",
        result.ok ? "ASSET_CREATED" : result.code,
        result.ok ? tx(locale, `已创建「${result.title}」`, `“${result.title}” created`) : result.message,
      ),
    );
  }

  async function updateAssetAction(formData: FormData) {
    "use server";

    const assetId = stringFromFormData(formData, "assetId");
    const payload = optionalJsonObjectFromFormData(formData, "payload", locale);
    if (!payload.ok) {
      redirect(assetStatusRoute(tenantSlug, projectId, searchState, "error", payload.code, payload.message));
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
        searchState,
        result.ok ? "success" : "error",
        result.ok ? "ASSET_UPDATED" : result.code,
        result.ok
          ? tx(locale, `已更新「${result.title || result.asset_id}」`, `“${result.title || result.asset_id}” updated`)
          : result.message,
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
        searchState,
        result.ok ? "success" : "error",
        result.ok ? "ASSET_DELETED" : result.code,
        result.ok ? tx(locale, "资产已删除", "Asset deleted") : result.message,
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
        searchState,
        result.ok ? "success" : "error",
        result.ok ? "ASSET_ADOPTED" : result.code,
        result.ok
          ? tx(locale, `已采纳「${result.title || result.asset_id}」`, `“${result.title || result.asset_id}” adopted`)
          : result.message,
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
        searchState,
        memoryAssetId,
        result.ok ? "success" : "error",
        result.ok ? "ARCHIVE_MEMORY_ADOPTED" : result.code,
        result.ok ? tx(locale, "记忆已采纳", "Memory adopted") : result.message,
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
        searchState,
        memoryAssetId,
        result.ok ? "success" : "error",
        result.ok ? "ARCHIVE_MEMORY_REJECTED" : result.code,
        result.ok ? tx(locale, "记忆已拒绝", "Memory rejected") : result.message,
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
        searchState,
        result.ok ? "success" : "error",
        result.ok ? "ASSET_BULK_ACTION_ACCEPTED" : result.code,
        result.ok
          ? tx(
              locale,
              `已更新 ${result.updated_count}/${result.matched_count} 项资产`,
              `${result.updated_count}/${result.matched_count} assets updated`,
            )
          : result.message,
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
        searchState,
        result.ok ? "success" : "error",
        result.ok ? "ASSET_INGESTION_QUEUED" : result.code,
        result.ok ? tx(locale, "素材导入任务已加入队列", "Material ingestion queued") : result.message,
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
        searchState,
        result.ok ? "success" : "error",
        result.ok ? "ASSET_REINDEX_QUEUED" : result.code,
        result.ok ? tx(locale, "索引任务已加入队列", "Reindex queued") : result.message,
        result.ok ? result.run_id : "",
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
        searchState,
        result.ok ? "success" : "error",
        result.ok ? "STYLE_EXTRACTION_QUEUED" : result.code,
        result.ok ? tx(locale, "风格提取任务已加入队列", "Style extraction queued") : result.message,
      ),
    );
  }

  return (
    <AssetLibraryShell
      locale={locale}
      tenantSlug={tenantSlug}
      projectId={projectId}
      searchQuery={searchQuery}
      searchMode={searchMode}
      searchFilters={searchFilters}
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
      reindexRun={reindexRun}
      styleStatus={query.styleStatus?.trim() || ""}
      styleCode={query.styleCode?.trim() || ""}
      styleMessage={query.styleMessage?.trim() || ""}
      assets={assets}
      facets={facets}
      searchCapabilities={searchCapabilities}
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
  searchState: AssetSearchState,
  status: string,
  code: string,
  message: string,
) {
  const params = baseAssetQuery(searchState);
  params.set("assetStatus", status);
  params.set("assetCode", code);
  params.set("assetMessage", message);
  return assetRoute(tenantSlug, projectId, params);
}

function ingestionStatusRoute(
  tenantSlug: string,
  projectId: string,
  searchState: AssetSearchState,
  status: string,
  code: string,
  message: string,
) {
  const params = baseAssetQuery(searchState);
  params.set("ingestionStatus", status);
  params.set("ingestionCode", code);
  params.set("ingestionMessage", message);
  return assetRoute(tenantSlug, projectId, params);
}

function memoryStatusRoute(
  tenantSlug: string,
  projectId: string,
  searchState: AssetSearchState,
  memoryAssetId: string,
  status: string,
  code: string,
  message: string,
) {
  const params = baseAssetQuery(searchState);
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
  searchState: AssetSearchState,
  status: string,
  code: string,
  message: string,
) {
  const params = baseAssetQuery(searchState);
  params.set("bulkStatus", status);
  params.set("bulkCode", code);
  params.set("bulkMessage", message);
  return assetRoute(tenantSlug, projectId, params);
}

function reindexStatusRoute(
  tenantSlug: string,
  projectId: string,
  searchState: AssetSearchState,
  status: string,
  code: string,
  message: string,
  runId: string,
) {
  const params = baseAssetQuery(searchState);
  params.set("reindexStatus", status);
  params.set("reindexCode", code);
  params.set("reindexMessage", message);
  if (runId) {
    params.set("reindexRunId", runId);
  }
  return assetRoute(tenantSlug, projectId, params);
}

function styleStatusRoute(
  tenantSlug: string,
  projectId: string,
  searchState: AssetSearchState,
  status: string,
  code: string,
  message: string,
) {
  const params = baseAssetQuery(searchState);
  params.set("styleStatus", status);
  params.set("styleCode", code);
  params.set("styleMessage", message);
  return assetRoute(tenantSlug, projectId, params);
}

function assetRoute(tenantSlug: string, projectId: string, params: URLSearchParams) {
  const query = params.toString();
  return `/${tenantSlug}/projects/${projectId}/assets${query ? `?${query}` : ""}`;
}

type AssetSearchState = {
  query: string;
  mode: "keyword" | "vector" | "hybrid";
  asset_types: string[];
  categories: string[];
  lifecycles: string[];
  sources: string[];
  tags: string[];
  pinned?: boolean;
};

function baseAssetQuery(searchState: AssetSearchState) {
  const params = new URLSearchParams();
  if (searchState.query) {
    params.set("query", searchState.query);
  }
  params.set("mode", searchState.mode);
  setOptionalQuery(params, "assetType", searchState.asset_types[0] || "");
  setOptionalQuery(params, "category", searchState.categories[0] || "");
  setOptionalQuery(params, "lifecycle", searchState.lifecycles[0] || "");
  setOptionalQuery(params, "source", searchState.sources[0] || "");
  setOptionalQuery(params, "tag", searchState.tags[0] || "");
  if (searchState.pinned !== undefined) {
    params.set("pinned", String(searchState.pinned));
  }
  return params;
}

function setOptionalQuery(params: URLSearchParams, key: string, value: string) {
  if (value) {
    params.set(key, value);
  }
}

function optionalFilterValues(value: string | undefined) {
  const normalized = value?.trim();
  return normalized ? [normalized] : [];
}

function optionalBooleanQuery(value: string | undefined) {
  if (value === "true") {
    return true;
  }
  if (value === "false") {
    return false;
  }
  return undefined;
}

function compactSearchFilters(filters: Omit<AssetSearchState, "query" | "mode">) {
  const compact = Object.fromEntries(
    Object.entries(filters).filter(([, value]) => value !== undefined && (!Array.isArray(value) || value.length > 0)),
  );
  return Object.keys(compact).length > 0 ? compact : undefined;
}

function stringFromFormData(formData: FormData, key: string) {
  const value = formData.get(key);
  return typeof value === "string" ? value.trim() : "";
}

function normalizeSearchMode(value: string | undefined): "keyword" | "vector" | "hybrid" {
  switch (value?.trim().toLowerCase()) {
    case "vector":
      return "vector";
    case "hybrid":
      return "hybrid";
    default:
      return "keyword";
  }
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

function jsonObjectFromFormData(formData: FormData, key: string, locale: Locale) {
  const raw = stringFromFormData(formData, key) || "{}";
  return parseJsonObject(raw, locale);
}

function optionalJsonObjectFromFormData(formData: FormData, key: string, locale: Locale) {
  const raw = stringFromFormData(formData, key);
  return raw ? parseJsonObject(raw, locale) : { ok: true as const, value: undefined };
}

function parseJsonObject(raw: string, locale: Locale) {
  try {
    const value = JSON.parse(raw) as unknown;
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return { ok: true as const, value: value as Record<string, unknown> };
    }
    return {
      ok: false as const,
      code: "ASSET_PAYLOAD_INVALID",
      message: tx(locale, "请输入 JSON 对象", "Enter a JSON object"),
    };
  } catch {
    return {
      ok: false as const,
      code: "ASSET_PAYLOAD_INVALID",
      message: tx(locale, "JSON 格式无效", "Invalid JSON"),
    };
  }
}

function targetLifecycleFromFormData(formData: FormData, key: string): "canon" | "material" {
  return stringFromFormData(formData, key) === "material" ? "material" : "canon";
}
