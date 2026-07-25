"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { GraphEdge, GraphNode } from "@/lib/api/graph-types";
import { computeForceLayout, type LayoutGroup } from "./graph-layout";
import { layerKeyOf, resolveConcept } from "./graph-concept";
import { layerVisual } from "./graph-visual";
import { ConstellationNode, type ConstellationNodeType } from "./graph-node";
import { FlowEdge, type FlowEdgeType } from "./graph-edge";

/**
 * The Story Graph constellation canvas, now on React Flow.
 *
 * React Flow owns pan / zoom / selection / minimap / controls; we supply the
 * constellation look — deep-ink starfield background, rich node cards (the
 * label lives *inside* the card so names never collide), flowing-mote edges,
 * and a d3-force layout with collision + clustering that keeps cards apart.
 * Concepts are banded into labelled shelves (via `bands`) instead of scattered
 * by the force cast, and concept slips render their cleaned Chinese-first
 * display title keyed to their subtype's palette.
 * Hover and selection drive a neighbourhood spotlight: focused cards light up
 * while the rest of the sky recedes.
 */

const nodeTypes = { constellation: ConstellationNode };
const edgeTypes = { flow: FlowEdge };

export type GraphCanvasProps = {
  nodes: GraphNode[];
  edges: GraphEdge[];
  /** Band assignment for background concepts (world/subtype shelves). */
  bands: Map<string, LayoutGroup>;
  selectedId: string | null;
  hoveredId: string | null;
  focusSignal: { nodeId: string; nonce: number } | null;
  onHover: (nodeId: string | null) => void;
  onSelect: (nodeId: string | null) => void;
};

function GraphCanvasInner({
  nodes,
  edges,
  bands,
  selectedId,
  hoveredId,
  focusSignal,
  onHover,
  onSelect,
}: GraphCanvasProps) {
  const { setCenter, fitView } = useReactFlow();
  const didFitRef = useRef(false);

  // Neighbourhood of the focused (selected → hovered) node.
  const focusId = selectedId ?? hoveredId;
  const neighbours = useMemo(() => {
    const set = new Set<string>();
    if (focusId) {
      set.add(focusId);
      for (const e of edges) {
        if (e.source_node_id === focusId) set.add(e.target_node_id);
        if (e.target_node_id === focusId) set.add(e.source_node_id);
      }
    }
    return set;
  }, [focusId, edges]);

  // Layout (recomputed only when the underlying graph or banding changes).
  const layout = useMemo(() => {
    if (nodes.length === 0) return new Map();
    return computeForceLayout(nodes, edges, 1100, { bands });
  }, [nodes, edges, bands]);

  const rfNodes: Node[] = useMemo(
    () =>
      nodes.map((node) => {
        const p = layout.get(node.node_id) ?? { x: 0, y: 0 };
        const dimmed = focusId !== null && !neighbours.has(node.node_id);
        const concept = resolveConcept(node);
        return {
          id: node.node_id,
          type: "constellation",
          position: p,
          selected: node.node_id === selectedId,
          data: {
            title: concept ? concept.displayTitle : node.title,
            layerKey: layerKeyOf(node),
            importance: node.importance,
            dimmed,
            focused: node.node_id === focusId,
            isUntitled: concept?.isUntitled ?? false,
          },
          draggable: true,
        } as ConstellationNodeType;
      }),
    [nodes, layout, focusId, neighbours, selectedId],
  );

  const rfEdges: Edge[] = useMemo(
    () =>
      edges.map((edge) => {
        const touchesFocus =
          focusId !== null && (edge.source_node_id === focusId || edge.target_node_id === focusId);
        const dimmed = focusId !== null && !touchesFocus;
        return {
          id: edge.edge_id,
          source: edge.source_node_id,
          target: edge.target_node_id,
          type: "flow",
          data: {
            edgeType: edge.edge_type,
            weight: edge.weight,
            focused: touchesFocus,
            dimmed,
          },
        } as FlowEdgeType;
      }),
    [edges, focusId],
  );

  // One-shot framing when the constellation first appears.
  useEffect(() => {
    if (didFitRef.current || rfNodes.length === 0) return;
    didFitRef.current = true;
    const t = setTimeout(() => {
      void fitView({ padding: 0.18, duration: 600 });
    }, 60);
    return () => clearTimeout(t);
  }, [rfNodes.length, fitView]);

  // Smooth fly-to when a search pick / neighbour click asks for focus.
  useEffect(() => {
    if (!focusSignal) return;
    const p = layout.get(focusSignal.nodeId);
    if (!p) return;
    // Seal nodes are anchored top-center-ish; nudge to their visual centre.
    void setCenter(p.x + 40, p.y + 34, { zoom: 1.2, duration: 650 });
  }, [focusSignal, layout, setCenter]);

  const onNodeClick = useCallback(
    (_: unknown, node: Node) => {
      onSelect(node.id === selectedId ? null : node.id);
    },
    [onSelect, selectedId],
  );
  const onPaneClick = useCallback(() => onSelect(null), [onSelect]);
  const onNodeMouseEnter = useCallback((_: unknown, node: Node) => onHover(node.id), [onHover]);
  const onNodeMouseLeave = useCallback(() => onHover(null), [onHover]);

  return (
    <ReactFlow
      nodes={rfNodes}
      edges={rfEdges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodeClick={onNodeClick}
      onPaneClick={onPaneClick}
      onNodeMouseEnter={onNodeMouseEnter}
      onNodeMouseLeave={onNodeMouseLeave}
      minZoom={0.2}
      maxZoom={2.5}
      proOptions={{ hideAttribution: true }}
      nodesConnectable={false}
      elementsSelectable
      zoomOnScroll
      panOnDrag
      className="constellation-flow"
      style={{ background: "transparent" }}
    >
      <Background
        variant={BackgroundVariant.Dots}
        gap={28}
        size={1.2}
        color="rgba(86,69,45,0.12)"
        bgColor="transparent"
      />
      <Controls
        position="bottom-left"
        showInteractive={false}
        className="constellation-controls"
      />
      <MiniMap
        position="bottom-right"
        pannable
        zoomable
        className="constellation-minimap"
        nodeColor={(n) => layerVisual((n.data as { layerKey?: string }).layerKey ?? "concept").color}
        maskColor="rgba(9,11,17,0.72)"
        bgColor="rgba(13,16,23,0.85)"
      />
    </ReactFlow>
  );
}

export function GraphCanvas(props: GraphCanvasProps) {
  return (
    <ReactFlowProvider>
      <div className="constellation-sky relative h-full w-full overflow-hidden">
        <GraphCanvasInner {...props} />
      </div>
    </ReactFlowProvider>
  );
}
