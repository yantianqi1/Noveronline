"use client";

import { Minus, Network, Plus, RotateCcw, Search } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";

import { type Locale, tx } from "../lib/locale";
import type {
  AssetListSummary,
  StoryGraphClustersSummary,
  StoryGraphCurrentSummary,
  StoryGraphEvidenceSummary,
  StoryGraphLayoutSummary,
  StoryGraphViewSummary,
  WorkflowRunEventsSummary,
  WorkflowRunSummary,
} from "../lib/api";
import { Bi, FailureText, StatusValue } from "./bilingual-text";
import { InspectorPanel } from "./inspector-panel";
import { WorkspaceHeader } from "./workspace-header";

export { storyGraphBondStatus, storyGraphBuildStatus } from "./story-graph-status";

type StoryGraphShellProps = {
  locale: Locale;
  tenantSlug: string;
  projectId: string;
  buildStatus: string;
  buildCode: string;
  buildMessage: string;
  bondStatus: string;
  bondCode: string;
  bondMessage: string;
  adoptionStatus: string;
  adoptionCode: string;
  adoptionMessage: string;
  adoptionTargetId: string;
  selectedRunId: string;
  selectedBuildRunId: string;
  selectedBondRunId: string;
  current: StoryGraphCurrentSummary;
  view: StoryGraphViewSummary;
  evidence: StoryGraphEvidenceSummary;
  layout: StoryGraphLayoutSummary;
  clusters: StoryGraphClustersSummary;
  graphCandidates: AssetListSummary;
  workflowRun: WorkflowRunSummary | null;
  workflowEvents: WorkflowRunEventsSummary | null;
  buildAction: (formData: FormData) => Promise<void>;
  bondAction: (formData: FormData) => Promise<void>;
  adoptStoryGraphCandidateAction: (formData: FormData) => Promise<void>;
};

export function StoryGraphShell({
  locale,
  buildStatus,
  buildCode,
  buildMessage,
  bondStatus,
  bondCode,
  bondMessage,
  adoptionStatus,
  adoptionCode,
  adoptionMessage,
  selectedRunId,
  current,
  view,
  evidence,
  layout,
  clusters,
  graphCandidates,
  workflowRun,
  workflowEvents,
  buildAction,
  bondAction,
  adoptStoryGraphCandidateAction,
}: StoryGraphShellProps) {
  const [workspaceMode, setWorkspaceMode] = useState<"explore" | "build" | "curate" | "compose">("explore");
  const initialNodeId = view.ok ? view.nodes[0]?.node_id ?? "" : "";
  const [selectedNodeId, setSelectedNodeId] = useState(initialNodeId);
  const selectedNode = view.ok
    ? view.nodes.find((node) => node.node_id === selectedNodeId) ?? view.nodes[0] ?? null
    : null;

  return (
    <div className="overview-root story-graph-root">
      <WorkspaceHeader
        className="story-graph-header"
        eyebrow={<Bi zh="故事图谱" en="Story Graph" />}
        icon={<Network size={22} strokeWidth={1.8} />}
        meta={(
          <>
            <span className="status-pill"><Bi zh="图谱：" en="Graph: " />{current.ok ? <StatusValue value={current.status} /> : <Bi zh="暂不可用" en="unavailable" />}</span>
            <span className="status-pill"><Bi zh="构建：" en="Build: " />{buildStatus || tx(locale, "空闲", "idle")}</span>
            <span className="status-pill"><Bi zh="关系生成：" en="Bond: " />{bondStatus || tx(locale, "空闲", "idle")}</span>
          </>
        )}
        title={<Bi zh="故事图谱" en="Story Graph" />}
        actions={(
          <div className="workspace-mode-switcher" role="tablist" aria-label={tx(locale, "图谱工作模式", "Graph workspace mode")}>
            {([
              ["explore", tx(locale, "探索", "Explore")],
              ["build", tx(locale, "构建", "Build")],
              ["curate", tx(locale, "整理", "Curate")],
              ["compose", tx(locale, "创作", "Compose")],
            ] as const).map(([mode, label]) => (
              <button
                aria-selected={workspaceMode === mode}
                key={mode}
                onClick={() => setWorkspaceMode(mode)}
                role="tab"
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
        )}
      />

      {workspaceMode === "explore" ? (
      <div className="workbench-grid story-graph-explore-grid">
        <main>
          <section className="panel story-graph-canvas-panel" aria-labelledby="graph-canvas-heading">
            <p className="eyebrow"><Bi zh="探索" en="Explore" /></p>
            <h2 id="graph-canvas-heading"><Bi zh="图谱画布" en="Graph canvas" /></h2>
            <GraphCanvas
              clusters={clusters}
              current={current}
              layout={layout}
              locale={locale}
              onSelectNodeId={setSelectedNodeId}
              selectedNodeId={selectedNode?.node_id ?? selectedNodeId}
              view={view}
            />
          </section>
          <details className="story-graph-snapshot-disclosure">
            <summary>
              <span><Bi zh="快照摘要" en="Snapshot summary" /></span>
              <small>{current.ok ? <StatusValue value={current.status} /> : <Bi zh="暂不可用" en="unavailable" />}</small>
            </summary>
            <div className="story-graph-snapshot-content">
              <section
                className={`panel story-graph-snapshot-panel ${current.ok ? "" : "error-box"}`}
                aria-labelledby="graph-current-heading"
              >
                <p className="eyebrow"><Bi zh="当前快照" en="Current Snapshot" /></p>
                <h2 id="graph-current-heading"><Bi zh="图谱快照" en="Graph snapshot" /></h2>
                <CurrentSnapshot current={current} locale={locale} />
              </section>
            </div>
          </details>
        </main>

        <InspectorPanel
          className="story-graph-explore-rail"
          title={<Bi zh="图谱检视" en="Graph inspector" />}
          status={selectedNode ? (selectedNode.title || <Bi zh="已选节点" en="Selected node" />) : <Bi zh="选择节点查看" en="Select a node" />}
        >
          <section className="panel story-graph-ink-section" aria-labelledby="graph-selected-heading">
            <p className="eyebrow"><Bi zh="选中" en="Selected" /></p>
            <h2 id="graph-selected-heading"><Bi zh="当前节点" en="Current node" /></h2>
            {selectedNode ? (
              <dl>
                <dt><Bi zh="名称" en="Name" /></dt>
                <dd>{selectedNode.title || <Bi zh="未命名节点" en="Untitled node" />}</dd>
                <dt><Bi zh="类型" en="Type" /></dt>
                <dd>{publicGraphLabel(selectedNode.node_type, selectedNode.node_type)}</dd>
                <dt><Bi zh="摘要" en="Summary" /></dt>
                <dd>{selectedNode.summary || <Bi zh="暂无公开摘要。" en="No public summary." />}</dd>
              </dl>
            ) : (
              <p className="form-hint"><Bi zh="在画布上选择一个节点。" en="Select a node on the canvas." /></p>
            )}
          </section>

          <section className={`panel story-graph-ink-section ${evidence.ok ? "" : "error-box"}`} aria-labelledby="graph-evidence-heading">
            <p className="eyebrow"><Bi zh="证据" en="Evidence" /></p>
            <h2 id="graph-evidence-heading"><Bi zh="公开证据" en="Public evidence" /></h2>
            <GraphEvidence evidence={evidence} selectedNodeId={selectedNode?.node_id} />
          </section>

          <details className="story-graph-stats-disclosure">
            <summary>
              <span><Bi zh="布局与聚类统计" en="Layout and cluster stats" /></span>
              <small><Bi zh="次要信息" en="Secondary" /></small>
            </summary>
            <div className="story-graph-stats-content">
              <section className={`panel story-graph-ink-section ${layout.ok ? "" : "error-box"}`} aria-labelledby="graph-layout-heading">
                <p className="eyebrow"><Bi zh="布局" en="Layout" /></p>
                <h2 id="graph-layout-heading"><Bi zh="世界布局" en="World layout" /></h2>
                <GraphLayoutSummary layout={layout} locale={locale} />
              </section>
              <section className={`panel story-graph-ink-section ${clusters.ok ? "" : "error-box"}`} aria-labelledby="graph-clusters-heading">
                <p className="eyebrow"><Bi zh="聚类" en="Clusters" /></p>
                <h2 id="graph-clusters-heading"><Bi zh="图谱聚类" en="Graph clusters" /></h2>
                <GraphClusters clusters={clusters} />
              </section>
              <section className={`panel story-graph-ink-section ${view.ok ? "" : "error-box"}`} aria-labelledby="graph-view-heading">
                <p className="eyebrow"><Bi zh="视图" en="Viewport" /></p>
                <h2 id="graph-view-heading"><Bi zh="世界视图" en="World view" /></h2>
                <GraphViewport locale={locale} view={view} />
              </section>
            </div>
          </details>
        </InspectorPanel>
      </div>
      ) : null}

      {workspaceMode === "build" ? (
      <div className="workbench-grid story-graph-compose-grid" data-mode="build">
        <main>
          <section className="panel story-graph-paper-panel" aria-labelledby="graph-build-heading" data-mode-panel="build">
            <p className="eyebrow"><Bi zh="构建模式" en="Build Mode" /></p>
            <h2 id="graph-build-heading"><Bi zh="开始构建" en="Start build" /></h2>
            <StatusLine status={buildStatus} code={buildCode} message={buildMessage} />
            <form action={buildAction} className="binding-form story-graph-build-form">
              <div className="story-graph-field">
                <label htmlFor="graph-build-mode"><Bi zh="模式" en="Mode" /></label>
                <select id="graph-build-mode" name="mode" defaultValue="full">
                  <option value="full">{tx(locale, "完整构建", "Full")}</option>
                  <option value="incremental">{tx(locale, "增量构建", "Incremental")}</option>
                </select>
              </div>
              <div className="story-graph-field">
                <label htmlFor="graph-build-source"><Bi zh="来源" en="Source" /></label>
                <select id="graph-build-source" name="source" defaultValue="seed_canon">
                  <option value="seed_canon">{tx(locale, "种子正典", "Seed canon")}</option>
                  <option value="assets">{tx(locale, "资产", "Assets")}</option>
                </select>
              </div>
              <button type="submit"><Bi zh="构建" en="Build" /></button>
            </form>
          </section>
        </main>
        <aside className="story-graph-ops-rail" aria-label={tx(locale, "构建操作", "Build operations")}>
          <section
            className={`panel story-graph-ink-section ${workflowRun && !workflowRun.ok ? "error-box" : ""}`}
            aria-labelledby="graph-build-progress-heading"
            data-mode-panel="build"
          >
            <p className="eyebrow"><Bi zh="构建模式" en="Build Mode" /></p>
            <h2 id="graph-build-progress-heading"><Bi zh="构建进度" en="Build progress" /></h2>
            <StoryGraphBuildProgress locale={locale} selectedBuildRunId={selectedRunId} workflowRun={workflowRun} />
          </section>
          <section
            className={`panel story-graph-ink-section ${workflowEvents && !workflowEvents.ok ? "error-box" : ""}`}
            aria-labelledby="graph-build-events-heading"
            data-mode-panel="build"
          >
            <p className="eyebrow"><Bi zh="构建模式" en="Build Mode" /></p>
            <h2 id="graph-build-events-heading"><Bi zh="工作流事件" en="Workflow events" /></h2>
            <WorkflowEvents locale={locale} selectedBuildRunId={selectedRunId} workflowEvents={workflowEvents} />
          </section>
        </aside>
      </div>
      ) : null}

      {workspaceMode === "curate" ? (
      <div className="workbench-grid story-graph-compose-grid" data-mode="curate">
        <main>
          <section className="panel story-graph-paper-panel" aria-labelledby="graph-curate-heading" data-mode-panel="curate">
            <p className="eyebrow"><Bi zh="整理模式" en="Curate Mode" /></p>
            <h2 id="graph-curate-heading"><Bi zh="图谱候选" en="Graph candidates" /></h2>
            <p className="form-hint"><Bi zh="审阅图谱候选，显式采纳为正史或素材。" en="Review graph candidates and explicitly adopt them into canon or material." /></p>
            <StatusLine status={adoptionStatus} code={adoptionCode} message={adoptionMessage} />
            <GraphCandidates
              graphCandidates={graphCandidates}
              adoptStoryGraphCandidateAction={adoptStoryGraphCandidateAction}
            />
          </section>
        </main>
      </div>
      ) : null}

      {workspaceMode === "compose" ? (
      <div className="workbench-grid story-graph-compose-grid" data-mode="compose">
        <main>
          <section className="panel story-graph-paper-panel" aria-labelledby="graph-compose-heading" data-mode-panel="compose">
            <p className="eyebrow"><Bi zh="生成模式" en="Compose Mode" /></p>
            <h2 id="graph-compose-heading"><Bi zh="生成关系" en="Generate bonds" /></h2>
            <StatusLine status={bondStatus} code={bondCode} message={bondMessage} />
            <form action={bondAction} className="binding-form story-graph-bond-form">
              <input type="hidden" name="graphId" value={current.ok ? current.graph_id : ""} />
              <div className="story-graph-field story-graph-field-full">
                <label htmlFor="graph-bond-node-ids"><Bi zh="选择节点" en="Select nodes" /></label>
                <select
                  defaultValue={defaultBondNodeIds(view)}
                  disabled={!view.ok || view.nodes.length === 0}
                  id="graph-bond-node-ids"
                  multiple
                  name="nodeIds"
                  size={view.ok ? Math.min(Math.max(view.nodes.length, 3), 7) : 3}
                >
                  {view.ok && view.nodes.length > 0 ? view.nodes.map((node, index) => (
                    <option key={node.node_id} value={node.node_id}>
                      {node.title || tx(locale, `未命名节点 ${index + 1}`, `Untitled node ${index + 1}`)}
                    </option>
                  )) : (
                    <option value=""><Bi zh="暂无节点" en="No nodes available" /></option>
                  )}
                </select>
              </div>
              <div className="story-graph-field story-graph-field-full">
                <label htmlFor="graph-bond-focus"><Bi zh="生成重点" en="Focus" /></label>
                <textarea
                  id="graph-bond-focus"
                  name="focus"
                  defaultValue={tx(locale, "关系张力或尚未解决的剧情线索", "relationship tension or unresolved plot thread")}
                  rows={3}
                />
              </div>
              <div className="story-graph-field story-graph-field-full">
                <label htmlFor="graph-bond-mode"><Bi zh="模式" en="Mode" /></label>
                <select id="graph-bond-mode" name="mode" defaultValue="bonds_and_threads">
                  <option value="bonds_and_threads">{tx(locale, "关系与剧情线索", "Bonds and threads")}</option>
                  <option value="bonds">{tx(locale, "仅关系", "Bonds only")}</option>
                  <option value="threads">{tx(locale, "仅剧情线索", "Threads only")}</option>
                </select>
              </div>
              <button type="submit"><Bi zh="生成关系" en="Generate bonds" /></button>
            </form>
          </section>
        </main>
      </div>
      ) : null}
    </div>
  );
}

function GraphCandidates({
  graphCandidates,
  adoptStoryGraphCandidateAction,
}: {
  graphCandidates: AssetListSummary;
  adoptStoryGraphCandidateAction: (formData: FormData) => Promise<void>;
}) {
  if (!graphCandidates.ok) {
    return <p className="form-hint"><FailureText /></p>;
  }
  if (graphCandidates.items.length === 0) {
    return <p className="form-hint"><Bi zh="没有等待采用的图谱候选。" en="No graph candidates awaiting adoption." /></p>;
  }
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th><Bi zh="候选" en="Candidate" /></th>
            <th><Bi zh="类型" en="Type" /></th>
            <th><Bi zh="来源" en="Source" /></th>
            <th><Bi zh="操作" en="Action" /></th>
          </tr>
        </thead>
        <tbody>
          {graphCandidates.items.map((candidate, index) => (
            <tr key={candidate.asset_id}>
              <td>
                <strong>{candidate.title || <Bi zh={`未命名候选 ${index + 1}`} en={`Untitled candidate ${index + 1}`} />}</strong>
                <br />
                <span className="form-hint">{candidate.summary || <Bi zh="暂无摘要" en="No summary" />}</span>
              </td>
              <td>{candidate.asset_type}</td>
              <td>{candidate.source_ref || <Bi zh="图谱关系生成" en="graph bond generation" />}</td>
              <td>
                <form action={adoptStoryGraphCandidateAction} className="inline-action-form">
                  <input type="hidden" name="assetId" value={candidate.asset_id} />
                  {candidate.asset_type === "graph_bond" ? (
                    <button type="submit" name="targetKind" value="relationship"><Bi zh="采用为关系" en="Adopt relationship" /></button>
                  ) : (
                    <button type="submit" name="targetKind" value="plot_thread"><Bi zh="采用为剧情线索" en="Adopt plot thread" /></button>
                  )}
                </form>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function defaultBondNodeIds(view: StoryGraphViewSummary) {
  if (!view.ok) {
    return [];
  }
  return view.nodes.slice(0, 2).map((node) => node.node_id);
}

type LayoutNode = {
  nodeId: string;
  x: number;
  y: number;
  clusterId: string;
};

type LayoutCluster = {
  clusterId: string;
  clusterKey: string;
  x: number;
  y: number;
  width: number;
  height: number;
  nodeCount: number;
};

type LayoutViewport = {
  mode: string;
  totalNodeCount: number;
  omittedNodeCount: number;
  strategyBasis: string;
};

function GraphCanvas({
  clusters,
  current,
  layout,
  locale,
  onSelectNodeId,
  selectedNodeId,
  view,
}: {
  clusters: StoryGraphClustersSummary;
  current: StoryGraphCurrentSummary;
  layout: StoryGraphLayoutSummary;
  locale: Locale;
  onSelectNodeId?: (nodeId: string) => void;
  selectedNodeId?: string;
  view: StoryGraphViewSummary;
}) {
  if (!view.ok) {
    return (
      <div className="story-graph-canvas story-graph-canvas-empty" aria-label={tx(locale, "故事图谱元数据画布", "Story graph metadata canvas")}>
        <p className="form-hint"><FailureText /></p>
      </div>
    );
  }
  if (!layout.ok) {
    return (
      <div className="story-graph-canvas story-graph-canvas-empty" aria-label={tx(locale, "故事图谱画布", "Story graph canvas")}>
        <p className="form-hint"><FailureText /></p>
      </div>
    );
  }
  if (view.nodes.length === 0) {
    return (
      <div className="story-graph-canvas story-graph-canvas-empty" aria-label={tx(locale, "故事图谱元数据画布", "Story graph metadata canvas")}>
        <strong><Bi zh="暂无图谱节点" en="No graph nodes available" /></strong>
        <p className="form-hint"><Bi zh="运行故事图谱构建后，这里会显示可查看的节点。" en="Run a Story Graph build to populate the public viewport." /></p>
      </div>
    );
  }

  return (
    <InteractiveGraphCanvas
      clusters={clusters}
      current={current}
      layout={layout}
      locale={locale}
      onSelectNodeId={onSelectNodeId}
      selectedNodeId={selectedNodeId}
      view={view}
    />
  );
}

function InteractiveGraphCanvas({
  clusters,
  current,
  layout,
  locale,
  onSelectNodeId,
  selectedNodeId: controlledSelectedNodeId,
  view,
}: {
  clusters: StoryGraphClustersSummary;
  current: StoryGraphCurrentSummary;
  layout: Extract<StoryGraphLayoutSummary, { ok: true }>;
  locale: Locale;
  onSelectNodeId?: (nodeId: string) => void;
  selectedNodeId?: string;
  view: Extract<StoryGraphViewSummary, { ok: true }>;
}) {
  const model = useMemo(() => graphLayoutModel(layout.layout), [layout.layout]);
  const currentNodeCount = current.ok ? current.node_count : model.viewport.totalNodeCount;
  const largeGraph = model.viewport.mode === "cluster_overview" || currentNodeCount > view.nodes.length;
  const [mode, setMode] = useState<"clusters" | "nodes">(largeGraph ? "clusters" : "nodes");
  const [query, setQuery] = useState("");
  const [nodeType, setNodeType] = useState("all");
  const [clusterId, setClusterId] = useState("all");
  const [internalSelectedNodeId, setInternalSelectedNodeId] = useState(view.nodes[0]?.node_id ?? "");
  const selectedNodeId = controlledSelectedNodeId ?? internalSelectedNodeId;
  const setSelectedNodeId = (nodeId: string) => {
    setInternalSelectedNodeId(nodeId);
    onSelectNodeId?.(nodeId);
  };
  const [zoom, setZoom] = useState(1);

  const positionedNodes = useMemo(() => {
    const layoutByNodeId = new Map(model.nodes.map((node) => [node.nodeId, node]));
    return view.nodes.flatMap((node) => {
      const position = layoutByNodeId.get(node.node_id);
      return position ? [{ node, position }] : [];
    });
  }, [model.nodes, view.nodes]);
  const nodeTypes = useMemo(
    () => [...new Set(view.nodes.map((node) => node.node_type))].sort(),
    [view.nodes],
  );
  const filteredNodes = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    return positionedNodes.filter(({ node, position }) => {
      if (nodeType !== "all" && node.node_type !== nodeType) {
        return false;
      }
      if (clusterId !== "all" && position.clusterId !== clusterId && node.cluster_id !== clusterId) {
        return false;
      }
      return !normalizedQuery || [node.title, node.summary, node.node_id, node.node_type]
        .some((value) => value.toLocaleLowerCase().includes(normalizedQuery));
    });
  }, [clusterId, nodeType, positionedNodes, query]);
  const positionByNodeId = useMemo(
    () => new Map(filteredNodes.map(({ node, position }) => [node.node_id, position])),
    [filteredNodes],
  );
  const visibleEdges = useMemo(
    () => view.edges.filter((edge) => positionByNodeId.has(edge.source_node_id) && positionByNodeId.has(edge.target_node_id)),
    [positionByNodeId, view.edges],
  );
  const selectedNode = view.nodes.find((node) => node.node_id === selectedNodeId) ?? filteredNodes[0]?.node;
  const selectedNodeIndex = selectedNode ? view.nodes.findIndex((node) => node.node_id === selectedNode.node_id) : -1;
  const selectedNodeLabel = selectedNode
    ? graphNodeLabel(selectedNode.title, selectedNodeIndex, locale)
    : "";
  const selectedRelations = selectedNode
    ? view.edges.filter((edge) => edge.source_node_id === selectedNode.node_id || edge.target_node_id === selectedNode.node_id)
    : [];
  const bounds = graphBounds(mode === "clusters" ? model.clusters : filteredNodes.map(({ position }) => position));
  const viewBox = zoomedViewBox(bounds, zoom);
  const missingLayoutCount = view.nodes.length - positionedNodes.length;
  const viewportOmitted = Math.max(model.viewport.omittedNodeCount, currentNodeCount - view.nodes.length, 0);

  function chooseCluster(value: string) {
    setClusterId(value);
    setMode(value === "all" && largeGraph ? "clusters" : "nodes");
    setSelectedNodeId("");
  }

  return (
    <div className="story-graph-canvas" style={{ display: "block" }} aria-label={tx(locale, "故事图谱交互画布", "Interactive story graph canvas")}>
      <div className="binding-stack">
        <div className="status-row" aria-label={tx(locale, "图谱视图控制", "Graph view controls")}>
          <button type="button" aria-pressed={mode === "clusters"} onClick={() => setMode("clusters")}>
            <Bi zh="聚类概览" en="Cluster overview" />
          </button>
          <button type="button" aria-pressed={mode === "nodes"} onClick={() => setMode("nodes")}>
            <Bi zh="节点视图" en="Node view" />
          </button>
          <button type="button" aria-label={tx(locale, "缩小图谱", "Zoom out")} title={tx(locale, "缩小", "Zoom out")} onClick={() => setZoom((value) => Math.max(0.7, value - 0.15))}>
            <Minus size={16} aria-hidden="true" />
          </button>
          <button type="button" aria-label={tx(locale, "放大图谱", "Zoom in")} title={tx(locale, "放大", "Zoom in")} onClick={() => setZoom((value) => Math.min(2, value + 0.15))}>
            <Plus size={16} aria-hidden="true" />
          </button>
          <button type="button" aria-label={tx(locale, "重置图谱视图", "Reset graph view")} title={tx(locale, "重置视图", "Reset view")} onClick={() => { setZoom(1); setQuery(""); setNodeType("all"); chooseCluster("all"); }}>
            <RotateCcw size={16} aria-hidden="true" />
          </button>
        </div>

        <div className="inline-controls">
          <label htmlFor="story-graph-search"><Bi zh="搜索节点" en="Search nodes" /></label>
          <span style={{ position: "relative", minWidth: 0 }}>
            <Search size={16} aria-hidden="true" style={{ position: "absolute", left: 12, top: 14, pointerEvents: "none" }} />
            <input
              id="story-graph-search"
              value={query}
              onChange={(event) => { setQuery(event.target.value); setMode("nodes"); }}
              style={{ width: "100%", paddingLeft: 36 }}
            />
          </span>
          <label htmlFor="story-graph-node-type"><Bi zh="节点类型" en="Node type" /></label>
          <select id="story-graph-node-type" value={nodeType} onChange={(event) => { setNodeType(event.target.value); setMode("nodes"); }}>
            <option value="all">{tx(locale, "全部类型", "All types")}</option>
            {nodeTypes.map((type) => <option key={type} value={type}>{type}</option>)}
          </select>
          <label htmlFor="story-graph-cluster"><Bi zh="聚类" en="Cluster" /></label>
          <select id="story-graph-cluster" value={clusterId} onChange={(event) => chooseCluster(event.target.value)}>
            <option value="all">{tx(locale, "全部聚类", "All clusters")}</option>
            {model.clusters.map((cluster, index) => (
              <option key={cluster.clusterId} value={cluster.clusterId}>
                {publicGraphLabel(cluster.clusterKey, tx(locale, `聚类 ${index + 1}`, `Cluster ${index + 1}`))}
              </option>
            ))}
          </select>
        </div>

        <p className="form-hint" role="status">
          {mode === "clusters"
            ? tx(locale, `${model.clusters.length} 个聚类代表 ${currentNodeCount} 个节点`, `${model.clusters.length} clusters represent ${currentNodeCount} nodes`)
            : tx(locale, `当前窗口显示 ${filteredNodes.length}/${currentNodeCount} 个节点、${visibleEdges.length} 条关系`, `Viewport shows ${filteredNodes.length}/${currentNodeCount} nodes and ${visibleEdges.length} edges`)}
          {viewportOmitted > 0 ? tx(locale, `；其余 ${viewportOmitted} 个节点由聚类概览表示`, `; ${viewportOmitted} remaining nodes are represented by cluster overview`) : ""}
        </p>
        {missingLayoutCount > 0 ? (
          <p className="form-hint error-box" role="alert">
            {tx(locale, `${missingLayoutCount} 个视图节点缺少持久化布局坐标。`, `${missingLayoutCount} viewport nodes are missing persisted layout coordinates.`)}
          </p>
        ) : null}

        <svg
          className="story-graph-svg"
          data-graph-canvas="true"
          role="img"
          aria-label={mode === "clusters" ? tx(locale, "故事图谱聚类概览", "Story graph cluster overview") : tx(locale, "故事图谱节点与关系", "Story graph nodes and edges")}
          viewBox={viewBox}
          preserveAspectRatio="xMidYMid meet"
        >
          {mode === "clusters" ? model.clusters.map((cluster, index) => {
            const clusterLabel = publicGraphLabel(cluster.clusterKey, tx(locale, `聚类 ${index + 1}`, `Cluster ${index + 1}`));
            return (
            <g
              key={cluster.clusterId}
              data-graph-cluster-id={cluster.clusterId}
              role="button"
              tabIndex={0}
              aria-label={tx(locale, `打开${clusterLabel}，${cluster.nodeCount} 个节点`, `Open ${clusterLabel} with ${cluster.nodeCount} nodes`)}
              onClick={() => chooseCluster(cluster.clusterId)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  chooseCluster(cluster.clusterId);
                }
              }}
              style={{ cursor: "pointer" }}
            >
              <rect x={cluster.x} y={cluster.y} width={cluster.width} height={cluster.height} rx={8} fill={clusterColor(cluster.clusterKey)} fillOpacity={0.18} stroke={clusterColor(cluster.clusterKey)} strokeWidth={2} />
              <text x={cluster.x + 18} y={cluster.y + 30} fill="#f0ebe2" fontSize={16} fontWeight={700}>{shortGraphLabel(clusterLabel, 26)}</text>
              <text x={cluster.x + 18} y={cluster.y + 54} fill="#b8b0a4" fontSize={13}>{tx(locale, `${cluster.nodeCount} 个节点`, `${cluster.nodeCount} nodes`)}</text>
              <title>{`${clusterLabel}: ${cluster.nodeCount}`}</title>
            </g>
            );
          }) : (
            <>
              {visibleEdges.map((edge) => {
                const source = positionByNodeId.get(edge.source_node_id);
                const target = positionByNodeId.get(edge.target_node_id);
                if (!source || !target) {
                  return null;
                }
                return (
                  <line
                    key={edge.edge_id}
                    data-graph-edge-id={edge.edge_id}
                    x1={source.x + 60}
                    y1={source.y + 28}
                    x2={target.x + 60}
                    y2={target.y + 28}
                    stroke="#8a7a62"
                    strokeOpacity={0.55}
                    strokeWidth={Math.max(1.2, Math.min(3.5, edge.weight))}
                  >
                    <title>{edge.label || edge.edge_type}</title>
                  </line>
                );
              })}
              {filteredNodes.map(({ node, position }) => {
                const selected = selectedNode?.node_id === node.node_id;
                const color = nodeTypeColor(node.node_type);
                const nodeLabel = graphNodeLabel(node.title, view.nodes.findIndex((item) => item.node_id === node.node_id), locale);
                return (
                  <g
                    key={node.node_id}
                    data-graph-node-id={node.node_id}
                    role="button"
                    tabIndex={0}
                    aria-pressed={selected}
                    aria-label={tx(locale, `查看节点 ${nodeLabel}`, `Inspect node ${nodeLabel}`)}
                    transform={`translate(${position.x} ${position.y})`}
                    onClick={() => setSelectedNodeId(node.node_id)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        setSelectedNodeId(node.node_id);
                      }
                    }}
                    style={{ cursor: "pointer" }}
                  >
                    <rect width={120} height={56} rx={6} fill={selected ? color : "rgba(28,32,34,0.92)"} stroke={selected ? color : "rgba(201,168,98,0.55)"} strokeWidth={selected ? 3 : 1.4} />
                    <text x={12} y={23} fill={selected ? "#ffffff" : "#f0ebe2"} fontSize={13} fontWeight={700}>{shortGraphLabel(nodeLabel, 16)}</text>
                    <text x={12} y={42} fill={selected ? "#ffffff" : "#a89f92"} fontSize={10}>{shortGraphLabel(node.node_type, 18)}</text>
                    <title>{`${nodeLabel} (${node.node_type})`}</title>
                  </g>
                );
              })}
            </>
          )}
        </svg>

        {mode === "nodes" && filteredNodes.length === 0 ? (
          <p className="form-hint" role="status"><Bi zh="当前过滤条件没有匹配节点。" en="No nodes match the current filters." /></p>
        ) : null}
        {selectedNode ? (
          <section className="story-graph-node-inspector" aria-labelledby="story-graph-inspector-heading" aria-live="polite">
            <p className="eyebrow"><Bi zh="节点检查器" en="Node inspector" /></p>
            <h3 id="story-graph-inspector-heading">{selectedNodeLabel}</h3>
            <p>{selectedNode.summary || tx(locale, "暂无公开摘要。", "No public summary available.")}</p>
            <dl>
              <dt><Bi zh="类型" en="Type" /></dt><dd>{selectedNode.node_type}</dd>
              <dt><Bi zh="生命周期" en="Lifecycle" /></dt><dd><StatusValue value={selectedNode.lifecycle} /></dd>
              <dt><Bi zh="聚类" en="Cluster" /></dt>
              <dd>{publicGraphLabel(selectedNode.cluster_id, tx(locale, "未分配", "Unassigned"))}</dd>
              <dt><Bi zh="重要度" en="Importance" /></dt><dd>{selectedNode.importance}</dd>
              <dt><Bi zh="公开证据" en="Public evidence" /></dt><dd>{selectedNode.evidence_count}</dd>
              <dt><Bi zh="当前窗口关系" en="Viewport relations" /></dt><dd>{selectedRelations.length}</dd>
            </dl>
          </section>
        ) : null}
        <p className="form-hint">
          {model.viewport.strategyBasis || tx(locale, "布局来自已持久化的确定性聚类坐标。", "Layout uses persisted deterministic cluster coordinates.")}
        </p>
      </div>
    </div>
  );
}

function graphLayoutModel(layout: Record<string, unknown>) {
  const nodes = arrayRecords(layout.nodes).flatMap((item): LayoutNode[] => {
    const nodeId = textValue(item.node_id);
    const x = finiteNumber(item.x);
    const y = finiteNumber(item.y);
    if (!nodeId || x === null || y === null) {
      return [];
    }
    return [{ nodeId, x, y, clusterId: textValue(item.cluster_id) || textValue(item.cluster_key) }];
  });
  const persistedClusters = arrayRecords(layout.clusters).flatMap((item): LayoutCluster[] => {
    const clusterId = textValue(item.cluster_id) || textValue(item.cluster_key);
    const x = finiteNumber(item.x);
    const y = finiteNumber(item.y);
    const width = finiteNumber(item.width);
    const height = finiteNumber(item.height);
    if (!clusterId || x === null || y === null || width === null || height === null) {
      return [];
    }
    return [{
      clusterId,
      clusterKey: textValue(item.cluster_key) || clusterId,
      x,
      y,
      width: Math.max(140, width),
      height: Math.max(80, height),
      nodeCount: Math.max(0, finiteNumber(item.node_count) ?? 0),
    }];
  });
  const clusters = persistedClusters.length > 0 ? persistedClusters : derivedLayoutClusters(nodes);
  const viewportRecord = recordValue(layout.viewport);
  return {
    nodes,
    clusters,
    viewport: {
      mode: textValue(viewportRecord.mode) || "expanded",
      totalNodeCount: Math.max(nodes.length, finiteNumber(viewportRecord.total_node_count) ?? nodes.length),
      omittedNodeCount: Math.max(0, finiteNumber(viewportRecord.omitted_node_count) ?? 0),
      strategyBasis: textValue(viewportRecord.strategy_basis),
    } satisfies LayoutViewport,
  };
}

function derivedLayoutClusters(nodes: LayoutNode[]): LayoutCluster[] {
  const grouped = new Map<string, LayoutNode[]>();
  for (const node of nodes) {
    const key = node.clusterId || "unassigned";
    grouped.set(key, [...(grouped.get(key) ?? []), node]);
  }
  return [...grouped.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([key, items], index) => {
    const minX = Math.min(...items.map((item) => item.x));
    const minY = Math.min(...items.map((item) => item.y));
    const maxX = Math.max(...items.map((item) => item.x));
    const maxY = Math.max(...items.map((item) => item.y));
    return {
      clusterId: key,
      clusterKey: key,
      x: Number.isFinite(minX) ? minX - 24 : (index % 4) * 240,
      y: Number.isFinite(minY) ? minY - 24 : Math.floor(index / 4) * 160,
      width: Math.max(180, maxX - minX + 168),
      height: Math.max(104, maxY - minY + 104),
      nodeCount: items.length,
    };
  });
}

function graphBounds(items: Array<LayoutNode | LayoutCluster>) {
  if (items.length === 0) {
    return { x: 0, y: 0, width: 900, height: 520 };
  }
  const minX = Math.min(...items.map((item) => item.x));
  const minY = Math.min(...items.map((item) => item.y));
  const maxX = Math.max(...items.map((item) => item.x + ("width" in item ? item.width : 120)));
  const maxY = Math.max(...items.map((item) => item.y + ("height" in item ? item.height : 56)));
  return { x: minX - 48, y: minY - 48, width: Math.max(320, maxX - minX + 96), height: Math.max(220, maxY - minY + 96) };
}

function zoomedViewBox(bounds: { x: number; y: number; width: number; height: number }, zoom: number) {
  const width = bounds.width / zoom;
  const height = bounds.height / zoom;
  const x = bounds.x + (bounds.width - width) / 2;
  const y = bounds.y + (bounds.height - height) / 2;
  return `${x} ${y} ${width} ${height}`;
}

function arrayRecords(value: unknown): Record<string, unknown>[] {
  return Array.isArray(value) ? value.map(recordValue) : [];
}

function recordValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function textValue(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

function finiteNumber(value: unknown) {
  const parsed = typeof value === "number" ? value : typeof value === "string" ? Number(value) : Number.NaN;
  return Number.isFinite(parsed) ? parsed : null;
}

function shortGraphLabel(value: string, limit: number) {
  return value.length > limit ? `${value.slice(0, Math.max(1, limit - 1))}...` : value;
}

function graphNodeLabel(title: string, index: number, locale: Locale) {
  return title || tx(locale, `未命名节点 ${Math.max(index + 1, 1)}`, `Untitled node ${Math.max(index + 1, 1)}`);
}

function graphNodeName(
  view: Extract<StoryGraphViewSummary, { ok: true }>,
  nodeId: string,
  locale: Locale,
) {
  const index = view.nodes.findIndex((node) => node.node_id === nodeId);
  const node = index >= 0 ? view.nodes[index] : undefined;
  return node ? graphNodeLabel(node.title, index, locale) : tx(locale, "未知节点", "Unknown node");
}

function publicGraphLabel<T extends ReactNode>(value: string, fallback: T): string | T {
  const normalized = value.trim();
  const technicalIdentifier = /^(?:[0-9a-f]{8}-[0-9a-f-]{27,}|(?:asset|cluster|edge|evt|event|graph|node|run|view)[_-][a-z0-9_-]+)$/i;
  return normalized && !technicalIdentifier.test(normalized) ? normalized : fallback;
}

function nodeTypeColor(nodeType: string) {
  const colors: Record<string, string> = {
    character: "#8f211b",
    organization: "#6941c6",
    faction: "#7f56d9",
    location: "#a15c00",
    artifact: "#475467",
    plot_event: "#c2410c",
    plot_thread: "#b54708",
    world_rule: "#087a68",
    concept: "#52606d",
  };
  return colors[nodeType] ?? "#52606d";
}

function clusterColor(clusterKey: string) {
  return nodeTypeColor(clusterKey.toLocaleLowerCase());
}

function GraphViewport({ locale, view }: { locale: Locale; view: StoryGraphViewSummary }) {
  if (!view.ok) {
    return <p className="form-hint"><FailureText /></p>;
  }
  return (
    <div className="binding-stack">
      <p className="form-hint">
        {view.nodes.length} <Bi zh="个节点" en="nodes" /> / {view.edges.length} <Bi zh="条关系" en="edges" />
      </p>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th><Bi zh="节点" en="Node" /></th>
              <th><Bi zh="类型" en="Type" /></th>
              <th><Bi zh="生命周期" en="Lifecycle" /></th>
              <th><Bi zh="证据" en="Evidence" /></th>
            </tr>
          </thead>
          <tbody>
            {view.nodes.map((node, index) => (
              <tr key={node.node_id}>
                <td>{graphNodeLabel(node.title, index, locale)}</td>
                <td>{node.node_type}</td>
                <td><StatusValue value={node.lifecycle} /></td>
                <td>{node.evidence_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th><Bi zh="关系" en="Edge" /></th>
              <th><Bi zh="类型" en="Type" /></th>
              <th><Bi zh="起点" en="From" /></th>
              <th><Bi zh="终点" en="To" /></th>
            </tr>
          </thead>
          <tbody>
            {view.edges.map((edge, index) => (
              <tr key={edge.edge_id}>
                <td>{publicGraphLabel(edge.label, tx(locale, `关系 ${index + 1}`, `Relationship ${index + 1}`))}</td>
                <td>{edge.edge_type}</td>
                <td>{graphNodeName(view, edge.source_node_id, locale)}</td>
                <td>{graphNodeName(view, edge.target_node_id, locale)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function GraphEvidence({
  evidence,
  selectedNodeId,
}: {
  evidence: StoryGraphEvidenceSummary;
  selectedNodeId?: string;
}) {
  if (!evidence.ok) {
    return <p className="form-hint"><FailureText /></p>;
  }
  const items = selectedNodeId
    ? evidence.items.filter((item) => {
        const record = item as { node_id?: string; target_id?: string; subject_id?: string };
        return !record.node_id && !record.target_id && !record.subject_id
          ? true
          : record.node_id === selectedNodeId
            || record.target_id === selectedNodeId
            || record.subject_id === selectedNodeId;
      })
    : evidence.items;
  if (items.length === 0) {
    return <p className="form-hint"><Bi zh="当前节点暂无公开证据。" en="No public evidence for this node." /></p>;
  }
  return (
    <div className="binding-stack">
      <p className="form-hint">{items.length} <Bi zh="条公开证据" en="public evidence records" /></p>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th><Bi zh="来源" en="Source" /></th>
              <th><Bi zh="引用" en="Reference" /></th>
              <th><Bi zh="章节" en="Chapter" /></th>
              <th><Bi zh="置信度" en="Confidence" /></th>
            </tr>
          </thead>
          <tbody>
            {items.map((item, index) => (
              <tr key={item.evidence_id}>
                <td>{item.source_type}</td>
                <td><Bi zh={`证据 ${index + 1}`} en={`Evidence ${index + 1}`} /></td>
                <td>{item.chapter_id ? <Bi zh="已关联" en="Linked" /> : <Bi zh="无" en="None" />}</td>
                <td>{item.confidence}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function GraphLayoutSummary({ layout, locale }: { layout: StoryGraphLayoutSummary; locale: Locale }) {
  if (!layout.ok) {
    return <p className="form-hint"><FailureText /></p>;
  }
  const keys = Object.keys(layout.layout);
  return (
    <dl>
      <dt><Bi zh="布局项" en="Layout items" /></dt>
      <dd>{keys.length}</dd>
      <dt><Bi zh="更新时间" en="Updated" /></dt>
      <dd>{layout.updated_at}</dd>
    </dl>
  );
}

function GraphClusters({ clusters }: { clusters: StoryGraphClustersSummary }) {
  if (!clusters.ok) {
    return <p className="form-hint"><FailureText /></p>;
  }
  return (
    <div className="binding-stack">
      <p className="form-hint">{clusters.items.length} <Bi zh="个聚类" en="clusters" /></p>
      <div className="data-table-wrap">
        <table className="data-table">
          <thead>
            <tr>
              <th><Bi zh="聚类" en="Cluster" /></th>
              <th><Bi zh="节点" en="Nodes" /></th>
            </tr>
          </thead>
          <tbody>
            {clusters.items.map((cluster, index) => (
              <tr key={cluster.cluster_id}>
                <td>{publicGraphLabel(cluster.title || cluster.cluster_key, <Bi zh={`聚类 ${index + 1}`} en={`Cluster ${index + 1}`} />)}</td>
                <td>{cluster.node_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function CurrentSnapshot({ current, locale }: { current: StoryGraphCurrentSummary; locale: Locale }) {
  if (!current.ok) {
    return <p className="form-hint"><FailureText /></p>;
  }

  return (
    <dl className="story-graph-snapshot-metrics">
      <div>
        <dt><Bi zh="版本" en="Version" /></dt>
        <dd>{current.version}</dd>
      </div>
      <div>
        <dt><Bi zh="状态" en="Status" /></dt>
        <dd><StatusValue value={current.status} /></dd>
      </div>
      <div>
        <dt><Bi zh="节点" en="Nodes" /></dt>
        <dd>{current.node_count}</dd>
      </div>
      <div>
        <dt><Bi zh="关系" en="Edges" /></dt>
        <dd>{current.edge_count}</dd>
      </div>
      <div>
        <dt><Bi zh="更新时间" en="Updated" /></dt>
        <dd>{current.updated_at}</dd>
      </div>
    </dl>
  );
}

function StoryGraphBuildProgress({
  locale,
  selectedBuildRunId,
  workflowRun,
}: {
  locale: Locale;
  selectedBuildRunId: string;
  workflowRun: WorkflowRunSummary | null;
}) {
  if (!selectedBuildRunId) {
    return <p className="form-hint"><Bi zh="尚未选择构建任务。" en="No build run selected." /></p>;
  }
  if (!workflowRun) {
    return <p className="form-hint"><Bi zh="尚未选择构建任务。" en="No build run selected." /></p>;
  }
  if (!workflowRun.ok) {
    return <p className="form-hint"><FailureText /></p>;
  }
  return (
    <dl>
      <dt><Bi zh="类型" en="Type" /></dt>
      <dd>{workflowRun.workflow_type}</dd>
      <dt><Bi zh="状态" en="Status" /></dt>
      <dd><StatusValue value={workflowRun.status} /></dd>
      <dt><Bi zh="进度" en="Progress" /></dt>
      <dd>{workflowRun.progress}%</dd>
      <dt><Bi zh="更新时间" en="Updated" /></dt>
      <dd>{workflowRun.updated_at}</dd>
    </dl>
  );
}

function WorkflowEvents({
  locale,
  selectedBuildRunId,
  workflowEvents,
}: {
  locale: Locale;
  selectedBuildRunId: string;
  workflowEvents: WorkflowRunEventsSummary | null;
}) {
  if (!selectedBuildRunId) {
    return <p className="form-hint"><Bi zh="尚未选择构建任务。" en="No build run selected." /></p>;
  }
  if (!workflowEvents) {
    return <p className="form-hint"><Bi zh="尚未选择构建任务。" en="No build run selected." /></p>;
  }
  if (!workflowEvents.ok) {
    return <p className="form-hint"><FailureText /></p>;
  }
  if (workflowEvents.items.length === 0) {
    return <p className="form-hint"><Bi zh="该任务还没有工作流事件。" en="No workflow events recorded for this run." /></p>;
  }
  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            <th><Bi zh="序号" en="Sequence" /></th>
            <th><Bi zh="事件" en="Event" /></th>
            <th><Bi zh="创建时间" en="Created" /></th>
          </tr>
        </thead>
        <tbody>
          {workflowEvents.items.map((event) => (
            <tr key={event.event_id}>
              <td>{event.sequence}</td>
              <td>{event.event_type}</td>
              <td>{event.created_at}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function StatusLine({ status, code: _code, message: _message }: { status: string; code: string; message: string }) {
  if (!status) {
    return null;
  }
  return (
    <p className={`form-status ${status === "success" ? "success-box" : "error-box"}`}>
      {status === "success" ? <Bi zh="操作已提交。" en="Action submitted." /> : <FailureText />}
    </p>
  );
}
