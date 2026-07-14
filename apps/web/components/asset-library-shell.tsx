import { Boxes, ChevronRight, Filter, Search, SlidersHorizontal } from "lucide-react";

import { Bi, FailureText, StatusValue } from "./bilingual-text";
import type {
  ArchiveMemoryEventsSummary,
  ArchiveMemorySummary,
  AssetFacetsSummary,
  AssetListSummary,
  AssetSearchCapabilitiesSummary,
  AssetSearchSummary,
  WorkflowRunSummary,
} from "../lib/api";
import { type Locale, tx } from "../lib/locale";
import { AssetBrowseClient } from "./asset-browse-client";
import { AssetOperationWorkspace, type AssetOperationItem } from "./asset-operation-workspace";
import { CompactFilterBar } from "./compact-filter-bar";
import { InspectorPanel } from "./inspector-panel";
import { WorkspaceHeader } from "./workspace-header";

type AssetLibraryShellProps = {
  locale: Locale;
  tenantSlug: string;
  projectId: string;
  searchQuery: string;
  searchMode?: "keyword" | "vector" | "hybrid";
  searchFilters: {
    asset_types: string[];
    categories: string[];
    lifecycles: string[];
    sources: string[];
    tags: string[];
    pinned?: boolean;
  };
  assetStatus: string;
  assetCode: string;
  assetMessage: string;
  bulkStatus: string;
  bulkCode: string;
  bulkMessage: string;
  ingestionStatus: string;
  ingestionCode: string;
  ingestionMessage: string;
  memoryStatus: string;
  memoryCode: string;
  memoryMessage: string;
  reindexStatus: string;
  reindexCode: string;
  reindexMessage: string;
  reindexRun: WorkflowRunSummary | null;
  styleStatus: string;
  styleCode: string;
  styleMessage: string;
  assets: AssetListSummary;
  facets: AssetFacetsSummary;
  searchCapabilities: AssetSearchCapabilitiesSummary;
  searchResults: AssetSearchSummary | null;
  memoryAssetId: string;
  archiveMemories: ArchiveMemorySummary | null;
  archiveMemoryEvents: ArchiveMemoryEventsSummary | null;
  searchAction: (formData: FormData) => Promise<void>;
  memoryAssetAction: (formData: FormData) => Promise<void>;
  createAssetAction: (formData: FormData) => Promise<void>;
  updateAssetAction: (formData: FormData) => Promise<void>;
  deleteAssetAction: (formData: FormData) => Promise<void>;
  adoptAssetAction: (formData: FormData) => Promise<void>;
  adoptArchiveMemoryAction: (formData: FormData) => Promise<void>;
  rejectArchiveMemoryAction: (formData: FormData) => Promise<void>;
  bulkAssetAction: (formData: FormData) => Promise<void>;
  ingestAssetAction: (formData: FormData) => Promise<void>;
  reindexAssetsAction: (formData: FormData) => Promise<void>;
  extractStyleAction: (formData: FormData) => Promise<void>;
};

export function AssetLibraryShell({
  locale,
  tenantSlug,
  projectId,
  searchQuery,
  searchMode = "keyword",
  searchFilters,
  assetStatus,
  assetCode,
  assetMessage,
  bulkStatus,
  bulkCode,
  bulkMessage,
  ingestionStatus,
  ingestionCode,
  ingestionMessage,
  memoryStatus,
  memoryCode,
  memoryMessage,
  reindexStatus,
  reindexCode,
  reindexMessage,
  reindexRun,
  styleStatus,
  styleCode,
  styleMessage,
  assets,
  facets,
  searchCapabilities,
  searchResults,
  memoryAssetId,
  archiveMemories,
  archiveMemoryEvents,
  searchAction,
  memoryAssetAction,
  createAssetAction,
  updateAssetAction,
  deleteAssetAction,
  adoptAssetAction,
  adoptArchiveMemoryAction,
  rejectArchiveMemoryAction,
  bulkAssetAction,
  ingestAssetAction,
  reindexAssetsAction,
  extractStyleAction,
}: AssetLibraryShellProps) {
  const appliedFilters = appliedAssetFilters(locale, searchMode, searchFilters);
  const availableAssets = assets.ok ? assets.items : [];

  return (
    <div className="overview-root asset-library-root">
      <WorkspaceHeader
        className="asset-library-header"
        description={<Bi zh="浏览角色、设定与素材。" en="Browse characters, lore, and materials." />}
        icon={<Boxes size={22} strokeWidth={1.8} />}
        meta={(
          <>
            <span className="status-pill">{assets.ok ? assets.items.length : "—"} <Bi zh="项资产" en="assets" /></span>
            <span className="status-pill"><Bi zh="当前" en="Showing" /> {searchResults?.ok ? searchResults.items.length : assets.ok ? assets.items.length : 0}</span>
          </>
        )}
        title={<Bi zh="资产库" en="Asset Library" />}
      />

      <div className="workbench-grid asset-library-grid">
        <AssetFacetRail
          facets={facets}
          filters={searchFilters}
          locale={locale}
          projectId={projectId}
          searchMode={searchMode}
          searchQuery={searchQuery}
          tenantSlug={tenantSlug}
        />
        <main className="asset-library-main">
          <section
            className={`panel asset-overview-panel asset-search-panel ${assets.ok && (searchResults === null || searchResults.ok) ? "" : "error-box"}`}
            aria-labelledby="assets-heading"
          >
            <div className="asset-browse-heading">
              <div>
                <p className="eyebrow"><Bi zh="创作资料" en="Story materials" /></p>
                <h2 id="assets-heading"><Bi zh="浏览资产" en="Browse assets" /></h2>
              </div>
              <p className="form-hint asset-browse-hint">
                <Bi zh="搜索与筛选后，结果会列在下方。" en="Results appear below after search and filters." />
              </p>
            </div>
            <form action={searchAction} className="binding-form asset-search-form">
              <CompactFilterBar
                appliedFilters={appliedFilters.map((filter) => ({
                  href: assetSearchHref(tenantSlug, projectId, searchQuery, {
                    filters: searchFilters,
                    mode: searchMode,
                    omit: filter.parameter,
                  }),
                  key: filter.key,
                  label: filter.label,
                  removeLabel: tx(locale, `移除筛选：${filter.label}`, `Remove filter: ${filter.label}`),
                }))}
                clearHref={assetSearchHref(tenantSlug, projectId, searchQuery)}
                clearLabel={<Bi zh="清除筛选" en="Clear filters" />}
                disclosure={(
                  <details className="overview-details asset-filter-disclosure">
                    <summary className="asset-filter-trigger">
                      <SlidersHorizontal aria-hidden="true" size={16} strokeWidth={1.8} />
                      <span>
                        <strong><Bi zh="筛选" en="Filters" />{appliedFilters.length > 0 ? ` · ${appliedFilters.length}` : ""}</strong>
                      </span>
                      <ChevronRight className="overview-details-chevron" aria-hidden="true" size={16} />
                    </summary>
                    <div className="overview-details-content asset-filter-content">
                      <section aria-labelledby="asset-filter-options-heading">
                        <div className="asset-filter-panel-header">
                          <h3 id="asset-filter-options-heading"><Bi zh="筛选条件" en="Filter options" /></h3>
                          <p className="form-hint"><Bi zh="按类型、状态、来源或标签缩小范围" en="Narrow by type, status, source, or tag" /></p>
                        </div>
                        <div className="asset-filter-fields">
                          <div className="asset-filter-field-span">
                            <SearchModeSelect
                              capabilities={searchCapabilities}
                              defaultValue={searchMode}
                              id="asset-search-mode"
                              locale={locale}
                              name="mode"
                              tenantSlug={tenantSlug}
                            />
                          </div>
                          <FacetSelect
                            id="asset-search-type"
                            label={tx(locale, "资产类型", "Asset type")}
                            name="assetType"
                            items={facets.ok ? facets.asset_types : []}
                            value={searchFilters.asset_types[0]}
                            locale={locale}
                          />
                          <FacetSelect
                            id="asset-search-category"
                            label={tx(locale, "分类", "Category")}
                            name="category"
                            items={facets.ok ? facets.categories : []}
                            value={searchFilters.categories[0]}
                            locale={locale}
                          />
                          <FacetSelect
                            id="asset-search-lifecycle"
                            label={tx(locale, "创作状态", "Story status")}
                            name="lifecycle"
                            items={facets.ok ? facets.lifecycles : []}
                            value={searchFilters.lifecycles[0]}
                            locale={locale}
                          />
                          <FacetSelect
                            id="asset-search-source"
                            label={tx(locale, "来源", "Source")}
                            name="source"
                            items={facets.ok ? facets.sources : []}
                            value={searchFilters.sources[0]}
                            locale={locale}
                          />
                          <FacetSelect
                            id="asset-search-tag"
                            label={tx(locale, "标签", "Tag")}
                            name="tag"
                            items={facets.ok ? facets.tags : []}
                            value={searchFilters.tags[0]}
                            locale={locale}
                          />
                          <div className="asset-search-field">
                            <label htmlFor="asset-search-pinned"><Bi zh="置顶" en="Pinned" /></label>
                            <select id="asset-search-pinned" defaultValue={searchFilters.pinned === undefined ? "" : String(searchFilters.pinned)} name="pinned">
                              <option value="">{tx(locale, "全部", "All")}</option>
                              <option value="true">{tx(locale, "仅置顶", "Pinned only")}</option>
                              <option value="false">{tx(locale, "仅未置顶", "Unpinned only")}</option>
                            </select>
                          </div>
                        </div>
                        <details className="asset-facet-overview">
                          <summary>
                            <strong><Bi zh="分类概览" en="Facet overview" /></strong>
                            <small><Bi zh="查看各维度数量分布" en="Counts by dimension" /></small>
                          </summary>
                          <div className="asset-facet-overview-body">
                            <FacetSummary facets={facets} locale={locale} />
                          </div>
                        </details>
                      </section>
                    </div>
                  </details>
                )}
                searchField={(
                  <div className="asset-search-field asset-search-primary-field">
                    <label htmlFor="asset-search-query"><Bi zh="搜索词" en="Search query" /></label>
                    <input
                      id="asset-search-query"
                      defaultValue={searchQuery}
                      name="query"
                      placeholder={tx(locale, "世界规则、角色、风格（可留空浏览）", "world rule, character, style (optional)")}
                    />
                  </div>
                )}
                submitControl={(
                  <button className="submit-button asset-search-submit" data-tone="primary" type="submit"><Search aria-hidden="true" size={18} /><Bi zh="搜索" en="Search" /></button>
                )}
              />
            </form>
            <div className="asset-results-region">
              <AssetBrowseClient assets={assets} locale={locale} searchResults={searchResults} />
            </div>
          </section>

        </main>

        <InspectorPanel
          className="asset-library-aside"
          status={<Bi zh="操作与记忆" en="Operations and memory" />}
          title={<Bi zh="资产检视" en="Asset inspector" />}
        >
          <div id="asset-operations">
          <AssetOperationWorkspace
            description={<Bi zh="创建与管理资产" en="Create and manage assets" />}
            items={[
              operationItem("create", <Bi zh="创建资产" en="Create asset" />, <Bi zh="建立新的结构化创作资产" en="Create a structured story asset" />, <><StatusLine status={assetStatus} code={assetCode} message={assetMessage} /><CreateAssetForm action={createAssetAction} locale={locale} /></>),
              operationItem("update", <Bi zh="更新资产" en="Update asset" />, <Bi zh="修改内容、生命周期与标签" en="Edit content, lifecycle, and tags" />, <UpdateAssetForm action={updateAssetAction} assets={availableAssets} locale={locale} />),
              operationItem("delete", <Bi zh="删除资产" en="Delete asset" />, <Bi zh="从资产库中移除一条记录" en="Remove a record from the library" />, <DeleteAssetForm action={deleteAssetAction} assets={availableAssets} locale={locale} />, "danger"),
              operationItem("adopt", <Bi zh="采纳候选" en="Adopt candidate" />, <Bi zh="将候选资产转为素材或正史" en="Promote a candidate to material or canon" />, <AdoptAssetForm action={adoptAssetAction} assets={availableAssets} locale={locale} />),
              operationItem("bulk", <Bi zh="批量操作" en="Bulk action" />, <Bi zh="批量调整分类、状态与生命周期" en="Update classification and lifecycle in bulk" />, <><StatusLine status={bulkStatus} code={bulkCode} message={bulkMessage} /><BulkAssetActionForm action={bulkAssetAction} assets={availableAssets} locale={locale} /></>),
              operationItem("ingest", <Bi zh="导入素材" en="Ingest material" />, <Bi zh="将笔记、规则或风格素材交给 Agent 入库" en="Send material to ingestion" />, <><StatusLine status={ingestionStatus} code={ingestionCode} message={ingestionMessage} /><IngestAssetForm action={ingestAssetAction} locale={locale} /></>),
              operationItem("reindex", <Bi zh="刷新搜索" en="Reindex assets" />, <Bi zh="让最近修改的内容重新进入资产搜索" en="Make recent changes available in library search" />, <><StatusLine status={reindexStatus} code={reindexCode} message={reindexMessage} /><ReindexRunStatus run={reindexRun} locale={locale} /><ReindexAssetsForm action={reindexAssetsAction} capabilities={searchCapabilities} locale={locale} tenantSlug={tenantSlug} /></>),
              operationItem("style", <Bi zh="提取风格" en="Extract style" />, <Bi zh="从已有资产或素材中提取写作风格" en="Extract writing style" />, <><StatusLine status={styleStatus} code={styleCode} message={styleMessage} /><ExtractStyleForm action={extractStyleAction} assets={availableAssets} locale={locale} /></>),
            ]}
            moreLabel={<Bi zh="更多操作" en="More operations" />}
            openLabel={<Bi zh="创建资产" en="Create asset" />}
            primaryId="create"
            title={<Bi zh="资产操作" en="Asset operations" />}
          />
          </div>
          <details className={`overview-details asset-memory-panel ${archiveMemories === null || archiveMemories.ok ? "" : "error-box"}`}>
            <summary>
              <Boxes aria-hidden="true" size={18} strokeWidth={1.8} />
              <span>
                <strong><Bi zh="记忆审阅" en="Memory review" /></strong>
                <small><Bi zh="按需查看和处理档案记忆" en="Review archive memories when needed" /></small>
              </span>
              <ChevronRight className="overview-details-chevron" aria-hidden="true" size={18} />
            </summary>
            <div className="overview-details-content">
              <section aria-labelledby="archive-memory-heading">
                <h3 id="archive-memory-heading"><Bi zh="档案记忆" en="Archive Memory" /></h3>
                <StatusLine status={memoryStatus} code={memoryCode} message={memoryMessage} />
                <form action={memoryAssetAction} className="inline-controls">
                  <label className="asset-search-field" htmlFor="archive-memory-asset">
                    <span><Bi zh="选择资产" en="Choose asset" /></span>
                    <select id="archive-memory-asset" defaultValue={memoryAssetId} name="memoryAssetId">
                      <option value="">{tx(locale, "请选择", "Choose an asset")}</option>
                      {availableAssets.map((asset) => (
                        <option key={asset.asset_id} value={asset.asset_id}>{asset.title}</option>
                      ))}
                    </select>
                  </label>
                  <button type="submit"><Bi zh="查看" en="View" /></button>
                </form>
                <ArchiveMemoryPanel
                  memories={archiveMemories}
                  events={archiveMemoryEvents}
                  adoptAction={adoptArchiveMemoryAction}
                  rejectAction={rejectArchiveMemoryAction}
                  locale={locale}
                />
              </section>
            </div>
          </details>
        </InspectorPanel>
      </div>
    </div>
  );
}

function operationItem(
  id: AssetOperationItem["id"],
  title: React.ReactNode,
  description: React.ReactNode,
  content: React.ReactNode,
  tone: AssetOperationItem["tone"] = "default",
): AssetOperationItem {
  return { id, title, description, content, tone };
}

type FacetDimension = "assetType" | "category" | "lifecycle" | "source" | "tag";

function AssetFacetRail({
  facets,
  filters,
  locale,
  projectId,
  searchMode,
  searchQuery,
  tenantSlug,
}: {
  facets: AssetFacetsSummary;
  filters: AssetLibraryShellProps["searchFilters"];
  locale: Locale;
  projectId: string;
  searchMode: "keyword" | "vector" | "hybrid";
  searchQuery: string;
  tenantSlug: string;
}) {
  const groups: { dimension: FacetDimension; label: React.ReactNode; items: { value: string; count: number }[]; active: string | undefined; isLifecycle?: boolean }[] = facets.ok
    ? [
        { dimension: "assetType", label: <Bi zh="类型" en="Type" />, items: facets.asset_types, active: filters.asset_types[0] },
        { dimension: "lifecycle", label: <Bi zh="状态" en="Status" />, items: facets.lifecycles, active: filters.lifecycles[0], isLifecycle: true },
        { dimension: "category", label: <Bi zh="分类" en="Category" />, items: facets.categories, active: filters.categories[0] },
        { dimension: "source", label: <Bi zh="来源" en="Source" />, items: facets.sources, active: filters.sources[0] },
        { dimension: "tag", label: <Bi zh="标签" en="Tag" />, items: facets.tags, active: filters.tags[0] },
      ]
    : [];
  const totalActive = [
    filters.asset_types,
    filters.categories,
    filters.lifecycles,
    filters.sources,
    filters.tags,
  ].reduce((count, values) => count + values.length, 0) + (filters.pinned === undefined ? 0 : 1);

  return (
    <nav className="asset-facet-rail" aria-label={tx(locale, "资产分面筛选", "Asset facets")}>
      <div className="asset-facet-rail-head">
        <span className="asset-facet-rail-title">
          <Filter aria-hidden="true" size={15} strokeWidth={1.8} />
          <strong><Bi zh="筛选" en="Filters" /></strong>
        </span>
        {totalActive > 0 ? (
          <a className="asset-facet-rail-clear" href={facetFilterHref(tenantSlug, projectId, searchQuery, searchMode, filters, null, null)}>
            <Bi zh="清除全部" en="Clear all" />
          </a>
        ) : null}
      </div>
      {!facets.ok ? (
        <PublicFailureNotice code={facets.code} />
      ) : groups.every((group) => group.items.length === 0) ? (
        <p className="form-hint asset-facet-rail-empty"><Bi zh="暂无可筛选的分面。" en="No facets to filter yet." /></p>
      ) : (
        <div className="asset-facet-rail-groups">
          {groups.filter((group) => group.items.length > 0).map((group) => (
            <section className="asset-facet-group" key={group.dimension} aria-label={typeof group.label === "string" ? group.label : group.dimension}>
              <p className="asset-facet-group-label">{group.label}</p>
              <ul className="asset-facet-group-list">
                {group.items.slice(0, 8).map((item) => {
                  const active = group.active === item.value;
                  const nextValue = active ? null : item.value;
                  return (
                    <li key={`${group.dimension}-${item.value}`}>
                      <a
                        className="asset-facet-chip"
                        data-active={active ? "true" : "false"}
                        aria-current={active ? "true" : undefined}
                        href={facetFilterHref(tenantSlug, projectId, searchQuery, searchMode, filters, group.dimension, nextValue)}
                      >
                        <span className="asset-facet-chip-label">
                          {group.isLifecycle ? assetLifecycleLabel(locale, item.value) : assetValueLabel(locale, item.value)}
                        </span>
                        <span className="asset-facet-chip-count">{item.count}</span>
                      </a>
                    </li>
                  );
                })}
              </ul>
            </section>
          ))}
        </div>
      )}
    </nav>
  );
}

function facetFilterHref(
  tenantSlug: string,
  projectId: string,
  searchQuery: string,
  mode: "keyword" | "vector" | "hybrid",
  filters: AssetLibraryShellProps["searchFilters"],
  dimension: FacetDimension | null,
  value: string | null,
) {
  const next = {
    asset_types: [...filters.asset_types],
    categories: [...filters.categories],
    lifecycles: [...filters.lifecycles],
    sources: [...filters.sources],
    tags: [...filters.tags],
    pinned: filters.pinned,
  };
  if (dimension === null) {
    next.asset_types = [];
    next.categories = [];
    next.lifecycles = [];
    next.sources = [];
    next.tags = [];
    next.pinned = undefined;
  } else {
    const assignment: [FacetDimension, keyof typeof next][] = [
      ["assetType", "asset_types"],
      ["category", "categories"],
      ["lifecycle", "lifecycles"],
      ["source", "sources"],
      ["tag", "tags"],
    ];
    for (const [dim, key] of assignment) {
      if (dim === dimension) {
        (next[key] as string[]) = value ? [value] : [];
      }
    }
  }
  return assetSearchHref(tenantSlug, projectId, searchQuery, { filters: next, mode });
}

function StatusLine({ status, code: _code, message: _message }: { status: string; code: string; message: string }) {
  if (!status) {
    return null;
  }
  const statusClass = status === "success" ? "success-box" : "error-box";
  return (
    <p className={`form-status ${statusClass}`} data-status={status} role={status === "success" ? "status" : "alert"}>
      {status === "success" ? <Bi zh="操作已完成。" en="Action completed." /> : <FailureText />}
    </p>
  );
}

function ArchiveMemoryPanel({
  memories,
  events,
  adoptAction,
  rejectAction,
  locale,
}: {
  memories: ArchiveMemorySummary | null;
  events: ArchiveMemoryEventsSummary | null;
  adoptAction: (formData: FormData) => Promise<void>;
  rejectAction: (formData: FormData) => Promise<void>;
  locale: Locale;
}) {
  if (memories === null) {
    return <p className="form-hint"><Bi zh="请选择档案资产。" en="Select an archive asset." /></p>;
  }
  if (!memories.ok) {
    return <PublicFailureNotice code={memories.code} />;
  }
  return (
    <div className="trace-list" style={{ marginTop: 12 }}>
      {memories.items.length === 0 ? (
        <p className="form-hint"><Bi zh="暂无记忆记录。" en="No memories found." /></p>
      ) : (
        memories.items.map((memory) => (
          <article className="trace-event" key={memory.memory_id}>
            <div className="trace-event-header">
              <strong>{assetValueLabel(locale, memory.memory_type)}</strong>
              <span className="trace-redaction"><StatusValue value={memory.status} /></span>
            </div>
            <p className="trace-meta"><Bi zh="来源：" en="Source: " />{assetValueLabel(locale, memory.source_kind)}</p>
            <p>{memory.summary}</p>
            {memory.status === "candidate" ? (
              <div className="inline-controls">
                <form action={adoptAction}>
                  <input name="memoryId" type="hidden" value={memory.memory_id} />
                  <button type="submit"><Bi zh="采纳记忆" en="Adopt memory" /></button>
                </form>
                <form action={rejectAction}>
                  <input name="memoryId" type="hidden" value={memory.memory_id} />
                  <button type="submit"><Bi zh="拒绝记忆" en="Reject memory" /></button>
                </form>
              </div>
            ) : null}
          </article>
        ))
      )}
      <ArchiveMemoryEvents events={events} locale={locale} />
    </div>
  );
}

function ArchiveMemoryEvents({ events, locale }: { events: ArchiveMemoryEventsSummary | null; locale: Locale }) {
  if (events === null) {
    return null;
  }
  if (!events.ok) {
    return <PublicFailureNotice code={events.code} />;
  }
  return (
    <div className="compact-action-list">
      <strong><Bi zh="事件" en="Events" /></strong>
      {events.items.length === 0 ? (
        <span className="status-pill">{tx(locale, "暂无", "empty")}</span>
      ) : (
        events.items.map((event) => (
          <span className="status-pill" key={event.event_id}>
            {memoryEventLabel(locale, event.event_type)}: <StatusValue value={event.status} />
          </span>
        ))
      )}
    </div>
  );
}

function FacetSummary({ facets, locale }: { facets: AssetFacetsSummary; locale: Locale }) {
  if (!facets.ok) {
    return <PublicFailureNotice code={facets.code} />;
  }
  return (
    <div className="compact-action-list">
      <FacetGroup label={tx(locale, "类型", "Types")} items={facets.asset_types} locale={locale} />
      <FacetGroup label={tx(locale, "分类", "Categories")} items={facets.categories} locale={locale} />
      <FacetGroup label={tx(locale, "生命周期", "Lifecycles")} items={facets.lifecycles} locale={locale} />
      <FacetGroup label={tx(locale, "来源", "Sources")} items={facets.sources} locale={locale} />
      <FacetGroup label={tx(locale, "标签", "Tags")} items={facets.tags} locale={locale} />
    </div>
  );
}

function FacetSelect({
  id,
  label,
  name,
  items,
  value,
  locale,
}: {
  id: string;
  label: string;
  name: string;
  items: { value: string; count: number }[];
  value?: string;
  locale: Locale;
}) {
  return (
    <div className="asset-search-field">
      <label htmlFor={id}>{label}</label>
      <select id={id} name={name} defaultValue={value || ""}>
        <option value="">{tx(locale, "全部", "All")}</option>
        {items.map((item) => (
          <option value={item.value} key={`${name}-${item.value}`}>
            {assetValueLabel(locale, item.value)} ({item.count})
          </option>
        ))}
      </select>
    </div>
  );
}

function FacetGroup({ label, items, locale }: { label: string; items: { value: string; count: number }[]; locale: Locale }) {
  return (
    <div>
      <strong>{label}</strong>
      <div className="facet-pills">
        {items.length === 0 ? (
          <span className="status-pill">{tx(locale, "暂无", "empty")}</span>
        ) : (
          items.map((item) => (
            <span className="status-pill" key={`${label}-${item.value}`}>
              {assetValueLabel(locale, item.value)}: {item.count}
            </span>
          ))
        )}
      </div>
    </div>
  );
}

type AssetOption = Extract<AssetListSummary, { ok: true }>["items"][number];

function CreateAssetForm({ action, locale }: { action: (formData: FormData) => Promise<void>; locale: Locale }) {
  return (
    <form action={action} className="binding-form">
      <label htmlFor="asset-title"><Bi zh="标题" en="Title" /></label>
      <input id="asset-title" name="title" required />

      <label htmlFor="asset-type"><Bi zh="资产类型" en="Asset type" /></label>
      <input id="asset-type" name="assetType" required defaultValue="note" />

      <label htmlFor="asset-category"><Bi zh="分类" en="Category" /></label>
      <input id="asset-category" name="category" defaultValue="material" />

      <label htmlFor="asset-lifecycle"><Bi zh="生命周期" en="Lifecycle" /></label>
      <select id="asset-lifecycle" name="lifecycle" defaultValue="material">
        <option value="material">{tx(locale, "素材", "Material")}</option>
        <option value="canon">{tx(locale, "正史", "Canon")}</option>
        <option value="candidate">{tx(locale, "候选", "Candidate")}</option>
        <option value="archived">{tx(locale, "已归档", "Archived")}</option>
      </select>

      <label htmlFor="asset-summary"><Bi zh="摘要" en="Summary" /></label>
      <textarea id="asset-summary" name="summary" rows={3} />

      <label htmlFor="asset-content"><Bi zh="私有内容" en="Private content" /></label>
      <textarea id="asset-content" name="contentText" rows={4} />

      <label htmlFor="asset-tags"><Bi zh="标签" en="Tags" /></label>
      <input id="asset-tags" name="tags" placeholder={tx(locale, "风格、规则、笔记", "style, rule, note")} />

      <label className="checkbox-row">
        <input name="enabled" type="checkbox" defaultChecked />
        <Bi zh="启用" en="Enabled" />
      </label>
      <label className="checkbox-row">
        <input name="pinned" type="checkbox" />
        <Bi zh="置顶" en="Pinned" />
      </label>

      <details className="overview-details asset-advanced-fields">
        <summary>
          <SlidersHorizontal aria-hidden="true" size={18} strokeWidth={1.8} />
          <span>
            <strong><Bi zh="高级来源信息" en="Advanced source details" /></strong>
            <small><Bi zh="仅在导入或支持场景下使用" en="Use only for imports or support workflows" /></small>
          </span>
          <ChevronRight className="overview-details-chevron" aria-hidden="true" size={18} />
        </summary>
        <div className="overview-details-content">
          <section>
            <label htmlFor="asset-payload"><Bi zh="扩展数据" en="Structured metadata" /></label>
            <textarea id="asset-payload" name="payload" rows={4} defaultValue="{}" />

            <label htmlFor="asset-source-kind"><Bi zh="来源类型" en="Source kind" /></label>
            <input id="asset-source-kind" name="sourceKind" defaultValue="manual" />

            <label htmlFor="asset-source-ref"><Bi zh="来源引用" en="Source reference" /></label>
            <input id="asset-source-ref" name="sourceRef" placeholder={tx(locale, "可选", "optional")} />
          </section>
        </div>
      </details>

      <button data-tone="primary" type="submit"><Bi zh="创建资产" en="Create asset" /></button>
    </form>
  );
}

function UpdateAssetForm({ action, assets, locale }: { action: (formData: FormData) => Promise<void>; assets: AssetOption[]; locale: Locale }) {
  return (
    <form action={action} className="binding-form">
      <AssetPicker assets={assets} id="update-asset" label={tx(locale, "选择资产", "Choose asset")} name="assetId" required />

      <label htmlFor="update-title"><Bi zh="标题" en="Title" /></label>
      <input id="update-title" name="title" />

      <label htmlFor="update-lifecycle"><Bi zh="生命周期" en="Lifecycle" /></label>
      <select id="update-lifecycle" name="lifecycle" defaultValue="">
        <option value="">{tx(locale, "不变", "Unchanged")}</option>
        <option value="material">{tx(locale, "素材", "Material")}</option>
        <option value="canon">{tx(locale, "正史", "Canon")}</option>
        <option value="candidate">{tx(locale, "候选", "Candidate")}</option>
        <option value="archived">{tx(locale, "已归档", "Archived")}</option>
      </select>

      <label htmlFor="update-summary"><Bi zh="摘要" en="Summary" /></label>
      <textarea id="update-summary" name="summary" rows={3} />

      <label htmlFor="update-content"><Bi zh="私有内容" en="Private content" /></label>
      <textarea id="update-content" name="contentText" rows={3} />

      <label htmlFor="update-tags"><Bi zh="标签" en="Tags" /></label>
      <input id="update-tags" name="tags" />

      <label className="checkbox-row">
        <input name="enabled" type="checkbox" defaultChecked />
        <Bi zh="启用" en="Enabled" />
      </label>
      <label className="checkbox-row">
        <input name="pinned" type="checkbox" />
        <Bi zh="置顶" en="Pinned" />
      </label>

      <details className="overview-details asset-advanced-fields">
        <summary>
          <SlidersHorizontal aria-hidden="true" size={18} strokeWidth={1.8} />
          <span><strong><Bi zh="高级数据" en="Advanced data" /></strong></span>
          <ChevronRight className="overview-details-chevron" aria-hidden="true" size={18} />
        </summary>
        <div className="overview-details-content">
          <section>
            <label htmlFor="update-payload"><Bi zh="扩展数据" en="Structured metadata" /></label>
            <textarea id="update-payload" name="payload" rows={3} />
          </section>
        </div>
      </details>

      <button type="submit"><Bi zh="更新资产" en="Update asset" /></button>
    </form>
  );
}

function DeleteAssetForm({ action, assets, locale }: { action: (formData: FormData) => Promise<void>; assets: AssetOption[]; locale: Locale }) {
  return (
    <form action={action} className="binding-form">
      <AssetPicker assets={assets} id="delete-asset" label={tx(locale, "选择要删除的资产", "Choose an asset to delete")} name="assetId" required />
      <button className="danger-action" type="submit"><Bi zh="删除资产" en="Delete asset" /></button>
    </form>
  );
}

function AdoptAssetForm({ action, assets, locale }: { action: (formData: FormData) => Promise<void>; assets: AssetOption[]; locale: Locale }) {
  const candidates = assets.filter((asset) => asset.lifecycle === "candidate");
  return (
    <form action={action} className="binding-form">
      <AssetPicker
        assets={candidates.length > 0 ? candidates : assets}
        id="adopt-asset"
        label={tx(locale, "选择候选资产", "Choose a candidate")}
        name="assetId"
        required
      />

      <label htmlFor="adopt-target"><Bi zh="目标生命周期" en="Target lifecycle" /></label>
      <select id="adopt-target" name="targetLifecycle" defaultValue="canon">
        <option value="canon">{tx(locale, "正史", "Canon")}</option>
        <option value="material">{tx(locale, "素材", "Material")}</option>
      </select>

      <button type="submit"><Bi zh="采纳候选" en="Adopt candidate" /></button>
    </form>
  );
}

function BulkAssetActionForm({ action, assets, locale }: { action: (formData: FormData) => Promise<void>; assets: AssetOption[]; locale: Locale }) {
  const selections = bulkAssetSelections(assets, locale);
  return (
    <form action={action} className="binding-form">
      <label htmlFor="bulk-asset-selection"><Bi zh="选择范围" en="Selection" /></label>
      <select id="bulk-asset-selection" name="assetIds" required defaultValue="">
        <option value="">{tx(locale, "请选择", "Choose assets")}</option>
        {selections.map((selection) => (
          <option key={selection.label} value={selection.value}>{selection.label}</option>
        ))}
      </select>

      <label htmlFor="bulk-action"><Bi zh="操作" en="Action" /></label>
      <select id="bulk-action" name="bulkAction" defaultValue="disable">
        <option value="disable">{tx(locale, "停用", "Disable")}</option>
        <option value="enable">{tx(locale, "启用", "Enable")}</option>
        <option value="set_lifecycle">{tx(locale, "设置生命周期", "Set lifecycle")}</option>
        <option value="categorize">{tx(locale, "设置分类", "Categorize")}</option>
        <option value="pin">{tx(locale, "置顶", "Pin")}</option>
        <option value="unpin">{tx(locale, "取消置顶", "Unpin")}</option>
      </select>

      <label htmlFor="bulk-target-lifecycle"><Bi zh="目标生命周期" en="Target lifecycle" /></label>
      <select id="bulk-target-lifecycle" name="targetLifecycle" defaultValue="">
        <option value="">{tx(locale, "不变", "Unchanged")}</option>
        <option value="material">{tx(locale, "素材", "Material")}</option>
        <option value="canon">{tx(locale, "正史", "Canon")}</option>
        <option value="candidate">{tx(locale, "候选", "Candidate")}</option>
        <option value="archived">{tx(locale, "已归档", "Archived")}</option>
      </select>

      <label htmlFor="bulk-category"><Bi zh="分类" en="Category" /></label>
      <input id="bulk-category" name="category" placeholder={tx(locale, "可选", "optional")} />

      <label htmlFor="bulk-enabled"><Bi zh="启用状态" en="Enabled override" /></label>
      <select id="bulk-enabled" name="enabled" defaultValue="">
        <option value="">{tx(locale, "不变", "Unchanged")}</option>
        <option value="true">{tx(locale, "启用", "Enabled")}</option>
        <option value="false">{tx(locale, "停用", "Disabled")}</option>
      </select>

      <label htmlFor="bulk-pinned"><Bi zh="置顶状态" en="Pinned override" /></label>
      <select id="bulk-pinned" name="pinned" defaultValue="">
        <option value="">{tx(locale, "不变", "Unchanged")}</option>
        <option value="true">{tx(locale, "置顶", "Pinned")}</option>
        <option value="false">{tx(locale, "不置顶", "Not pinned")}</option>
      </select>

      <button type="submit"><Bi zh="应用批量操作" en="Apply bulk action" /></button>
    </form>
  );
}

function IngestAssetForm({ action, locale }: { action: (formData: FormData) => Promise<void>; locale: Locale }) {
  return (
    <form action={action} className="binding-form">
      <label htmlFor="ingest-hint"><Bi zh="素材类型" en="Material type" /></label>
      <select id="ingest-hint" name="hintType" defaultValue="note">
        <option value="note">{tx(locale, "笔记", "Note")}</option>
        <option value="writing_style">{tx(locale, "写作风格", "Writing style")}</option>
        <option value="world_rule">{tx(locale, "世界规则", "World rule")}</option>
        <option value="character_archetype">{tx(locale, "角色原型", "Character archetype")}</option>
        <option value="plot_template">{tx(locale, "剧情模板", "Plot template")}</option>
      </select>

      <label htmlFor="ingest-scope"><Bi zh="范围" en="Scope" /></label>
      <select id="ingest-scope" name="scope" defaultValue="project">
        <option value="project">{tx(locale, "项目", "Project")}</option>
        <option value="tenant">{tx(locale, "工作区", "Workspace")}</option>
      </select>

      <label htmlFor="ingest-material"><Bi zh="素材内容" en="Material" /></label>
      <textarea id="ingest-material" name="materialText" required rows={5} />

      <button type="submit"><Bi zh="导入素材" en="Ingest material" /></button>
    </form>
  );
}

function ReindexAssetsForm({
  action,
  capabilities,
  locale,
  tenantSlug,
}: {
  action: (formData: FormData) => Promise<void>;
  capabilities: AssetSearchCapabilitiesSummary;
  locale: Locale;
  tenantSlug: string;
}) {
  const defaultMode = capabilities.ok && capabilities.hybrid ? "hybrid" : "keyword";
  return (
    <form action={action} className="binding-form">
      <label htmlFor="reindex-scope"><Bi zh="范围" en="Scope" /></label>
      <select id="reindex-scope" name="scope" defaultValue="project">
        <option value="project">{tx(locale, "项目", "Project")}</option>
      </select>

      <SearchModeSelect
        capabilities={capabilities}
        defaultValue={defaultMode}
        id="reindex-mode"
        locale={locale}
        name="mode"
        tenantSlug={tenantSlug}
      />

      <button type="submit"><Bi zh="刷新搜索" en="Refresh search" /></button>
    </form>
  );
}

function SearchModeSelect({
  capabilities,
  defaultValue,
  id,
  locale,
  name,
  tenantSlug,
}: {
  capabilities: AssetSearchCapabilitiesSummary;
  defaultValue: "keyword" | "vector" | "hybrid";
  id: string;
  locale: Locale;
  name: string;
  tenantSlug: string;
}) {
  const vectorEnabled = capabilities.ok ? capabilities.vector : false;
  const hybridEnabled = capabilities.ok ? capabilities.hybrid : false;
  const reason = capabilities.ok ? assetSearchCapabilityReason(locale, capabilities.reason) : "";
  const configHref = capabilities.ok && capabilities.config_href
    ? `/${encodeURIComponent(tenantSlug)}${capabilities.config_href}`
    : "";

  return (
    <div className="asset-search-field">
      <label htmlFor={id}><Bi zh="匹配方式" en="Match style" /></label>
      <select id={id} defaultValue={defaultValue} name={name}>
        <option value="keyword">{tx(locale, "精确文字", "Exact wording")}</option>
        <option disabled={!vectorEnabled} value="vector">{tx(locale, "含义相近", "Similar meaning")}</option>
        <option disabled={!hybridEnabled} value="hybrid">{tx(locale, "智能匹配", "Best match")}</option>
      </select>
      {!vectorEnabled || !hybridEnabled ? (
        <p className="form-hint">
          {reason || <Bi zh="向量搜索暂不可用。" en="Vector search is unavailable." />}
          {configHref ? (
            <>
              {" "}
              <a href={configHref}><Bi zh="配置搜索嵌入模块" en="Configure search embedding module" /></a>
            </>
          ) : null}
        </p>
      ) : null}
    </div>
  );
}

function assetSearchCapabilityReason(locale: Locale, reason: string) {
  const normalized = reason.trim().toLowerCase();
  const labels: Record<string, [string, string]> = {
    "asset_search_embedding module is not bound": ["尚未绑定 asset_search_embedding 模块。", "The asset_search_embedding module is not bound."],
    "asset vector search index is not available": ["向量搜索索引尚未就绪。", "The vector search index is not available."],
    "asset query embedding credential is unavailable": ["搜索嵌入凭证不可用。", "The search embedding credential is unavailable."],
    "asset query embedding provider is incomplete": ["搜索嵌入提供方配置不完整。", "The search embedding provider is incomplete."],
    "asset query embedding provider is unsupported": ["搜索嵌入提供方不受支持。", "The search embedding provider is unsupported."],
    "asset search embedding dimensions are not configured": ["搜索嵌入维度尚未配置。", "Search embedding dimensions are not configured."],
  };
  const label = labels[normalized];
  if (label) {
    return tx(locale, label[0], label[1]);
  }
  return reason;
}

function ReindexRunStatus({ run, locale }: { run: WorkflowRunSummary | null; locale: Locale }) {
  if (run === null) {
    return null;
  }
  if (!run.ok) {
    return <PublicFailureNotice code={run.code} />;
  }
  const failed = run.status === "failed" || run.status === "cancelled";
  return (
    <div className={failed ? "form-status error-box" : "compact-action-list"} aria-live="polite">
      <span className="status-pill"><Bi zh="状态" en="Status" />: <StatusValue value={run.status} /></span>
      <span className="status-pill"><Bi zh="进度" en="Progress" />: {Math.round(run.progress)}%</span>
      {run.error_code ? <p className="form-hint"><FailureText /></p> : null}
      {run.status === "queued" || run.status === "running" ? (
        <p className="form-hint">{tx(locale, "刷新页面以获取最新状态。", "Refresh to load the latest status.")}</p>
      ) : null}
    </div>
  );
}

function ExtractStyleForm({ action, assets, locale }: { action: (formData: FormData) => Promise<void>; assets: AssetOption[]; locale: Locale }) {
  return (
    <form action={action} className="binding-form">
      <AssetPicker assets={assets} id="style-source-asset" label={tx(locale, "参考资产（可选）", "Reference asset (optional)")} name="sourceAssetId" />

      <label htmlFor="style-scope"><Bi zh="范围" en="Scope" /></label>
      <select id="style-scope" name="scope" defaultValue="project">
        <option value="project">{tx(locale, "项目", "Project")}</option>
        <option value="tenant">{tx(locale, "工作区", "Workspace")}</option>
      </select>

      <label htmlFor="style-material"><Bi zh="素材内容" en="Material" /></label>
      <textarea id="style-material" name="materialText" rows={5} />

      <button type="submit"><Bi zh="提取风格" en="Extract style" /></button>
    </form>
  );
}

function assetLifecycleLabel(locale: Locale, lifecycle: string) {
  const labels: Record<string, [string, string]> = {
    archived: ["已归档", "Archived"],
    candidate: ["候选", "Candidate"],
    canon: ["正史", "Canon"],
    material: ["素材", "Material"],
  };
  const label = labels[lifecycle];
  return label ? tx(locale, label[0], label[1]) : assetValueLabel(locale, lifecycle);
}

function AssetPicker({
  assets,
  id,
  label,
  name,
  required = false,
}: {
  assets: AssetOption[];
  id: string;
  label: string;
  name: string;
  required?: boolean;
}) {
  return (
    <>
      <label htmlFor={id}>{label}</label>
      <select id={id} name={name} required={required} defaultValue="">
        <option value="">{required ? "--" : "—"}</option>
        {assets.map((asset) => (
          <option key={asset.asset_id} value={asset.asset_id}>
            {asset.title}
          </option>
        ))}
      </select>
    </>
  );
}

function bulkAssetSelections(assets: AssetOption[], locale: Locale) {
  if (assets.length === 0) {
    return [];
  }
  const selections = [{
    label: tx(locale, `全部资产（${assets.length}）`, `All assets (${assets.length})`),
    value: assets.map((asset) => asset.asset_id).join(","),
  }];
  for (const lifecycle of ["candidate", "canon", "material", "archived"]) {
    const matching = assets.filter((asset) => asset.lifecycle === lifecycle);
    if (matching.length > 1) {
      selections.push({
        label: `${assetLifecycleLabel(locale, lifecycle)} (${matching.length})`,
        value: matching.map((asset) => asset.asset_id).join(","),
      });
    }
  }
  return selections.concat(assets.map((asset) => ({ label: asset.title, value: asset.asset_id })));
}

function appliedAssetFilters(
  locale: Locale,
  mode: "keyword" | "vector" | "hybrid",
  filters: AssetLibraryShellProps["searchFilters"],
) {
  const applied: { key: string; label: string; parameter: AssetFilterParameter }[] = [];
  if (mode !== "keyword") {
    applied.push({
      key: "mode",
      label: mode === "vector" ? tx(locale, "含义相近", "Similar meaning") : tx(locale, "智能匹配", "Best match"),
      parameter: "mode",
    });
  }
  for (const value of filters.asset_types) {
    applied.push({ key: `assetType-${value}`, label: `${tx(locale, "类型", "Type")}: ${assetValueLabel(locale, value)}`, parameter: "assetType" });
  }
  for (const value of filters.categories) {
    applied.push({ key: `category-${value}`, label: `${tx(locale, "分类", "Category")}: ${assetValueLabel(locale, value)}`, parameter: "category" });
  }
  for (const value of filters.lifecycles) {
    applied.push({ key: `lifecycle-${value}`, label: `${tx(locale, "状态", "Status")}: ${assetLifecycleLabel(locale, value)}`, parameter: "lifecycle" });
  }
  for (const value of filters.sources) {
    applied.push({ key: `source-${value}`, label: `${tx(locale, "来源", "Source")}: ${assetValueLabel(locale, value)}`, parameter: "source" });
  }
  for (const value of filters.tags) {
    applied.push({ key: `tag-${value}`, label: `${tx(locale, "标签", "Tag")}: ${value}`, parameter: "tag" });
  }
  if (filters.pinned !== undefined) {
    applied.push({
      key: "pinned",
      label: filters.pinned ? tx(locale, "仅置顶", "Pinned only") : tx(locale, "仅未置顶", "Unpinned only"),
      parameter: "pinned",
    });
  }
  return applied;
}

type AssetFilterParameter = "assetType" | "category" | "lifecycle" | "mode" | "pinned" | "source" | "tag";

function assetSearchHref(
  tenantSlug: string,
  projectId: string,
  query: string,
  state?: {
    filters: AssetLibraryShellProps["searchFilters"];
    mode: "keyword" | "vector" | "hybrid";
    omit?: AssetFilterParameter;
  },
) {
  const params = new URLSearchParams();
  if (query) {
    params.set("query", query);
  }
  if (state) {
    if (state.mode !== "keyword" && state.omit !== "mode") {
      params.set("mode", state.mode);
    }
    setAssetFilterQuery(params, "assetType", state.filters.asset_types[0], state.omit);
    setAssetFilterQuery(params, "category", state.filters.categories[0], state.omit);
    setAssetFilterQuery(params, "lifecycle", state.filters.lifecycles[0], state.omit);
    setAssetFilterQuery(params, "source", state.filters.sources[0], state.omit);
    setAssetFilterQuery(params, "tag", state.filters.tags[0], state.omit);
    if (state.filters.pinned !== undefined && state.omit !== "pinned") {
      params.set("pinned", String(state.filters.pinned));
    }
  }
  const suffix = params.toString();
  return `/${encodeURIComponent(tenantSlug)}/projects/${encodeURIComponent(projectId)}/assets${suffix ? `?${suffix}` : ""}`;
}

function setAssetFilterQuery(params: URLSearchParams, name: AssetFilterParameter, value: string | undefined, omit?: AssetFilterParameter) {
  if (value && name !== omit) {
    params.set(name, value);
  }
}

function assetValueLabel(locale: Locale, value: string) {
  const labels: Record<string, [string, string]> = {
    archive: ["档案", "Archive"],
    character: ["角色", "Character"],
    character_archetype: ["角色原型", "Character archetype"],
    clue: ["伏笔", "Clue"],
    graph: ["故事图谱", "Story graph"],
    manual: ["手动创建", "Created here"],
    note: ["笔记", "Note"],
    organization: ["组织", "Organization"],
    plot_template: ["剧情模板", "Plot template"],
    relationship: ["关系", "Relationship"],
    seed: ["种子分析", "Seed analysis"],
    seed_canon: ["种子正史", "Seed canon"],
    style: ["风格", "Style"],
    writing_style: ["写作风格", "Writing style"],
    world_rule: ["世界规则", "World rule"],
  };
  const normalized = value.trim().toLowerCase();
  const label = labels[normalized];
  if (label) {
    return tx(locale, label[0], label[1]);
  }
  return value.replaceAll("_", " ").replaceAll("-", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

function memoryEventLabel(locale: Locale, eventType: string) {
  const labels: Record<string, [string, string]> = {
    adopted: ["已采纳", "Adopted"],
    created: ["已创建", "Created"],
    rejected: ["已拒绝", "Rejected"],
    reviewed: ["已审阅", "Reviewed"],
  };
  const normalized = eventType.trim().toLowerCase().split(".").at(-1) || eventType;
  const label = labels[normalized];
  return label ? tx(locale, label[0], label[1]) : assetValueLabel(locale, normalized);
}

function PublicFailureNotice({ code }: { code: string }) {
  void code;
  return <p className="form-status error-box" role="alert"><FailureText /></p>;
}
