<template>
  <div class="overview-stage stack">
    <!-- Idle: command grid with hero + focus card side by side -->
    <section v-if="!isProcessing" class="overview-command-grid">
      <OverviewHeroPanel
        :projects="projects"
        :upload-phase="upload.state.uploadPhase"
        :active-stage-label="upload.state.activeStage.label"
        :error-message="projectActionError"
        @refresh="refresh"
        @start-new="scrollToUpload"
      />

      <OverviewTaskFocusCard
        :project-name="focusProjectName"
        :upload-phase="upload.state.uploadPhase"
        :task-status="upload.state.taskStatus"
        :active-stage="upload.state.activeStage"
        :task-metrics="upload.state.taskMetrics"
        :timeline="upload.state.timeline"
        :status-text="upload.state.statusText"
        :error-message="focusError"
      />
    </section>

    <!-- Processing: hero full-width, then stream + focus card in 2-col grid -->
    <template v-if="isProcessing">
      <OverviewHeroPanel
        :projects="projects"
        :upload-phase="upload.state.uploadPhase"
        :active-stage-label="upload.state.activeStage.label"
        :error-message="projectActionError"
        @refresh="refresh"
        @start-new="scrollToUpload"
      />

      <section class="overview-processing-grid">
        <InlineWorkflowStream
          :task-id="upload.state.taskId"
          :timeline="upload.state.timeline"
          :active-stage-key="upload.state.activeStage.key"
          :task-status="upload.state.taskStatus"
          :upload-phase="upload.state.uploadPhase"
        />

        <div class="focus-card-wrapper">
          <OverviewTaskFocusCard
            :project-name="focusProjectName"
            :upload-phase="upload.state.uploadPhase"
            :task-status="upload.state.taskStatus"
            :active-stage="upload.state.activeStage"
            :task-metrics="upload.state.taskMetrics"
            :timeline="upload.state.timeline"
            :status-text="upload.state.statusText"
            :error-message="focusError"
          />
        </div>
      </section>
    </template>

    <OverviewRecentProjects v-if="!isProcessing" :projects="recentProjects" @delete-project="handleDeleteProject" />

    <section v-if="!isProcessing" :class="['overview-workbench-grid', { single: !latestProjectWithResults }]">
      <div id="seed-upload-anchor" class="upload-module">
        <SeedUploadPanel :initially-expanded="uploadModuleExpanded" @uploaded="handleUploaded" />
      </div>

      <div v-if="latestProjectWithResults" id="seed-analysis" class="analysis-module">
        <div class="module-head">
          <div>
            <div class="module-code mono">结果</div>
            <h3 class="title-ancient">最新分析结果</h3>
          </div>
          <span class="mono module-project">{{ latestProjectWithResults.name }}</span>
        </div>
        <SeedAnalysisPanel ref="seedAnalysisPanel" :projects="projects" :project-id="latestProjectWithResults?.project_id || ''" />
      </div>
    </section>

  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";

import { deleteProject } from "../api/project";
import { useProjectCatalog } from "../composables/useProjectCatalog";
import { useSeedUpload } from "../composables/useSeedUpload";
import InlineWorkflowStream from "./overview/InlineWorkflowStream.vue";
import OverviewHeroPanel from "./overview/OverviewHeroPanel.vue";
import OverviewRecentProjects from "./overview/OverviewRecentProjects.vue";
import OverviewTaskFocusCard from "./overview/OverviewTaskFocusCard.vue";
import SeedAnalysisPanel from "./overview/SeedAnalysisPanel.vue";
import SeedUploadPanel from "./overview/SeedUploadPanel.vue";

const upload = useSeedUpload();
const { projects, refreshProjects } = useProjectCatalog();
const isProcessing = computed(() => upload.state.uploadPhase !== "idle");
const seedAnalysisPanel = ref(null);
const projectActionError = ref("");
const uploadModuleExpanded = ref(upload.state.uploadPhase === "idle");

const recentProjects = computed(() => projects.value.slice(0, 4));
const latestProject = computed(() => projects.value[0] || null);
const latestProjectWithResults = computed(
  () => projects.value.find((project) => project.status && project.status.includes("completed")),
);
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
  grid-template-columns: minmax(0, 1fr) minmax(280px, 0.7fr);
  gap: 12px;
  align-items: start;
}

.overview-workbench-grid,
.upload-module,
.analysis-module {
  width: 100%;
}

.overview-workbench-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
  align-items: start;
}

.overview-workbench-grid.single {
  grid-template-columns: 1fr;
}

.analysis-module {
  padding: 16px;
  border-radius: 12px;
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

.overview-processing-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 0.35fr);
  gap: 12px;
  align-items: start;
}

.focus-card-wrapper {
  position: sticky;
  top: var(--space-lg);
}

@media (max-width: 1180px) {
  .overview-command-grid,
  .overview-workbench-grid,
  .overview-processing-grid {
    grid-template-columns: 1fr;
  }

  .focus-card-wrapper {
    position: static;
  }
}
</style>
