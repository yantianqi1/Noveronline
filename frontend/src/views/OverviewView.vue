<template>
  <div class="overview-stage stack">
    <section class="overview-command-grid">
      <div class="command-column stack">
        <OverviewHeroPanel
          :projects="projects"
          :upload-phase="upload.state.uploadPhase"
          :active-stage-label="upload.state.activeStage.label"
          :error-message="projectActionError"
          @refresh="refresh"
          @start-new="scrollToUpload"
        />
        <OverviewNextActionsPanel :project="nextActionProject" @start-new="scrollToUpload" />
      </div>

      <OverviewTaskFocusCard
        :project-name="focusProjectName"
        :upload-phase="upload.state.uploadPhase"
        :task-status="upload.state.taskStatus"
        :active-stage="upload.state.activeStage"
        :task-metrics="upload.state.taskMetrics"
        :timeline="upload.state.timeline"
        :status-text="upload.state.statusText"
        :error-message="focusError"
        @open-drawer="drawerOpen = true"
        @start-new="scrollToUpload"
      />
    </section>

    <OverviewRecentProjects :projects="recentProjects" @delete-project="handleDeleteProject" />

    <section :class="['overview-workbench-grid', { single: !latestProjectWithResults }]">
      <div id="seed-upload-anchor" class="upload-module">
        <SeedUploadPanel :initially-expanded="uploadModuleExpanded" @uploaded="handleUploaded" />
      </div>

      <div v-if="latestProjectWithResults" id="seed-analysis" class="analysis-module">
        <div class="module-head">
          <div>
            <div class="module-code mono">成果速览</div>
            <h3 class="title-ancient">最新种子分析</h3>
          </div>
          <span class="mono module-project">{{ latestProjectWithResults.name }}</span>
        </div>
        <SeedAnalysisPanel ref="seedAnalysisPanel" :projects="projects" @refresh-projects="refresh" />
      </div>
    </section>

    <OverviewTaskDrawer
      :open="drawerOpen"
      :project-name="focusProjectName"
      :upload-phase="upload.state.uploadPhase"
      :task-status="upload.state.taskStatus"
      :active-stage="upload.state.activeStage"
      :task-metrics="upload.state.taskMetrics"
      :llm-activity="upload.state.llmActivity"
      :timeline="upload.state.timeline"
      :task-started-at="upload.state.taskStartedAt"
      @close="drawerOpen = false"
    />
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";

import { deleteProject } from "../api/project";
import { useProjectCatalog } from "../composables/useProjectCatalog";
import { useSeedUpload } from "../composables/useSeedUpload";
import OverviewHeroPanel from "./overview/OverviewHeroPanel.vue";
import OverviewNextActionsPanel from "./overview/OverviewNextActionsPanel.vue";
import OverviewRecentProjects from "./overview/OverviewRecentProjects.vue";
import OverviewTaskDrawer from "./overview/OverviewTaskDrawer.vue";
import OverviewTaskFocusCard from "./overview/OverviewTaskFocusCard.vue";
import SeedAnalysisPanel from "./overview/SeedAnalysisPanel.vue";
import SeedTaskDrawer from "./overview/SeedTaskDrawer.vue";
import SeedUploadPanel from "./overview/SeedUploadPanel.vue";

const upload = useSeedUpload();
const { projects, refreshProjects } = useProjectCatalog();
const seedAnalysisPanel = ref(null);
const drawerOpen = ref(false);
const projectActionError = ref("");
const uploadModuleExpanded = ref(upload.state.uploadPhase === "idle");

const recentProjects = computed(() => projects.value.slice(0, 4));
const latestProject = computed(() => projects.value[0] || null);
const latestProjectWithResults = computed(
  () => projects.value.find((project) => project.status && project.status.includes("completed")),
);
const nextActionProject = computed(() => latestProjectWithResults.value || latestProject.value);
const focusProjectName = computed(() => {
  if (upload.state.uploadPhase !== "idle") {
    return upload.state.projectName.trim() || latestProject.value?.name || "当前卷宗";
  }
  return latestProject.value?.name || "当前卷宗";
});
const focusError = computed(() => upload.state.error || projectActionError.value);

watch(
  () => upload.state.uploadPhase,
  (phase, previousPhase) => {
    if (phase === "idle") {
      uploadModuleExpanded.value = true;
      return;
    }
    if (previousPhase === "idle") {
      uploadModuleExpanded.value = false;
    }
  },
);

function statusClass(status) {
  if (status === "failed") return "danger";
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
    await deleteProject(project.project_id);
    await refresh();
  } catch (error) {
    projectActionError.value = error.message || "删除项目失败";
  }
}

function scrollToUpload() {
  const element = document.getElementById("seed-upload-anchor");
  if (element) {
    element.scrollIntoView({ behavior: "smooth" });
  }
}
</script>

<style scoped>
.overview-stage {
  width: 100%;
}

.overview-command-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.98fr) minmax(360px, 0.88fr);
  gap: var(--space-lg);
  align-items: start;
}

.command-column,
.overview-workbench-grid,
.upload-module,
.analysis-module {
  width: 100%;
}

.overview-workbench-grid {
  display: grid;
  grid-template-columns: minmax(0, 0.92fr) minmax(0, 1.08fr);
  gap: var(--space-lg);
  align-items: start;
}

.overview-workbench-grid.single {
  grid-template-columns: 1fr;
}

.analysis-module {
  padding: var(--space-lg);
  border-radius: 16px;
  border: 1px solid var(--line-soft);
  background: rgba(255, 255, 255, 0.68);
}

.module-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}

.module-code,
.module-project {
  color: var(--text-dim);
  font-size: 12px;
}

@media (max-width: 1180px) {
  .overview-command-grid,
  .overview-workbench-grid {
    grid-template-columns: 1fr;
  }
}
</style>
