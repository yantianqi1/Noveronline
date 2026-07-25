"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "motion/react";
import { Loader2, Maximize2, Network, RefreshCw, Search, X } from "lucide-react";

import {
  fetchGraphSnapshot,
  fetchGraphView,
  fetchGraphNode,
  fetchNodeEvidence,
  startGraphBuild,
  GraphError,
  readGraphSelection,
} from "@/lib/api/graph-client";
import { fetchCsrfToken } from "@/lib/api/session";
import type {
  GraphEdge,
  GraphEvidence,
  GraphNode,
  GraphNodeDetail,
  GraphSnapshot,
} from "@/lib/api/graph-types";

import { GraphCanvas } from "./graph-canvas";
import { GraphFilterRail, type LayerSpec } from "./graph-filter-rail";
import { GraphInspector } from "./graph-inspector";
import { isConceptLayerKey, layerKeyOf, resolveConcept, worldGroupLabel } from "./graph-concept";
import { layerVisual, nodeVisual } from "./graph-visual";

/**
 * The Story Graph (故事图谱) workbench — a living constellation of the story
 * world's characters and their relations, on warm manuscript paper.
 *
 * Loads the current snapshot + the full ranked viewport through the BFF and
 * renders it as a fluid constellation. Honest provenance throughout: no
 * snapshot → a clear empty state; snapshot present but empty viewport → a
 * quiet note; never a fabricated node.
 */

const VIEW_LIMIT = 320;
const BUILD_POLL_MS = 4000;
const BUILD_TIMEOUT_MS = 10 * 60 * 1000;

type LoadState =
  | { status: "loading" }
  | { status: "no-selection" }
  | { status: "error"; message: string }
  | { status: "ready" };

export function GraphWorkspace({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [snapshot, setSnapshot] = useState<GraphSnapshot | null>(null);
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);

  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [worldScope, setWorldScope] = useState<string>("all");
  const [query, setQuery] = useState("");
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<GraphNodeDetail | null>(null);
  const [evidence, setEvidence] = useState<GraphEvidence | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [focusSignal, setFocusSignal] = useState<{ nodeId: string; nonce: number } | null>(null);
  const [searchActive, setSearchActive] = useState(false);

  const selectionRef = useRef<{ tenant_id: string; project_id: string } | null>(null);
  const mountedRef = useRef(true);

  // Build lifecycle: starting (POST in flight) → building (snapshot reports
  // building) → terminal (ready/failed), or error when the start call fails.
  const [buildPhase, setBuildPhase] = useState<"idle" | "starting">("idle");
  const [buildError, setBuildError] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  // Identity of the build we kicked off, so polling never mistakes a
  // pre-existing ready snapshot (from an earlier, successful build) for ours.
  const buildWatchRef = useRef<{ startedAt: number; baselineVersion: number } | null>(null);

  // ── Load snapshot + viewport ──────────────────────────────────────────────
  // Reusable so a finished build can re-pull the fresh snapshot + viewport.
  const load = useCallback(async () => {
    const sel = selectionRef.current;
    if (!sel) return;
    try {
      const snap = await fetchGraphSnapshot(sel.project_id, sel.tenant_id);
      if (!mountedRef.current) return;
      setSnapshot(snap);
      const view = await fetchGraphView(sel.project_id, sel.tenant_id, {
        viewId: "world",
        limit: VIEW_LIMIT,
        includeEdges: true,
      });
      if (!mountedRef.current) return;
      setNodes(view.nodes ?? []);
      setEdges(view.edges ?? []);
      setState({ status: "ready" });
    } catch (error) {
      if (!mountedRef.current) return;
      if (error instanceof GraphError && error.status === 401) {
        router.replace("/login");
        return;
      }
      if (error instanceof GraphError && error.code === "NOT_FOUND") {
        setSnapshot(null);
        setNodes([]);
        setEdges([]);
        setState({ status: "ready" });
        return;
      }
      setState({
        status: "error",
        message: error instanceof Error ? error.message : "图谱暂时读不出来，请重试。",
      });
    }
  }, [router]);

  useEffect(() => {
    mountedRef.current = true;
    const sel = readGraphSelection(projectId);
    if (!sel) {
      setState({ status: "no-selection" });
      return;
    }
    selectionRef.current = sel;
    void load();
    return () => {
      mountedRef.current = false;
    };
  }, [projectId, load]);

  // ── Build + poll ──────────────────────────────────────────────────────────

  const handleBuild = useCallback(async () => {
    const sel = selectionRef.current;
    if (!sel || buildPhase === "starting") return;
    setBuildPhase("starting");
    setBuildError(null);
    try {
      // Capture the snapshot version we're starting from, so the poll loop can
      // tell "a new snapshot landed" apart from "the old ready one is still there".
      let baselineVersion = 0;
      try {
        const before = await fetchGraphSnapshot(sel.project_id, sel.tenant_id);
        baselineVersion = before.version ?? 0;
      } catch {
        baselineVersion = 0; // no snapshot yet — that absence is the baseline
      }
      const token = await fetchCsrfToken();
      await startGraphBuild(sel.project_id, sel.tenant_id, token);
      if (!mountedRef.current) return;
      // The snapshot row may not report `building` for a beat; start polling
      // immediately so the UI shows progress even before the first flip.
      buildWatchRef.current = { startedAt: Date.now(), baselineVersion };
      setBuilding(true);
    } catch (error) {
      if (!mountedRef.current) return;
      if (error instanceof GraphError && error.status === 401) {
        router.replace("/login");
        return;
      }
      setBuildError(
        error instanceof Error ? error.message : "图谱构建没能启动，请稍后重试。",
      );
    } finally {
      if (mountedRef.current) setBuildPhase("idle");
    }
  }, [buildPhase, router]);

  // While a build is in flight, poll the snapshot until our build reaches a
  // terminal state, then reload the viewport so the new constellation renders.
  useEffect(() => {
    if (!building) return;
    const sel = selectionRef.current;
    if (!sel) return;
    let cancelled = false;
    const tick = async () => {
      const watch = buildWatchRef.current;
      if (!watch) {
        setBuilding(false);
        return;
      }
      if (Date.now() - watch.startedAt > BUILD_TIMEOUT_MS) {
        if (!cancelled) {
          setBuilding(false);
          buildWatchRef.current = null;
          setBuildError("构建比预期久，还没出结果。可以稍后再来看看，或重新构建一次。");
        }
        return;
      }
      let snap: GraphSnapshot;
      try {
        snap = await fetchGraphSnapshot(sel.project_id, sel.tenant_id);
      } catch (error) {
        // No snapshot row yet — the build hasn't written one; keep polling.
        if (error instanceof GraphError && error.code === "NOT_FOUND") return;
        // Any other transient read hiccup mid-build — keep polling.
        return;
      }
      if (cancelled) return;
      setSnapshot(snap);

      const isNewSnapshot = snap.version > watch.baselineVersion;
      if (snap.status === "building" || snap.status === "queued") return;
      if (snap.status === "ready" && !isNewSnapshot) return; // stale pre-existing graph
      if (snap.status === "failed" && !isNewSnapshot) return; // stale failure marker

      // Our build reached a terminal state.
      setBuilding(false);
      buildWatchRef.current = null;
      if (snap.status === "ready") {
        // Let the layer priming re-run so the fresh constellation opens on
        // the 人物关系图 with background concepts hidden.
        primedRef.current = false;
        await load();
      } else {
        setBuildError("这次图谱构建没有成功。已读出的内容不会丢，可重新构建。");
      }
    };
    const timer = window.setInterval(() => void tick(), BUILD_POLL_MS);
    void tick();
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [building, load]);

  // ── Derived ───────────────────────────────────────────────────────────────

  // Concept refinement memoized per node — display title + subtype + world.
  const conceptInfo = useMemo(() => {
    const map = new Map<string, NonNullable<ReturnType<typeof resolveConcept>>>();
    for (const node of nodes) {
      const info = resolveConcept(node);
      if (info) map.set(node.node_id, info);
    }
    return map;
  }, [nodes]);

  // Filter layers: entity node_types plus concept subtypes, each with a count.
  const layers = useMemo<LayerSpec[]>(() => {
    const counts = new Map<string, number>();
    for (const node of nodes) {
      const key = layerKeyOf(node);
      counts.set(key, (counts.get(key) ?? 0) + 1);
    }
    const conceptLabel: Record<string, string> = {
      "concept:event": "分析·事件",
      "concept:world": "世界观·设定",
      "concept:concept": "概念",
    };
    const entityOrder = ["character", "organization", "faction", "location", "artifact", "plot_thread", "plot_event", "manuscript_scene"];
    const conceptOrder = ["concept:event", "concept:world", "concept:concept"];
    const rank = (key: string) => {
      const ei = entityOrder.indexOf(key);
      if (ei >= 0) return ei;
      const ci = conceptOrder.indexOf(key);
      if (ci >= 0) return 100 + ci;
      return 200;
    };
    return [...counts.keys()]
      .sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
      .map((key) => ({
        key,
        label: isConceptLayerKey(key) ? (conceptLabel[key] ?? "概念") : nodeVisual(key).label,
        count: counts.get(key) ?? 0,
        isConcept: isConceptLayerKey(key),
      }));
  }, [nodes]);

  const conceptLayerKeys = useMemo(() => layers.filter((l) => l.isConcept).map((l) => l.key), [layers]);
  const hasEvents = useMemo(() => layers.some((l) => l.key === "concept:event"), [layers]);

  // Background concepts start hidden so the canvas opens on the人物关系图.
  const primedRef = useRef(false);
  useEffect(() => {
    if (primedRef.current || nodes.length === 0) return;
    primedRef.current = true;
    setHidden(new Set(conceptLayerKeys));
  }, [nodes, conceptLayerKeys]);

  const nodeIndex = useMemo(() => {
    const map = new Map<string, GraphNode>();
    for (const node of nodes) map.set(node.node_id, node);
    return map;
  }, [nodes]);

  const trimmedQuery = query.trim().toLowerCase();

  const visibleNodes = useMemo(
    () =>
      nodes.filter((node) => {
        const key = layerKeyOf(node);
        if (hidden.has(key)) return false;
        // 世界 scope narrows the timeline-event band only.
        if (key === "concept:event" && worldScope !== "all") {
          const info = conceptInfo.get(node.node_id);
          if (info && info.world !== worldGroupLabel(worldScope)) return false;
        }
        return true;
      }),
    [nodes, hidden, worldScope, conceptInfo],
  );

  const visibleNodeIds = useMemo(() => new Set(visibleNodes.map((n) => n.node_id)), [visibleNodes]);

  const visibleEdges = useMemo(
    () => edges.filter((edge) => visibleNodeIds.has(edge.source_node_id) && visibleNodeIds.has(edge.target_node_id)),
    [edges, visibleNodeIds],
  );

  // Band assignment: visible concepts file into shelves by world/subtype.
  const bands = useMemo(() => {
    const map = new Map<string, { band: string; order: number }>();
    for (const node of visibleNodes) {
      const info = conceptInfo.get(node.node_id);
      if (!info) continue;
      const payload = (node.attributes?.payload ?? {}) as Record<string, unknown>;
      const order = typeof payload.event_order === "number" ? payload.event_order : Number.MAX_SAFE_INTEGER;
      map.set(node.node_id, {
        band: info.subtype === "event" ? `event:${info.world}` : info.subtype,
        order,
      });
    }
    return map;
  }, [visibleNodes, conceptInfo]);

  const searchMatches = useMemo(() => {
    if (!trimmedQuery) return [] as GraphNode[];
    return nodes
      .filter((node) => node.title.toLowerCase().includes(trimmedQuery))
      .sort((a, b) => (b.importance || 0) - (a.importance || 0))
      .slice(0, 8);
  }, [nodes, trimmedQuery]);

  const selectedNeighbours = useMemo(() => {
    if (!selectedId) return [] as Array<{ node: GraphNode; edge: GraphEdge }>;
    const out: Array<{ node: GraphNode; edge: GraphEdge }> = [];
    for (const edge of edges) {
      let otherId: string | null = null;
      if (edge.source_node_id === selectedId) otherId = edge.target_node_id;
      else if (edge.target_node_id === selectedId) otherId = edge.source_node_id;
      if (!otherId) continue;
      const other = nodeIndex.get(otherId);
      if (other) out.push({ node: other, edge });
    }
    return out.sort((a, b) => (b.edge.weight || 0) - (a.edge.weight || 0));
  }, [selectedId, edges, nodeIndex]);

  // ── Handlers ──────────────────────────────────────────────────────────────

  const loadDetail = useCallback(async (nodeId: string) => {
    const sel = selectionRef.current;
    if (!sel) return;
    setDetailLoading(true);
    setDetail(null);
    setEvidence(null);
    try {
      const [nodeDetail, nodeEvidence] = await Promise.all([
        fetchGraphNode(sel.project_id, sel.tenant_id, nodeId),
        fetchNodeEvidence(sel.project_id, sel.tenant_id, nodeId).catch(() => null),
      ]);
      setDetail(nodeDetail);
      setEvidence(nodeEvidence);
    } catch {
      setDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const handleSelect = useCallback(
    (nodeId: string | null) => {
      setSelectedId(nodeId);
      setDetail(null);
      setEvidence(null);
      if (nodeId) {
        setFocusSignal({ nodeId, nonce: Date.now() });
        void loadDetail(nodeId);
      }
    },
    [loadDetail],
  );

  const handleToggleLayer = useCallback((layerKey: string) => {
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(layerKey)) next.delete(layerKey);
      else next.add(layerKey);
      return next;
    });
  }, []);

  const handleShowAll = useCallback(() => setHidden(new Set()), []);

  const handleSearchPick = useCallback(
    (nodeId: string) => {
      setQuery("");
      setSearchActive(false);
      const node = nodeIndex.get(nodeId);
      if (node) {
        const key = layerKeyOf(node);
        if (hidden.has(key)) {
          setHidden((prev) => {
            const next = new Set(prev);
            next.delete(key);
            return next;
          });
        }
      }
      handleSelect(nodeId);
    },
    [nodeIndex, hidden, handleSelect],
  );

  const handleReset = useCallback(() => {
    setSelectedId(null);
    setDetail(null);
    setEvidence(null);
    setFocusSignal(null);
  }, []);

  // ── Render ────────────────────────────────────────────────────────────────

  if (state.status === "loading") return <GraphLoading />;
  if (state.status === "no-selection") return <NoSelection onBack={() => router.push("/workspace")} />;
  if (state.status === "error") {
    return (
      <div className="flex min-h-[70vh] flex-col items-center justify-center bg-paper px-8 text-center">
        <h2 className="font-serif text-[22px] font-semibold text-ink">图谱暂时打不开</h2>
        <p className="mt-2 max-w-[380px] text-[13.5px] text-muted">{state.message}</p>
      </div>
    );
  }

  if (!snapshot)
    return (
      <GraphEmpty
        building={building || buildPhase === "starting"}
        error={buildError}
        onBuild={() => void handleBuild()}
      />
    );

  const selectedNode = selectedId ? nodeIndex.get(selectedId) ?? null : null;

  return (
    <div className="relative flex h-full min-h-0 flex-col overflow-hidden bg-paper">
      {/* Header — compact栏目条 */}
      <div className="relative z-10 flex h-[52px] shrink-0 items-center gap-3 border-b border-line-soft bg-paper/80 px-5 backdrop-blur-sm">
        <span className="flex shrink-0 items-center gap-1.5 rounded-[6px] border border-accent/30 bg-accent-wash px-2 py-1 text-[10.5px] font-medium tracking-[0.22em] text-accent">
          <Network className="size-3" aria-hidden />
          角 色 图 谱
        </span>
        <h1 className="shrink-0 font-serif text-[18px] font-semibold leading-none text-ink">人物关系图谱</h1>
        <span aria-hidden className="h-4 w-px shrink-0 bg-line" />
        <p className="min-w-0 flex-1 truncate text-[12.5px] leading-none text-muted">
          {building
            ? "正在构建新的图谱…"
            : `${snapshot.node_count} 个存在 · ${snapshot.edge_count} 条关系 · 快照 v${snapshot.version}`}
        </p>

        {/* Rebuild */}
        <button
          type="button"
          onClick={() => void handleBuild()}
          disabled={building || buildPhase === "starting"}
          className="flex shrink-0 items-center gap-1.5 rounded-[9px] border border-line bg-panel px-3 py-1.5 text-[12.5px] font-medium text-ink shadow-[0_1px_3px_rgba(23,26,27,0.05)] transition-colors hover:border-accent/50 hover:text-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {building || buildPhase === "starting" ? (
            <Loader2 className="size-3.5 animate-spin" aria-hidden />
          ) : (
            <RefreshCw className="size-3.5" aria-hidden />
          )}
          {building ? "构建中…" : "重新构建"}
        </button>

        {/* Search */}
        <div className="relative w-[280px] shrink-0">
          <div className="flex items-center gap-2 rounded-[10px] border border-line bg-panel px-3 py-1.5 shadow-[0_1px_3px_rgba(23,26,27,0.05)] transition-colors focus-within:border-accent/50">
            <Search className="size-3.5 shrink-0 text-muted" aria-hidden />
            <input
              value={query}
              onChange={(event) => {
                setQuery(event.target.value);
                setSearchActive(true);
              }}
              onFocus={() => setSearchActive(true)}
              placeholder="搜索角色、组织、地点…"
              className="min-w-0 flex-1 bg-transparent text-[13px] text-ink outline-none placeholder:text-muted/60"
            />
            {query ? (
              <button
                type="button"
                onClick={() => setQuery("")}
                aria-label="清空"
                className="grid size-5 place-items-center rounded-full text-muted hover:text-ink"
              >
                <X className="size-3.5" aria-hidden />
              </button>
            ) : null}
          </div>

          <AnimatePresence>
            {searchActive && trimmedQuery && (
              <motion.ul
                initial={{ opacity: 0, y: -6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -6 }}
                transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                className="absolute inset-x-0 top-full z-20 mt-2 overflow-hidden rounded-[12px] border border-line bg-panel shadow-panel"
              >
                  {searchMatches.length > 0 ? (
                    searchMatches.map((node) => {
                      const concept = conceptInfo.get(node.node_id);
                      const visual = concept ? layerVisual(`concept:${concept.subtype}`) : nodeVisual(node.node_type);
                      return (
                        <li key={node.node_id}>
                          <button
                            type="button"
                            onClick={() => handleSearchPick(node.node_id)}
                            className="flex w-full items-center gap-2.5 px-3.5 py-2.5 text-left transition-colors hover:bg-accent-wash"
                          >
                            <span className="size-2 shrink-0 rounded-full" style={{ backgroundColor: visual.color }} />
                            <span className="min-w-0 flex-1 truncate text-[13px] text-ink">
                              {concept ? concept.displayTitle : node.title}
                            </span>
                            <span className="shrink-0 text-[11px] text-muted">{visual.label}</span>
                          </button>
                        </li>
                      );
                    })
                  ) : (
                    <li className="px-3.5 py-3 text-[12.5px] text-muted">没有匹配「{query}」的星点。</li>
                  )}
              </motion.ul>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* Body */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <GraphFilterRail
          snapshot={snapshot}
          layers={layers}
          hidden={hidden}
          onToggle={handleToggleLayer}
          onShowAll={handleShowAll}
          worldScope={worldScope}
          onWorldScope={setWorldScope}
          hasEvents={hasEvents}
        />

        {/* Canvas */}
        <div className="relative min-w-0 flex-1">
          {visibleNodes.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center px-8 text-center">
              <p className="font-serif text-[18px] text-ink">这片星野暂时没有星星</p>
              <p className="mt-1.5 max-w-[320px] text-[13px] text-muted">
                {hidden.size > 0 ? "所有图层都被藏起来了，点「全部显示」再把它们点亮。" : "图谱已就绪，但这个视口里还没有节点。"}
              </p>
              {hidden.size > 0 ? (
                <button
                  type="button"
                  onClick={handleShowAll}
                  className="mt-5 rounded-[10px] border border-line bg-panel px-4 py-2 text-[13px] font-medium text-ink transition-colors hover:border-accent/50 hover:text-accent"
                >
                  全部显示
                </button>
              ) : null}
            </div>
          ) : (
            <GraphCanvas
              nodes={visibleNodes}
              edges={visibleEdges}
              bands={bands}
              selectedId={selectedId}
              hoveredId={hoveredId}
              focusSignal={focusSignal}
              onHover={setHoveredId}
              onSelect={handleSelect}
            />
          )}

          {/* Reset */}
          {selectedId ? (
            <motion.button
              type="button"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              onClick={handleReset}
              className="absolute bottom-5 left-1/2 z-10 flex -translate-x-1/2 items-center gap-2 rounded-full border border-line bg-panel/90 px-4 py-2 text-[12.5px] font-medium text-ink shadow-panel backdrop-blur-sm transition-colors hover:border-accent/50 hover:text-accent"
            >
              <Maximize2 className="size-3.5" aria-hidden />
              回到全景
            </motion.button>
          ) : null}

          {/* Hint */}
          <div className="pointer-events-none absolute bottom-5 right-5 z-10 text-[11px] tracking-wide text-muted/60">
            拖拽平移 · 滚轮缩放 · 点击星点查看档案
          </div>
        </div>

        {/* Inspector */}
        <AnimatePresence mode="wait">
          {selectedNode ? (
            <GraphInspector
              key={selectedNode.node_id}
              node={selectedNode}
              detail={detail}
              evidence={evidence}
              neighbours={selectedNeighbours}
              loading={detailLoading}
              onClose={() => setSelectedId(null)}
              onFocusNode={handleSelect}
            />
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  );
}

// ── States ──────────────────────────────────────────────────────────────────

function GraphLoading() {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-paper">
      <div className="border-b border-line-soft px-8 pb-4 pt-6">
        <div className="h-3 w-20 animate-pulse rounded bg-paper-deep" />
        <div className="mt-3 h-7 w-52 animate-pulse rounded bg-paper-deep" />
        <div className="mt-2 h-4 w-64 animate-pulse rounded bg-paper-deep" />
      </div>
      <div className="flex flex-1 items-center justify-center">
        <div className="flex flex-col items-center gap-4 text-muted">
          <Loader2 className="size-7 animate-spin text-gold" aria-hidden />
          <p className="text-[13px]">正在点亮星图…</p>
        </div>
      </div>
    </div>
  );
}

function GraphEmpty({
  building,
  error,
  onBuild,
}: {
  building: boolean;
  error: string | null;
  onBuild: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-paper">
      <div className="border-b border-line-soft px-8 pb-4 pt-6">
        <p className="mb-1 flex items-center gap-2 text-[11px] font-medium tracking-[0.28em] text-accent">
          <Network className="size-3.5" aria-hidden />
          角 色 图 谱
        </p>
        <h1 className="font-serif text-[26px] font-semibold leading-tight text-ink">人物关系图谱</h1>
      </div>
      <div className="flex flex-1 items-center justify-center px-8 py-16">
        <div className="flex max-w-md flex-col items-center text-center">
          <motion.span
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="grid size-16 place-items-center rounded-[16px] bg-accent-wash text-accent"
          >
            <Network className="size-7" aria-hidden />
          </motion.span>
          <motion.h2
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="mt-6 font-serif text-[22px] font-semibold text-ink"
          >
            {building ? "正在把角色连成一片星图" : "这个故事的图谱还没亮起"}
          </motion.h2>
          <motion.p
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.16, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="mt-2 text-[13.5px] leading-relaxed text-muted"
          >
            {building
              ? "图谱构建需要一点时间。角色与他们的羁绊连好之后，会自动亮在这里。"
              : "总览里的 Seed 分析已经把原文读进了故事记忆。点一下构建，角色与他们的羁绊就会在这里连成一片会流动的图谱。"}
          </motion.p>
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.24, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
            className="mt-7 flex flex-col items-center gap-3"
          >
            <button
              type="button"
              onClick={onBuild}
              disabled={building}
              className="flex items-center gap-2 rounded-[10px] bg-accent px-5 py-2.5 text-[13.5px] font-medium text-white shadow-[0_6px_16px_rgba(23,26,27,0.12)] transition-all hover:brightness-105 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {building ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Network className="size-4" aria-hidden />}
              {building ? "构建中…" : "构建故事图谱"}
            </button>
            {error ? <p className="text-[12.5px] text-[#b4542a]">{error}</p> : null}
          </motion.div>
        </div>
      </div>
    </div>
  );
}

function NoSelection({ onBack }: { onBack: () => void }) {
  return (
    <div className="flex min-h-[70vh] flex-col items-center justify-center bg-paper px-8 text-center">
      <h2 className="font-serif text-[22px] font-semibold text-ink">请先回到书架进入项目</h2>
      <p className="mt-2 max-w-[380px] text-[13.5px] text-muted">
        图谱需要知道你正在看哪部作品的世界。回到书架，挑一部作品再进来。
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
