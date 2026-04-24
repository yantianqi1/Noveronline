import * as React from "react";
import * as d3 from "d3";

import { cn } from "@/lib/utils";
import {
  buildRenderableGraphData,
  buildNeighborStrengthMap,
  buildLegendItems,
  truncateNodeLabel,
  type RenderableNode,
  type RenderableEdge,
  type RenderableGraphData,
  type LegendItem,
} from "@/pages/story-graph/graph-render-model";
import { GRAPH_TYPE_OPTIONS } from "@/pages/story-graph/graph-view-model";
import type { GraphNodeVM, GraphEdgeVM } from "@/pages/story-graph/graph-view-model";

/* ---------- constants ---------- */

const DEFAULT_EDGE_COLOR = "#c4b393";
const DEFAULT_EDGE_WIDTH = 1.6;
const EDGE_HIGHLIGHT_COLOR = "#E91E63";
const EDGE_HIGHLIGHT_WIDTH = 2.6;
const EDGE_SELECTED_WIDTH = 3;
const EDGE_LABEL_COLOR = "#7d6a4d";
const EDGE_LABEL_HIGHLIGHT_COLOR = "#E91E63";
const EDGE_LABEL_BG = "rgba(255, 255, 255, 0.78)";
const EDGE_LABEL_BG_HIGHLIGHT = "rgba(233, 30, 99, 0.14)";
const NODE_STROKE = "#ffffff";
const NODE_STROKE_HOVER = "#333333";
const NODE_STROKE_SELECTED = "#E91E63";
const NODE_STROKE_WIDTH = 2.5;
const NODE_SELECTED_WIDTH = 4;
const NODE_RADIUS = 10;
const DRAG_THRESHOLD = 3;

/* ---------- types ---------- */

interface DragExtra {
  dragStartX?: number;
  dragStartY?: number;
  dragMoved?: boolean;
}

export interface StoryGraphPanelProps {
  nodes: GraphNodeVM[];
  edges: GraphEdgeVM[];
  selectedNodeId?: string | null;
  selectedNodeIds?: ReadonlySet<string>;
  selectedEdgeId?: string | null;
  showEdgeLabels?: boolean;
  visibleLabelNodeIds?: Set<string>;
  onNodeSelect?: (
    node: GraphNodeVM,
    modifiers?: { ctrlOrMeta: boolean; shift: boolean },
  ) => void;
  onEdgeSelect?: (edge: GraphEdgeVM) => void;
  onCanvasSelect?: () => void;
  onBoxSelect?: (nodeIds: string[]) => void;
  className?: string;
}

/* ---------- edge path builders ---------- */

type SimEdge = RenderableEdge & d3.SimulationLinkDatum<RenderableNode>;

function srcNode(edge: SimEdge): RenderableNode {
  return edge.source as RenderableNode;
}
function tgtNode(edge: SimEdge): RenderableNode {
  return edge.target as RenderableNode;
}

function buildCurveControlPoint(edge: SimEdge) {
  const src = srcNode(edge);
  const tgt = tgtNode(edge);
  const dx = (tgt.x ?? 0) - (src.x ?? 0);
  const dy = (tgt.y ?? 0) - (src.y ?? 0);
  const distance = Math.hypot(dx, dy) || 1;
  const offset = Math.max(35, distance * (0.25 + edge.pairTotal * 0.05));

  return {
    x: ((src.x ?? 0) + (tgt.x ?? 0)) / 2 + (-dy / distance) * (edge.curvature ?? 0) * offset,
    y: ((src.y ?? 0) + (tgt.y ?? 0)) / 2 + (dx / distance) * (edge.curvature ?? 0) * offset,
  };
}

function buildEdgePath(edge: SimEdge): string {
  const src = srcNode(edge);
  const tgt = tgtNode(edge);

  if (edge.isSelfLoop) {
    const startX = (src.x ?? 0) + 8;
    const startY = (src.y ?? 0) - 4;
    const endX = (src.x ?? 0) + 8;
    const endY = (src.y ?? 0) + 4;
    const r = edge.loopRadius ?? 30;
    return `M${startX},${startY} A${r},${r} 0 1,1 ${endX},${endY}`;
  }

  if (edge.pairTotal <= 1) {
    return `M${src.x ?? 0},${src.y ?? 0} L${tgt.x ?? 0},${tgt.y ?? 0}`;
  }

  const control = buildCurveControlPoint(edge);
  return `M${src.x ?? 0},${src.y ?? 0} Q${control.x},${control.y} ${tgt.x ?? 0},${tgt.y ?? 0}`;
}

function getEdgeLabelPoint(edge: SimEdge) {
  const src = srcNode(edge);
  const tgt = tgtNode(edge);

  if (edge.isSelfLoop) {
    return { x: (src.x ?? 0) + (edge.loopRadius ?? 30) + 40, y: src.y ?? 0 };
  }

  if (edge.pairTotal <= 1) {
    return {
      x: ((src.x ?? 0) + (tgt.x ?? 0)) / 2,
      y: ((src.y ?? 0) + (tgt.y ?? 0)) / 2,
    };
  }

  const control = buildCurveControlPoint(edge);
  return {
    x: 0.25 * (src.x ?? 0) + 0.5 * control.x + 0.25 * (tgt.x ?? 0),
    y: 0.25 * (src.y ?? 0) + 0.5 * control.y + 0.25 * (tgt.y ?? 0),
  };
}

/* ---------- main component ---------- */

export function StoryGraphPanel({
  nodes,
  edges,
  selectedNodeId,
  selectedNodeIds,
  selectedEdgeId,
  showEdgeLabels = false,
  visibleLabelNodeIds,
  onNodeSelect,
  onEdgeSelect,
  onCanvasSelect,
  onBoxSelect,
  className,
}: StoryGraphPanelProps) {
  const containerRef = React.useRef<HTMLDivElement>(null);
  const svgRef = React.useRef<SVGSVGElement>(null);
  const stateRef = React.useRef<{
    simulation: d3.Simulation<RenderableNode, RenderableEdge> | null;
    model: RenderableGraphData | null;
    selections: {
      edge: d3.Selection<SVGPathElement, RenderableEdge, SVGGElement, unknown>;
      edgeLabelBackground: d3.Selection<SVGRectElement, RenderableEdge, SVGGElement, unknown>;
      edgeLabelText: d3.Selection<SVGTextElement, RenderableEdge, SVGGElement, unknown>;
      node: d3.Selection<SVGCircleElement, RenderableNode, SVGGElement, unknown>;
      nodeLabel: d3.Selection<SVGTextElement, RenderableNode, SVGGElement, unknown>;
    } | null;
    zoomTransform: d3.ZoomTransform;
  }>({
    simulation: null,
    model: null,
    selections: null,
    zoomTransform: d3.zoomIdentity,
  });

  const [legendItems, setLegendItems] = React.useState<LegendItem[]>([]);

  // Keep latest callbacks in refs to avoid re-rendering the entire D3 scene
  const onNodeSelectRef = React.useRef(onNodeSelect);
  const onEdgeSelectRef = React.useRef(onEdgeSelect);
  const onCanvasSelectRef = React.useRef(onCanvasSelect);
  const onBoxSelectRef = React.useRef(onBoxSelect);
  onNodeSelectRef.current = onNodeSelect;
  onEdgeSelectRef.current = onEdgeSelect;
  onCanvasSelectRef.current = onCanvasSelect;
  onBoxSelectRef.current = onBoxSelect;

  // Build & mount D3 scene when node/edge data changes
  React.useEffect(() => {
    const container = containerRef.current;
    const svg = svgRef.current;
    if (!container || !svg) return;

    const width = container.clientWidth || 600;
    const height = container.clientHeight || 400;
    const st = stateRef.current;

    // Clear previous
    d3.select(svg).selectAll("*").remove();
    if (st.simulation) {
      st.simulation.stop();
      st.simulation = null;
    }
    st.selections = null;
    st.model = null;

    if (!nodes.length) {
      setLegendItems([]);
      return;
    }

    // Build render model (curved edges, self-loops, adjacency)
    const model = buildRenderableGraphData({
      nodes: nodes as unknown as Record<string, unknown>[],
      edges: edges as unknown as Record<string, unknown>[],
    });
    st.model = model;

    setLegendItems(
      buildLegendItems({
        nodes: model.nodes.map((n) => ({ normalizedType: n.normalizedType })),
        typeOptions: GRAPH_TYPE_OPTIONS as unknown as Array<{ key: string; label: string }>,
      }),
    );

    // SVG setup
    const svgSel = d3
      .select(svg)
      .attr("width", width)
      .attr("height", height)
      .attr("viewBox", `0 0 ${width} ${height}`);

    // Viewport with zoom/pan
    const viewport = svgSel.append("g").attr("class", "story-graph-viewport");

    // Canvas click rect for deselection
    svgSel
      .append("rect")
      .attr("width", width)
      .attr("height", height)
      .attr("fill", "transparent")
      .lower()
      .on("click", () => onCanvasSelectRef.current?.());

    const zoomBehavior = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 4])
      .filter((event) => {
        // Let shift+drag fall through for box selection
        if (event.type === "mousedown" && event.shiftKey) return false;
        return !event.ctrlKey && !event.button;
      })
      .on("zoom", (event: d3.D3ZoomEvent<SVGSVGElement, unknown>) => {
        st.zoomTransform = event.transform;
        viewport.attr("transform", event.transform.toString());
      });
    svgSel.call(zoomBehavior);
    svgSel.call(zoomBehavior.transform, st.zoomTransform);

    // --- Create selections ---
    const edgeLayer = viewport.append("g").attr("class", "story-graph-edges");
    const labelLayer = viewport.append("g").attr("class", "story-graph-edge-labels");
    const nodeLayer = viewport.append("g").attr("class", "story-graph-nodes");

    const handleEdgeClick = (_event: Event, edge: RenderableEdge) => {
      (_event as Event).stopPropagation();
      onEdgeSelectRef.current?.(edge.raw as unknown as GraphEdgeVM);
    };

    // Edge paths (curved)
    const edgePaths = edgeLayer
      .selectAll<SVGPathElement, RenderableEdge>("path")
      .data(model.edges, (d) => d.id)
      .join("path")
      .attr("fill", "none")
      .attr("stroke", DEFAULT_EDGE_COLOR)
      .attr("stroke-width", DEFAULT_EDGE_WIDTH)
      .style("cursor", "pointer")
      .on("click", handleEdgeClick);

    // Edge label backgrounds
    const edgeLabelBgGroup = labelLayer.append("g");
    const edgeLabelBgs = edgeLabelBgGroup
      .selectAll<SVGRectElement, RenderableEdge>("rect")
      .data(model.edges, (d) => d.id)
      .join("rect")
      .attr("rx", 4)
      .attr("ry", 4)
      .attr("fill", EDGE_LABEL_BG)
      .style("cursor", "pointer")
      .on("click", handleEdgeClick);

    // Edge label text
    const edgeLabelTextGroup = labelLayer.append("g");
    const edgeLabelTexts = edgeLabelTextGroup
      .selectAll<SVGTextElement, RenderableEdge>("text")
      .data(model.edges, (d) => d.id)
      .join("text")
      .text((d) => (d.raw as Record<string, string>).name || "关系")
      .attr("font-size", 11)
      .attr("text-anchor", "middle")
      .attr("dominant-baseline", "middle")
      .attr("fill", EDGE_LABEL_COLOR)
      .style("cursor", "pointer")
      .on("click", handleEdgeClick);

    // Node drag
    const dragBehavior = d3
      .drag<SVGCircleElement, RenderableNode>()
      .on("start", (event, d) => {
        const n = d as RenderableNode & DragExtra;
        n.dragStartX = event.x;
        n.dragStartY = event.y;
        n.dragMoved = false;
        d.fx = d.x;
        d.fy = d.y;
      })
      .on("drag", (event, d) => {
        const n = d as RenderableNode & DragExtra;
        const dist = Math.hypot(event.x - (n.dragStartX ?? 0), event.y - (n.dragStartY ?? 0));
        if (!n.dragMoved && dist > DRAG_THRESHOLD) {
          n.dragMoved = true;
          st.simulation?.alphaTarget(0.3).restart();
        }
        if (n.dragMoved) {
          d.fx = event.x;
          d.fy = event.y;
        }
      })
      .on("end", (_event, d) => {
        const n = d as RenderableNode & DragExtra;
        if (n.dragMoved) {
          st.simulation?.alphaTarget(0);
        }
        d.fx = null;
        d.fy = null;
      });

    const handleNodeClick = (event: Event, node: RenderableNode & DragExtra) => {
      event.stopPropagation();
      if (node.dragMoved) {
        node.dragMoved = false;
        return;
      }
      const me = event as MouseEvent;
      onNodeSelectRef.current?.(node.raw as unknown as GraphNodeVM, {
        ctrlOrMeta: Boolean(me.ctrlKey || me.metaKey),
        shift: Boolean(me.shiftKey),
      });
    };

    // Node circles
    const nodeCircles = nodeLayer
      .selectAll<SVGCircleElement, RenderableNode>("circle")
      .data(model.nodes, (d) => d.id)
      .join("circle")
      .attr("r", NODE_RADIUS)
      .attr("fill", (d) => d.color)
      .attr("stroke", NODE_STROKE)
      .attr("stroke-width", NODE_STROKE_WIDTH)
      .style("cursor", "pointer")
      .call(dragBehavior)
      .on("mouseenter", function (_event: Event, d: RenderableNode) {
        if (d.id !== selectedNodeId) {
          d3.select(this).attr("stroke", NODE_STROKE_HOVER);
        }
      })
      .on("mouseleave", function (_event: Event, d: RenderableNode) {
        if (d.id !== selectedNodeId) {
          d3.select(this).attr("stroke", NODE_STROKE);
        }
      })
      .on("click", handleNodeClick);

    // Node labels
    const nodeLabels = nodeLayer
      .selectAll<SVGTextElement, RenderableNode>("text")
      .data(model.nodes, (d) => d.id)
      .join("text")
      .text((d) => truncateNodeLabel((d.raw as Record<string, string>).name || d.id))
      .attr("font-size", 12)
      .attr("fill", "#2d2418")
      .attr("font-weight", 500)
      .style("pointer-events", "none");

    st.selections = {
      edge: edgePaths,
      edgeLabelBackground: edgeLabelBgs,
      edgeLabelText: edgeLabelTexts,
      node: nodeCircles,
      nodeLabel: nodeLabels,
    };

    // ---- Shift+drag box selection ----
    const boxSelectRect = viewport
      .append("rect")
      .attr("class", "story-graph-selection-box")
      .attr("fill", "rgba(233, 30, 99, 0.10)")
      .attr("stroke", "#E91E63")
      .attr("stroke-width", 1)
      .attr("stroke-dasharray", "4 3")
      .attr("pointer-events", "none")
      .style("display", "none");

    let boxStart: [number, number] | null = null;

    svgSel.on("mousedown.boxselect", (event: MouseEvent) => {
      if (!event.shiftKey || !onBoxSelectRef.current) return;
      const viewportNode = viewport.node() as SVGGElement | null;
      if (!viewportNode) return;
      const [x, y] = d3.pointer(event, viewportNode);
      boxStart = [x, y];
      boxSelectRect
        .attr("x", x)
        .attr("y", y)
        .attr("width", 0)
        .attr("height", 0)
        .style("display", "");
      event.preventDefault();
    });

    svgSel.on("mousemove.boxselect", (event: MouseEvent) => {
      if (!boxStart) return;
      const viewportNode = viewport.node() as SVGGElement | null;
      if (!viewportNode) return;
      const [x, y] = d3.pointer(event, viewportNode);
      const [sx, sy] = boxStart;
      boxSelectRect
        .attr("x", Math.min(sx, x))
        .attr("y", Math.min(sy, y))
        .attr("width", Math.abs(x - sx))
        .attr("height", Math.abs(y - sy));
    });

    const endBoxSelection = (event: MouseEvent) => {
      if (!boxStart) return;
      const viewportNode = viewport.node() as SVGGElement | null;
      if (!viewportNode) {
        boxStart = null;
        boxSelectRect.style("display", "none");
        return;
      }
      const [x, y] = d3.pointer(event, viewportNode);
      const [sx, sy] = boxStart;
      const x0 = Math.min(sx, x);
      const x1 = Math.max(sx, x);
      const y0 = Math.min(sy, y);
      const y1 = Math.max(sy, y);
      boxStart = null;
      boxSelectRect.style("display", "none");
      if (x1 - x0 < 4 && y1 - y0 < 4) return;
      const hits = model.nodes
        .filter((n) => {
          const nx = n.x ?? 0;
          const ny = n.y ?? 0;
          return nx >= x0 && nx <= x1 && ny >= y0 && ny <= y1;
        })
        .map((n) => n.id);
      if (hits.length > 0) {
        onBoxSelectRef.current?.(hits);
      }
    };

    svgSel.on("mouseup.boxselect", endBoxSelection);
    svgSel.on("mouseleave.boxselect", endBoxSelection);

    // Update edge label background rects to match text bounding box
    function updateEdgeLabelBackgrounds() {
      edgeLabelBgs.each(function (this: SVGRectElement, edge: RenderableEdge, index: number) {
        const point = getEdgeLabelPoint(edge as SimEdge);
        const textNode = edgeLabelTexts.nodes()[index];
        const textBox = textNode?.getBBox();
        if (!textBox) return;
        d3.select(this)
          .attr("x", point.x - textBox.width / 2 - 5)
          .attr("y", point.y - textBox.height / 2 - 3)
          .attr("width", textBox.width + 10)
          .attr("height", textBox.height + 6);
      });
    }

    // Force simulation
    const simulation = d3
      .forceSimulation(model.nodes)
      .force(
        "link",
        d3
          .forceLink<RenderableNode, RenderableEdge>(model.edges)
          .id((d) => d.id)
          .distance((d) => d.linkDistance),
      )
      .force("charge", d3.forceManyBody<RenderableNode>().strength(-400))
      .force("collide", d3.forceCollide<RenderableNode>(50))
      .force("center", d3.forceCenter<RenderableNode>(width / 2, height / 2))
      .force("x", d3.forceX<RenderableNode>(width / 2).strength(0.04))
      .force("y", d3.forceY<RenderableNode>(height / 2).strength(0.04))
      .on("tick", () => {
        edgePaths.attr("d", (d) => buildEdgePath(d as SimEdge));

        edgeLabelTexts.each(function (this: SVGTextElement, edge: RenderableEdge) {
          const point = getEdgeLabelPoint(edge as SimEdge);
          d3.select(this).attr("x", point.x).attr("y", point.y);
        });

        updateEdgeLabelBackgrounds();

        nodeCircles
          .attr("cx", (d) => d.x ?? 0)
          .attr("cy", (d) => d.y ?? 0);

        nodeLabels
          .attr("x", (d) => (d.x ?? 0) + 14)
          .attr("y", (d) => (d.y ?? 0) + 4);
      });

    st.simulation = simulation;

    // ResizeObserver
    const resizeObserver = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width: w, height: h } = entry.contentRect;
      if (w > 0 && h > 0) {
        svgSel.attr("width", w).attr("height", h).attr("viewBox", `0 0 ${w} ${h}`);
      }
    });
    resizeObserver.observe(container);

    return () => {
      simulation.stop();
      st.simulation = null;
      resizeObserver.disconnect();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges]);

  // Apply selection styles whenever selection changes
  React.useEffect(() => {
    const st = stateRef.current;
    if (!st.selections || !st.model) return;

    const multiIds = selectedNodeIds ?? new Set<string>();
    const isInMulti = (id: string) => multiIds.has(id);
    const hasMulti = multiIds.size > 0;

    const adjacentEdgeIds = st.model.adjacencyByNodeId.get(selectedNodeId ?? "") ?? new Set<string>();
    const neighborStrength = buildNeighborStrengthMap(st.model.edges, selectedNodeId ?? null);
    const hasNodeSelection = !!selectedNodeId;

    const adjacentEdges = hasNodeSelection
      ? st.model.edges.filter((e) => adjacentEdgeIds.has(e.id))
      : [];
    const maxAdjacentWeight = Math.max(...adjacentEdges.map((e) => e.weight || 1), 1);

    // Nodes
    st.selections.node
      .attr("stroke", (node) => {
        if (node.id === selectedNodeId || isInMulti(node.id)) return NODE_STROKE_SELECTED;
        return NODE_STROKE;
      })
      .attr("stroke-width", (node) => {
        if (node.id === selectedNodeId || isInMulti(node.id)) return NODE_SELECTED_WIDTH;
        return NODE_STROKE_WIDTH;
      })
      .attr("r", (node) => {
        if (isInMulti(node.id)) return NODE_RADIUS + 3;
        if (!hasNodeSelection) return NODE_RADIUS;
        if (node.id === selectedNodeId) return NODE_RADIUS + 4;
        const strength = neighborStrength.get(node.id);
        if (strength !== undefined) return NODE_RADIUS + strength * 6;
        return NODE_RADIUS;
      })
      .attr("opacity", (node) => {
        if (isInMulti(node.id)) return 1;
        if (hasMulti && !hasNodeSelection) return 0.35;
        if (!hasNodeSelection) return 1;
        if (node.id === selectedNodeId) return 1;
        if (neighborStrength.has(node.id)) return 0.6 + neighborStrength.get(node.id)! * 0.4;
        return 0.2;
      })
      .style("filter", (node) => {
        if (isInMulti(node.id)) return "drop-shadow(0 0 5px rgba(233, 30, 99, 0.8))";
        if (!hasNodeSelection) return null;
        if (node.id === selectedNodeId) return "drop-shadow(0 0 6px #E91E63)";
        const strength = neighborStrength.get(node.id);
        if (strength !== undefined && strength > 0.5) {
          const blur = 2 + strength * 4;
          return `drop-shadow(0 0 ${blur}px rgba(233, 30, 99, ${(strength * 0.6).toFixed(2)}))`;
        }
        return null;
      });

    // Edges
    st.selections.edge
      .attr("stroke", (edge) => {
        if (edge.id === selectedEdgeId || adjacentEdgeIds.has(edge.id)) {
          return EDGE_HIGHLIGHT_COLOR;
        }
        return DEFAULT_EDGE_COLOR;
      })
      .attr("stroke-width", (edge) => {
        if (edge.id === selectedEdgeId) return EDGE_SELECTED_WIDTH;
        if (adjacentEdgeIds.has(edge.id)) {
          const norm = (edge.weight || 1) / maxAdjacentWeight;
          return EDGE_HIGHLIGHT_WIDTH + norm * 2.4;
        }
        return DEFAULT_EDGE_WIDTH;
      })
      .attr("opacity", (edge) => {
        if (!hasNodeSelection) return 1;
        if (edge.id === selectedEdgeId || adjacentEdgeIds.has(edge.id)) return 1;
        return 0.15;
      });

    // Edge label styles
    st.selections.edgeLabelBackground.attr("fill", (edge) =>
      edge.id === selectedEdgeId ? EDGE_LABEL_BG_HIGHLIGHT : EDGE_LABEL_BG,
    );
    st.selections.edgeLabelText.attr("fill", (edge) =>
      edge.id === selectedEdgeId ? EDGE_LABEL_HIGHLIGHT_COLOR : EDGE_LABEL_COLOR,
    );

    // Show labels for selected node's neighbors
    if (hasNodeSelection && st.selections.nodeLabel) {
      st.selections.nodeLabel.attr("display", (node) => {
        if (node.id === selectedNodeId || neighborStrength.has(node.id)) return null;
        return visibleLabelNodeIds?.has(node.id) ? null : "none";
      });
    }
  }, [selectedNodeId, selectedEdgeId, visibleLabelNodeIds, selectedNodeIds]);

  // Toggle node label visibility
  React.useEffect(() => {
    const st = stateRef.current;
    if (!st.selections) return;
    if (selectedNodeId) return; // handled by selection effect

    st.selections.nodeLabel.attr("display", (node) =>
      visibleLabelNodeIds?.has(node.id) ? null : "none",
    );
  }, [visibleLabelNodeIds, selectedNodeId]);

  // Toggle edge label visibility
  React.useEffect(() => {
    const st = stateRef.current;
    if (!st.selections) return;

    const opacity = showEdgeLabels ? 1 : 0;
    const pointerEvents = showEdgeLabels ? "auto" : "none";

    st.selections.edgeLabelBackground
      .attr("opacity", opacity)
      .style("pointer-events", pointerEvents);
    st.selections.edgeLabelText
      .attr("opacity", opacity)
      .style("pointer-events", pointerEvents);
  }, [showEdgeLabels]);

  const hasNodes = nodes.length > 0;

  return (
    <div
      ref={containerRef}
      className={cn(
        "relative min-h-0 overflow-hidden rounded-xl border border-border",
        "bg-[radial-gradient(circle_at_1px_1px,rgba(121,102,69,0.14)_1px,transparent_0)] bg-[length:18px_18px]",
        "bg-gradient-to-b from-[#fffdf8] to-[#f7efdf]",
        className,
      )}
    >
      <svg
        ref={svgRef}
        className="relative z-[1] block h-full w-full"
        aria-label="故事图谱"
      />

      {/* Top fade mask */}
      <div
        className="pointer-events-none absolute inset-x-0 top-0 z-[2] h-[72px] bg-gradient-to-b from-white/96 to-transparent"
        aria-hidden
      />

      {/* Empty state */}
      {!hasNodes && (
        <div className="absolute inset-0 z-[2] grid place-items-center bg-[#fffcf4]/60 text-muted-foreground">
          {"暂无图谱数据。可先选择项目并构建图谱。"}
        </div>
      )}

      {/* Legend */}
      {legendItems.length > 0 && (
        <div className="absolute bottom-3.5 left-3.5 z-[3] max-w-[min(320px,calc(100%-28px))] rounded-xl border border-amber-800/18 bg-[#fffcf4]/92 p-2.5 shadow-lg backdrop-blur-sm">
          <p className="mb-2 text-xs font-semibold text-amber-800">{"图例"}</p>
          <div className="flex flex-wrap gap-x-2.5 gap-y-2">
            {legendItems.map((item) => (
              <span
                key={item.key}
                className="inline-flex items-center gap-1.5 text-xs text-amber-900"
              >
                <span
                  className="h-2.5 w-2.5 rounded-full shadow-[0_0_0_2px_rgba(255,255,255,0.9)]"
                  style={{ backgroundColor: item.color }}
                />
                {item.label} {item.count}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
