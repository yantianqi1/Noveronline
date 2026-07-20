import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Simulation,
} from "d3-force";
import { useEffect, useMemo, useRef } from "react";

export type StoryGraphForceNodeInput = {
  id: string;
  seedX: number;
  seedY: number;
  radius: number;
};

export type StoryGraphForceLinkInput = {
  id: string;
  sourceId: string;
  targetId: string;
  weight: number;
};

export type GraphViewBounds = { x: number; y: number; width: number; height: number };

export const GRAPH_ZOOM_MIN = 0.3;
export const GRAPH_ZOOM_MAX = 4;

type ForceNode = {
  id: string;
  radius: number;
  x: number;
  y: number;
  vx?: number;
  vy?: number;
  fx?: number | null;
  fy?: number | null;
};

type ForceEdge = {
  id: string;
  weight: number;
  source: string | ForceNode;
  target: string | ForceNode;
};

export type StoryGraphForceField = {
  positionOf(nodeId: string): { x: number; y: number } | undefined;
  extent(padding: number): GraphViewBounds | null;
  attachNode(nodeId: string, element: SVGGElement | null): void;
  attachLabel(nodeId: string, element: SVGTextElement | null): void;
  attachEdge(edgeId: string, element: SVGLineElement | null): void;
  beginDrag(nodeId: string): void;
  moveDrag(nodeId: string, x: number, y: number): void;
  endDrag(nodeId: string): void;
  nudge(alpha?: number): void;
};

/**
 * Live force-directed physics for the story graph canvas.
 *
 * The simulation runs outside the React render loop: registered SVG elements
 * are moved imperatively on every tick, so continuous motion never re-renders
 * the tree, while a throttled onFrame callback lets the host refresh derived
 * chrome such as the minimap and the auto-fit camera.
 */
export function useStoryGraphForce({
  nodes,
  links,
  active,
  onFrame,
}: {
  nodes: StoryGraphForceNodeInput[];
  links: StoryGraphForceLinkInput[];
  active: boolean;
  onFrame?: () => void;
}): StoryGraphForceField {
  const simulationRef = useRef<Simulation<ForceNode, ForceEdge> | null>(null);
  const liveNodesRef = useRef(new Map<string, ForceNode>());
  const memoryRef = useRef(new Map<string, { x: number; y: number }>());
  const nodeElementsRef = useRef(new Map<string, SVGGElement>());
  const labelElementsRef = useRef(new Map<string, SVGTextElement>());
  const edgeElementsRef = useRef(new Map<string, SVGLineElement>());
  const nodesRef = useRef(nodes);
  nodesRef.current = nodes;
  const linksRef = useRef(links);
  linksRef.current = links;
  const onFrameRef = useRef(onFrame);
  onFrameRef.current = onFrame;

  const structureKey = useMemo(
    () => `${nodes.map((node) => node.id).join(",")}#${links.map((link) => link.id).join(",")}`,
    [nodes, links],
  );

  useEffect(() => {
    if (!active) {
      return;
    }
    const inputNodes = nodesRef.current;
    if (inputNodes.length === 0) {
      return;
    }
    const memory = memoryRef.current;
    const forceNodes: ForceNode[] = inputNodes.map((node) => {
      const remembered = memory.get(node.id);
      return {
        id: node.id,
        radius: node.radius,
        x: remembered?.x ?? node.seedX,
        y: remembered?.y ?? node.seedY,
      };
    });
    const nodeById = new Map(forceNodes.map((node) => [node.id, node]));
    const forceEdges: ForceEdge[] = linksRef.current
      .filter((link) => nodeById.has(link.sourceId) && nodeById.has(link.targetId))
      .map((link) => ({ id: link.id, weight: link.weight, source: link.sourceId, target: link.targetId }));
    const anchorX = forceNodes.reduce((total, node) => total + node.x, 0) / forceNodes.length;
    const anchorY = forceNodes.reduce((total, node) => total + node.y, 0) / forceNodes.length;

    const simulation = forceSimulation(forceNodes)
      .force(
        "link",
        forceLink<ForceNode, ForceEdge>(forceEdges)
          .id((node) => node.id)
          .distance((edge) => Math.max(76, Math.min(170, 150 - (Number(edge.weight) || 0) * 16))),
      )
      .force("charge", forceManyBody<ForceNode>().strength(-300).distanceMax(560))
      .force("collide", forceCollide<ForceNode>().radius((node) => node.radius + 22).iterations(2))
      .force("anchor-x", forceX<ForceNode>(anchorX).strength(0.045))
      .force("anchor-y", forceY<ForceNode>(anchorY).strength(0.055));

    const reduceMotion = typeof window !== "undefined"
      && Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches);

    // Settle most of the layout synchronously so the first paint is already
    // organized, then let the remaining energy play out as visible motion.
    simulation.stop();
    simulation.velocityDecay(0.32);
    simulation.tick(reduceMotion ? 300 : Math.min(220, 90 + forceNodes.length));
    liveNodesRef.current = nodeById;

    let lastNotifiedAt = 0;
    const syncElements = () => {
      for (const node of forceNodes) {
        const transform = `translate(${node.x} ${node.y})`;
        nodeElementsRef.current.get(node.id)?.setAttribute("transform", transform);
        labelElementsRef.current.get(node.id)?.setAttribute("transform", transform);
      }
      for (const edge of forceEdges) {
        const element = edgeElementsRef.current.get(edge.id);
        if (!element) {
          continue;
        }
        const source = edge.source as ForceNode;
        const target = edge.target as ForceNode;
        element.setAttribute("x1", String(source.x));
        element.setAttribute("y1", String(source.y));
        element.setAttribute("x2", String(target.x));
        element.setAttribute("y2", String(target.y));
      }
      const now = Date.now();
      if (now - lastNotifiedAt > 240) {
        lastNotifiedAt = now;
        onFrameRef.current?.();
      }
    };

    simulation.on("tick", syncElements);
    simulation.alphaMin(0.004);
    if (!reduceMotion) {
      simulation.alpha(0.16);
      simulation.restart();
    }
    syncElements();
    simulationRef.current = simulation;

    return () => {
      simulation.on("tick", null);
      simulation.stop();
      for (const node of forceNodes) {
        memory.set(node.id, { x: node.x, y: node.y });
      }
      simulationRef.current = null;
      liveNodesRef.current = new Map();
    };
  }, [active, structureKey]);

  const fieldRef = useRef<StoryGraphForceField | null>(null);
  if (!fieldRef.current) {
    fieldRef.current = {
      positionOf(nodeId) {
        const live = liveNodesRef.current.get(nodeId);
        if (live) {
          return { x: live.x, y: live.y };
        }
        return memoryRef.current.get(nodeId);
      },
      extent(padding) {
        const liveNodes = [...liveNodesRef.current.values()];
        if (liveNodes.length === 0) {
          return null;
        }
        let minX = Number.POSITIVE_INFINITY;
        let minY = Number.POSITIVE_INFINITY;
        let maxX = Number.NEGATIVE_INFINITY;
        let maxY = Number.NEGATIVE_INFINITY;
        for (const node of liveNodes) {
          minX = Math.min(minX, node.x - node.radius);
          minY = Math.min(minY, node.y - node.radius);
          maxX = Math.max(maxX, node.x + node.radius);
          maxY = Math.max(maxY, node.y + node.radius);
        }
        return {
          x: minX - padding,
          y: minY - padding,
          width: Math.max(320, maxX - minX + padding * 2),
          height: Math.max(220, maxY - minY + padding * 2),
        };
      },
      attachNode(nodeId, element) {
        if (!element) {
          nodeElementsRef.current.delete(nodeId);
          return;
        }
        nodeElementsRef.current.set(nodeId, element);
        const position = fieldRef.current?.positionOf(nodeId);
        if (position) {
          element.setAttribute("transform", `translate(${position.x} ${position.y})`);
        }
      },
      attachLabel(nodeId, element) {
        if (!element) {
          labelElementsRef.current.delete(nodeId);
          return;
        }
        labelElementsRef.current.set(nodeId, element);
        const position = fieldRef.current?.positionOf(nodeId);
        if (position) {
          element.setAttribute("transform", `translate(${position.x} ${position.y})`);
        }
      },
      attachEdge(edgeId, element) {
        if (!element) {
          edgeElementsRef.current.delete(edgeId);
          return;
        }
        edgeElementsRef.current.set(edgeId, element);
      },
      beginDrag(nodeId) {
        const simulation = simulationRef.current;
        const node = liveNodesRef.current.get(nodeId);
        if (!simulation || !node) {
          return;
        }
        node.fx = node.x;
        node.fy = node.y;
        simulation.alphaTarget(0.3).restart();
      },
      moveDrag(nodeId, x, y) {
        const node = liveNodesRef.current.get(nodeId);
        if (!node) {
          return;
        }
        node.fx = x;
        node.fy = y;
      },
      endDrag(nodeId) {
        const simulation = simulationRef.current;
        const node = liveNodesRef.current.get(nodeId);
        if (node) {
          node.fx = null;
          node.fy = null;
        }
        simulation?.alphaTarget(0);
      },
      nudge(alpha = 0.3) {
        simulationRef.current?.alpha(alpha).restart();
      },
    };
  }
  return fieldRef.current;
}

export function boundsAroundPoints(points: Array<{ x: number; y: number }>, padding: number): GraphViewBounds {
  if (points.length === 0) {
    return { x: -450, y: -280, width: 900, height: 560 };
  }
  let minX = Number.POSITIVE_INFINITY;
  let minY = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const point of points) {
    minX = Math.min(minX, point.x);
    minY = Math.min(minY, point.y);
    maxX = Math.max(maxX, point.x);
    maxY = Math.max(maxY, point.y);
  }
  return {
    x: minX - padding,
    y: minY - padding,
    width: Math.max(320, maxX - minX + padding * 2),
    height: Math.max(220, maxY - minY + padding * 2),
  };
}

export function viewBoxAttribute(bounds: GraphViewBounds): string {
  return `${bounds.x} ${bounds.y} ${bounds.width} ${bounds.height}`;
}

/** Shrinks (factor > 1) or grows the view box while keeping focus stationary. */
export function zoomViewBounds(
  bounds: GraphViewBounds,
  factor: number,
  focus?: { x: number; y: number },
): GraphViewBounds {
  const width = bounds.width / factor;
  const height = bounds.height / factor;
  const focusX = focus?.x ?? bounds.x + bounds.width / 2;
  const focusY = focus?.y ?? bounds.y + bounds.height / 2;
  const relativeX = bounds.width > 0 ? (focusX - bounds.x) / bounds.width : 0.5;
  const relativeY = bounds.height > 0 ? (focusY - bounds.y) / bounds.height : 0.5;
  return {
    x: focusX - width * relativeX,
    y: focusY - height * relativeY,
    width,
    height,
  };
}

export function panViewBounds(bounds: GraphViewBounds, dx: number, dy: number): GraphViewBounds {
  return { x: bounds.x + dx, y: bounds.y + dy, width: bounds.width, height: bounds.height };
}

export function clientPointToGraph(
  svg: SVGSVGElement,
  viewBounds: GraphViewBounds,
  clientX: number,
  clientY: number,
): { x: number; y: number } {
  const rect = svg.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0 || viewBounds.width === 0 || viewBounds.height === 0) {
    return { x: viewBounds.x + viewBounds.width / 2, y: viewBounds.y + viewBounds.height / 2 };
  }
  // preserveAspectRatio="xMidYMid meet" letterboxes the view box inside the
  // element box; account for that uniform scale and centering offset.
  const scale = Math.min(rect.width / viewBounds.width, rect.height / viewBounds.height);
  const offsetX = (rect.width - viewBounds.width * scale) / 2;
  const offsetY = (rect.height - viewBounds.height * scale) / 2;
  return {
    x: viewBounds.x + (clientX - rect.left - offsetX) / scale,
    y: viewBounds.y + (clientY - rect.top - offsetY) / scale,
  };
}

export function graphUnitsPerPixel(svg: SVGSVGElement, viewBounds: GraphViewBounds): number {
  const rect = svg.getBoundingClientRect();
  if (rect.width === 0 || rect.height === 0 || viewBounds.width === 0 || viewBounds.height === 0) {
    return 1;
  }
  const scale = Math.min(rect.width / viewBounds.width, rect.height / viewBounds.height);
  return scale > 0 ? 1 / scale : 1;
}
