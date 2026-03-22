const NODE_LABEL_THRESHOLD = 24;
const LABEL_LIMIT = 18;

export const DEFAULT_GRAPH_TYPE_VISIBILITY = Object.freeze({
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
});

export const GRAPH_TYPE_OPTIONS = Object.freeze([
  { key: "character", label: "角色" },
  { key: "organization", label: "组织" },
  { key: "faction", label: "势力" },
  { key: "artifact", label: "物件" },
  { key: "plotevent", label: "事件" },
  { key: "location", label: "地点" },
]);

const TYPE_PRIORITY = Object.freeze({
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
});

function normalizeType(value) {
  const type = String(value || "").trim().toLowerCase();
  return type || "unknown";
}

function nodeId(node) {
  return node.id || node.uuid || "";
}

function edgeNodeId(edge, key) {
  return edge[key] || "";
}

function degreeMap(nodes, edges) {
  const map = Object.fromEntries(nodes.map((node) => [nodeId(node), 0]));
  for (const edge of edges) {
    const sourceId = edgeNodeId(edge, "source_id");
    const targetId = edgeNodeId(edge, "target_id");
    if (sourceId in map) {
      map[sourceId] += 1;
    }
    if (targetId in map) {
      map[targetId] += 1;
    }
  }
  return map;
}

function typeRank(type) {
  return TYPE_PRIORITY[type] ?? TYPE_PRIORITY.unknown;
}

export function shouldRenderNodeLabels(nodeCount) {
  return nodeCount <= NODE_LABEL_THRESHOLD;
}

export function buildGraphDisplayState({
  nodes = [],
  edges = [],
  visibleTypes = DEFAULT_GRAPH_TYPE_VISIBILITY,
} = {}) {
  const normalizedNodes = nodes.map((node) => ({
    ...node,
    normalizedType: normalizeType(node.entity_type),
  }));
  const countsByType = normalizedNodes.reduce((accumulator, node) => {
    const key = node.normalizedType;
    accumulator[key] = (accumulator[key] || 0) + 1;
    return accumulator;
  }, {});
  const allowedNodeIds = new Set(
    normalizedNodes
      .filter((node) => visibleTypes[node.normalizedType] ?? false)
      .map((node) => nodeId(node)),
  );
  const visibleNodes = normalizedNodes.filter((node) => allowedNodeIds.has(nodeId(node)));
  const visibleEdges = edges.filter((edge) =>
    allowedNodeIds.has(edgeNodeId(edge, "source_id")) &&
    allowedNodeIds.has(edgeNodeId(edge, "target_id")),
  );
  return {
    countsByType,
    visibleNodes,
    visibleEdges,
  };
}

export function buildHighlightedNodeIds(nodes = [], edges = [], maxLabels = LABEL_LIMIT) {
  const degrees = degreeMap(nodes, edges);
  return new Set(
    [...nodes]
      .sort((left, right) => {
        const degreeDelta = (degrees[nodeId(right)] || 0) - (degrees[nodeId(left)] || 0);
        if (degreeDelta !== 0) {
          return degreeDelta;
        }
        const typeDelta = typeRank(left.normalizedType) - typeRank(right.normalizedType);
        if (typeDelta !== 0) {
          return typeDelta;
        }
        return String(left.name || "").localeCompare(String(right.name || ""), "zh-Hans-CN");
      })
      .slice(0, maxLabels)
      .map((node) => nodeId(node)),
  );
}
