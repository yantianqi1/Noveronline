<template>
  <section class="layout">
    <article class="workbench-card left">
      <h2 class="card-title">图谱构建流程</h2>
      <p>选择已有项目后发起图谱构建，并可生成角色/势力档案与平行世界配置。</p>

      <div class="field">
        <label>项目</label>
        <select v-model="projectId">
          <option value="">请选择项目</option>
          <option v-for="item in projects" :key="item.project_id" :value="item.project_id">
            {{ item.name }} ({{ item.status }})
          </option>
        </select>
      </div>

      <div class="toolbar-row">
        <button class="btn" @click="loadProjects">刷新项目</button>
        <button class="btn primary" :disabled="!projectId || busy" @click="startBuildGraph">构建图谱</button>
      </div>

      <div class="status-area">
        <span class="status" :class="taskError ? 'warn' : 'ok'">
          {{ taskError || (taskMessage || "等待执行") }}
        </span>
      </div>

      <hr />

      <h3>档案与世界配置</h3>
      <div class="field">
        <label>变量 (每行一个)</label>
        <textarea v-model="variablesText" placeholder="例如：王朝税率上升 20%\n某宗门提前结盟"></textarea>
      </div>
      <div class="toolbar-row">
        <button class="btn" :disabled="!currentGraphId" @click="createArchives">生成角色档案</button>
        <button class="btn" :disabled="!currentGraphId" @click="createParallelConfig">生成平行世界配置</button>
      </div>
    </article>

    <StoryGraphPanel :nodes="graphNodes" :edges="graphEdges" :loading="busy" @refresh="refreshGraph" />
  </section>
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
    taskMessage.value = "图谱构建任务已提交。";
    const res = await buildGraph(projectId.value, "Novel Story Graph");
    const taskId = res.data.task_id;
    const task = await pollGraphTask(taskId, updateTaskMessage);
    currentGraphId.value = task.result?.graph_id || "";
    taskMessage.value = `图谱构建完成: ${currentGraphId.value || "无 graph_id"}`;
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
  const res = await getProject(projectId.value);
  const project = res.data;
  currentGraphId.value = project.graph_id || currentGraphId.value;
  if (!currentGraphId.value) {
    graphNodes.value = [];
    graphEdges.value = [];
    return;
  }
  try {
    const graphRes = await getProjectGraph(projectId.value);
    const graph = graphRes.data;
    currentGraphId.value = graph.graph_id || currentGraphId.value;
    graphNodes.value = (graph.nodes || []).map((node) => ({
      id: node.uuid,
      uuid: node.uuid,
      name: node.name,
      entity_type: node.labels?.find((label) => !["Entity", "Node"].includes(label)) || "Unknown",
      labels: node.labels || [],
      summary: node.summary || "",
      attributes: node.attributes || {},
      evidence_refs: node.evidence_refs || [],
    }));
    const nodeMap = Object.fromEntries(graphNodes.value.map((node) => [node.id, node]));
    graphEdges.value = (graph.edges || []).map((edge) => ({
      id: edge.uuid,
      uuid: edge.uuid,
      source_id: edge.source_node_uuid,
      target_id: edge.target_node_uuid,
      source_name: nodeMap[edge.source_node_uuid]?.name || edge.source_node_uuid,
      target_name: nodeMap[edge.target_node_uuid]?.name || edge.target_node_uuid,
      name: edge.name,
      fact: edge.fact,
      weight: edge.weight,
      attributes: edge.attributes || {},
      evidence_refs: edge.evidence_refs || [],
    }));
  } catch (error) {
    if (String(error.message || "").includes("尚未生成本地图谱")) {
      graphNodes.value = [];
      graphEdges.value = [];
      return;
    }
    throw error;
  }
}

async function createArchives() {
  try {
    busy.value = true;
    const res = await generateArchives({
      projectId: projectId.value,
      graphId: currentGraphId.value,
      useLlm: false,
    });
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
    const variables = variablesText.value
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);
    const res = await generateParallelWorldConfig({
      projectId: projectId.value,
      graphId: currentGraphId.value,
      variables,
      branchCount: 4,
      focusQuestion: selectedProject.value?.analysis_goal,
      useLlm: false,
    });
    taskMessage.value = `已生成平行世界配置: ${res.data.config?.world_name || "完成"}`;
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
.layout {
  display: grid;
  grid-template-columns: 380px minmax(0, 1fr);
  gap: 14px;
}

.left {
  padding: 16px;
}

.left p {
  color: var(--text-sub);
}

.left hr {
  border: none;
  border-top: 1px dashed var(--line-soft);
  margin: 16px 0;
}

.status-area {
  margin-top: 10px;
}

@media (max-width: 1200px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>
