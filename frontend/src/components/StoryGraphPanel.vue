<template>
  <div class="graph-panel stack">
    <header class="panel-toolbar workbench-card">
      <div class="toolbar-main">
        <h3 class="title-ancient">故事实体图谱</h3>
        <div class="graph-controls">
          <button class="btn subtle small" :disabled="loading" @click="$emit('refresh')">
            {{ loading ? "同步中..." : "同步图谱" }}
          </button>
          <button class="btn subtle small" @click="resetVisibleTypes">还原视角</button>
          <button class="btn subtle small" @click="showEdgeLabels = !showEdgeLabels">
            {{ showEdgeLabels ? "隐去关系" : "显现关系" }}
          </button>
        </div>
      </div>
      <div class="type-filters">
        <button
          v-for="item in typeOptions"
          :key="item.key"
          class="type-tag"
          :class="[item.key.toLowerCase(), { active: visibleTypes[item.key] }]"
          @click="toggleType(item.key)"
        >
          {{ item.label }} <small>{{ countsByType[item.key] || 0 }}</small>
        </button>
      </div>
    </header>

    <div class="panel-layout">
      <section class="canvas-container workbench-card">
        <div class="canvas-header">
          <span class="mono">已映射 {{ positionedNodes.length }} / {{ props.nodes.length }} 实体</span>
        </div>
        <svg v-if="positionedNodes.length" viewBox="0 0 900 600" class="graph-canvas">
          <!-- Edges -->
          <line
            v-for="edge in normalizedEdges"
            :key="edge.id"
            :x1="getNode(edge.source_id)?.x || 0"
            :y1="getNode(edge.source_id)?.y || 0"
            :x2="getNode(edge.target_id)?.x || 0"
            :y2="getNode(edge.target_id)?.y || 0"
            class="edge-line"
            :class="{ highlighted: isEdgeHighlighted(edge) }"
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
            {{ edge.name || "关联" }}
          </text>

          <!-- Nodes -->
          <g v-for="node in positionedNodes" :key="node.id" class="node-group" @click="selectNode(node)">
            <circle
              :cx="node.x"
              :cy="node.y"
              :r="node.id === selectedNode?.id ? 16 : 10"
              class="node-circle"
              :class="[node.entity_type.toLowerCase(), { selected: node.id === selectedNode?.id }]"
            />
            <text
              v-if="shouldShowNodeLabel(node)"
              :x="node.x"
              :y="node.y + 24"
              class="node-label"
              text-anchor="middle"
            >
              {{ node.name }}
            </text>
          </g>
        </svg>
        <div v-else class="empty-canvas">
          <div class="empty-icon">🕸️</div>
          <p>图谱尚未织就。请先在左侧选择卷宗并点击构建。</p>
        </div>
      </section>

      <aside class="inspector-container">
        <StoryGraphInspector :selected-node="selectedNode" :selected-edge="selectedEdge" />
      </aside>
    </div>
  </div>
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

const graphDisplayState = computed(() =>
  buildGraphDisplayState({ nodes: props.nodes, edges: props.edges, visibleTypes }),
);

const countsByType = computed(() => graphDisplayState.value.countsByType);
const highlightedNodeIds = computed(() =>
  buildHighlightedNodeIds(graphDisplayState.value.visibleNodes, graphDisplayState.value.visibleEdges),
);

const positionedNodes = computed(() => {
  const nodesByType = groupNodesByType(graphDisplayState.value.visibleNodes);
  const centerX = 450;
  const centerY = 300;
  return Object.entries(nodesByType).flatMap(([type, nodes]) =>
    nodes.map((node, index) => {
      const angleStep = nodes.length ? (Math.PI * 2) / nodes.length : 0;
      const angle = angleStep * index;
      const radius = ringRadius(type);
      return {
        ...node,
        x: centerX + Math.cos(angle) * radius + (Math.random() - 0.5) * 10,
        y: centerY + Math.sin(angle) * radius + (Math.random() - 0.5) * 10,
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
  return positionedNodes.value.find((node) => node.id === nodeId);
}

function ringRadius(type) {
  const t = String(type).toLowerCase();
  if (t === "character") return 150;
  if (["organization", "faction", "group"].includes(t)) return 240;
  if (["artifact", "knowledgeitem"].includes(t)) return 320;
  if (t === "plotevent") return 100;
  return 360;
}

function groupNodesByType(nodes) {
  return nodes.reduce((acc, node) => {
    const type = String(node.normalizedType || "unknown");
    if (!acc[type]) acc[type] = [];
    acc[type].push(node);
    return acc;
  }, {});
}

function resetVisibleTypes() {
  Object.keys(visibleTypes).forEach(k => visibleTypes[k] = DEFAULT_GRAPH_TYPE_VISIBILITY[k]);
}

function toggleType(type) { visibleTypes[type] = !visibleTypes[type]; }

function shouldShowNodeLabel(node) {
  return (
    shouldRenderNodeLabels(positionedNodes.value.length) ||
    highlightedNodeIds.value.has(node.id) ||
    selectedNode.value?.id === node.id
  );
}

function isEdgeHighlighted(edge) {
  if (!selectedNode.value) return false;
  return edge.source_id === selectedNode.value.id || edge.target_id === selectedNode.value.id;
}

function selectNode(node) {
  selectedEdge.value = null;
  selectedNode.value = node;
}

function selectEdge(edge) {
  selectedNode.value = null;
  selectedEdge.value = edge;
}

watch(() => positionedNodes.value.map(n => n.id), (ids) => {
  if (selectedNode.value && !ids.includes(selectedNode.value.id)) selectedNode.value = null;
});
</script>

<style scoped>
.graph-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.panel-toolbar {
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.toolbar-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.graph-controls {
  display: flex;
  gap: var(--space-xs);
}

.type-filters {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-xs);
}

.type-tag {
  padding: 4px 10px;
  border-radius: var(--radius-full);
  font-size: 12px;
  cursor: pointer;
  border: 1px solid var(--line-soft);
  background: var(--bg-panel-soft);
  color: var(--text-dim);
  transition: all 0.2s ease;
}

.type-tag.active {
  color: var(--text-main);
  border-color: var(--line-medium);
  background: #fff;
}

.type-tag.character.active { border-color: var(--accent-copper); color: var(--accent-copper-deep); }
.type-tag.organization.active { border-color: var(--accent-blue); color: var(--accent-blue); }

.panel-layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: var(--space-lg);
  flex: 1;
  min-height: 0;
}

.canvas-container {
  position: relative;
  background-image: 
    radial-gradient(var(--line-soft) 1px, transparent 1px),
    linear-gradient(var(--bg-paper-warm), var(--bg-paper-warm));
  background-size: 40px 40px, 100% 100%;
  overflow: hidden;
}

.canvas-header {
  position: absolute;
  top: var(--space-sm);
  left: var(--space-md);
  font-size: 11px;
  color: var(--text-dim);
}

.graph-canvas {
  width: 100%;
  height: 100%;
}

.edge-line {
  stroke: var(--line-medium);
  stroke-width: 1;
  opacity: 0.4;
  cursor: pointer;
  transition: all 0.2s ease;
}

.edge-line:hover, .edge-line.highlighted {
  stroke: var(--accent-copper);
  stroke-width: 2;
  opacity: 1;
}

.edge-label {
  font-size: 10px;
  fill: var(--text-dim);
  pointer-events: none;
}

.node-circle {
  cursor: pointer;
  fill: var(--line-medium);
  stroke: #fff;
  stroke-width: 2;
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.node-circle.character { fill: var(--accent-copper); }
.node-circle.organization { fill: var(--accent-blue); }
.node-circle.plotevent { fill: var(--accent-seal); }

.node-circle.selected {
  stroke: var(--bg-ink);
  stroke-width: 3;
  filter: drop-shadow(0 0 8px rgba(0,0,0,0.2));
}

.node-label {
  font-size: 12px;
  fill: var(--text-main);
  pointer-events: none;
  font-family: "ZCOOL XiaoWei", serif;
}

.empty-canvas {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: var(--text-dim);
}

.empty-icon { font-size: 64px; margin-bottom: var(--space-md); }

.inspector-container {
  min-height: 0;
  overflow-y: auto;
}

@media (max-width: 1200px) {
  .panel-layout { grid-template-columns: 1fr; }
  .inspector-container { display: none; }
}
</style>

