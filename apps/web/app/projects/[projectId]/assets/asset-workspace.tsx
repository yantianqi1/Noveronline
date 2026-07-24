"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, MotionConfig, motion } from "motion/react";

import {
  addToCollection,
  adoptAsset,
  AssetError,
  createCollection,
  fetchAssetFacets,
  fetchAssets,
  fetchAssetVersions,
  fetchCatalogAsset,
  fetchCollections,
  fetchSearchCapabilities,
  patchAsset,
  readAssetSelection,
  removeFromCollection,
  restoreAssetVersion,
  searchAssets,
} from "@/lib/api/asset-client";
import type {
  AssetRecord,
  AssetVersion,
  CatalogAsset,
  Collection,
  Facets,
  SearchCapabilities,
} from "@/lib/api/asset-types";
import { fetchCsrfToken } from "@/lib/api/session";

import { EMPTY_FILTERS, AssetFilterBar, type AssetFilterState } from "./asset-filter-bar";
import { AssetInspector } from "./asset-inspector";
import { AssetList } from "./asset-list";
import { AssetCollectionsRail } from "./asset-collections-rail";
import { DUR, EASE, useFadeUp, useSlideIn } from "./asset-motion";
import { WorkbenchMasthead } from "@/components/workbench-masthead";

type LoadState =
  | { status: "loading" }
  | { status: "no-selection" }
  | { status: "error"; message: string }
  | { status: "ready" };

const SEARCH_DEBOUNCE_MS = 320;

/**
 * The Asset Library (资产库) workbench — the unified entry to a project's
 * story knowledge.
 *
 * Editorial three-column surface: a collections rail on the left, the
 * filterable asset list in the center, and a detail inspector on the right.
 * The list reads the unified asset model (list + facets + search); the
 * inspector reads the catalog (detail, versions, collections) and carries the
 * panel's explicit, optimistic-locked actions — candidate → canon adoption,
 * version restore, pin, and collection membership. Nothing here fabricates
 * data: empty facets, empty lists, and missing backend capability all render
 * as honest states.
 */
export function AssetWorkspace({ projectId }: { projectId: string }) {
  const router = useRouter();
  const fadeUp = useFadeUp();
  const slideIn = useSlideIn();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selection, setSelection] = useState<{ tenant_id: string; project_id: string } | null>(null);
  const [csrfToken, setCsrfToken] = useState<string | null>(null);

  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [facets, setFacets] = useState<Facets | null>(null);
  const [capabilities, setCapabilities] = useState<SearchCapabilities | null>(null);
  const [collections, setCollections] = useState<Collection[]>([]);

  const [filters, setFilters] = useState<AssetFilterState>(EMPTY_FILTERS);
  // Search results (asset ids in ranked order) while a query is active; null
  // means "browse mode", showing the full list filtered client-side.
  const [searchOrder, setSearchOrder] = useState<string[] | null>(null);
  const [searching, setSearching] = useState(false);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CatalogAsset | null>(null);
  const [versions, setVersions] = useState<AssetVersion[] | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const searchSeqRef = useRef(0);
  const searchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // ── Initial load ─────────────────────────────────────────────────────────

  const reload = useCallback(async (sel: { tenant_id: string; project_id: string }) => {
    const [assetList, facetData, collectionList] = await Promise.all([
      fetchAssets(sel.project_id, sel.tenant_id),
      fetchAssetFacets(sel.project_id, sel.tenant_id).catch(() => null),
      fetchCollections(sel.project_id, sel.tenant_id).catch(() => [] as Collection[]),
    ]);
    setAssets(assetList);
    setFacets(facetData);
    setCollections(collectionList);
    return assetList;
  }, []);

  useEffect(() => {
    const sel = readAssetSelection(projectId);
    if (!sel) {
      setState({ status: "no-selection" });
      return;
    }
    setSelection(sel);
    let cancelled = false;
    (async () => {
      try {
        const token = await fetchCsrfToken().catch(() => null);
        await reload(sel);
        if (cancelled) return;
        setCsrfToken(token);
        // Search capability is advisory (does hybrid/vector actually work?);
        // never block the list on it.
        void fetchSearchCapabilities(sel.project_id, sel.tenant_id)
          .then((caps) => {
            if (!cancelled) setCapabilities(caps);
          })
          .catch(() => {});
        setState({ status: "ready" });
      } catch (error) {
        if (cancelled) return;
        if (error instanceof AssetError && error.status === 401) {
          router.replace("/login");
          return;
        }
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "资产库暂时读不出来，请重试。",
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [projectId, reload, router]);

  // ── Search (debounced, capability-aware) ─────────────────────────────────

  useEffect(() => {
    if (state.status !== "ready" || !selection) return;
    const query = filters.query.trim();
    if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    if (!query) {
      setSearchOrder(null);
      setSearching(false);
      return;
    }
    // Without a usable search backend we degrade to a client-side title/summary
    // match rather than firing a request that can't be honoured.
    if (!csrfToken || (capabilities && !capabilities.keyword)) {
      setSearchOrder(null);
      return;
    }
    setSearching(true);
    searchTimerRef.current = setTimeout(() => {
      const seq = ++searchSeqRef.current;
      searchAssets(selection.project_id, selection.tenant_id, csrfToken, query)
        .then((hits) => {
          if (seq !== searchSeqRef.current) return;
          setSearchOrder(hits.map((hit) => hit.source_ref));
        })
        .catch(() => {
          if (seq !== searchSeqRef.current) return;
          setSearchOrder(null); // fall back to client-side match below
        })
        .finally(() => {
          if (seq === searchSeqRef.current) setSearching(false);
        });
    }, SEARCH_DEBOUNCE_MS);
    return () => {
      if (searchTimerRef.current) clearTimeout(searchTimerRef.current);
    };
  }, [filters.query, state.status, selection, csrfToken, capabilities]);

  // ── Derived, filtered list ────────────────────────────────────────────────

  const activeCollection = useMemo(
    () => collections.find((c) => c.collection_id === filters.collectionId) ?? null,
    [collections, filters.collectionId],
  );

  // The facets endpoint powers the filter pickers, but the lifecycle chips
  // should reflect what is actually in the list even when that endpoint is
  // unavailable — so we derive an honest lifecycle facet from the loaded
  // assets and only fall back to it when the server facet is missing/empty.
  const lifecycleFacet = useMemo(() => {
    if (facets && facets.lifecycles && facets.lifecycles.length > 0) {
      return facets.lifecycles;
    }
    const counts = new Map<string, number>();
    for (const asset of assets) {
      counts.set(asset.lifecycle, (counts.get(asset.lifecycle) ?? 0) + 1);
    }
    return [...counts.entries()]
      .map(([value, count]) => ({ value, count }))
      .sort((a, b) => b.count - a.count);
  }, [facets, assets]);

  const visibleAssets = useMemo(() => {
    let list = assets;

    if (activeCollection) {
      const memberIds = new Set(activeCollection.items.map((item) => item.asset_id));
      list = list.filter((asset) => memberIds.has(asset.asset_id));
    }
    if (filters.assetType) list = list.filter((asset) => asset.asset_type === filters.assetType);
    if (filters.source) list = list.filter((asset) => asset.source_kind === filters.source);
    if (filters.lifecycle) {
      list = list.filter((asset) =>
        filters.lifecycle === "canon"
          ? asset.lifecycle === "canon" || asset.lifecycle === "enabled"
          : asset.lifecycle === filters.lifecycle,
      );
    }

    const query = filters.query.trim().toLowerCase();
    if (query) {
      if (searchOrder) {
        // Server-ranked order, restricted to the id set it returned.
        const rank = new Map(searchOrder.map((id, index) => [id, index]));
        list = list
          .filter((asset) => rank.has(asset.asset_id))
          .sort((a, b) => (rank.get(a.asset_id) ?? 0) - (rank.get(b.asset_id) ?? 0));
      } else {
        list = list.filter(
          (asset) =>
            asset.title.toLowerCase().includes(query) ||
            asset.summary.toLowerCase().includes(query) ||
            asset.tags.some((tag) => tag.toLowerCase().includes(query)),
        );
      }
    } else {
      // Pinned first, then most-recently-updated, in browse mode.
      list = [...list].sort((a, b) => {
        if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
        return b.updated_at.localeCompare(a.updated_at);
      });
    }
    return list;
  }, [assets, activeCollection, filters, searchOrder]);

  // ── Selection + detail ────────────────────────────────────────────────────

  const openAsset = useCallback(
    async (assetId: string) => {
      if (!selection) return;
      setSelectedId(assetId);
      setDetail(null);
      setVersions(null);
      setActionError(null);
      try {
        const asset = await fetchCatalogAsset(selection.project_id, selection.tenant_id, assetId);
        setDetail(asset);
        const includePrivate = asset.capabilities.read_private;
        const versionList = await fetchAssetVersions(
          selection.project_id,
          selection.tenant_id,
          assetId,
          includePrivate,
        ).catch(() => []);
        setVersions(versionList);
      } catch (error) {
        setActionError(error instanceof Error ? error.message : "这条资产暂时打不开，请重试。");
      }
    },
    [selection],
  );

  const closeInspector = useCallback(() => {
    setSelectedId(null);
    setDetail(null);
    setVersions(null);
  }, []);

  // After a mutation, sync the affected row + refresh detail in place.
  const refreshAfterMutation = useCallback(
    async (assetId: string, updated?: CatalogAsset) => {
      if (!selection) return;
      const next = updated ?? (await fetchCatalogAsset(selection.project_id, selection.tenant_id, assetId));
      setDetail(next);
      setAssets((prev) =>
        prev.map((row) =>
          row.asset_id === assetId
            ? {
                ...row,
                title: next.title,
                summary: next.summary ?? "",
                lifecycle: next.lifecycle,
                pinned: next.pinned,
                tags: next.tags,
                updated_at: next.updated_at,
              }
            : row,
        ),
      );
    },
    [selection],
  );

  // ── Mutations (explicit, optimistic-locked, capability-gated) ────────────

  const runMutation = useCallback(
    async (assetId: string, action: () => Promise<CatalogAsset>, fallback: string) => {
      if (busy) return;
      setBusy(true);
      setActionError(null);
      try {
        const updated = await action();
        await refreshAfterMutation(assetId, updated);
        const versionList = await fetchAssetVersions(
          selection!.project_id,
          selection!.tenant_id,
          assetId,
          updated.capabilities.read_private,
        ).catch(() => null);
        if (versionList) setVersions(versionList);
      } catch (error) {
        if (error instanceof AssetError && error.code === "ASSET_VERSION_CONFLICT") {
          setActionError("这条资产刚在别处被改过了。已为你刷新到最新版本，请再操作一次。");
          if (selection) void refreshAfterMutation(assetId);
        } else {
          setActionError(error instanceof Error ? error.message : fallback);
        }
      } finally {
        setBusy(false);
      }
    },
    [busy, refreshAfterMutation, selection],
  );

  const handleAdopt = useCallback(async () => {
    if (!selection || !csrfToken || !detail) return;
    await runMutation(
      detail.asset_id,
      () => adoptAsset(selection.project_id, selection.tenant_id, csrfToken, detail.asset_id, "canon").then(
        () => fetchCatalogAsset(selection.project_id, selection.tenant_id, detail.asset_id),
      ),
      "采用失败，请重试。",
    );
  }, [selection, csrfToken, detail, runMutation]);

  const handleRestore = useCallback(
    async (versionNumber: number) => {
      if (!selection || !csrfToken || !detail) return;
      await runMutation(
        detail.asset_id,
        () =>
          restoreAssetVersion(
            selection.project_id,
            selection.tenant_id,
            csrfToken,
            detail.asset_id,
            detail.current_version,
            versionNumber,
          ),
        "恢复版本失败，请重试。",
      );
    },
    [selection, csrfToken, detail, runMutation],
  );

  const handleTogglePin = useCallback(async () => {
    if (!selection || !csrfToken || !detail) return;
    await runMutation(
      detail.asset_id,
      () =>
        patchAsset(
          selection.project_id,
          selection.tenant_id,
          csrfToken,
          detail.asset_id,
          detail.current_version,
          { pinned: !detail.pinned },
        ),
      "操作失败，请重试。",
    );
  }, [selection, csrfToken, detail, runMutation]);

  // Constant injection (doc 41 §4.2): mark this asset as always-on canon so the
  // writer injects it into every run regardless of recall relevance.
  const handleToggleAlwaysOn = useCallback(async () => {
    if (!selection || !csrfToken || !detail) return;
    await runMutation(
      detail.asset_id,
      () =>
        patchAsset(
          selection.project_id,
          selection.tenant_id,
          csrfToken,
          detail.asset_id,
          detail.current_version,
          { always_on: !detail.always_on },
        ),
      "操作失败，请重试。",
    );
  }, [selection, csrfToken, detail, runMutation]);

  // Spoiler gate (doc 41 §4.5): hide this asset from writer recall until the
  // author writes at or past the given chapter order. null clears the gate.
  const handleSetRevealAfter = useCallback(
    async (chapterOrder: number | null) => {
      if (!selection || !csrfToken || !detail) return;
      await runMutation(
        detail.asset_id,
        () =>
          patchAsset(
            selection.project_id,
            selection.tenant_id,
            csrfToken,
            detail.asset_id,
            detail.current_version,
            // The API clears the gate on a negative value (NULL = always visible).
            { reveal_after_chapter_order: chapterOrder === null ? -1 : chapterOrder },
          ),
        "操作失败，请重试。",
      );
    },
    [selection, csrfToken, detail, runMutation],
  );

  const handleToggleCollection = useCallback(
    async (collectionId: string, member: boolean) => {
      if (!selection || !csrfToken || !detail) return;
      setBusy(true);
      setActionError(null);
      try {
        const updated = member
          ? await addToCollection(selection.project_id, selection.tenant_id, csrfToken, collectionId, detail.asset_id)
          : await removeFromCollection(
              selection.project_id,
              selection.tenant_id,
              csrfToken,
              collectionId,
              detail.asset_id,
            );
        setCollections((prev) =>
          prev.map((c) => (c.collection_id === updated.collection_id ? updated : c)),
        );
        await refreshAfterMutation(detail.asset_id);
      } catch (error) {
        setActionError(error instanceof Error ? error.message : "更新集合失败，请重试。");
      } finally {
        setBusy(false);
      }
    },
    [selection, csrfToken, detail, refreshAfterMutation],
  );

  const handleCreateCollection = useCallback(
    async (title: string) => {
      if (!selection || !csrfToken) return;
      setActionError(null);
      try {
        const created = await createCollection(selection.project_id, selection.tenant_id, csrfToken, { title });
        setCollections((prev) => [...prev, created]);
      } catch (error) {
        setActionError(error instanceof Error ? error.message : "新建集合失败，请重试。");
      }
    },
    [selection, csrfToken],
  );

  // ── Render ────────────────────────────────────────────────────────────────

  if (state.status === "loading") return <AssetSkeleton />;
  if (state.status === "no-selection") return <NoSelection onBack={() => router.push("/workspace")} />;
  if (state.status === "error") {
    return (
      <div className="flex min-h-[70vh] flex-col items-center justify-center px-8 text-center">
        <h2 className="font-serif text-[22px] font-semibold text-ink">资产库暂时打不开</h2>
        <p className="mt-2 max-w-[380px] text-[13.5px] text-muted">{state.message}</p>
      </div>
    );
  }

  const isEmptyProject = assets.length === 0;

  return (
    <MotionConfig reducedMotion="user">
      <div className="flex h-full min-h-0 flex-col overflow-hidden">
      {/* section header — compact栏目条 */}
      <WorkbenchMasthead
        eyebrow="资 产 库"
        title="故事资产"
        tagline="角色、设定、关系、伏笔、世界规则与档案，都在这里统一查阅与管理。"
        aside={
          <span className="text-[12.5px] tabular-nums text-muted">
            {isEmptyProject ? "" : `${visibleAssets.length} / ${assets.length} 条`}
            {searching ? " · 搜索中…" : ""}
          </span>
        }
      />

      {actionError ? (
        <div className="shrink-0 border-b border-line bg-accent-wash px-6 py-2.5 text-[13px] text-accent">
          {actionError}
        </div>
      ) : null}

      {isEmptyProject ? (
        <AssetEmpty />
      ) : (
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <AssetCollectionsRail
            collections={collections}
            activeCollectionId={filters.collectionId}
            canManage={Boolean(csrfToken)}
            onSelect={(collectionId) => setFilters((f) => ({ ...f, collectionId }))}
            onCreate={handleCreateCollection}
          />

          {/* center: filter bar + list */}
          <div className="flex h-full min-w-0 flex-1 flex-col overflow-hidden">
            <AssetFilterBar
              value={filters}
              facets={facets}
              capabilities={capabilities}
              collections={collections}
              lifecycles={lifecycleFacet}
              onChange={setFilters}
            />
            <div className="min-h-0 flex-1 overflow-y-auto">
              {visibleAssets.length === 0 ? (
                <NoMatches onClear={() => setFilters(EMPTY_FILTERS)} />
              ) : (
                <AssetList assets={visibleAssets} selectedId={selectedId} onSelect={(id) => void openAsset(id)} />
              )}
            </div>
          </div>

          {/* right: inspector — inline column on lg+, overlay panel below lg */}
          <AnimatePresence mode="wait">
            {detail ? (
              <motion.aside
                key={detail.asset_id}
                initial={slideIn.initial}
                animate={slideIn.animate}
                exit={slideIn.exit}
                transition={{ duration: DUR.med, ease: EASE }}
                className="flex h-full w-[380px] shrink-0 flex-col overflow-hidden border-l border-line bg-panel max-lg:fixed max-lg:inset-y-0 max-lg:right-0 max-lg:z-40 max-lg:w-full max-lg:max-w-[420px] max-lg:shadow-panel"
              >
                <AssetInspector
                  asset={detail}
                  versions={versions}
                  collections={collections}
                  busy={busy}
                  onClose={closeInspector}
                  onAdopt={handleAdopt}
                  onRestore={handleRestore}
                  onTogglePin={handleTogglePin}
                  onToggleAlwaysOn={handleToggleAlwaysOn}
                  onSetRevealAfter={handleSetRevealAfter}
                  onToggleCollection={handleToggleCollection}
                />
              </motion.aside>
            ) : selectedId ? (
              <motion.aside
                key="inspector-loading"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: DUR.fast, ease: EASE }}
                className="flex h-full w-[380px] shrink-0 flex-col gap-4 border-l border-line bg-panel px-5 py-5 max-lg:fixed max-lg:inset-y-0 max-lg:right-0 max-lg:z-40 max-lg:w-full max-lg:max-w-[420px]"
              >
                <div className="h-6 w-2/3 animate-pulse rounded bg-line-soft" />
                <div className="h-4 w-full animate-pulse rounded bg-line-soft" />
                <div className="h-4 w-5/6 animate-pulse rounded bg-line-soft" />
                <div className="h-24 w-full animate-pulse rounded bg-line-soft" />
              </motion.aside>
            ) : null}
          </AnimatePresence>
        </div>
      )}
    </div>
    </MotionConfig>
  );
}

// ── States ──────────────────────────────────────────────────────────────────

function AssetEmpty() {
  const fadeUp = useFadeUp();
  return (
    <div className="flex flex-1 items-center justify-center px-8 py-16">
      <div className="flex max-w-md flex-col items-center text-center">
        <motion.span
          initial={fadeUp.initial}
          animate={fadeUp.animate}
          transition={{ duration: DUR.med, ease: EASE }}
          className="grid size-16 place-items-center rounded-card bg-accent-wash text-accent"
        >
          <BoxesIcon />
        </motion.span>
        <motion.h2
          initial={fadeUp.initial}
          animate={fadeUp.animate}
          transition={{ delay: 0.08, duration: DUR.med, ease: EASE }}
          className="mt-6 font-serif text-[22px] font-semibold text-ink"
        >
          这个项目还没有故事资产
        </motion.h2>
        <motion.p
          initial={fadeUp.initial}
          animate={fadeUp.animate}
          transition={{ delay: 0.16, duration: DUR.med, ease: EASE }}
          className="mt-2 text-[13.5px] leading-relaxed text-muted"
        >
          上传原文跑一次 Seed 分析，或在写作台里边写边蒸馏，角色、设定和伏笔会自动汇聚到这里。
        </motion.p>
      </div>
    </div>
  );
}

function NoMatches({ onClear }: { onClear: () => void }) {
  const fadeUp = useFadeUp();
  return (
    <motion.div
      initial={fadeUp.initial}
      animate={fadeUp.animate}
      transition={{ duration: DUR.med, ease: EASE }}
      className="flex h-full flex-col items-center justify-center px-8 py-16 text-center"
    >
      <p className="font-serif text-[17px] font-medium text-ink">没有符合条件的资产</p>
      <p className="mt-1.5 max-w-[300px] text-[13px] text-muted">换个关键词，或者清空筛选再看看。</p>
      <button
        type="button"
        onClick={onClear}
        className="mt-5 rounded-[10px] border border-line bg-panel px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent"
      >
        清空筛选
      </button>
    </motion.div>
  );
}

function NoSelection({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-8 text-center">
      <h2 className="font-serif text-[22px] font-semibold text-ink">请先回到书架进入项目</h2>
      <p className="mt-2 max-w-[380px] text-[13.5px] text-muted">
        资产库需要知道你正在整理哪部作品。回到书架，挑一部作品再进来。
      </p>
      <button
        type="button"
        onClick={onBack}
        className="mt-6 rounded-[10px] border border-line bg-panel px-5 py-2.5 text-[13.5px] font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent"
      >
        返回书架
      </button>
    </div>
  );
}

function AssetSkeleton() {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: DUR.med, ease: EASE }}
      className="flex h-full min-h-0 flex-col overflow-hidden"
    >
      <div className="border-b border-line-soft px-8 pb-5 pt-7">
        <div className="h-3 w-16 animate-pulse rounded bg-line-soft" />
        <div className="mt-3 h-7 w-40 animate-pulse rounded bg-line-soft" />
        <div className="mt-2 h-4 w-72 animate-pulse rounded bg-line-soft" />
      </div>
      <div className="space-y-3 px-6 py-6">
        {Array.from({ length: 6 }).map((_, index) => (
          <div key={index} className="flex items-start gap-3">
            <div className="size-9 shrink-0 animate-pulse rounded-[9px] bg-line-soft" />
            <div className="flex-1 space-y-2">
              <div className="h-4 w-1/3 animate-pulse rounded bg-line-soft" />
              <div className="h-3 w-2/3 animate-pulse rounded bg-line-soft" />
            </div>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

function BoxesIcon() {
  // Inline to keep the empty state self-contained; mirrors the nav Boxes glyph.
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="size-7" aria-hidden>
      <path d="M2.97 12.92A2 2 0 0 0 2 14.63v3.24a2 2 0 0 0 .97 1.71l3 1.8a2 2 0 0 0 2.06 0L12 19v-5.5l-5-3-4.03 2.42Z" />
      <path d="m7 16.5-4.74-2.85" />
      <path d="m7 16.5 5-3" />
      <path d="M7 16.5v5.17" />
      <path d="M12 13.5V19l3.97 2.38a2 2 0 0 0 2.06 0l3-1.8a2 2 0 0 0 .97-1.71v-3.24a2 2 0 0 0-.97-1.71L17 10.5l-5 3Z" />
      <path d="m17 16.5-5-3" />
      <path d="m17 16.5 4.74-2.85" />
      <path d="M17 16.5v5.17" />
      <path d="M7.97 4.42A2 2 0 0 0 7 6.13v4.37l5 3 5-3V6.13a2 2 0 0 0-.97-1.71l-3-1.8a2 2 0 0 0-2.06 0l-3 1.8Z" />
      <path d="M12 8 7.26 5.15" />
      <path d="m12 8 4.74-2.85" />
      <path d="M12 13.5V8" />
    </svg>
  );
}
