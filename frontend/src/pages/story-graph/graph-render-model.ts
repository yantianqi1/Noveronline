/**
 * Graph render model — D3 data normalization, parallel edges, self-loops, curvature.
 * Ported from src-vue/views/story-graph/storyGraphRenderModel.js.
 */

const BASE_LINK_DISTANCE = 150;
const LINK_DISTANCE_STEP = 50;
const LOOP_RADIUS = 30;
const LOOP_RADIUS_STEP = 14;
const CURVE_STEP = 0.6;

const TYPE_COLOR_PALETTE = [
  "#FF6B35", "#004E89", "#7B2D8E", "#1A936F", "#C5283D",
  "#E9724C", "#3498db", "#9b59b6", "#27ae60", "#f39c12",
] as const;

const TYPE_COLOR_ORDER = [
  "character", "organization", "faction", "group", "artifact",
  "knowledgeitem", "plotevent", "location", "rulesystem", "unknown",
] as const;

const TYPE_LABELS: Record<string, string> = {
  character: "\u89D2\u8272",
  organization: "\u7EC4\u7EC7",
  faction: "\u52BF\u529B",
  group: "\u7FA4\u4F53",
  artifact: "\u7269\u4EF6",
  knowledgeitem: "\u77E5\u8BC6",
  plotevent: "\u4E8B\u4EF6",
  location: "\u5730\u70B9",
  rulesystem: "\u89C4\u5219",
  unknown: "\u672A\u5206\u7C7B",
};

const TYPE_COLOR_MAP: Record<string, string> = {};
for (let i = 0; i < TYPE_COLOR_ORDER.length; i++) {
  TYPE_COLOR_MAP[TYPE_COLOR_ORDER[i]!] = TYPE_COLOR_PALETTE[i]!;
}

export function normalizeEntityType(value: string | undefined): string {
  const normalized = String(value || "").trim().toLowerCase();
  return normalized || "unknown";
}

export function getTypeColor(type: string): string {
  const normalized = normalizeEntityType(type);
  if (TYPE_COLOR_MAP[normalized]) return TYPE_COLOR_MAP[normalized]!;
  const hash = [...normalized].reduce((acc, c) => acc + c.charCodeAt(0), 0);
  return TYPE_COLOR_PALETTE[hash % TYPE_COLOR_PALETTE.length]!;
}

export function truncateNodeLabel(value: string, maxLength = 8): string {
  const label = String(value || "");
  if (label.length <= maxLength) return label;
  return `${label.slice(0, maxLength)}\u2026`;
}

export interface LegendItem {
  key: string;
  label: string;
  color: string;
  count: number;
}

export function buildLegendItems({
  nodes = [],
  typeOptions = [],
}: {
  nodes?: Array<{ normalizedType?: string; entity_type?: string }>;
  typeOptions?: Array<{ key: string; label: string }>;
} = {}): LegendItem[] {
  const counts: Record<string, number> = {};
  for (const node of nodes) {
    const type = normalizeEntityType(node.normalizedType || node.entity_type);
    counts[type] = (counts[type] || 0) + 1;
  }
  const optionLabels = new Map(
    typeOptions.map((item) => [normalizeEntityType(item.key), item.label]),
  );
  const orderedKeys = typeOptions
    .map((item) => normalizeEntityType(item.key))
    .filter((key, index, list) => list.indexOf(key) === index && (counts[key] || 0) > 0);
  const extraKeys = Object.keys(counts)
    .filter((key) => !orderedKeys.includes(key))
    .sort((a, b) => a.localeCompare(b, "zh-Hans-CN"));

  return [...orderedKeys, ...extraKeys].map((key) => ({
    key,
    label: optionLabels.get(key) || TYPE_LABELS[key] || key,
    color: getTypeColor(key),
    count: counts[key] || 0,
  }));
}

export interface RenderableNode {
  id: string;
  color: string;
  normalizedType: string;
  raw: Record<string, unknown>;
  // d3 simulation fields
  x?: number;
  y?: number;
  fx?: number | null;
  fy?: number | null;
  vx?: number;
  vy?: number;
  index?: number;
}

export interface RenderableEdge {
  id: string;
  pairKey: string;
  pairTotal: number;
  sourceId: string;
  targetId: string;
  source: string;
  target: string;
  isSelfLoop: boolean;
  linkDistance: number;
  weight: number;
  curvature?: number;
  loopRadius?: number;
  raw: Record<string, unknown>;
}

export interface RenderableGraphData {
  nodes: RenderableNode[];
  edges: RenderableEdge[];
  adjacencyByNodeId: Map<string, Set<string>>;
}

function resolveNodeId(node: Record<string, unknown>): string {
  return String(node.id || node.uuid || "");
}

function resolveEdgeId(edge: Record<string, unknown>, index: number): string {
  return String(edge.uuid || edge.id || `edge_${index}`);
}

function resolveEdgeNodeId(edge: Record<string, unknown>, key: string): string {
  return String(edge[key] || "");
}

function buildPairKey(sourceId: string, targetId: string): string {
  return [sourceId, targetId].sort().join("::");
}

function countPairTotals(edges: Array<Record<string, unknown>>): Record<string, number> {
  return edges.reduce((acc: Record<string, number>, edge) => {
    const sourceId = resolveEdgeNodeId(edge, "source_id");
    const targetId = resolveEdgeNodeId(edge, "target_id");
    const pairKey = buildPairKey(sourceId, targetId);
    acc[pairKey] = (acc[pairKey] || 0) + 1;
    return acc;
  }, {});
}

function buildCurveIndex(position: number, total: number): number {
  return position - (total - 1) / 2;
}

function buildCurveValue(curvatureIndex: number, total: number): number {
  if (total <= 1) return 0;
  const offset = curvatureIndex >= 0 ? curvatureIndex + 0.5 : curvatureIndex - 0.5;
  return offset * CURVE_STEP;
}

export function buildNeighborStrengthMap(
  edges: RenderableEdge[],
  selectedNodeId: string | null,
): Map<string, number> {
  if (!selectedNodeId) return new Map();
  const neighborWeights = new Map<string, number>();
  for (const edge of edges) {
    if (edge.isSelfLoop) continue;
    if (edge.sourceId === selectedNodeId) {
      neighborWeights.set(edge.targetId, (neighborWeights.get(edge.targetId) || 0) + (edge.weight || 1));
    } else if (edge.targetId === selectedNodeId) {
      neighborWeights.set(edge.sourceId, (neighborWeights.get(edge.sourceId) || 0) + (edge.weight || 1));
    }
  }
  const maxWeight = Math.max(...neighborWeights.values(), 1);
  const normalized = new Map<string, number>();
  for (const [nodeId, weight] of neighborWeights) {
    normalized.set(nodeId, weight / maxWeight);
  }
  return normalized;
}

export function buildRenderableGraphData({
  nodes = [],
  edges = [],
}: {
  nodes?: Array<Record<string, unknown>>;
  edges?: Array<Record<string, unknown>>;
} = {}): RenderableGraphData {
  const normalizedNodes: RenderableNode[] = nodes.map((node, index) => {
    const id = resolveNodeId(node) || `node_${index}`;
    const normalizedType = normalizeEntityType(
      String(node.normalizedType || node.entity_type || ""),
    );
    return { id, color: getTypeColor(normalizedType), normalizedType, raw: node };
  });

  const nodeIds = new Set(normalizedNodes.map((n) => n.id));
  const filteredEdges = edges.filter((edge) => {
    const sourceId = resolveEdgeNodeId(edge, "source_id");
    const targetId = resolveEdgeNodeId(edge, "target_id");
    return nodeIds.has(sourceId) && nodeIds.has(targetId);
  });
  const pairTotals = countPairTotals(filteredEdges);
  const pairSeen = new Map<string, number>();
  const selfLoopSeen = new Map<string, number>();

  const normalizedEdges: RenderableEdge[] = filteredEdges.map((edge, index) => {
    const sourceId = resolveEdgeNodeId(edge, "source_id");
    const targetId = resolveEdgeNodeId(edge, "target_id");
    const pairKey = buildPairKey(sourceId, targetId);
    const pairTotal = pairTotals[pairKey] || 1;
    const weight = Number(edge.weight || 1);

    if (sourceId === targetId) {
      const loopIndex = selfLoopSeen.get(sourceId) || 0;
      selfLoopSeen.set(sourceId, loopIndex + 1);
      return {
        id: resolveEdgeId(edge, index),
        pairKey,
        pairTotal,
        sourceId,
        targetId,
        source: sourceId,
        target: targetId,
        isSelfLoop: true,
        loopRadius: LOOP_RADIUS + loopIndex * LOOP_RADIUS_STEP,
        linkDistance: BASE_LINK_DISTANCE + (pairTotal - 1) * LINK_DISTANCE_STEP,
        weight,
        raw: edge,
      };
    }

    const pairIndex = pairSeen.get(pairKey) || 0;
    pairSeen.set(pairKey, pairIndex + 1);
    const curvatureIndex = buildCurveIndex(pairIndex, pairTotal);
    const isCanonicalDirection = [sourceId, targetId].sort()[0] === sourceId;
    const curvature = buildCurveValue(curvatureIndex, pairTotal);

    return {
      id: resolveEdgeId(edge, index),
      pairKey,
      pairTotal,
      sourceId,
      targetId,
      source: sourceId,
      target: targetId,
      isSelfLoop: false,
      curvature: isCanonicalDirection ? curvature : -curvature,
      linkDistance: BASE_LINK_DISTANCE + (pairTotal - 1) * LINK_DISTANCE_STEP,
      weight,
      raw: edge,
    };
  });

  // Build adjacency map
  const adjacencyByNodeId = new Map<string, Set<string>>();
  for (const edge of normalizedEdges) {
    if (!adjacencyByNodeId.has(edge.sourceId)) adjacencyByNodeId.set(edge.sourceId, new Set());
    adjacencyByNodeId.get(edge.sourceId)!.add(edge.id);
    if (!adjacencyByNodeId.has(edge.targetId)) adjacencyByNodeId.set(edge.targetId, new Set());
    adjacencyByNodeId.get(edge.targetId)!.add(edge.id);
  }

  return { nodes: normalizedNodes, edges: normalizedEdges, adjacencyByNodeId };
}
