<template>
  <div class="overview-stage stack">
    <!-- Layer 1: Main Narrative Area -->
    <section class="hero-section">
      <OverviewHeroPanel
        :projects="projects"
        :upload-phase="upload.state.uploadPhase"
        :active-stage-label="upload.state.activeStage.label"
        :error-message="projectActionError"
        @refresh="refresh"
        @start-new="scrollToUpload"
      />
    </section>

    <!-- Layer 2: Recent Projects Strip -->
    <section v-if="projects.length" class="recent-projects">
      <div class="section-header">
        <h3 class="title-ancient">最近卷宗</h3>
        <RouterLink to="/archive-library" class="btn subtle">查看全部</RouterLink>
      </div>
      <div class="project-strip">
        <div v-for="item in recentProjects" :key="item.project_id" class="project-mini-card workbench-card">
          <div class="project-top">
            <span class="status-tag" :class="statusClass(item.status)">{{ formatProjectStatus(item.status) }}</span>
            <button class="delete-icon" @click.stop="handleDeleteProject(item)">×</button>
          </div>
          <div class="project-info">
            <div class="project-name">{{ item.name }}</div>
            <div class="project-goal">{{ item.analysis_goal || '无明确分析目标' }}</div>
          </div>
          <div class="project-footer">
            <span class="mono">{{ item.project_id.slice(0, 8) }}</span>
            <RouterLink :to="`/archive-library?project_id=${item.project_id}`" class="btn subtle small">详情</RouterLink>
          </div>
        </div>
      </div>
    </section>

    <!-- Layer 3: Phase Preview Area -->
    <section class="phase-preview">
      <div v-if="upload.state.uploadPhase !== 'idle'" class="active-task-preview">
        <div class="preview-header">
          <h3 class="title-ancient">当前管线任务进度</h3>
        </div>
        <div id="seed-upload" class="task-panel">
          <SeedUploadPanel @uploaded="handleUploaded" />
        </div>
      </div>

      <div v-else-if="latestProjectWithResults" class="results-preview">
        <div class="preview-header">
          <h3 class="title-ancient">最新种子分析成果</h3>
          <span class="mono">{{ latestProjectWithResults.name }}</span>
        </div>
        <div id="seed-analysis" class="task-panel">
          <SeedAnalysisPanel ref="seedAnalysisPanel" :projects="projects" @refresh-projects="refresh" />
        </div>
      </div>

      <div v-else class="empty-guide-preview container-7-5">
        <div class="guide-text stack">
          <h3 class="title-ancient">从何处开始？</h3>
          <p>
            MiroFish-Novel 采用种子分析技术。您只需投放一份小说文本，
            系统便会通过一系列自动化管线，为您建立起该小说的故事图谱与世界线雏形。
          </p>
          <div class="guide-actions">
            <button class="btn primary" @click="scrollToUpload">投放小说文本</button>
            <RouterLink to="/guide" class="btn subtle">阅读详细指南</RouterLink>
          </div>
        </div>
        <div class="guide-illustration workbench-card">
          <!-- Placeholder for a light ancient style illustration or simplified flow diagram -->
          <div class="flow-placeholder">
            <div class="flow-step">上传文本</div>
            <div class="flow-arrow">→</div>
            <div class="flow-step">管线分析</div>
            <div class="flow-arrow">→</div>
            <div class="flow-step">生成图谱/世界线</div>
          </div>
        </div>
      </div>
    </section>

    <!-- Hidden upload area for scrolling -->
    <div v-if="upload.state.uploadPhase === 'idle' && projects.length" id="seed-upload-anchor" class="hidden-upload">
       <SeedUploadPanel @uploaded="handleUploaded" />
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";

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

const recentProjects = computed(() => projects.value.slice(0, 4));

const latestProjectWithResults = computed(() => {
  return projects.value.find(p => p.status && p.status.includes('completed'));
});

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
  if (!payload?.project_id) return;
  await refresh();
  await seedAnalysisPanel.value?.runForProject(payload.project_id);
}

async function handleDeleteProject(project) {
  if (!project?.project_id) return;
  if (!window.confirm(`确认删除项目「${project.name}」吗？`)) return;
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

function scrollToUpload() {
  const el = document.getElementById('seed-upload-anchor') || document.getElementById('seed-upload');
  if (el) el.scrollIntoView({ behavior: 'smooth' });
}
</script>

<style scoped>
.overview-stage {
  max-width: 1200px;
  margin: 0 auto;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-md);
}

.project-strip {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: var(--space-md);
}

.project-mini-card {
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  position: relative;
}

.project-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.delete-icon {
  border: none;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  font-size: 18px;
  padding: 4px;
  line-height: 1;
}

.delete-icon:hover {
  color: var(--accent-seal);
}

.project-name {
  font-weight: 700;
  font-size: 16px;
  color: var(--text-main);
}

.project-goal {
  font-size: 13px;
  color: var(--text-sub);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  height: 2.8em;
  line-height: 1.4;
}

.project-footer {
  margin-top: auto;
  padding-top: var(--space-sm);
  border-top: 1px solid var(--line-soft);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
}

.preview-header {
  display: flex;
  align-items: baseline;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}

.preview-header .mono {
  font-size: 13px;
  color: var(--text-dim);
}

.empty-guide-preview {
  padding: var(--space-xl);
  background: rgba(255, 255, 255, 0.4);
  border-radius: var(--radius-lg);
  border: 1px dashed var(--line-medium);
}

.guide-text p {
  font-size: 15px;
  color: var(--text-sub);
  line-height: 1.8;
}

.guide-illustration {
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-paper-warm);
}

.flow-placeholder {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  color: var(--line-strong);
  font-family: "ZCOOL XiaoWei", serif;
}

.flow-step {
  padding: var(--space-sm) var(--space-md);
  border: 1px solid var(--line-medium);
  border-radius: var(--radius-sm);
  background: #fff;
}

.hidden-upload {
  margin-top: var(--space-xl);
}

@media (max-width: 768px) {
  .project-strip {
    grid-template-columns: 1fr;
  }
}
</style>
