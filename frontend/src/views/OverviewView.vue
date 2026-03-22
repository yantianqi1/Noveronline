<template>
  <section class="overview-grid">
    <OverviewHeroPanel
      :projects="projects"
      :upload-phase="upload.state.uploadPhase"
      :active-stage-label="upload.state.activeStage.label"
      :error-message="projectActionError"
      @refresh="refresh"
    />

    <article class="workbench-card panel project-panel">
      <h2 class="card-title">项目档案簿</h2>
      <p>这里会持续记录每个项目的状态、最近一次产物阶段，以及后续删除入口。</p>

      <div v-if="projects.length" class="list">
        <div v-for="item in projects" :key="item.project_id" class="list-row">
          <div class="list-copy">
            <div class="name">{{ item.name }}</div>
            <div class="meta mono">{{ item.project_id }}</div>
            <div class="summary">{{ item.analysis_goal || item.analysis_summary || "等待填写分析目标。" }}</div>
          </div>
          <div class="list-actions">
            <span class="status" :class="statusClass(item.status)">{{ formatProjectStatus(item.status) }}</span>
            <button
              class="btn subtle danger"
              :disabled="deletingProjectId === item.project_id"
              @click="handleDeleteProject(item)"
            >
              {{ deletingProjectId === item.project_id ? "删除中..." : "删除" }}
            </button>
          </div>
        </div>
      </div>

      <div v-else class="project-empty">
        <strong>还没有项目。</strong>
        <p>请在下方上传小说文本创建第一个项目，系统会自动开始分析。</p>
      </div>
    </article>

    <div id="seed-upload" class="overview-anchor">
      <SeedUploadPanel @uploaded="handleUploaded" />
    </div>
    <div id="seed-analysis" class="overview-anchor">
      <SeedAnalysisPanel ref="seedAnalysisPanel" :projects="projects" @refresh-projects="refresh" />
    </div>
  </section>
</template>

<script setup>
import { ref } from "vue";

import { deleteProject } from "../api/project";
import { useProjectCatalog } from "../composables/useProjectCatalog";
import { useSeedUpload } from "../composables/useSeedUpload";
import { formatProjectStatus } from "../utils/chineseDisplay";
import OverviewHeroPanel from "./overview/OverviewHeroPanel.vue";
import SeedAnalysisPanel from "./overview/SeedAnalysisPanel.vue";
import SeedUploadPanel from "./overview/SeedUploadPanel.vue";

const upload = useSeedUpload();
const { projects, refreshProjects } = useProjectCatalog();
const seedAnalysisPanel = ref(null);
const deletingProjectId = ref("");
const projectActionError = ref("");

function statusClass(status) {
  if (status === "failed") {
    return "danger-status";
  }
  return status && status.includes("completed") ? "ok" : "warn";
}

async function refresh() {
  try {
    projectActionError.value = "";
    await refreshProjects(30);
  } catch (error) {
    projectActionError.value = error.message || "刷新项目失败";
    console.error(error);
  }
}

async function handleUploaded(payload) {
  if (!payload?.project_id) {
    return;
  }
  await refresh();
  await seedAnalysisPanel.value?.runForProject(payload.project_id);
}

async function handleDeleteProject(project) {
  if (!project?.project_id) {
    return;
  }
  if (!window.confirm(`确认删除项目「${project.name}」吗？`)) {
    return;
  }
  try {
    projectActionError.value = "";
    deletingProjectId.value = project.project_id;
    await deleteProject(project.project_id);
    await refresh();
  } catch (error) {
    projectActionError.value = error.message || "删除项目失败";
  } finally {
    deletingProjectId.value = "";
  }
}
</script>

<style scoped>
.overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.panel {
  padding: 18px;
}

.panel p {
  margin: 8px 0 0;
  color: var(--text-sub);
}

.overview-anchor {
  grid-column: 1 / -1;
  scroll-margin-top: 18px;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
  max-height: 430px;
  overflow: auto;
}

.list-row {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  padding: 12px;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  background: #fffcf6;
}

.list-copy {
  min-width: 0;
}

.list-actions {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.name {
  font-weight: 700;
}

.meta,
.summary {
  color: var(--text-sub);
}

.meta {
  margin-top: 4px;
  font-size: 12px;
}

.summary {
  margin-top: 8px;
  line-height: 1.6;
}

.project-empty {
  margin-top: 12px;
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fffbf0;
  padding: 10px;
}

.danger {
  color: #9b4326;
  border-color: rgba(155, 67, 38, 0.25);
}

.danger-status {
  background: rgba(155, 67, 38, 0.12);
  color: #9b4326;
}

@media (max-width: 980px) {
  .overview-grid {
    grid-template-columns: 1fr;
  }

  .list-row {
    flex-direction: column;
  }
}
</style>
