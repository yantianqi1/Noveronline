<template>
  <div class="graph-workbench">
    <!-- Left Sidebar: Controls -->
    <aside class="workbench-sidebar stack">
      <section class="control-group workbench-card">
        <h3 class="title-ancient">卷宗图谱构建</h3>
        <p class="subtitle">选择项目卷宗并构建其底层实体关系图谱。</p>
        
        <div class="field">
          <label>当前卷宗</label>
          <select v-model="projectId" @change="refreshGraph">
            <option value="">-- 请选择卷宗 --</option>
            <option v-for="item in projects" :key="item.project_id" :value="item.project_id">
              {{ item.name }}
            </option>
          </select>
        </div>

        <div class="actions stack">
          <button class="btn primary" :disabled="!projectId || busy" @click="startBuildGraph">
            {{ busy ? "构建中..." : "启动图谱构建" }}
          </button>
          <button class="btn subtle small" @click="loadProjects">刷新卷宗列表</button>
        </div>

        <div v-if="taskMessage || taskError" class="status-box" :class="{ error: taskError }">
          <div class="status-pulse" v-if="busy"></div>
          <span class="mono">{{ taskError || taskMessage }}</span>
        </div>
      </section>

      <section class="control-group workbench-card">
        <h3 class="title-ancient">衍生配置生成</h3>
        <p class="subtitle">基于图谱生成角色档案或平行世界初始变量。</p>
        
        <div class="field">
          <label>世界线变量 (每行一条)</label>
          <textarea v-model="variablesText" rows="4"></textarea>
        </div>

        <div class="actions stack">
          <button class="btn" :disabled="!currentGraphId || busy" @click="createArchives">生成全量角色档案</button>
          <button class="btn" :disabled="!currentGraphId || busy" @click="createParallelConfig">生成世界线初始配置</button>
        </div>
      </section>
    </aside>

    <!-- Main Area: Canvas -->
    <main class="workbench-main">
      <StoryGraphPanel
        :nodes="graphNodes"
        :edges="graphEdges"
        :loading="busy"
        @refresh="refreshGraph"
      />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import StoryGraphPanel from "../components/StoryGraphPanel.vue";
import { buildGraph, getProject, getProjectGraph, getTask, listProjects } from "../api/project";
import { generateArchives, generateParallelWorldConfig } from "../api/novel";
import { createGraphBuildTaskPoller } from "./story-graph/graphBuildTaskPoller.js";

const projects = ref([]);
const projectId = ref("");
const busy = ref(false);
const taskMessage = ref("");
const taskError = ref("");
const currentGraphId = ref("");
const graphNodes = ref([]);
const graphEdges = ref([]);
const variablesText = ref("主角提前三个月知晓天灾\n敌对势力误判主角阵营");
const pollGraphTask = createGraphBuildTaskPoller({ getTask });

const selectedProject = computed(() => projects.value.find((p) => p.project_id === projectId.value));

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
      fact: edge.fact
    }));
  } catch (error) {
    graphNodes.value = [];
    graphEdges.value = [];
  }
}

async function createArchives() {
  try {
    busy.value = true;
    const res = await generateArchives({ projectId: projectId.value, graphId: currentGraphId.value, useLlm: false });
    taskMessage.value = `已生成档案: ${res.data.count} 项`;
  } catch (error) {
    taskError.value = error.message;
  } finally {
    busy.value = false;
  }
}

async function createParallelConfig() {
  try {
    busy.value = true;
    const variables = variablesText.value.split("\n").map(v => v.trim()).filter(Boolean);
    const res = await generateParallelWorldConfig({
      projectId: projectId.value,
      graphId: currentGraphId.value,
      variables,
      branchCount: 4,
      focusQuestion: selectedProject.value?.analysis_goal,
      useLlm: false,
    });
    taskMessage.value = `世界线配置已就绪`;
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
  display: grid;
  grid-template-columns: 368px minmax(0, 1fr);
  gap: var(--space-lg);
  min-height: calc(100vh - 104px);
  height: calc(100vh - 104px);
  align-items: stretch;
}

.workbench-sidebar {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
  padding-right: var(--space-xs);
}

.control-group {
  padding: var(--space-md);
}

.subtitle {
  font-size: 12px;
  color: var(--text-dim);
  margin-top: 4px;
  margin-bottom: var(--space-md);
}

.actions {
  margin-top: var(--space-md);
}

.status-box {
  margin-top: var(--space-md);
  padding: var(--space-sm);
  background: var(--bg-paper-warm);
  border-radius: var(--radius-sm);
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.status-box.error {
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
  min-width: 0;
  min-height: 0;
}

.workbench-sidebar :deep(.control-group:last-child) {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.workbench-sidebar :deep(.control-group:last-child .field) {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.workbench-sidebar :deep(.control-group:last-child textarea) {
  flex: 1;
  min-height: 220px;
}

.workbench-sidebar :deep(.control-group:last-child .actions) {
  margin-top: auto;
}

.workbench-main :deep(.panel) {
  flex: 1;
  min-width: 0;
  min-height: 0;
}

@media (max-width: 1024px) {
  .graph-workbench {
    grid-template-columns: 1fr;
    height: auto;
  }
}
</style>
