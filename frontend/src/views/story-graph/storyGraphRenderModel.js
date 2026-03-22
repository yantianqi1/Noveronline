const BASE_LINK_DISTANCE = 150;
const LINK_DISTANCE_STEP = 50;
const LOOP_RADIUS = 30;
const LOOP_RADIUS_STEP = 14;
const CURVE_STEP = 0.6;
const TYPE_COLOR_PALETTE = Object.freeze([
  "#FF6B35",
  "#004E89",
  "#7B2D8E",
  "#1A936F",
  "#C5283D",
  "#E9724C",
  "#3498db",
  "#9b59b6",
  "#27ae60",
  "#f39c12",
]);

const TYPE_COLOR_ORDER = Object.freeze([
  "character",
  "organization",
  "faction",
  "group",
  "artifact",
  "knowledgeitem",
  "plotevent",
  "location",
  "rulesystem",
  "unknown",
]);

const TYPE_LABELS = Object.freeze({
  character: "角色",
  organization: "组织",
  faction: "势力",
  group: "群体",
  artifact: "物件",
  knowledgeitem: "知识",
  plotevent: "事件",
  location: "地点",
  rulesystem: "规则",
  unknown: "未分类",
});

const TYPE_COLOR_MAP = Object.freeze(
  Object.fromEntries(TYPE_COLOR_ORDER.map((type, index) => [type, TYPE_COLOR_PALETTE[index]])),
);

export function normalizeEntityType(value) {
  const normalized = String(value || "").trim().toLowerCase();
  return normalized || "unknown";
}

export function resolveNodeId(node = {}) {
  return node.id || node.uuid || "";
}

export function resolveEdgeId(edge = {}, index = 0) {
  return edge.uuid || edge.id || `edge_${index}`;
}

function resolveEdgeNodeId(edge, key) {
  return edge[key] || "";
}

function pairKeyFor(sourceId, targetId) {
  return [sourceId, targetId].sort().join("::");
}

function countPairTotals(edges = []) {
  return edges.reduce((accumulator, edge) => {
    const sourceId = resolveEdgeNodeId(edge, "source_id");
    const targetId = resolveEdgeNodeId(edge, "target_id");
    const key = pairKeyFor(sourceId, targetId);
    accumulator[key] = (accumulator[key] || 0) + 1;
    return accumulator;
  }, {});
}

function centeredCurveIndex(position, total) {
  return position - (total - 1) / 2;
}

function curveValueFromIndex(curvatureIndex, total) {
  if (total <= 1) {
    return 0;
  }

  const direction = curvatureIndex >= 0 ? curvatureIndex + 0.5 : curvatureIndex - 0.5;
  return direction * CURVE_STEP;
}

function hashType(value) {
  return [...value].reduce((accumulator, char) => accumulator + char.charCodeAt(0), 0);
}

function labelForType(type, optionLabelMap) {
  return optionLabelMap.get(type) || TYPE_LABELS[type] || type;
}

export function getTypeColor(type) {
  const normalizedType = normalizeEntityType(type);
  if (TYPE_COLOR_MAP[normalizedType]) {
    return TYPE_COLOR_MAP[normalizedType];
  }

  const paletteIndex = hashType(normalizedType) % TYPE_COLOR_PALETTE.length;
  return TYPE_COLOR_PALETTE[paletteIndex];
}

export function truncateNodeLabel(value, maxLength = 8) {
  const label = String(value || "");
  if (label.length <= maxLength) {
    return label;
  }
  return `${label.slice(0, maxLength)}…`;
}

export function buildLegendItems({ nodes = [], typeOptions = [] } = {}) {
  const counts = nodes.reduce((accumulator, node) => {
    const type = normalizeEntityType(node.normalizedType || node.entity_type);
    accumulator[type] = (accumulator[type] || 0) + 1;
    return accumulator;
  }, {});
  const optionLabelMap = new Map(
    typeOptions.map((item) => [normalizeEntityType(item.key), item.label]),
  );
  const orderedKeys = typeOptions
    .map((item) => normalizeEntityType(item.key))
    .filter((key, index, keys) => keys.indexOf(key) === index && (counts[key] || 0) > 0);
  const extraKeys = Object.keys(counts)
    .filter((key) => !orderedKeys.includes(key))
    .sort((left, right) => left.localeCompare(right, "zh-Hans-CN"));

  return [...orderedKeys, ...extraKeys].map((key) => ({
    key,
    label: labelForType(key, optionLabelMap),
    color: getTypeColor(key),
    count: counts[key],
  }));
}

function normalizeRenderableNode(node, index) {
  const id = resolveNodeId(node) || `node_${index}`;
  const normalizedType = normalizeEntityType(node.normalizedType || node.entity_type);

  return {
    id,
    color: getTypeColor(normalizedType),
    normalizedType,
    raw: node,
  };
}

function normalizeRenderableEdge(edge, pairTotals, pairSeen, selfLoopSeen, index) {
  const sourceId = resolveEdgeNodeId(edge, "source_id");
  const targetId = resolveEdgeNodeId(edge, "target_id");
  const key = pairKeyFor(sourceId, targetId);
  const pairTotal = pairTotals[key] || 1;
  const isSelfLoop = sourceId === targetId;

  if (isSelfLoop) {
    const loopIndex = selfLoopSeen.get(sourceId) || 0;
    selfLoopSeen.set(sourceId, loopIndex + 1);
    return {
      id: resolveEdgeId(edge, index),
      pairKey: key,
      pairTotal,
      sourceId,
      targetId,
      source: sourceId,
      target: targetId,
      isSelfLoop: true,
      loopIndex,
      loopRadius: LOOP_RADIUS + loopIndex * LOOP_RADIUS_STEP,
      arcSweepFlag: 1,
      linkDistance: BASE_LINK_DISTANCE + (pairTotal - 1) * LINK_DISTANCE_STEP,
      raw: edge,
    };
  }

  const currentPairIndex = pairSeen.get(key) || 0;
  pairSeen.set(key, currentPairIndex + 1);
  const curvatureIndex = centeredCurveIndex(currentPairIndex, pairTotal);
  const isCanonicalDirection = [sourceId, targetId].sort()[0] === sourceId;
  const curvature = curveValueFromIndex(curvatureIndex, pairTotal);

  return {
    id: resolveEdgeId(edge, index),
    pairKey: key,
    pairTotal,
    pairIndex: currentPairIndex,
    curvatureIndex,
    curvature: isCanonicalDirection ? curvature : -curvature,
    sourceId,
    targetId,
    source: sourceId,
    target: targetId,
    isSelfLoop: false,
    linkDistance: BASE_LINK_DISTANCE + (pairTotal - 1) * LINK_DISTANCE_STEP,
    raw: edge,
  };
}

function buildAdjacencyMap(edges = []) {
  const adjacency = new Map();
  for (const edge of edges) {
    const sourceEdges = adjacency.get(edge.sourceId) || new Set();
    sourceEdges.add(edge.id);
    adjacency.set(edge.sourceId, sourceEdges);

    const targetEdges = adjacency.get(edge.targetId) || new Set();
    targetEdges.add(edge.id);
    adjacency.set(edge.targetId, targetEdges);
  }
  return adjacency;
}

export function buildRenderableGraphData({ nodes = [], edges = [] } = {}) {
  const normalizedNodes = nodes.map(normalizeRenderableNode);
  const nodeIds = new Set(normalizedNodes.map((node) => node.id));
  const filteredEdges = edges.filter((edge) => {
    const sourceId = resolveEdgeNodeId(edge, "source_id");
    const targetId = resolveEdgeNodeId(edge, "target_id");
    return nodeIds.has(sourceId) && nodeIds.has(targetId);
  });
  const pairTotals = countPairTotals(filteredEdges);
  const pairSeen = new Map();
  const selfLoopSeen = new Map();
  const normalizedEdges = filteredEdges.map((edge, index) =>
    normalizeRenderableEdge(edge, pairTotals, pairSeen, selfLoopSeen, index),
  );

  return {
    nodes: normalizedNodes,
    edges: normalizedEdges,
    adjacencyByNodeId: buildAdjacencyMap(normalizedEdges),
  };
}
