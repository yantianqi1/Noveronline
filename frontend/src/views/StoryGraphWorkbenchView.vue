<template>
  <div class="graph-workbench">
    <div class="workbench-toolbar workbench-card">
      <n-select
        v-model:value="projectId"
        :options="projectOptions"
        placeholder="-- 请选择卷宗 --"
        style="min-width: 180px"
        @update:value="refreshGraph"
      />

      <n-button type="primary" :disabled="!projectId" :loading="busy" @click="startBuildGraph">
        {{ busy ? "构建中..." : "启动图谱构建" }}
      </n-button>
      <n-button quaternary @click="loadProjects">刷新卷宗列表</n-button>
      <n-button :disabled="!projectId || busy" @click="openArchiveConfigurator">
        生成全量角色档案
      </n-button>

      <div v-if="taskMessage || taskError" class="status-indicator" :class="{ error: taskError }">
        <div class="status-pulse" v-if="busy"></div>
        <span class="mono">{{ taskError || taskMessage }}</span>
      </div>
    </div>

    <main class="workbench-main">
      <StoryGraphPanel
        :nodes="graphNodes"
        :edges="graphEdges"
        :loading="busy"
        :project-id="projectId"
        @refresh="refreshGraph"
      />
    </main>
    <AgentTemplateConfigurator
      :visible="configuratorVisible"
      :candidates="archiveCandidates"
      :busy="busy"
      :error="taskError"
      @close="closeArchiveConfigurator"
      @confirm="createArchives"
    />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { NButton, NSelect } from "naive-ui";
import StoryGraphPanel from "../components/StoryGraphPanel.vue";
import { buildGraph, getProject, getProjectGraph, getTask, listProjects } from "../api/project";
import { generateArchiveCandidates, generateArchives } from "../api/novel";
import AgentTemplateConfigurator from "./story-graph/AgentTemplateConfigurator.vue";
import { createGraphBuildTaskPoller } from "./story-graph/graphBuildTaskPoller.js";

const projects = ref([]);
const projectId = ref("");
const busy = ref(false);
const taskMessage = ref("");
const taskError = ref("");
const currentGraphId = ref("");
const graphNodes = ref([]);
const graphEdges = ref([]);
const configuratorVisible = ref(false);
const archiveCandidates = ref([]);
const pollGraphTask = createGraphBuildTaskPoller({ getTask });

const projectOptions = computed(() =>
  projects.value.map((item) => ({ label: item.name, value: item.project_id }))
);

async function loadProjects() {
  const res = await listProjects(50);
  projects.value = res.data || [];
}

async function startBuildGraph() {
  try {
    busy.value = true;
    taskError.value = "";
    taskMessage.value = "图谱构建任务已提交...";
    const res = await buildGraph(projectId.value, "Novel Story Graph");
    const taskId = res.data.task_id;
    const task = await pollGraphTask(taskId, updateTaskMessage);
    currentGraphId.value = task.result?.graph_id || "";
    taskMessage.value = `图谱构建完成`;
    await refreshGraph();
  } catch (error) {
    taskError.value = error.message;
  } finally {
    busy.value = false;
  }
}

function updateTaskMessage(task) {
  taskMessage.value = `${task.message || "处理中"} (${task.progress || 0}%)`;
}

async function refreshGraph() {
  if (!projectId.value) {
    graphNodes.value = [];
    graphEdges.value = [];
    currentGraphId.value = "";
    return;
  }
  try {
    const res = await getProject(projectId.value);
    const project = res.data;
    currentGraphId.value = project.graph_id || "";
    
    if (!currentGraphId.value) {
      graphNodes.value = [];
      graphEdges.value = [];
      return;
    }

    const graphRes = await getProjectGraph(projectId.value);
    const graph = graphRes.data;
    graphNodes.value = (graph.nodes || []).map(node => ({
      id: node.uuid,
      name: node.name,
      entity_type: node.labels?.find(l => !['Entity', 'Node'].includes(l)) || 'Unknown',
      summary: node.summary || '',
      attributes: node.attributes || {}
    }));
    const nodeMap = Object.fromEntries(graphNodes.value.map(n => [n.id, n]));
    graphEdges.value = (graph.edges || []).map(edge => ({
      id: edge.uuid,
      source_id: edge.source_node_uuid,
      target_id: edge.target_node_uuid,
      source_name: nodeMap[edge.source_node_uuid]?.name || 'Unknown',
      target_name: nodeMap[edge.target_node_uuid]?.name || 'Unknown',
      name: edge.name,
      fact: edge.fact,
      weight: edge.weight || 1,
    }));
  } catch (error) {
    graphNodes.value = [];
    graphEdges.value = [];
  }
}

async function openArchiveConfigurator() {
  try {
    busy.value = true;
    taskError.value = "";
    const res = await generateArchiveCandidates({
      projectId: projectId.value,
      graphId: currentGraphId.value,
    });
    archiveCandidates.value = res.data.candidates || [];
    configuratorVisible.value = true;
  } catch (error) {
    taskError.value = error.message;
  } finally {
    busy.value = false;
  }
}

function closeArchiveConfigurator() {
  configuratorVisible.value = false;
}

async function createArchives(candidateSnapshot) {
  try {
    busy.value = true;
    taskError.value = "";
    const tierOverrides = (candidateSnapshot || [])
      .filter((item) => item.selected_importance_tier && item.selected_importance_tier !== item.recommended_importance_tier)
      .map((item) => ({
        entity_uuid: item.entity_uuid,
        importance_tier: item.selected_importance_tier,
      }));
    const res = await generateArchives({
      projectId: projectId.value,
      graphId: currentGraphId.value,
      useLlm: false,
      tierOverrides,
      candidateSnapshot: candidateSnapshot || [],
    });
    taskMessage.value = `已生成档案: ${res.data.count} 项`;
    configuratorVisible.value = false;
  } catch (error) {
    taskError.value = error.message;
  } finally {
    busy.value = false;
  }
}

onMounted(async () => {
  await loadProjects();
  if (projects.value[0]) {
    projectId.value = projects.value[0].project_id;
    await refreshGraph();
  }
});
</script>

<style scoped>
.graph-workbench {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-height: calc(100vh - 104px);
  height: calc(100vh - 104px);
}

.workbench-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  flex-shrink: 0;
}

.workbench-toolbar:hover {
  box-shadow: none;
  border-color: var(--line-soft);
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 4px var(--space-sm);
  background: var(--bg-paper-warm);
  border-radius: var(--radius-sm);
  font-size: 12px;
  margin-left: auto;
}

.status-indicator.error {
  color: var(--accent-seal);
  background: rgba(155, 67, 38, 0.05);
}

.status-pulse {
  width: 6px;
  height: 6px;
  background: var(--accent-copper);
  border-radius: 50%;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0% { opacity: 0.4; }
  50% { opacity: 1; }
  100% { opacity: 0.4; }
}

.workbench-main {
  display: flex;
  flex: 1;
  min-width: 0;
  min-height: 0;
}

.workbench-main :deep(.panel) {
  flex: 1;
  min-width: 0;
  min-height: 0;
}

@media (max-width: 1024px) {
  .graph-workbench {
    height: auto;
  }
}
</style>
