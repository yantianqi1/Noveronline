<template>
  <section class="workbench-card panel">
    <div class="panel-body">
      <div ref="canvasRef" class="canvas-area">
        <svg ref="svgRef" class="graph-svg" aria-label="故事图谱" />
        <div class="canvas-mask" aria-hidden="true"></div>
        <n-empty v-if="!visibleNodeCount" description="暂无图谱数据。可先选择项目并构建图谱。" class="empty-box" />
        <div v-if="legendItems.length" class="legend-card">
          <p class="legend-title">图例</p>
          <div class="legend-list">
            <span v-for="item in legendItems" :key="item.key" class="legend-item">
              <span class="legend-dot" :style="{ backgroundColor: item.color }"></span>
              {{ item.label }} {{ item.count }}
            </span>
          </div>
        </div>
      </div>

      <div class="right-col">
        <div class="panel-head">
          <h2 class="card-title">故事图谱面板</h2>
          <div class="toolbar-row">
            <n-button size="small" quaternary :disabled="loading" :loading="loading" @click="$emit('refresh')">
              刷新图谱
            </n-button>
            <n-button size="small" quaternary @click="resetVisibleTypes">核心视图</n-button>
            <n-button size="small" quaternary @click="showEdgeLabels = !showEdgeLabels">
              {{ showEdgeLabels ? "隐藏标签" : "显示标签" }}
            </n-button>
          </div>
        </div>

        <div class="filter-row">
          <n-button
            v-for="item in typeOptions"
            :key="item.key"
            size="small"
            :quaternary="!visibleTypes[item.key]"
            :type="visibleTypes[item.key] ? 'primary' : 'default'"
            @click="toggleType(item.key)"
          >
            {{ item.label }} {{ countsByType[item.key] || 0 }}
          </n-button>
          <span class="graph-meta mono">显示 {{ visibleNodeCount }} / {{ props.nodes.length }}</span>
        </div>

        <StoryGraphInspector :selected-node="selectedNode" :selected-edge="selectedEdge" :project-id="projectId" />
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";
import { NButton, NEmpty } from "naive-ui";

import StoryGraphInspector from "./StoryGraphInspector.vue";
import { createStoryGraphRenderer } from "../views/story-graph/storyGraphRenderer.js";
import {
  buildLegendItems,
  resolveEdgeId,
  resolveNodeId,
} from "../views/story-graph/storyGraphRenderModel.js";
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
  projectId: { type: String, default: "" },
});

defineEmits(["refresh"]);

const canvasRef = ref(null);
const svgRef = ref(null);
const renderer = ref(null);
const showEdgeLabels = ref(false);
const selectedNode = ref(null);
const selectedEdge = ref(null);
const visibleTypes = reactive({ ...DEFAULT_GRAPH_TYPE_VISIBILITY });
const typeOptions = GRAPH_TYPE_OPTIONS;

const graphDisplayState = computed(() =>
  buildGraphDisplayState({
    nodes: props.nodes,
    edges: props.edges,
    visibleTypes,
  }),
);

const visibleNodes = computed(() => graphDisplayState.value.visibleNodes);
const visibleEdges = computed(() => graphDisplayState.value.visibleEdges);
const visibleNodeCount = computed(() => visibleNodes.value.length);
const countsByType = computed(() => graphDisplayState.value.countsByType);
const highlightedNodeIds = computed(() =>
  buildHighlightedNodeIds(visibleNodes.value, visibleEdges.value),
);
const legendItems = computed(() =>
  buildLegendItems({ nodes: visibleNodes.value, typeOptions }),
);
const selectedNodeId = computed(() => resolveNodeId(selectedNode.value || {}));
const selectedEdgeId = computed(() => {
  const edge = selectedEdge.value;
  if (!edge) {
    return "";
  }

  const visibleIndex = visibleEdges.value.findIndex((item) => item === edge);
  return resolveEdgeId(edge, visibleIndex >= 0 ? visibleIndex : 0);
});
const visibleLabelNodeIds = computed(() => {
  if (shouldRenderNodeLabels(visibleNodeCount.value)) {
    return new Set(visibleNodes.value.map((node) => resolveNodeId(node)));
  }

  const labelIds = new Set(highlightedNodeIds.value);
  if (selectedNodeId.value) {
    labelIds.add(selectedNodeId.value);
  }
  return labelIds;
});

function resetVisibleTypes() {
  for (const key of Object.keys(visibleTypes)) {
    visibleTypes[key] = DEFAULT_GRAPH_TYPE_VISIBILITY[key];
  }
}

function toggleType(type) {
  visibleTypes[type] = !visibleTypes[type];
}

function clearSelection() {
  selectedNode.value = null;
  selectedEdge.value = null;
}

function handleNodeSelect(node) {
  selectedEdge.value = null;
  selectedNode.value = node;
}

function handleEdgeSelect(edge) {
  selectedNode.value = null;
  selectedEdge.value = edge;
}

function syncRenderer() {
  renderer.value?.setGraphData({
    nodes: visibleNodes.value,
    edges: visibleEdges.value,
  });
  renderer.value?.setShowEdgeLabels(showEdgeLabels.value);
  renderer.value?.setVisibleLabelNodeIds(visibleLabelNodeIds.value);
  renderer.value?.setSelection({
    selectedNodeId: selectedNodeId.value || null,
    selectedEdgeId: selectedEdgeId.value || null,
  });
}

watch([visibleNodes, visibleEdges], ([nodes, edges]) => {
  const visibleNodeIds = new Set(nodes.map((node) => resolveNodeId(node)));
  const visibleEdgeIds = new Set(edges.map((edge, index) => resolveEdgeId(edge, index)));

  if (selectedNode.value && !visibleNodeIds.has(selectedNodeId.value)) {
    selectedNode.value = null;
  }
  if (selectedEdge.value && !visibleEdgeIds.has(selectedEdgeId.value)) {
    selectedEdge.value = null;
  }

  renderer.value?.setGraphData({ nodes, edges });
});

watch(showEdgeLabels, (value) => {
  renderer.value?.setShowEdgeLabels(value);
});

watch(visibleLabelNodeIds, (nodeIds) => {
  renderer.value?.setVisibleLabelNodeIds(nodeIds);
});

watch([selectedNodeId, selectedEdgeId], ([nodeId, edgeId]) => {
  renderer.value?.setSelection({
    selectedNodeId: nodeId || null,
    selectedEdgeId: edgeId || null,
  });
});

onMounted(() => {
  if (!canvasRef.value || !svgRef.value) {
    return;
  }

  renderer.value = createStoryGraphRenderer({
    container: canvasRef.value,
    svg: svgRef.value,
    onNodeSelect: handleNodeSelect,
    onEdgeSelect: handleEdgeSelect,
    onCanvasSelect: clearSelection,
  });
  syncRenderer();
});

onBeforeUnmount(() => {
  renderer.value?.destroy();
  renderer.value = null;
});
</script>

<style scoped src="./StoryGraphPanel.css"></style>
