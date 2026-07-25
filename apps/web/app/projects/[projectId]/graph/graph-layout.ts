import {
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  forceX,
  forceY,
  type Force,
  type SimulationLinkDatum,
  type SimulationNodeDatum,
} from "d3-force";

import type { GraphEdge, GraphNode } from "@/lib/api/graph-types";

/**
 * Force-directed constellation layout, backed by d3-force.
 *
 * Compared to the hand-rolled version this adds the two forces that actually
 * fix readability:
 *  - `forceCollide` sized to each node's visual card so labels stop overlapping;
 *  - `forceCluster` pulling nodes toward their own cluster's strongest member,
 *    which gathers related characters into legible neighbourhoods.
 * The simulation is deterministic (seeded phyllotaxis start, fixed ticks), so
 * the same graph always lands in the same arrangement.
 */

export type LayoutPoint = { x: number; y: number };
export type GraphLayoutMap = Map<string, LayoutPoint>;

/**
 * Grouping context for banding background concepts. Derived per-node by the
 * workspace (world for timeline events, subtype for the rest) and threaded
 * through the layout so concepts collect into tidy shelves instead of the
 * force scatter.
 */
export type LayoutGroup = {
  /** e.g. "event:ancient" | "event:modern" | "world" | "concept" */
  band: string;
  /** Order hint within the band (lower = earlier). */
  order: number;
};

export type GraphLayoutOptions = {
  /** Per-node band assignment; nodes without an entry stay in the force cast. */
  bands?: Map<string, LayoutGroup>;
};

type SimNode = SimulationNodeDatum & {
  id: string;
  x: number;
  y: number;
  /** Collision radius — matches the rendered card size + breathing room. */
  radius: number;
  /** Pull strength toward the cluster hub (important nodes resist). */
  strength: number;
};

/** Stable 32-bit string hash (FNV-1a) → deterministic per-node seed. */
function hashId(id: string): number {
  let h = 0x811c9dc5;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return h >>> 0;
}

function rand01(seed: number): number {
  const x = Math.sin(seed) * 43758.5453123;
  return x - Math.floor(x);
}

/** Visual radius from importance — seals sit close, slips get clearance. */
export function nodeRadius(node: GraphNode): number {
  const importance = Math.max(0, Math.min(1, node.importance || 0));
  return 30 + importance * 20; // 30..50
}

/**
 * Compute the force layout. `radius` scales the spread to the canvas size.
 * Synchronous and bounded — heavier for 300 nodes but still well under a frame
 * budget on a modern machine, and it runs once per graph load, not per frame.
 */
export function computeForceLayout(
  nodes: GraphNode[],
  edges: GraphEdge[],
  radius: number,
  options: GraphLayoutOptions = {},
): GraphLayoutMap {
  const n = nodes.length;
  if (n === 0) return new Map();

  const bands = options.bands ?? new Map<string, LayoutGroup>();
  const forceNodes = nodes.filter((node) => !bands.has(node.node_id));
  const bandedNodes = nodes.filter((node) => bands.has(node.node_id));

  const map: GraphLayoutMap = new Map();

  // Lay the character constellation first; banded concepts are placed relative
  // to its vertical extent afterwards.
  let minY = 0;
  let maxY = 0;
  if (forceNodes.length > 0) {
    const forceMap = computeForceCast(forceNodes, edges, radius);
    for (const [id, point] of forceMap) {
      map.set(id, point);
      if (point.y < minY) minY = point.y;
      if (point.y > maxY) maxY = point.y;
    }
  }

  placeBands(bandedNodes, bands, map, { minY, maxY, empty: forceNodes.length === 0 });
  return map;
}

/**
 * Deterministic banding: concepts file into labelled horizontal shelves keyed
 * by band (world for events, subtype for settings). Each band is a centered
 * wrapped grid stacked beneath the character constellation, so nothing drifts.
 */
function placeBands(
  bandedNodes: GraphNode[],
  bands: Map<string, LayoutGroup>,
  map: GraphLayoutMap,
  extent: { minY: number; maxY: number; empty: boolean },
): void {
  if (bandedNodes.length === 0) return;

  // Stable band order: timeline worlds first (现代 before 古代), then settings.
  const bandRank = (band: string): number => {
    if (band.startsWith("event:")) {
      const world = band.slice("event:".length);
      if (world === "现代") return 0;
      if (world === "古代") return 1;
      return 2;
    }
    if (band === "world") return 3;
    return 4;
  };

  const byBand = new Map<string, GraphNode[]>();
  for (const node of bandedNodes) {
    const band = bands.get(node.node_id)!.band;
    const list = byBand.get(band) ?? [];
    list.push(node);
    byBand.set(band, list);
  }
  const orderedBands = [...byBand.keys()].sort((a, b) => bandRank(a) - bandRank(b) || a.localeCompare(b));

  const COLS = 7;
  const CELL_W = 176;
  const CELL_H = 74;
  const BAND_GAP = 84;
  const startY = extent.empty ? 0 : extent.maxY + 150;

  let cursorY = startY;
  for (const band of orderedBands) {
    const members = byBand.get(band)!;
    // Deterministic order inside a band: by payload order hint then title.
    members.sort((a, b) => {
      const oa = bands.get(a.node_id)!.order;
      const ob = bands.get(b.node_id)!.order;
      if (oa !== ob) return oa - ob;
      return a.title.localeCompare(b.title);
    });
    const rows = Math.ceil(members.length / COLS);
    members.forEach((node, i) => {
      const col = i % COLS;
      const row = Math.floor(i / COLS);
      const rowCount = Math.min(COLS, members.length - row * COLS);
      const x = (col - (rowCount - 1) / 2) * CELL_W;
      const y = cursorY + row * CELL_H;
      map.set(node.node_id, { x, y });
    });
    cursorY += rows * CELL_H + BAND_GAP;
  }
}

/** Force simulation for the connected cast (characters + named entities). */
function computeForceCast(nodes: GraphNode[], edges: GraphEdge[], radius: number): GraphLayoutMap {
  const n = nodes.length;
  if (n === 0) return new Map();

  const byId = new Map<string, GraphNode>();
  nodes.forEach((node) => byId.set(node.node_id, node));

  // Deterministic phyllotaxis seeding so clusters start untangled.
  const golden = Math.PI * (3 - Math.sqrt(5));
  const simNodes: SimNode[] = nodes.map((node, i) => {
    const seed = hashId(node.node_id);
    const angle = i * golden + rand01(seed) * 0.6;
    const r = radius * 0.4 * Math.sqrt((i + 0.5) / n);
    const importance = Math.max(0, Math.min(1, node.importance || 0));
    return {
      id: node.node_id,
      x: Math.cos(angle) * r,
      y: Math.sin(angle) * r,
      // The force cast only ever holds the character constellation now — banded
      // concepts are placed separately, so seals keep a tight, uniform clearance.
      radius: nodeRadius(node) + 10,
      strength: 0.35 + (1 - importance) * 0.5,
    };
  });

  const links: SimulationLinkDatum<SimNode>[] = edges
    .filter((e) => byId.has(e.source_node_id) && byId.has(e.target_node_id))
    .map((e) => ({ source: e.source_node_id, target: e.target_node_id }));

  // Cluster hubs: the strongest member of each cluster_id.
  const clusterHub = new Map<string, SimNode>();
  for (const simNode of simNodes) {
    const node = byId.get(simNode.id)!;
    const key = node.cluster_id || "__none__";
    const hub = clusterHub.get(key);
    if (!hub) {
      clusterHub.set(key, simNode);
    } else {
      const hubNode = byId.get(hub.id)!;
      if ((node.importance || 0) > (hubNode.importance || 0)) clusterHub.set(key, simNode);
    }
  }
  const hubOf = (simNode: SimNode): SimNode => {
    const node = byId.get(simNode.id)!;
    return clusterHub.get(node.cluster_id || "__none__") ?? simNode;
  };

  // A tiny custom cluster force: every node is gently attracted to the current
  // position of its cluster's hub, gathering related characters into legible
  // neighbourhoods without pinning anyone rigidly.
  function makeClusterForce(hubOf: (d: SimNode) => SimNode, strengthOf: (d: SimNode) => number): Force<SimNode, undefined> {
    let nodes: SimNode[] = [];
    const force = (alpha: number) => {
      for (const d of nodes) {
        const hub = hubOf(d);
        if (hub === d) continue;
        const k = strengthOf(d) * alpha * 0.06;
        d.vx = (d.vx ?? 0) + (hub.x - d.x) * k;
        d.vy = (d.vy ?? 0) + (hub.y - d.y) * k;
      }
    };
    force.initialize = (initNodes: SimNode[]) => {
      nodes = initNodes;
    };
    return force as Force<SimNode, undefined>;
  }

  const spread = Math.max(360, radius);
  const simulation = forceSimulation<SimNode>(simNodes)
    .force(
      "charge",
      forceManyBody<SimNode>().strength((d) => (d.radius > 80 ? -320 : -150 - d.radius * 4)),
    )
    .force(
      "link",
      forceLink<SimNode, SimulationLinkDatum<SimNode>>(links)
        .id((d) => d.id)
        .distance((link) => {
          const a = link.source as SimNode;
          const b = link.target as SimNode;
          const base = Math.max(170, spread / Math.sqrt(Math.max(n, 1)));
          return (a.radius > 80 || b.radius > 80) ? base * 1.7 : base;
        })
        .strength(0.35),
    )
    .force("x", forceX<SimNode>(0).strength(0.04))
    .force("y", forceY<SimNode>(0).strength(0.045))
    .force("cluster", makeClusterForce(hubOf, (d) => d.strength))
    .force(
      "collide",
      forceCollide<SimNode>()
        .radius((d) => d.radius)
        .strength(0.95)
        .iterations(4),
    )
    .stop();

  const ticks = Math.max(120, Math.min(300, Math.round(9000 / Math.max(n, 1)) + 80));
  for (let i = 0; i < ticks; i++) simulation.tick();

  const map: GraphLayoutMap = new Map();
  for (const simNode of simNodes) {
    map.set(simNode.id, { x: simNode.x, y: simNode.y });
  }
  return map;
}
