import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, RefreshCw, Network, BarChart3, FileArchive, Eye, EyeOff, Target, MousePointerSquareDashed, Sparkles } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ApiResponse } from "@/api/http";
import {
  listProjects,
  getProject,
  getProjectGraph,
  buildGraph,
  getTask,
} from "@/api/project";
import {
  generateArchiveCandidates,
  generateArchives,
} from "@/api/novel";
import { useNotification } from "@/hooks/use-notification";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { StoryGraphPanel } from "@/components/story-graph-panel";
import { StoryGraphInspector } from "@/components/story-graph-inspector";

import { GraphBuildConsole } from "./graph-build-console";
import { WorldOverviewDashboard } from "./world-overview-dashboard";
import {
  AgentTemplateConfigurator,
  type ArchiveCandidate,
} from "./agent-template-configurator";
import { GraphBondGeneratorDialog } from "./graph-bond-generator-dialog";
import { createGraphBuildTaskPoller, type TaskData } from "./graph-build-task-poller";
import {
  type GraphNodeVM,
  type GraphEdgeVM,
  buildGraphDisplayState,
  buildHighlightedNodeIds,
  shouldRenderNodeLabels,
  DEFAULT_GRAPH_TYPE_VISIBILITY,
  GRAPH_TYPE_OPTIONS,
} from "./graph-view-model";
import {
  formatProjectDisplayName,
  sanitizeGraphEdge,
  sanitizeGraphNode,
} from "./display-text";

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

interface ProjectOption {
  project_id: string;
  name?: string;
  project_name?: string;
  title?: string;
}

function projectOptionLabel(project: ProjectOption, index: number): string {
  const label = formatProjectDisplayName(project as unknown as Record<string, unknown>);
  return label === "未命名卷宗" ? `未命名卷宗 ${index + 1}` : label;
}

function toViewNodes(rawNodes: unknown[]): GraphNodeVM[] {
  return (rawNodes || []).map((raw: unknown) => {
    const n = raw as Record<string, unknown>;
    const labels = (n.labels as string[]) || [];
    return sanitizeGraphNode({
      id: String(n.uuid || n.id || ""),
      name: String(n.name || ""),
      entity_type: labels.find((l: string) => !["Entity", "Node"].includes(l)) || "Unknown",
      summary: String(n.summary || ""),
      attributes: (n.attributes as Record<string, unknown>) || {},
      evidence_refs: (n.evidence_refs as GraphNodeVM["evidence_refs"]) || [],
    });
  });
}

function toViewEdges(rawEdges: unknown[], nodeMap: Record<string, GraphNodeVM>): GraphEdgeVM[] {
  return (rawEdges || []).map((raw: unknown) => {
    const e = raw as Record<string, unknown>;
    const sourceId = String(e.source_node_uuid || "");
    const targetId = String(e.target_node_uuid || "");
    return sanitizeGraphEdge({
      id: String(e.uuid || e.id || ""),
      source_id: sourceId,
      target_id: targetId,
      source_name: nodeMap[sourceId]?.name || "Unknown",
      target_name: nodeMap[targetId]?.name || "Unknown",
      name: String(e.name || ""),
      fact: String(e.fact || ""),
      weight: Number(e.weight || 1),
    });
  });
}

function resolveNodeId(node: GraphNodeVM): string {
  return node.id || "";
}

function resolveEdgeId(edge: GraphEdgeVM, index: number): string {
  return edge.id || `edge_${index}`;
}

/* ------------------------------------------------------------------ */
/*  Main page                                                          */
/* ------------------------------------------------------------------ */

export default function StoryGraphPage() {
  const { notifySuccess, notifyError } = useNotification();

  /* -- state -- */
  const [projectId, setProjectId] = React.useState("");
  const [activeTab, setActiveTab] = React.useState<"overview" | "graph">("overview");
  const [busy, setBusy] = React.useState(false);
  const [taskError, setTaskError] = React.useState("");
  const [latestTask, setLatestTask] = React.useState<TaskData | null>(null);
  const [graphNodes, setGraphNodes] = React.useState<GraphNodeVM[]>([]);
  const [graphEdges, setGraphEdges] = React.useState<GraphEdgeVM[]>([]);
  const [currentGraphId, setCurrentGraphId] = React.useState("");
  const [configuratorVisible, setConfiguratorVisible] = React.useState(false);
  const [archiveCandidates, setArchiveCandidates] = React.useState<ArchiveCandidate[]>([]);

  // Selection
  const [selectedNode, setSelectedNode] = React.useState<GraphNodeVM | null>(null);
  const [selectedEdge, setSelectedEdge] = React.useState<GraphEdgeVM | null>(null);
  const [selectedNodeIds, setSelectedNodeIds] = React.useState<Set<string>>(() => new Set());
  const [selectionMode, setSelectionMode] = React.useState<"single" | "multi">("single");
  const [bondDialogOpen, setBondDialogOpen] = React.useState(false);

  // Type filtering
  const [visibleTypes, setVisibleTypes] = React.useState<Record<string, boolean>>({
    ...DEFAULT_GRAPH_TYPE_VISIBILITY,
  });
  const [showEdgeLabels, setShowEdgeLabels] = React.useState(false);

  const hasGraphData = graphNodes.length > 0;
  const hasFailed = latestTask?.status === "failed";

  /* -- projects query -- */
  const projectsQuery = useQuery({
    queryKey: ["projects"],
    queryFn: () => listProjects(50),
  });
  const projects = ((projectsQuery.data as ApiResponse | undefined)?.data || []) as ProjectOption[];

  const currentProjectName = React.useMemo(
    () => formatProjectDisplayName(
      projects.find((p) => p.project_id === projectId) as Record<string, unknown> | undefined,
    ),
    [projects, projectId],
  );

  /* -- auto-select first project -- */
  React.useEffect(() => {
    if (projects.length > 0 && !projectId) {
      setProjectId(projects[0]!.project_id);
    }
  }, [projects, projectId]);

  /* -- computed display state -- */
  const graphDisplayState = React.useMemo(
    () => buildGraphDisplayState({ nodes: graphNodes, edges: graphEdges, visibleTypes }),
    [graphNodes, graphEdges, visibleTypes],
  );

  const visibleNodes = graphDisplayState.visibleNodes;
  const visibleEdges = graphDisplayState.visibleEdges;
  const countsByType = graphDisplayState.countsByType;

  const highlightedNodeIds = React.useMemo(
    () => buildHighlightedNodeIds(visibleNodes, visibleEdges),
    [visibleNodes, visibleEdges],
  );

  const selectedNodeId = selectedNode ? resolveNodeId(selectedNode) : null;
  const selectedEdgeId = selectedEdge
    ? resolveEdgeId(selectedEdge, visibleEdges.findIndex((e) => e === selectedEdge))
    : null;

  const visibleLabelNodeIds = React.useMemo(() => {
    if (shouldRenderNodeLabels(visibleNodes.length)) {
      return new Set(visibleNodes.map(resolveNodeId));
    }
    const labelIds = new Set(highlightedNodeIds);
    if (selectedNodeId) labelIds.add(selectedNodeId);
    return labelIds;
  }, [visibleNodes, highlightedNodeIds, selectedNodeId]);

  // Clear selection if node/edge is no longer visible
  React.useEffect(() => {
    if (selectedNode) {
      const visibleNodeIds = new Set(visibleNodes.map(resolveNodeId));
      if (!visibleNodeIds.has(resolveNodeId(selectedNode))) {
        setSelectedNode(null);
      }
    }
    if (selectedEdge) {
      const visibleEdgeIds = new Set(visibleEdges.map((e, i) => resolveEdgeId(e, i)));
      const eid = resolveEdgeId(selectedEdge, visibleEdges.findIndex((e) => e === selectedEdge));
      if (!visibleEdgeIds.has(eid)) {
        setSelectedEdge(null);
      }
    }
    if (selectedNodeIds.size > 0) {
      const visibleIds = new Set(visibleNodes.map(resolveNodeId));
      let changed = false;
      const next = new Set<string>();
      selectedNodeIds.forEach((id) => {
        if (visibleIds.has(id)) next.add(id);
        else changed = true;
      });
      if (changed) setSelectedNodeIds(next);
    }
  }, [visibleNodes, visibleEdges, selectedNode, selectedEdge, selectedNodeIds]);

  /* -- graph data refresh -- */
  const refreshGraph = React.useCallback(
    async (pid?: string) => {
      const id = pid || projectId;
      if (!id) {
        setGraphNodes([]);
        setGraphEdges([]);
        setCurrentGraphId("");
        return;
      }
      try {
        const res = await getProject(id);
        const project = (res as ApiResponse).data as Record<string, unknown>;
        const graphId = String(project?.graph_id || "");
        setCurrentGraphId(graphId);

        if (!graphId) {
          setGraphNodes([]);
          setGraphEdges([]);
          return;
        }

        const graphRes = await getProjectGraph(id);
        const graph = (graphRes as ApiResponse).data as Record<string, unknown>;
        const nodes = toViewNodes((graph?.nodes || []) as unknown[]);
        const nodeMap = Object.fromEntries(nodes.map((n) => [n.id, n]));
        const edges = toViewEdges((graph?.edges || []) as unknown[], nodeMap);
        setGraphNodes(nodes);
        setGraphEdges(edges);
      } catch {
        setGraphNodes([]);
        setGraphEdges([]);
      }
    },
    [projectId],
  );

  /* -- load graph when project changes -- */
  React.useEffect(() => {
    if (projectId) {
      void refreshGraph(projectId);
    }
  }, [projectId, refreshGraph]);

  /* -- build graph -- */
  const pollRef = React.useRef(createGraphBuildTaskPoller({ getTask }));

  async function startBuildGraph() {
    if (!projectId) return;
    try {
      setBusy(true);
      setTaskError("");
      setLatestTask({ status: "processing", progress: 0, metadata: { stages: [] } });
      const res = await buildGraph(projectId, "Novel Story Graph");
      const taskId = String(((res as ApiResponse).data as Record<string, unknown>)?.task_id || "");
      const task = await pollRef.current(taskId, (t) => setLatestTask(t));
      setLatestTask(task);
      setCurrentGraphId(String(task.result?.graph_id || ""));
      await refreshGraph();
      setActiveTab("overview");
      notifySuccess("图谱构建完成");
    } catch (error) {
      const msg = error instanceof Error ? error.message : "构建失败";
      setTaskError(msg);
      if (latestTask) {
        setLatestTask((prev) => prev ? { ...prev, status: "failed", error: msg } : null);
      }
      notifyError(msg);
    } finally {
      setBusy(false);
    }
  }

  /* -- archive configurator -- */
  async function openArchiveConfigurator() {
    try {
      setBusy(true);
      setTaskError("");
      const res = await generateArchiveCandidates({
        projectId,
        graphId: currentGraphId,
      });
      setArchiveCandidates(
        ((res as ApiResponse).data as Record<string, unknown>)?.candidates as ArchiveCandidate[] || [],
      );
      setConfiguratorVisible(true);
    } catch (error) {
      const msg = error instanceof Error ? error.message : "获取候选失败";
      setTaskError(msg);
      notifyError(msg);
    } finally {
      setBusy(false);
    }
  }

  async function createArchives(candidateSnapshot: ArchiveCandidate[]) {
    try {
      setBusy(true);
      setTaskError("");
      const tierOverrides = candidateSnapshot
        .filter((item) => item.selected_importance_tier && item.selected_importance_tier !== item.recommended_importance_tier)
        .map((item) => ({
          entity_uuid: item.entity_uuid,
          importance_tier: item.selected_importance_tier,
        }));
      const res = await generateArchives({
        projectId,
        graphId: currentGraphId,
        useLlm: false,
        tierOverrides,
        candidateSnapshot,
      });
      const count = ((res as ApiResponse).data as Record<string, unknown>)?.count || 0;
      notifySuccess(`已生成档案: ${count} 项`);
      setConfiguratorVisible(false);
    } catch (error) {
      const msg = error instanceof Error ? error.message : "生成失败";
      setTaskError(msg);
      notifyError(msg);
    } finally {
      setBusy(false);
    }
  }

  /* -- type filtering -- */
  function toggleType(typeKey: string) {
    setVisibleTypes((prev) => ({ ...prev, [typeKey]: !prev[typeKey] }));
  }

  function resetVisibleTypes() {
    setVisibleTypes({ ...DEFAULT_GRAPH_TYPE_VISIBILITY });
  }

  /* -- selection handlers -- */
  function toggleMultiSelect(nodeId: string) {
    setSelectedNodeIds((prev) => {
      const next = new Set(prev);
      if (next.has(nodeId)) next.delete(nodeId);
      else next.add(nodeId);
      return next;
    });
  }

  function handleNodeSelect(
    node: GraphNodeVM,
    modifiers?: { ctrlOrMeta: boolean; shift: boolean },
  ) {
    const isMultiClick = selectionMode === "multi" || Boolean(modifiers?.ctrlOrMeta);
    if (isMultiClick) {
      toggleMultiSelect(node.id);
      return;
    }
    setSelectedEdge(null);
    setSelectedNode(node);
    setSelectedNodeIds(new Set());
  }

  function handleEdgeSelect(edge: GraphEdgeVM) {
    setSelectedNode(null);
    setSelectedEdge(edge);
    setSelectedNodeIds(new Set());
  }

  function handleCanvasSelect() {
    setSelectedNode(null);
    setSelectedEdge(null);
    setSelectedNodeIds(new Set());
  }

  function handleBoxSelect(ids: string[]) {
    setSelectedNodeIds((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.add(id));
      return next;
    });
    setSelectedNode(null);
    setSelectedEdge(null);
  }

  /* -- focus handlers from dashboard -- */
  function handleFocusNodeFromDashboard(nodeId: string) {
    setActiveTab("graph");
    const node = graphNodes.find((n) => n.id === nodeId);
    if (!node) return;
    // Ensure the node's type is visible
    const typeKey = (node.entity_type || "unknown").toLowerCase();
    if (typeKey in visibleTypes && !visibleTypes[typeKey]) {
      setVisibleTypes((prev) => ({ ...prev, [typeKey]: true }));
    }
    setSelectedEdge(null);
    setSelectedNode(node);
  }

  function handleFocusEdgeFromDashboard(edge: { source_id?: string }) {
    if (edge?.source_id) handleFocusNodeFromDashboard(edge.source_id);
  }

  /* -- render -- */
  return (
    <div className="flex h-[calc(100svh-7rem)] min-h-0 flex-col gap-3 overflow-hidden">
      {/* Toolbar */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 rounded-xl border border-border/60 bg-card px-2.5 py-1.5">
        <Select value={projectId} onValueChange={(v) => setProjectId(v ?? "")}>
          <SelectTrigger className="min-w-[180px]">
            <SelectValue placeholder="-- 请选择卷宗 --">
              {projectId ? currentProjectName : undefined}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {projects.map((p, index) => (
              <SelectItem key={p.project_id} value={p.project_id}>
                {projectOptionLabel(p, index)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button
          disabled={!projectId || busy}
          onClick={startBuildGraph}
        >
          {busy ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : (
            <Network className="mr-1.5 h-3.5 w-3.5" />
          )}
          {busy ? "构建中..." : "启动图谱构建"}
        </Button>

        <Button
          variant="outline"
          size="sm"
          onClick={() => { void projectsQuery.refetch(); }}
        >
          <RefreshCw className="mr-1 h-3 w-3" />
          {"刷新卷宗列表"}
        </Button>

        <Button
          variant="outline"
          size="sm"
          disabled={!projectId || busy || !currentGraphId}
          onClick={openArchiveConfigurator}
        >
          <FileArchive className="mr-1 h-3 w-3" />
          {"生成全量角色档案"}
        </Button>

        {/* Tab switcher */}
        <div className="ml-auto flex gap-1 rounded-lg bg-muted/40 p-0.5">
          <button
            type="button"
            disabled={!hasGraphData}
            className={cn(
              "rounded-md px-3 py-1 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-40",
              activeTab === "overview"
                ? "bg-card font-semibold shadow-sm"
                : "hover:bg-card/50",
            )}
            onClick={() => setActiveTab("overview")}
          >
            <BarChart3 className="mr-1 inline h-3 w-3" />
            {"世界速览"}
          </button>
          <button
            type="button"
            disabled={!hasGraphData}
            className={cn(
              "rounded-md px-3 py-1 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-40",
              activeTab === "graph"
                ? "bg-card font-semibold shadow-sm"
                : "hover:bg-card/50",
            )}
            onClick={() => setActiveTab("graph")}
          >
            <Network className="mr-1 inline h-3 w-3" />
            {"关系图谱"}
          </button>
        </div>

        {taskError && !busy && (
          <span className="min-w-0 break-words text-xs text-destructive">{taskError}</span>
        )}
      </div>

      {/* Build console */}
      {(busy || hasFailed) && (
        <GraphBuildConsole task={latestTask} onRetry={startBuildGraph} />
      )}

      {/* Main content */}
      {!busy && (
        <main className="flex min-h-0 flex-1 gap-3 overflow-hidden">
          {activeTab === "overview" && hasGraphData ? (
            <WorldOverviewDashboard
              nodes={graphNodes}
              edges={graphEdges}
              projectName={currentProjectName}
              onFocusNode={handleFocusNodeFromDashboard}
              onFocusEdge={handleFocusEdgeFromDashboard}
            />
          ) : (
            /* Graph tab: 2-column grid (canvas + right panel) */
            <div className="grid min-h-0 flex-1 gap-3.5" style={{ gridTemplateColumns: "minmax(0, 1fr) minmax(300px, 340px)" }}>
              {/* Left: Canvas */}
              <StoryGraphPanel
                nodes={visibleNodes}
                edges={visibleEdges}
                selectedNodeId={selectedNodeId}
                selectedNodeIds={selectedNodeIds}
                selectedEdgeId={selectedEdgeId}
                showEdgeLabels={showEdgeLabels}
                visibleLabelNodeIds={visibleLabelNodeIds}
                onNodeSelect={handleNodeSelect}
                onEdgeSelect={handleEdgeSelect}
                onCanvasSelect={handleCanvasSelect}
                onBoxSelect={handleBoxSelect}
                className="h-full"
              />

              {/* Right: Controls + Inspector */}
              <div className="flex min-h-0 flex-col gap-2.5">
                {/* Panel head */}
                <div className="flex items-center justify-between gap-2 flex-shrink-0">
                  <h2 className="text-sm font-semibold whitespace-nowrap">{"故事图谱面板"}</h2>
                  <div className="flex gap-1 flex-wrap">
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-xs"
                      onClick={() => void refreshGraph()}
                    >
                      {"刷新图谱"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-xs"
                      onClick={resetVisibleTypes}
                    >
                      <Target className="mr-1 h-3 w-3" />
                      {"核心视图"}
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-7 px-2 text-xs"
                      onClick={() => setShowEdgeLabels((v) => !v)}
                    >
                      {showEdgeLabels ? (
                        <><EyeOff className="mr-1 h-3 w-3" />{"隐藏标签"}</>
                      ) : (
                        <><Eye className="mr-1 h-3 w-3" />{"显示标签"}</>
                      )}
                    </Button>
                  </div>
                </div>

                {/* Multi-select toolbar */}
                <div className="flex flex-wrap items-center gap-1 flex-shrink-0 rounded-md border border-dashed border-border/60 bg-muted/30 px-2 py-1.5">
                  <Button
                    variant={selectionMode === "multi" ? "default" : "outline"}
                    size="sm"
                    className="h-6 px-2 text-[11px]"
                    onClick={() =>
                      setSelectionMode((m) => (m === "multi" ? "single" : "multi"))
                    }
                  >
                    <MousePointerSquareDashed className="mr-1 h-3 w-3" />
                    {selectionMode === "multi" ? "多选中" : "多选模式"}
                  </Button>
                  <span className="text-[11px] text-muted-foreground">
                    {"已选 "}
                    <span className="font-semibold text-foreground">{selectedNodeIds.size}</span>
                    {" 个"}
                    {selectedNodeIds.size === 0 && (
                      <span className="ml-1 text-[10px] opacity-70">
                        {"(Ctrl/⌘+点击 或 Shift+拖动框选)"}
                      </span>
                    )}
                  </span>
                  {selectedNodeIds.size > 0 && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 px-2 text-[11px]"
                      onClick={() => setSelectedNodeIds(new Set())}
                    >
                      {"清空"}
                    </Button>
                  )}
                  <Button
                    variant="default"
                    size="sm"
                    className="ml-auto h-6 px-2 text-[11px]"
                    disabled={selectedNodeIds.size < 2 || selectedNodeIds.size > 6}
                    onClick={() => setBondDialogOpen(true)}
                  >
                    <Sparkles className="mr-1 h-3 w-3" />
                    {"生成羁绊/支线"}
                  </Button>
                </div>

                {/* Type filter row */}
                <div className="flex flex-wrap gap-1 items-center flex-shrink-0">
                  {GRAPH_TYPE_OPTIONS.map((item) => (
                    <Button
                      key={item.key}
                      variant={visibleTypes[item.key] ? "default" : "outline"}
                      size="sm"
                      className="h-6 px-2 text-[11px]"
                      onClick={() => toggleType(item.key)}
                    >
                      {item.label} {countsByType[item.key] || 0}
                    </Button>
                  ))}
                  <span className="text-[11px] text-muted-foreground font-mono ml-auto">
                    {"显示"} {visibleNodes.length} / {graphNodes.length}
                  </span>
                </div>

                {/* Inspector */}
                <StoryGraphInspector
                  selectedNode={selectedNode}
                  selectedEdge={selectedEdge}
                  projectId={projectId}
                  className="flex-1 min-h-0"
                />
              </div>
            </div>
          )}
        </main>
      )}

      {/* Archive configurator dialog */}
      <AgentTemplateConfigurator
        open={configuratorVisible}
        candidates={archiveCandidates}
        busy={busy}
        error={taskError}
        onClose={() => setConfiguratorVisible(false)}
        onConfirm={createArchives}
      />

      {/* Graph bond/plot-thread generator dialog */}
      <GraphBondGeneratorDialog
        open={bondDialogOpen}
        projectId={projectId}
        selectedNodes={graphNodes.filter((n) => selectedNodeIds.has(n.id))}
        onOpenChange={setBondDialogOpen}
        onGenerated={() => {
          // Optional: refresh graph or notify. Keep selection so user can
          // re-generate without re-picking nodes.
        }}
      />
    </div>
  );
}
