/**
 * Graph view model — display state, type visibility, highlighted node selection.
 * Ported from src-vue/views/story-graph/storyGraphViewModel.js.
 */

export interface GraphNodeVM {
  id: string;
  name: string;
  entity_type: string;
  summary: string;
  attributes: Record<string, unknown>;
  normalizedType?: string;
}

export interface GraphEdgeVM {
  id: string;
  source_id: string;
  target_id: string;
  source_name: string;
  target_name: string;
  name: string;
  fact: string;
  weight: number;
}

const NODE_LABEL_THRESHOLD = 24;
const LABEL_LIMIT = 18;

export const DEFAULT_GRAPH_TYPE_VISIBILITY: Record<string, boolean> = {
  character: true,
  organization: true,
  faction: true,
  group: true,
  artifact: false,
  knowledgeitem: false,
  plotevent: false,
  location: false,
  rulesystem: false,
  unknown: false,
};

export const GRAPH_TYPE_OPTIONS = [
  { key: "character", label: "\u89D2\u8272" },
  { key: "organization", label: "\u7EC4\u7EC7" },
  { key: "faction", label: "\u52BF\u529B" },
  { key: "artifact", label: "\u7269\u4EF6" },
  { key: "plotevent", label: "\u4E8B\u4EF6" },
  { key: "location", label: "\u5730\u70B9" },
] as const;

const TYPE_PRIORITY: Record<string, number> = {
  character: 0,
  organization: 1,
  faction: 2,
  group: 3,
  artifact: 4,
  knowledgeitem: 5,
  plotevent: 6,
  rulesystem: 7,
  location: 8,
  unknown: 9,
};

function normalizeType(value: string | undefined): string {
  const type = String(value || "").trim().toLowerCase();
  return type || "unknown";
}

function nodeId(node: GraphNodeVM): string {
  return node.id || "";
}

function edgeNodeId(edge: GraphEdgeVM, key: "source_id" | "target_id"): string {
  return edge[key] || "";
}

function degreeMap(nodes: GraphNodeVM[], edges: GraphEdgeVM[]): Record<string, number> {
  const map: Record<string, number> = {};
  for (const node of nodes) map[nodeId(node)] = 0;
  for (const edge of edges) {
    const sourceId = edgeNodeId(edge, "source_id");
    const targetId = edgeNodeId(edge, "target_id");
    if (sourceId in map) map[sourceId]! += 1;
    if (targetId in map) map[targetId]! += 1;
  }
  return map;
}

function typeRank(type: string): number {
  return TYPE_PRIORITY[type] ?? TYPE_PRIORITY.unknown!;
}

export function shouldRenderNodeLabels(nodeCount: number): boolean {
  return nodeCount <= NODE_LABEL_THRESHOLD;
}

export interface GraphDisplayState {
  countsByType: Record<string, number>;
  visibleNodes: (GraphNodeVM & { normalizedType: string })[];
  visibleEdges: GraphEdgeVM[];
}

export function buildGraphDisplayState({
  nodes = [],
  edges = [],
  visibleTypes = DEFAULT_GRAPH_TYPE_VISIBILITY,
}: {
  nodes?: GraphNodeVM[];
  edges?: GraphEdgeVM[];
  visibleTypes?: Record<string, boolean>;
} = {}): GraphDisplayState {
  const normalizedNodes = nodes.map((node) => ({
    ...node,
    normalizedType: normalizeType(node.entity_type),
  }));
  const countsByType: Record<string, number> = {};
  for (const node of normalizedNodes) {
    const key = node.normalizedType;
    countsByType[key] = (countsByType[key] || 0) + 1;
  }
  const allowedNodeIds = new Set(
    normalizedNodes
      .filter((node) => visibleTypes[node.normalizedType] ?? false)
      .map(nodeId),
  );
  const visibleNodes = normalizedNodes.filter((node) => allowedNodeIds.has(nodeId(node)));
  const visibleEdges = edges.filter(
    (edge) =>
      allowedNodeIds.has(edgeNodeId(edge, "source_id")) &&
      allowedNodeIds.has(edgeNodeId(edge, "target_id")),
  );
  return { countsByType, visibleNodes, visibleEdges };
}

export function buildHighlightedNodeIds(
  nodes: (GraphNodeVM & { normalizedType: string })[] = [],
  edges: GraphEdgeVM[] = [],
  maxLabels = LABEL_LIMIT,
): Set<string> {
  const degrees = degreeMap(nodes, edges);
  return new Set(
    [...nodes]
      .sort((left, right) => {
        const degreeDelta = (degrees[nodeId(right)] || 0) - (degrees[nodeId(left)] || 0);
        if (degreeDelta !== 0) return degreeDelta;
        const typeDelta = typeRank(left.normalizedType) - typeRank(right.normalizedType);
        if (typeDelta !== 0) return typeDelta;
        return String(left.name || "").localeCompare(String(right.name || ""), "zh-Hans-CN");
      })
      .slice(0, maxLabels)
      .map(nodeId),
  );
}
