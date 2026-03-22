<template>
  <section class="workbench-card panel">
    <div class="panel-head">
      <div>
        <h2 class="card-title">故事图谱面板</h2>
        <p>可视化展示角色、势力与关系，支持节点和边的细节侧栏。</p>
      </div>
      <div class="toolbar-row">
        <button class="btn" :disabled="loading" @click="$emit('refresh')">
          {{ loading ? "刷新中..." : "刷新图谱" }}
        </button>
        <button class="btn" @click="resetVisibleTypes">核心视图</button>
        <button class="btn" @click="showEdgeLabels = !showEdgeLabels">
          {{ showEdgeLabels ? "隐藏关系标签" : "显示关系标签" }}
        </button>
      </div>
    </div>

    <div class="filter-row">
      <button
        v-for="item in typeOptions"
        :key="item.key"
        class="btn subtle"
        :class="{ active: visibleTypes[item.key] }"
        type="button"
        @click="toggleType(item.key)"
      >
        {{ item.label }} {{ countsByType[item.key] || 0 }}
      </button>
      <span class="graph-meta mono">当前显示 {{ positionedNodes.length }} / {{ props.nodes.length }} 个节点</span>
    </div>

    <div class="panel-body">
      <div class="canvas-area">
        <svg v-if="positionedNodes.length" viewBox="0 0 900 520" class="graph-svg">
          <line
            v-for="edge in normalizedEdges"
            :key="edge.id"
            :x1="getNode(edge.source_id)?.x || 0"
            :y1="getNode(edge.source_id)?.y || 0"
            :x2="getNode(edge.target_id)?.x || 0"
            :y2="getNode(edge.target_id)?.y || 0"
            class="edge-line"
            @click="selectEdge(edge)"
          />
          <text
            v-for="edge in normalizedEdges"
            v-show="showEdgeLabels"
            :key="`${edge.id}_label`"
            :x="((getNode(edge.source_id)?.x || 0) + (getNode(edge.target_id)?.x || 0)) / 2"
            :y="((getNode(edge.source_id)?.y || 0) + (getNode(edge.target_id)?.y || 0)) / 2"
            class="edge-label"
          >
            {{ edge.name || "关系" }}
          </text>
          <g v-for="node in positionedNodes" :key="node.id" @click="selectNode(node)">
            <circle
              :cx="node.x"
              :cy="node.y"
              :r="node.id === selectedNode?.id ? 16 : 12"
              :fill="node.color"
              class="node-dot"
            />
            <text
              v-if="shouldShowNodeLabel(node)"
              :x="node.x + 14"
              :y="node.y + 4"
              class="node-name"
            >
              {{ node.name }}
            </text>
          </g>
        </svg>
        <div v-else class="empty-box">暂无图谱数据。可先选择项目并构建图谱。</div>
      </div>
      <StoryGraphInspector :selected-node="selectedNode" :selected-edge="selectedEdge" />
    </div>
  </section>
</template>

<script setup>
import { computed, reactive, ref, watch } from "vue";
import StoryGraphInspector from "./StoryGraphInspector.vue";
import {
  buildGraphDisplayState,
  buildHighlightedNodeIds,
  DEFAULT_GRAPH_TYPE_VISIBILITY,
  GRAPH_TYPE_OPTIONS,
  shouldRenderNodeLabels,
} from "../views/story-graph/storyGraphViewModel.js";

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
});

defineEmits(["refresh"]);

const showEdgeLabels = ref(false);
const selectedNode = ref(null);
const selectedEdge = ref(null);
const visibleTypes = reactive({ ...DEFAULT_GRAPH_TYPE_VISIBILITY });
const typeOptions = GRAPH_TYPE_OPTIONS;

const palette = {
  character: "#8f4f1f",
  organization: "#275a78",
  faction: "#386a4f",
  group: "#6b5f40",
};

const graphDisplayState = computed(() =>
  buildGraphDisplayState({
    nodes: props.nodes,
    edges: props.edges,
    visibleTypes,
  }),
);

const countsByType = computed(() => graphDisplayState.value.countsByType);
const highlightedNodeIds = computed(() =>
  buildHighlightedNodeIds(graphDisplayState.value.visibleNodes, graphDisplayState.value.visibleEdges),
);

const positionedNodes = computed(() => {
  const nodesByType = groupNodesByType(graphDisplayState.value.visibleNodes);
  const centerX = 390;
  const centerY = 250;
  return Object.entries(nodesByType).flatMap(([type, nodes]) =>
    nodes.map((node, index) => {
      const angleStep = nodes.length ? (Math.PI * 2) / nodes.length : 0;
      const angle = angleStep * index;
      const radius = ringRadius(type);
      return {
        ...node,
        color: palette[type] || "#866f4d",
        x: centerX + Math.cos(angle) * radius + ((index % 3) - 1) * 6,
        y: centerY + Math.sin(angle) * radius + ((index % 4) - 1.5) * 5,
      };
    }),
  );
});

const normalizedEdges = computed(() =>
  graphDisplayState.value.visibleEdges.map((edge, idx) => ({
    id: edge.uuid || edge.id || `edge_${idx}`,
    ...edge,
  }))
);

function getNode(nodeId) {
  return positionedNodes.value.find((node) => node.id === nodeId || node.uuid === nodeId);
}

function ringRadius(type) {
  if (type === "character") {
    return 135;
  }
  if (type === "organization" || type === "faction" || type === "group") {
    return 220;
  }
  if (type === "artifact" || type === "knowledgeitem") {
    return 290;
  }
  if (type === "plotevent") {
    return 95;
  }
  return 330;
}

function groupNodesByType(nodes) {
  return nodes.reduce((accumulator, node) => {
    const type = String(node.normalizedType || "unknown");
    if (!accumulator[type]) {
      accumulator[type] = [];
    }
    accumulator[type].push(node);
    return accumulator;
  }, {});
}

function resetVisibleTypes() {
  for (const key of Object.keys(visibleTypes)) {
    visibleTypes[key] = DEFAULT_GRAPH_TYPE_VISIBILITY[key];
  }
}

function toggleType(type) {
  visibleTypes[type] = !visibleTypes[type];
}

function shouldShowNodeLabel(node) {
  return (
    shouldRenderNodeLabels(positionedNodes.value.length) ||
    highlightedNodeIds.value.has(node.id) ||
    selectedNode.value?.id === node.id
  );
}

function selectNode(node) {
  selectedEdge.value = null;
  selectedNode.value = node;
}

function selectEdge(edge) {
  selectedNode.value = null;
  selectedEdge.value = edge;
}

watch(
  () => positionedNodes.value.map((node) => node.id),
  (visibleIds) => {
    if (selectedNode.value && !visibleIds.includes(selectedNode.value.id)) {
      selectedNode.value = null;
    }
  },
);
</script>

<style scoped>
.panel {
  padding: 16px;
}

.panel-head p {
  margin: 6px 0 0;
  color: var(--text-sub);
}

.filter-row {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.btn.active {
  border-color: var(--line-strong);
  background: rgba(255, 252, 244, 0.92);
}

.graph-meta {
  color: var(--text-sub);
}

.panel-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 300px;
  gap: 12px;
  margin-top: 12px;
}

.canvas-area {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: linear-gradient(180deg, #fffcf4, #fbf5e8);
  min-height: 520px;
}

.graph-svg {
  width: 100%;
  height: 520px;
}

.edge-line {
  stroke: #c4b393;
  stroke-width: 1.6;
  cursor: pointer;
}

.edge-label {
  font-size: 11px;
  fill: #806d4e;
}

.node-dot {
  cursor: pointer;
  transition: r 120ms ease;
}

.node-name {
  font-size: 12px;
  fill: #2d2418;
}

.empty-box {
  min-height: 520px;
  display: grid;
  place-items: center;
  color: var(--text-sub);
}

@media (max-width: 1180px) {
  .panel-body {
    grid-template-columns: 1fr;
  }
}
</style>
