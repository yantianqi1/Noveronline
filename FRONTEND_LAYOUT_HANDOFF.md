# Frontend Layout Handoff

这是一份可脱离仓库单独阅读的前端布局交接文档，供无法直接访问项目源码的模型使用。

## 交接目标

- 让接手模型直接看到当前前端布局相关源码，而不是只看摘要。
- 重点覆盖应用壳子、路由、核心页面、布局 composable、接口层、布局测试。
- 以下代码均来自当前仓库 `MiroFish-Novel`，按用户指定顺序嵌入。

## 项目背景

- 项目：`MiroFish-Novel`
- 前端目录：`frontend/`
- 前端端口：`3891`
- 后端端口：`5101`
- 技术栈：`Vue 3 + Vue Router + Vite + D3 + 原生 fetch/XMLHttpRequest`
- 本文档生成时间：`2026-03-24`

## 文件目录

- `frontend/src/App.vue`
- `frontend/src/styles.css`
- `frontend/src/router/index.js`
- `frontend/src/views/OverviewView.vue`
- `frontend/src/views/overview/SeedUploadPanel.vue`
- `frontend/src/components/ArchiveLibraryPicker.vue`
- `frontend/src/components/ArchiveLibraryPicker.css`
- `frontend/src/views/StoryGraphWorkbenchView.vue`
- `frontend/src/components/StoryGraphPanel.vue`
- `frontend/src/views/WriterWorkbenchView.vue`
- `frontend/src/views/WriterWorkbenchView.css`
- `frontend/src/views/WorldlineWorkbenchView.vue`
- `frontend/src/views/WorldlineWorkbenchView.css`
- `frontend/src/views/worldline/WorldlineControlPanel.vue`
- `frontend/src/views/worldline/WorldlineDirectorPanel.vue`
- `frontend/src/views/CharacterConsoleView.vue`
- `frontend/src/views/LlmFacilityView.vue`
- `frontend/src/composables/useProjectCatalog.js`
- `frontend/src/composables/useSeedUpload.js`
- `frontend/src/composables/useArchiveLibraryLayout.js`
- `frontend/src/composables/useWorldlineWorkbenchLayout.js`
- `frontend/src/api/project.js`
- `frontend/src/api/novel.js`
- `frontend/src/api/archive.js`
- `frontend/src/api/worldline.js`
- `frontend/src/api/llm.js`
- `frontend/tests/vite-config.test.mjs`
- `frontend/tests/overview-layout.test.mjs`
- `frontend/tests/archive-library-layout.test.mjs`
- `frontend/tests/worldline-workbench-layout.test.mjs`
- `frontend/tests/writer-workbench-layout.test.mjs`

## `frontend/src/App.vue`

````vue
<template>
  <div class="shell">
    <aside class="left-track">
      <div class="brand">
        <div class="seal">
          <span class="seal-inner">MF</span>
        </div>
        <div class="brand-text">
          <div class="brand-name">{{ APP_BRAND_NAME }}</div>
          <div class="brand-sub mono">{{ APP_SUBTITLE }}</div>
        </div>
      </div>

      <nav class="nav-track">
        <div class="nav-group">
          <div class="group-label">主要通路</div>
          <RouterLink v-for="item in mainNav" :key="item.path" :to="item.path" class="nav-item">
            <span class="nav-dot"></span>
            <span class="nav-label">{{ item.label }}</span>
            <span class="nav-code mono">{{ item.code }}</span>
          </RouterLink>
        </div>

        <div class="nav-group">
          <div class="group-label">辅助与配置</div>
          <RouterLink v-for="item in subNav" :key="item.path" :to="item.path" class="nav-item sub">
            <span class="nav-label">{{ item.label }}</span>
          </RouterLink>
        </div>
      </nav>

      <footer class="track-footer">
        <div v-if="upload.state.uploadPhase !== 'idle'" class="mini-status" @click="showUploadOverlay = true">
          <div class="status-pulse"></div>
          <span class="mono">{{ upload.state.statusText }}</span>
        </div>
      </footer>
    </aside>

    <main class="main-stage">
      <header class="stage-header">
        <div class="breadcrumb">
          <span class="title-ancient">{{ currentNavLabel }}</span>
        </div>
        <div class="header-actions">
          <!-- Add global project indicator or help button here if needed -->
        </div>
      </header>

      <div class="stage-content">
        <RouterView />
      </div>
    </main>

    <!-- Global Upload Overlay -->
    <Transition name="fade">
      <div v-if="showUploadOverlay" class="overlay" @click.self="showUploadOverlay = false">
        <div class="overlay-card workbench-card">
          <div class="overlay-header">
            <h3 class="title-ancient">分析任务进行中</h3>
            <button class="btn subtle" @click="showUploadOverlay = false">收起</button>
          </div>
          <div class="overlay-body">
            <div class="progress-info">
              <div class="info-row">
                <strong>{{ upload.state.statusText }}</strong>
                <span class="mono">{{ upload.state.progressPercent }}%</span>
              </div>
              <div class="progress-track">
                <div class="progress-bar" :style="{ width: `${upload.state.progressPercent}%` }"></div>
              </div>
              <div class="info-meta">
                <span>{{ upload.state.completedProjectId || '当前任务' }}</span>
                <span>{{ upload.state.stageLabel || formatUploadPhase(upload.state.uploadPhase) }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";

import { useProjectCatalog } from "./composables/useProjectCatalog";
import { useSeedUpload } from "./composables/useSeedUpload";
import { APP_BRAND_NAME, APP_SUBTITLE, formatUploadPhase } from "./utils/chineseDisplay";

const route = useRoute();
const upload = useSeedUpload();
const { refreshProjects } = useProjectCatalog();
const showUploadOverlay = ref(false);

const mainNav = [
  { path: "/", label: "总览", code: "00" },
  { path: "/archive-library", label: "档案库", code: "01" },
  { path: "/story-graph", label: "故事图谱", code: "02" },
  { path: "/writer", label: "写作台", code: "03" },
  { path: "/worldline", label: "世界线", code: "04" },
  { path: "/character-console", label: "角色控制", code: "05" },
];

const subNav = [
  { path: "/guide", label: "帮助指南" },
  { path: "/llm-facility", label: "设施面板" },
];

const currentNavLabel = computed(() => {
  const allNav = [...mainNav, ...subNav];
  const item = allNav.find((n) => n.path === route.path);
  return item ? item.label : "工作台";
});

watch(() => upload.state.uploadPhase, (val) => {
  if (val !== 'idle') {
    // Optionally auto-show overlay on start, or keep it subtle
  }
});

onMounted(() => {
  refreshProjects().catch((error) => {
    console.error(error);
  });
});
</script>

<style scoped>
.shell {
  display: flex;
  min-height: 100vh;
  background: var(--bg-paper);
}

.left-track {
  width: 240px;
  background: var(--bg-paper-warm);
  border-right: 1px solid var(--line-soft);
  display: flex;
  flex-direction: column;
  padding: var(--space-lg);
  position: sticky;
  top: 0;
  height: 100vh;
}

.brand {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  margin-bottom: var(--space-xl);
}

.seal {
  width: 50px;
  height: 50px;
  background: var(--accent-seal);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-ink);
  transform: rotate(-3deg);
}

.seal-inner {
  color: #fff;
  font-family: "JetBrains Mono", monospace;
  font-weight: 800;
  font-size: 20px;
  border: 1px solid rgba(255,255,255,0.4);
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-name {
  font-family: "ZCOOL XiaoWei", serif;
  font-size: 24px;
  letter-spacing: 0.1em;
  color: var(--bg-ink);
}

.brand-sub {
  font-size: 11px;
  color: var(--text-sub);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.nav-track {
  display: flex;
  flex-direction: column;
  gap: var(--space-xl);
  flex: 1;
}

.nav-group {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.group-label {
  font-size: 11px;
  color: var(--text-dim);
  margin-bottom: var(--space-sm);
  letter-spacing: 0.2em;
  padding-left: 12px;
}

.nav-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  text-decoration: none;
  color: var(--text-sub);
  border-radius: var(--radius-sm);
  transition: all 0.2s ease;
  position: relative;
  gap: var(--space-sm);
}

.nav-dot {
  width: 4px;
  height: 4px;
  background: transparent;
  border-radius: 50%;
  transition: all 0.2s ease;
}

.nav-label {
  font-size: 15px;
  font-weight: 500;
  flex: 1;
}

.nav-code {
  font-size: 11px;
  opacity: 0.3;
}

.nav-item:hover {
  background: rgba(44, 42, 39, 0.04);
  color: var(--text-main);
}

.nav-item.router-link-active {
  background: #fff;
  color: var(--accent-copper-deep);
  box-shadow: var(--shadow-sm);
}

.nav-item.router-link-active .nav-dot {
  background: var(--accent-copper);
  box-shadow: 0 0 8px var(--accent-copper);
}

.nav-item.router-link-active .nav-code {
  opacity: 0.8;
}

.nav-item.sub {
  padding: 6px 12px;
  font-size: 13px;
}

.track-footer {
  margin-top: auto;
  padding-top: var(--space-md);
}

.mini-status {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 8px 12px;
  background: rgba(176, 125, 75, 0.08);
  border: 1px solid rgba(176, 125, 75, 0.2);
  border-radius: var(--radius-sm);
  cursor: pointer;
  font-size: 12px;
  color: var(--accent-copper-deep);
}

.status-pulse {
  width: 8px;
  height: 8px;
  background: var(--accent-copper);
  border-radius: 50%;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(176, 125, 75, 0.7); }
  70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(176, 125, 75, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(176, 125, 75, 0); }
}

.main-stage {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.stage-header {
  height: 64px;
  padding: 0 var(--space-xl);
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--line-soft);
  background: rgba(255, 255, 255, 0.5);
  backdrop-filter: blur(8px);
  position: sticky;
  top: 0;
  z-index: 10;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.breadcrumb .title-ancient {
  font-size: 20px;
  color: var(--bg-ink);
}

.stage-content {
  padding: var(--space-xl);
  flex: 1;
}

/* Overlay Styles */
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(44, 42, 39, 0.4);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.overlay-card {
  width: 480px;
  padding: var(--space-lg);
  animation: slideUp 0.3s ease-out;
}

.overlay-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-lg);
}

.progress-info {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.progress-track {
  height: 6px;
  background: var(--bg-paper);
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: var(--accent-copper);
  transition: width 0.3s ease;
}

.info-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-dim);
}

@keyframes slideUp {
  from { transform: translateY(20px); opacity: 0; }
  to { transform: translateY(0); opacity: 1; }
}

.fade-enter-active, .fade-leave-active { transition: opacity 0.3s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

@media (max-width: 980px) {
  .shell { flex-direction: column; }
  .left-track { width: 100%; height: auto; position: static; }
  .nav-track { display: none; } /* Add mobile menu toggle if needed */
}
</style>
````

## `frontend/src/styles.css`

````css
:root {
  /* Colors - Light Ancient Palette */
  --bg-paper: #f8f5f0;
  --bg-paper-warm: #f4efe2;
  --bg-ink: #2c2a27;
  --bg-panel: #ffffff;
  --bg-panel-soft: #faf8f5;
  
  --line-soft: #e2dcd0;
  --line-medium: #d8cdb5;
  --line-strong: #9f8d6a;
  
  --text-main: #2c2a27;
  --text-sub: #786e60;
  --text-dim: #a8a095;
  
  --accent-copper: #b07d4b;
  --accent-copper-deep: #8f4f1f;
  --accent-seal: #9b4326;
  --accent-green: #4a6d54;
  --accent-blue: #3d5a80;
  
  /* Spacing */
  --space-xs: 4px;
  --space-sm: 8px;
  --space-md: 16px;
  --space-lg: 24px;
  --space-xl: 40px;
  
  /* Border Radius */
  --radius-sm: 6px;
  --radius-md: 12px;
  --radius-lg: 20px;
  --radius-full: 999px;
  
  /* Shadows */
  --shadow-sm: 0 2px 8px rgba(44, 42, 39, 0.05);
  --shadow-md: 0 8px 20px rgba(44, 42, 39, 0.08);
  --shadow-lg: 0 16px 48px rgba(44, 42, 39, 0.12);
  --shadow-ink: 0 4px 12px rgba(44, 42, 39, 0.2);
}

* {
  box-sizing: border-box;
}

html,
body,
#app {
  margin: 0;
  min-height: 100vh;
  color: var(--text-main);
  background: var(--bg-paper);
  background-image: 
    radial-gradient(at 0% 0%, rgba(176, 125, 75, 0.05) 0px, transparent 50%),
    radial-gradient(at 100% 0%, rgba(61, 90, 128, 0.05) 0px, transparent 50%);
  font-family: "IBM Plex Sans SC", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
}

/* Scrollbar */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: transparent;
}
::-webkit-scrollbar-thumb {
  background: var(--line-medium);
  border-radius: 3px;
}
::-webkit-scrollbar-thumb:hover {
  background: var(--line-strong);
}

/* Typography */
h1, h2, h3, h4, .title-ancient {
  font-family: "ZCOOL XiaoWei", serif;
  font-weight: 400;
  margin: 0;
  letter-spacing: 0.02em;
}

.mono {
  font-family: "JetBrains Mono", "Courier New", monospace;
  font-size: 0.9em;
}

/* Layout Utilities */
.container-6-4 {
  display: grid;
  grid-template-columns: 6fr 4fr;
  gap: var(--space-lg);
}

.container-7-5 {
  display: grid;
  grid-template-columns: 7fr 5fr;
  gap: var(--space-lg);
}

.stack {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

/* Components */
.workbench-card {
  background: var(--bg-panel);
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-sm);
  transition: box-shadow 0.2s ease, border-color 0.2s ease;
}

.workbench-card:hover {
  box-shadow: var(--shadow-md);
  border-color: var(--line-medium);
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-sm);
  padding: 10px 20px;
  border-radius: var(--radius-full);
  border: 1px solid var(--line-strong);
  background: var(--bg-panel);
  color: var(--text-main);
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  text-decoration: none;
}

.btn:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
  background: var(--bg-paper);
}

.btn:active {
  transform: translateY(0);
}

.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}

.btn.primary {
  background: var(--accent-copper);
  border-color: var(--accent-copper);
  color: #ffffff;
}

.btn.primary:hover {
  background: var(--accent-copper-deep);
  border-color: var(--accent-copper-deep);
}

.btn.subtle {
  border-color: transparent;
  background: transparent;
  color: var(--text-sub);
}

.btn.subtle:hover {
  background: var(--bg-paper-warm);
  color: var(--text-main);
}

/* Forms */
.field {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

.field label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-sub);
  margin-left: 4px;
}

.field input,
.field textarea,
.field select {
  width: 100%;
  padding: 12px 16px;
  border-radius: var(--radius-md);
  border: 1px solid var(--line-soft);
  background: var(--bg-panel-soft);
  font-family: inherit;
  font-size: 14px;
  transition: all 0.2s ease;
}

.field input:focus,
.field textarea:focus,
.field select:focus {
  outline: none;
  border-color: var(--accent-copper);
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(176, 125, 75, 0.1);
}

/* Status Tags */
.status-tag {
  display: inline-flex;
  align-items: center;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.status-tag.ok {
  background: rgba(74, 109, 84, 0.1);
  color: var(--accent-green);
}

.status-tag.warn {
  background: rgba(176, 125, 75, 0.1);
  color: var(--accent-copper);
}

.status-tag.danger {
  background: rgba(155, 67, 38, 0.1);
  color: var(--accent-seal);
}

@media (max-width: 960px) {
  .container-6-4, .container-7-5 {
    grid-template-columns: 1fr;
  }
}


@media (max-width: 960px) {
  .card-title {
    font-size: 20px;
  }
}
````

## `frontend/src/router/index.js`

````js
import { createRouter, createWebHistory } from "vue-router";
import OverviewView from "../views/OverviewView.vue";
import GuideView from "../views/GuideView.vue";
import ArchiveLibraryView from "../views/ArchiveLibraryView.vue";
import StoryGraphWorkbenchView from "../views/StoryGraphWorkbenchView.vue";
import WorldlineWorkbenchView from "../views/WorldlineWorkbenchView.vue";
import WriterWorkbenchView from "../views/WriterWorkbenchView.vue";
import CharacterConsoleView from "../views/CharacterConsoleView.vue";
import LlmFacilityView from "../views/LlmFacilityView.vue";

const routes = [
  { path: "/", name: "overview", component: OverviewView },
  { path: "/guide", name: "guide", component: GuideView },
  { path: "/archive-library", name: "archive-library", component: ArchiveLibraryView },
  { path: "/story-graph", name: "story-graph", component: StoryGraphWorkbenchView },
  { path: "/writer", name: "writer", component: WriterWorkbenchView },
  { path: "/worldline", name: "worldline", component: WorldlineWorkbenchView },
  { path: "/character-console", name: "character-console", component: CharacterConsoleView },
  { path: "/llm-facility", name: "llm-facility", component: LlmFacilityView },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior(to, from, savedPosition) {
    if (savedPosition) {
      return savedPosition;
    }
    if (to.hash) {
      return {
        el: to.hash,
        behavior: "smooth",
      };
    }
    if (to.path !== from.path) {
      return { top: 0 };
    }
    return undefined;
  },
});

export default router;
````

## `frontend/src/views/OverviewView.vue`

````vue
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
  width: 100%;
  align-items: stretch;
}

.hero-section,
.recent-projects,
.phase-preview,
.active-task-preview,
.results-preview,
.task-panel,
.hidden-upload {
  width: 100%;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-md);
  flex-wrap: wrap;
  margin-bottom: var(--space-md);
}

.project-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
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
  justify-content: space-between;
  align-items: baseline;
  flex-wrap: wrap;
  gap: var(--space-md);
  margin-bottom: var(--space-md);
}

.preview-header .mono {
  font-size: 13px;
  color: var(--text-dim);
}

.empty-guide-preview {
  grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
  align-items: stretch;
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
  min-height: 220px;
}

.flow-placeholder {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-wrap: wrap;
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

@media (max-width: 1180px) {
  .empty-guide-preview {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .project-strip {
    grid-template-columns: 1fr;
  }
}
</style>
````

## `frontend/src/views/overview/SeedUploadPanel.vue`

````vue
<template>
  <article :class="['upload-container', { stack: !hasActiveTask, 'with-active-task': hasActiveTask }]">
    <div class="upload-main workbench-card">
      <header class="upload-header">
        <h2 class="title-ancient">卷宗投放</h2>
        <p class="subtitle">将小说文本投放至此，开启自动化解构管线。</p>
      </header>

      <div class="upload-form stack">
        <div class="field">
          <label>项目/卷宗名称</label>
          <input v-model="upload.state.projectName" placeholder="例如：天穹秘约" :disabled="upload.state.uploadBusy" />
        </div>

        <div
          class="dropzone"
          :class="{ active: upload.state.dragActive, busy: upload.state.uploadBusy, hasFiles: upload.state.files.length }"
          @dragenter.prevent="upload.state.dragActive = true"
          @dragover.prevent="upload.state.dragActive = true"
          @dragleave.prevent="upload.state.dragActive = false"
          @drop.prevent="handleDrop"
          @click="openPicker"
        >
          <input
            ref="fileInputRef"
            class="hidden-input"
            type="file"
            multiple
            accept=".txt,.md,.markdown,.pdf"
            @change="handleChange"
          />
          <div class="drop-icon">📤</div>
          <div v-if="!upload.state.files.length" class="drop-text">
            <strong>拖拽文件到这里</strong>
            <span>或点击选择 (txt, md, pdf)</span>
          </div>
          <div v-else class="selected-files">
            <div v-for="item in upload.state.files" :key="upload.fileKey(item)" class="file-chip">
              <span class="file-name">{{ item.name }}</span>
              <button class="remove-btn" @click.stop="upload.removeFile(item)">×</button>
            </div>
          </div>
        </div>

        <div class="advanced-toggle" @click="showAdvanced = !showAdvanced">
          <span class="toggle-icon">{{ showAdvanced ? '▾' : '▸' }}</span>
          <span>高级分析配置</span>
        </div>

        <Transition name="slide">
          <div v-if="showAdvanced" class="advanced-fields stack">
            <div class="field">
              <label>分析目标</label>
              <textarea v-model="upload.state.analysisGoal" placeholder="明确您的分析重点，如：重点提取支线剧情与隐藏关系。" :disabled="upload.state.uploadBusy"></textarea>
            </div>
            <div class="field">
              <label>补充背景</label>
              <textarea v-model="upload.state.additionalContext" placeholder="提供世界观、术语表或既定设定，有助于提升分析精度。" :disabled="upload.state.uploadBusy"></textarea>
            </div>
          </div>
        </Transition>

        <div class="upload-actions">
          <button class="btn primary large" :disabled="!canSubmit || upload.state.uploadBusy" @click="submitUpload">
            {{ upload.state.uploadBusy ? "管线分析中..." : "启动管线分析" }}
          </button>
        </div>
      </div>

      <div v-if="upload.state.error" class="status-error mono">{{ upload.state.error }}</div>
    </div>

    <!-- Active Task Status Section -->
    <Transition name="fade">
      <aside v-if="hasActiveTask" class="active-task-area stack">
        <div class="task-progress-card workbench-card stack">
          <h3 class="title-ancient">实时管线状态</h3>
          <PipelineVisualization
            :upload-phase="upload.state.uploadPhase"
            :task-status="upload.state.taskStatus"
            :active-stage="upload.state.activeStage"
          />
          <div class="progress-details stack">
            <div class="progress-row">
              <strong>{{ upload.state.statusText }}</strong>
              <span class="mono">{{ upload.state.progressPercent }}%</span>
            </div>
            <div class="progress-track">
              <div class="progress-bar" :style="{ width: `${upload.state.progressPercent}%` }"></div>
            </div>
            <div class="progress-meta mono">
              <span>{{ upload.state.activeStage.label || '准备分析' }}</span>
              <span v-if="upload.state.taskMetrics.totalBlocks">
                {{ upload.state.taskMetrics.completedBlocks }}/{{ upload.state.taskMetrics.totalBlocks }} 块
              </span>
            </div>
          </div>
        </div>

        <div class="task-logs-card workbench-card">
          <div class="logs-header">
            <h3 class="title-ancient">后台日志</h3>
            <button class="btn subtle small" @click="showLogs = !showLogs">{{ showLogs ? '收起日志' : '展开日志' }}</button>
          </div>
          <SeedTaskLogPanel
            v-if="showLogs"
            :upload-phase="upload.state.uploadPhase"
            :task-status="upload.state.taskStatus"
            :active-stage="upload.state.activeStage"
            :task-metrics="upload.state.taskMetrics"
            :llm-activity="upload.state.llmActivity"
            :timeline="upload.state.timeline"
            :task-started-at="upload.state.taskStartedAt"
          />
        </div>
      </aside>
    </Transition>
  </article>
</template>

<script setup>
import { computed, ref, watch } from "vue";

import { useSeedUpload } from "../../composables/useSeedUpload";
import PipelineVisualization from "./PipelineVisualization.vue";
import SeedTaskLogPanel from "./SeedTaskLogPanel.vue";

const emit = defineEmits(["uploaded"]);
const upload = useSeedUpload();
const fileInputRef = ref(null);
const showAdvanced = ref(false);
const showLogs = ref(true);

const canSubmit = computed(() => upload.state.projectName.trim() && upload.state.files.length > 0);
const hasActiveTask = computed(() => upload.state.uploadPhase !== "idle");

let lastEmittedProjectId = "";

function openPicker() {
  if (upload.state.uploadBusy) return;
  fileInputRef.value?.click();
}

function handleChange(event) {
  upload.appendFiles(Array.from(event.target.files || []));
  event.target.value = "";
}

function handleDrop(event) {
  if (upload.state.uploadBusy) return;
  upload.state.dragActive = false;
  upload.appendFiles(Array.from(event.dataTransfer?.files || []));
}

async function submitUpload() {
  try {
    await upload.submitUpload();
  } catch {
    return;
  }
}

watch(
  () => upload.state.result?.project_id,
  (projectId) => {
    if (!projectId || projectId === lastEmittedProjectId) return;
    lastEmittedProjectId = projectId;
    emit("uploaded", upload.state.result);
  },
  { immediate: true },
);
</script>

<style scoped>
.upload-container {
  width: 100%;
}

.upload-container.with-active-task {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
  gap: var(--space-lg);
  align-items: start;
}

.upload-main {
  min-width: 0;
  padding: var(--space-xl);
  background-image: 
    linear-gradient(135deg, rgba(176, 125, 75, 0.02) 0%, transparent 40%),
    linear-gradient(var(--bg-panel), var(--bg-panel));
}

.upload-header {
  margin-bottom: var(--space-lg);
  text-align: center;
}

.subtitle {
  color: var(--text-dim);
  font-size: 14px;
  margin-top: 4px;
}

.dropzone {
  border: 2px dashed var(--line-medium);
  border-radius: var(--radius-lg);
  padding: var(--space-xl);
  background: var(--bg-paper-warm);
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-md);
  text-align: center;
}

.dropzone:hover {
  border-color: var(--accent-copper);
  background: #ffffff;
}

.dropzone.active {
  border-color: var(--accent-copper-deep);
  background: rgba(176, 125, 75, 0.05);
}

.dropzone.busy {
  cursor: wait;
  opacity: 0.7;
}

.drop-icon {
  font-size: 40px;
  opacity: 0.6;
}

.drop-text strong {
  display: block;
  font-size: 16px;
  color: var(--text-main);
}

.drop-text span {
  font-size: 13px;
  color: var(--text-dim);
}

.selected-files {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  justify-content: center;
}

.file-chip {
  background: #fff;
  border: 1px solid var(--line-medium);
  border-radius: var(--radius-full);
  padding: 4px 12px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  box-shadow: var(--shadow-sm);
}

.remove-btn {
  border: none;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}

.remove-btn:hover {
  color: var(--accent-seal);
}

.hidden-input {
  display: none;
}

.advanced-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  font-size: 13px;
  color: var(--text-sub);
  cursor: pointer;
  user-select: none;
  width: fit-content;
}

.advanced-toggle:hover {
  color: var(--accent-copper);
}

.toggle-icon {
  font-family: monospace;
  font-size: 16px;
}

.upload-actions {
  display: flex;
  justify-content: center;
  margin-top: var(--space-md);
}

.large {
  padding: 14px 48px;
  font-size: 16px;
}

.active-task-area {
  min-width: 0;
}

.task-progress-card, .task-logs-card {
  padding: var(--space-lg);
  min-width: 0;
}

.progress-row {
  display: flex;
  justify-content: space-between;
}

.progress-track {
  height: 6px;
  background: var(--bg-paper);
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: var(--accent-copper);
  transition: width 0.3s ease;
}

.progress-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-dim);
}

.logs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-md);
}

.status-error {
  padding: var(--space-md);
  background: rgba(155, 67, 38, 0.05);
  border-radius: var(--radius-md);
  color: var(--accent-seal);
  font-size: 13px;
  margin-top: var(--space-md);
}

.slide-enter-active, .slide-leave-active { transition: all 0.3s ease-out; max-height: 300px; overflow: hidden; }
.slide-enter-from, .slide-leave-to { max-height: 0; opacity: 0; }

@media (max-width: 1180px) {
  .upload-container.with-active-task {
    grid-template-columns: 1fr;
  }
}
</style>
````

## `frontend/src/components/ArchiveLibraryPicker.vue`

````vue
<template>
  <div
    ref="stageRef"
    class="archive-museum"
    :class="[layoutMode, { resizing }]"
    :style="stageStyle"
  >
    <header class="museum-toolbar workbench-card">
      <div class="search-box">
        <span class="search-icon">🔍</span>
        <input v-model="searchText" placeholder="搜寻角色、组织、动机、关系..." />
      </div>

      <div class="filter-controls">
        <div class="filter-group">
          <label>卷宗</label>
          <select v-model="localProjectFilter">
            <option value="">全部</option>
            <option v-for="item in projectOptions" :key="item.project_id" :value="item.project_id">
              {{ item.name }}
            </option>
          </select>
        </div>

        <div class="filter-group">
          <label>类别</label>
          <select v-model="entityType">
            <option value="">全部</option>
            <option value="Character">角色</option>
            <option value="Organization">组织</option>
          </select>
        </div>

        <div class="filter-group">
          <label>位阶</label>
          <select v-model="importanceTier">
            <option value="">全部</option>
            <option value="protagonist">主角</option>
            <option value="major">主要</option>
            <option value="supporting">次要</option>
          </select>
        </div>
      </div>
    </header>

    <main class="museum-stage">
      <section class="archive-pane list-pane">
        <div class="pane-head">
          <div class="pane-copy">
            <p class="pane-kicker mono">ARCHIVE SHELVES</p>
            <h3>档案目录</h3>
            <p>统一检索、筛选并挑选进入会话的角色与组织档案。</p>
          </div>
          <div class="list-summary">
            <span v-if="loading" class="mono">载入中...</span>
            <span v-else class="mono">找到 {{ total }} 条档案</span>
            <span v-if="selectedArchives.length" class="selection-summary">
              {{ selectedArchives.length }} 已选
            </span>
          </div>
        </div>

        <p v-if="error" class="error-text">{{ error }}</p>

        <div class="scroll-list">
          <ArchiveLibraryGridItem
            v-for="item in items"
            :key="item.archive_id"
            :active="activeArchiveId === item.archive_id"
            :item="item"
            :selected="selectedIdSet.has(item.archive_id)"
            @select="selectActive(item)"
            @toggle="toggleSelected(item)"
          />

          <div v-if="!items.length && !loading" class="empty-museum">
            <div class="empty-icon">📜</div>
            <p>未找到符合条件的档案</p>
          </div>
        </div>
      </section>

      <button
        class="museum-divider"
        type="button"
        aria-label="拖拽调整档案列表与详情宽度"
        aria-orientation="vertical"
        @pointerdown.prevent="beginResize"
      >
        <span></span>
      </button>

      <aside class="archive-pane detail-pane">
        <div class="pane-head detail-head">
          <div class="pane-copy">
            <p class="pane-kicker mono">DOSSIER VIEW</p>
            <h3>{{ activeDetail ? activeDetail.entity_name : "档案详情" }}</h3>
            <p>右侧保留完整档案，便于边筛选边确认人物、势力与关系脉络。</p>
          </div>
          <p class="detail-hint">{{ activeDetail ? "当前聚焦卷宗" : "等待选中档案" }}</p>
        </div>

        <div class="detail-scroll">
          <ArchiveLibraryDetailCard
            :archive="activeDetail"
            :selected="selectedIdSet.has(activeDetail?.archive_id)"
            @toggle="toggleSelected(activeDetail)"
          />
        </div>
      </aside>
    </main>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { getArchiveLibraryDetail, listArchiveLibrary } from "../api/archive.js";
import { listProjects } from "../api/project.js";
import ArchiveLibraryDetailCard from "./ArchiveLibraryDetailCard.vue";
import ArchiveLibraryGridItem from "./ArchiveLibraryGridItem.vue";
import { useArchiveLibraryLayout } from "../composables/useArchiveLibraryLayout.js";
import { toggleArchiveSelection } from "../views/shared/worldlineSelectorState.js";

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  projectFilter: { type: String, default: "" },
});

const emit = defineEmits(["update:modelValue", "update:projectFilter"]);

const searchText = ref("");
const localProjectFilter = ref(props.projectFilter);
const entityType = ref("");
const importanceTier = ref("");
const projectOptions = ref([]);
const items = ref([]);
const total = ref(0);
const activeArchiveId = ref("");
const activeDetail = ref(null);
const loading = ref(false);
const error = ref("");
let reloadTimer = 0;

const selectedArchives = computed(() => props.modelValue || []);
const selectedIdSet = computed(() => new Set(selectedArchives.value.map((item) => item.archive_id)));
const { beginResize, layoutMode, resizing, stageRef, stageStyle } = useArchiveLibraryLayout();

watch(() => props.projectFilter, (value) => {
  localProjectFilter.value = value || "";
});

watch(localProjectFilter, (value) => {
  emit("update:projectFilter", value);
});

watch([searchText, localProjectFilter, entityType, importanceTier], scheduleReload);

async function loadProjects() {
  const response = await listProjects(100);
  projectOptions.value = response.data || [];
}

function scheduleReload() {
  clearTimeout(reloadTimer);
  reloadTimer = window.setTimeout(() => {
    loadItems();
  }, 200);
}

async function syncActiveArchive(nextItems) {
  if (!nextItems.length) {
    activeArchiveId.value = "";
    activeDetail.value = null;
    return;
  }
  const currentItem = nextItems.find((item) => item.archive_id === activeArchiveId.value);
  if (currentItem) {
    if (!activeDetail.value || activeDetail.value.archive_id !== currentItem.archive_id) {
      activeDetail.value = currentItem;
    }
    return;
  }
  await selectActive(nextItems[0]);
}

async function loadItems() {
  try {
    loading.value = true;
    error.value = "";
    const response = await listArchiveLibrary({
      q: searchText.value.trim(),
      projectId: localProjectFilter.value,
      entityType: entityType.value,
      importanceTier: importanceTier.value,
      limit: 60,
    });
    items.value = response.data?.items || [];
    total.value = response.data?.total || 0;
    await syncActiveArchive(items.value);
  } catch (err) {
    items.value = [];
    total.value = 0;
    activeArchiveId.value = "";
    activeDetail.value = null;
    error.value = err.message || "档案读取失败";
  } finally {
    loading.value = false;
  }
}

async function selectActive(item) {
  activeArchiveId.value = item.archive_id;
  try {
    const response = await getArchiveLibraryDetail(item.archive_id);
    activeDetail.value = response.data || item;
  } catch {
    activeDetail.value = item;
  }
}

function toggleSelected(item) {
  if (!item) {
    return;
  }
  emit("update:modelValue", toggleArchiveSelection(selectedArchives.value, item));
}

function reload() {
  return loadItems();
}

defineExpose({ reload });

onMounted(async () => {
  await loadProjects();
  await loadItems();
});

onBeforeUnmount(() => {
  clearTimeout(reloadTimer);
});
</script>

<style scoped src="./ArchiveLibraryPicker.css"></style>
````

## `frontend/src/components/ArchiveLibraryPicker.css`

````css
.archive-museum {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  height: calc(100vh - 170px);
  min-height: 620px;
}
.museum-toolbar {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  border-radius: 24px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(246, 241, 231, 0.92));
  box-shadow: 0 14px 34px rgba(44, 42, 39, 0.05);
}
.search-box {
  flex: 1 1 460px;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 16px;
  border-radius: var(--radius-full);
  border: 1px solid rgba(159, 141, 106, 0.24);
  background: rgba(255, 255, 255, 0.82);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.55);
}
.search-icon { font-size: 17px; opacity: 0.8; }
.search-box input {
  width: 100%;
  border: none;
  background: transparent;
  padding: 13px 0;
  font-size: 15px;
  color: var(--text-main);
}
.search-box:focus-within {
  border-color: rgba(176, 125, 75, 0.46);
  box-shadow: 0 0 0 3px rgba(176, 125, 75, 0.12);
}
.search-box input:focus,
.filter-group select:focus {
  outline: none;
}
.filter-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.filter-group {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 44px;
  padding: 0 14px;
  border-radius: var(--radius-full);
  border: 1px solid rgba(159, 141, 106, 0.22);
  background: rgba(255, 255, 255, 0.78);
  color: var(--text-sub);
  font-size: 13px;
}
.filter-group label { color: var(--accent-copper-deep); }
.filter-group select {
  min-width: 78px;
  border: none;
  background: transparent;
  color: var(--text-main);
  font-size: 13px;
}
.museum-stage {
  display: grid;
  grid-template-columns:
    minmax(0, calc((100% - var(--archive-library-divider-size)) * var(--archive-library-left-pane-ratio)))
    var(--archive-library-divider-size)
    minmax(0, calc((100% - var(--archive-library-divider-size)) * var(--archive-library-right-pane-ratio)));
  gap: 0;
  flex: 1;
  min-height: 0;
}
.archive-pane {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid rgba(159, 141, 106, 0.22);
  border-radius: 26px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.97), rgba(246, 241, 231, 0.9));
  box-shadow: 0 22px 48px rgba(44, 42, 39, 0.05);
  position: relative;
}
.archive-pane::before {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  border-radius: inherit;
  background:
    radial-gradient(circle at top left, rgba(255, 255, 255, 0.62), transparent 42%),
    linear-gradient(180deg, rgba(255, 255, 255, 0.08), transparent 22%);
}
.list-pane {
  container-type: inline-size;
  padding-right: var(--space-md);
}
.detail-pane {
  padding-left: var(--space-md);
}
.pane-head,
.detail-scroll,
.scroll-list {
  position: relative;
  z-index: 1;
}
.pane-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 20px 16px;
  border-bottom: 1px solid rgba(159, 141, 106, 0.14);
}
.pane-copy {
  display: grid;
  gap: 6px;
}
.pane-copy h3,
.pane-copy p,
.detail-hint,
.error-text {
  margin: 0;
}
.pane-kicker {
  color: var(--accent-copper-deep);
  letter-spacing: 0.14em;
  font-size: 11px;
}
.pane-copy h3 { font-size: 24px; }
.pane-copy p,
.detail-hint {
  color: var(--text-sub);
}
.list-summary {
  display: flex;
  align-items: center;
  align-self: flex-start;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  text-align: right;
  color: var(--text-dim);
}
.selection-summary {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 4px 12px;
  border-radius: var(--radius-full);
  background: rgba(176, 125, 75, 0.12);
  color: var(--accent-copper-deep);
}
.error-text {
  padding: 0 20px;
  color: var(--accent-seal);
}
.scroll-list,
.detail-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding-bottom: 20px;
}
.scroll-list {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  align-content: start;
  padding-left: 20px;
  padding-right: 8px;
}
.detail-scroll {
  padding-right: 8px;
}
.detail-head { align-items: flex-start; }
.detail-hint {
  align-self: flex-start;
  padding: 8px 12px;
  border-radius: var(--radius-full);
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(159, 141, 106, 0.14);
  white-space: nowrap;
}
.museum-divider {
  border: none;
  padding: 0;
  margin: 0 var(--space-xs);
  background: transparent;
  cursor: col-resize;
  position: relative;
}
.museum-divider span {
  position: absolute;
  inset: 0;
}
.museum-divider::before {
  content: "";
  position: absolute;
  top: 26px;
  bottom: 26px;
  left: 50%;
  width: 6px;
  transform: translateX(-50%);
  border-radius: var(--radius-full);
  background: linear-gradient(180deg, rgba(226, 210, 180, 0.96), rgba(176, 125, 75, 0.9));
  box-shadow: 0 10px 24px rgba(176, 125, 75, 0.18);
}
.archive-museum.resizing .museum-divider::before,
.museum-divider:hover::before {
  background: linear-gradient(180deg, #d7b988, #8f4f1f);
}
.empty-museum {
  grid-column: 1 / -1;
  padding: 56px 24px;
  text-align: center;
  color: var(--text-dim);
  border: 1px dashed rgba(159, 141, 106, 0.32);
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.62);
}
.empty-icon { font-size: 42px; margin-bottom: var(--space-md); }
@container (max-width: 820px) {
  .scroll-list {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 1100px) {
  .museum-toolbar {
    align-items: stretch;
    flex-direction: column;
  }
  .search-box {
    flex-basis: auto;
    width: 100%;
  }
  .filter-controls {
    width: 100%;
  }
}
@media (max-width: 840px) {
  .filter-controls {
    display: grid;
    grid-template-columns: 1fr;
  }
  .filter-group {
    justify-content: space-between;
  }
}
.archive-museum.stacked {
  height: auto;
  min-height: 0;
}
.archive-museum.stacked .museum-stage {
  grid-template-columns: 1fr;
  gap: var(--space-md);
}
.archive-museum.stacked .museum-toolbar {
  align-items: stretch;
}
.archive-museum.stacked .museum-divider {
  display: none;
}
.archive-museum.stacked .list-pane,
.archive-museum.stacked .detail-pane {
  padding: 0;
}
.archive-museum.stacked .search-box {
  flex-basis: auto;
  width: 100%;
}
.archive-museum.stacked .scroll-list,
.archive-museum.stacked .detail-scroll {
  padding-right: 20px;
}
@media (max-width: 760px) {
  .pane-head {
    flex-direction: column;
  }
  .detail-hint {
    white-space: normal;
  }
}
````

## `frontend/src/views/StoryGraphWorkbenchView.vue`

````vue
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
        <p class="subtitle">基于图谱生成角色档案；世界线创建与变量注入统一在世界线工作台完成。</p>

        <div class="actions stack">
          <button class="btn" :disabled="!currentGraphId || busy" @click="openArchiveConfigurator">生成全量角色档案</button>
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
import { onMounted, ref } from "vue";
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
````

## `frontend/src/components/StoryGraphPanel.vue`

````vue
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
        <button class="btn" type="button" @click="resetVisibleTypes">核心视图</button>
        <button class="btn" type="button" @click="showEdgeLabels = !showEdgeLabels">
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
      <span class="graph-meta mono">当前显示 {{ visibleNodeCount }} / {{ props.nodes.length }} 个节点</span>
    </div>

    <div class="panel-body">
      <div ref="canvasRef" class="canvas-area">
        <svg ref="svgRef" class="graph-svg" aria-label="故事图谱" />
        <div class="canvas-mask" aria-hidden="true"></div>
        <div v-if="!visibleNodeCount" class="empty-box">暂无图谱数据。可先选择项目并构建图谱。</div>
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
      <StoryGraphInspector :selected-node="selectedNode" :selected-edge="selectedEdge" />
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from "vue";

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
````

## `frontend/src/views/WriterWorkbenchView.vue`

````vue
<template>
  <div class="writer-stage" :class="workbenchMode" :style="{ gridTemplateColumns: gridTemplateColumns }">
    <aside class="writer-panel writer-controls workbench-card">
      <p class="panel-kicker mono">WRITER CONTEXT</p>
      <h2 class="panel-title title-ancient">写作工作台</h2>
      <p class="panel-subtitle">先选写作范围，再生成可直接喂给作者 Agent 的上下文包。</p>
      <p class="panel-status" :class="{ warning: !!error }">{{ error || message }}</p>

      <div class="writer-form">
        <div class="field">
          <label>项目</label>
          <select v-model="projectId" @change="handleProjectChange">
            <option value="">请选择项目</option>
            <option v-for="item in projects" :key="item.project_id" :value="item.project_id">
              {{ item.name }} · {{ item.project_id }}
            </option>
          </select>
        </div>

        <div class="scope-switch">
          <button
            v-for="item in scopeOptions"
            :key="item.value"
            type="button"
            class="scope-chip"
            :class="{ active: scopeType === item.value }"
            @click="updateScopeType(item.value)"
          >
            {{ item.label }}
          </button>
        </div>

        <div v-if="scopeType === 'project_chapter'" class="inline-grid">
          <div class="field">
            <label>章节</label>
            <select v-model="chapterId">
              <option value="">请选择章节</option>
              <option v-for="item in chapterOptions" :key="item.chapter_id" :value="item.chapter_id">
                第{{ item.order }}章 · {{ item.title }}
              </option>
            </select>
          </div>
          <div class="field">
            <label>POV</label>
            <select v-model="povCharacter">
              <option value="">请选择 POV</option>
              <option v-for="item in povOptions" :key="item" :value="item">{{ item }}</option>
            </select>
          </div>
        </div>

        <div v-else class="inline-grid">
          <div class="field">
            <label>世界线会话</label>
            <select v-model="sessionId" @change="handleSessionChange">
              <option value="">请选择会话</option>
              <option v-for="item in sessionOptions" :key="item.session_id" :value="item.session_id">
                {{ item.label }}
              </option>
            </select>
          </div>
          <div class="field">
            <label>POV</label>
            <select v-model="povCharacter">
              <option value="">请选择 POV</option>
              <option v-for="item in povOptions" :key="item" :value="item">{{ item }}</option>
            </select>
          </div>
        </div>

        <div class="field">
          <label>写作目标</label>
          <input v-model="writingGoal" type="text" placeholder="例如：生成本章场景卡 / 生成章节大纲" />
        </div>

        <div class="field">
          <label>场景焦点</label>
          <textarea v-model="sceneFocus" rows="4" placeholder="例如：废塔残响、顾行舟现身、镜湖谷公开对峙"></textarea>
        </div>

        <label class="inline-check">
          <input v-model="includeCandidates" type="checkbox" />
          <span>附带 candidate 设定</span>
        </label>

        <div class="panel-actions">
          <button class="btn primary" :disabled="busy || !canSubmit" @click="generatePack">
            {{ busy ? "生成中..." : "生成上下文包" }}
          </button>
          <button class="btn" :disabled="busy || !projectId" @click="refreshProjectData">刷新项目数据</button>
        </div>
      </div>
    </aside>

    <main class="writer-panel writer-context workbench-card">
      <p class="panel-kicker mono">CHAPTER CONTEXT PACK</p>
      <h2 class="panel-title title-ancient">上下文与 Prompt</h2>
      <p v-if="!contextPack" class="panel-empty">生成后会在这里显示 `must_know`、`warnings`、候选场景和稳定 prompt。</p>

      <div v-else class="context-sections">
        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">范围</h3>
            <span class="memory-badge">{{ contextPack.context_scope.scope_type }}</span>
          </div>
          <div class="context-list">
            <div class="context-item">
              <div class="context-summary">
                {{ contextScopeSummary }}
              </div>
              <div class="context-why">
                目标：{{ contextPack.context_scope.writing_goal || "未填写" }}；焦点：{{ contextPack.context_scope.scene_focus || "未填写" }}
              </div>
            </div>
          </div>
        </section>

        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">必须知道</h3>
            <span class="memory-badge">{{ contextPack.must_know.length }}</span>
          </div>
          <div class="context-list">
            <article
              v-for="item in contextPack.must_know"
              :key="item.item_id"
              class="context-item clickable"
              :class="{ active: selectedItem?.item_id === item.item_id }"
              @click="selectContextItem(item)"
            >
              <div class="context-topline">
                <span class="category-badge">{{ item.category }}</span>
                <span class="memory-badge" :class="{ candidate: item.memory_layer === 'candidate' }">{{ item.memory_layer }}</span>
              </div>
              <div class="context-summary">{{ item.summary }}</div>
              <div class="context-why">{{ item.why_it_matters }}</div>
            </article>
          </div>
        </section>

        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">应该知道</h3>
            <span class="memory-badge">{{ contextPack.should_know.length }}</span>
          </div>
          <div class="context-list">
            <article
              v-for="item in contextPack.should_know"
              :key="item.item_id"
              class="context-item clickable"
              :class="{ active: selectedItem?.item_id === item.item_id }"
              @click="selectContextItem(item)"
            >
              <div class="context-topline">
                <span class="category-badge">{{ item.category }}</span>
                <span class="memory-badge" :class="{ candidate: item.memory_layer === 'candidate' }">{{ item.memory_layer }}</span>
              </div>
              <div class="context-summary">{{ item.summary }}</div>
              <div class="context-why">{{ item.why_it_matters }}</div>
            </article>
          </div>
        </section>

        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">风险提示</h3>
            <span class="memory-badge warning-badge">{{ contextPack.warnings.length }}</span>
          </div>
          <div class="context-list">
            <article v-for="item in contextPack.warnings" :key="item.item_id" class="context-item">
              <div class="context-topline">
                <span class="category-badge">{{ item.category }}</span>
                <span class="memory-badge warning-badge">{{ item.rank_score }}</span>
              </div>
              <div class="context-summary">{{ item.summary }}</div>
              <div class="context-why">{{ item.why_it_matters }}</div>
            </article>
          </div>
        </section>

        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">候选场景</h3>
            <span class="memory-badge">{{ contextPack.scene_candidates.length }}</span>
          </div>
          <div class="scene-list">
            <article v-for="item in contextPack.scene_candidates" :key="item.title + item.setup" class="context-item">
              <div class="scene-title">{{ item.title }}</div>
              <div class="scene-copy">起点：{{ item.setup }}</div>
              <div class="scene-copy">张力：{{ item.tension }}</div>
              <div class="scene-copy">为什么现在：{{ item.why_now }}</div>
            </article>
          </div>
        </section>

        <section class="context-block prompt-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">Writer Prompt Block</h3>
          </div>
          <div>{{ contextPack.writer_prompt_block }}</div>
        </section>
      </div>
    </main>

    <aside class="writer-panel writer-debug workbench-card">
      <p class="panel-kicker mono">TRACE & REVIEW</p>
      <h2 class="panel-title title-ancient">来源与审校</h2>

      <div class="side-stack">
        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">调试来源</h3>
          </div>
          <div v-if="!contextPack?.debug_trace?.length" class="review-hint">生成上下文包后，这里会显示每条信息的来源和排序分数。</div>
          <div v-else class="trace-list">
            <article v-for="item in contextPack.debug_trace" :key="item.item_id" class="trace-item">
              <div class="trace-topline">
                <span class="category-badge">{{ item.category }}</span>
                <span class="score-badge">{{ item.rank_score }}</span>
              </div>
              <div class="trace-copy">{{ item.source_kind }} · {{ item.source_ref }}</div>
            </article>
          </div>
        </section>

        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">记忆审校</h3>
          </div>
          <div v-if="!selectedItem" class="review-hint">点选中间栏的 runtime memory 条目后，可在这里读取 timeline 并执行 adopt / reject。</div>
          <template v-else>
            <div class="timeline-card">
              <div class="timeline-topline">
                <span class="category-badge">{{ selectedItem.category }}</span>
                <span class="memory-badge" :class="{ candidate: selectedItem.memory_layer === 'candidate' }">{{ selectedItem.memory_layer }}</span>
              </div>
              <div class="timeline-title">{{ selectedItem.summary }}</div>
              <div class="timeline-copy">{{ selectedItem.why_it_matters }}</div>
              <div class="timeline-meta">{{ selectedItem.source_kind }} · {{ selectedItem.source_ref }}</div>
            </div>

            <div class="review-actions">
              <button class="btn" :disabled="reviewBusy || !canLoadTimeline" @click="loadSelectedTimeline">
                {{ reviewBusy ? "读取中..." : "查看记忆时间线" }}
              </button>
              <button class="btn primary" :disabled="reviewBusy || !activeCandidateMemoryId" @click="adoptSelectedMemory">
                采纳为 Canon
              </button>
              <button class="btn" :disabled="reviewBusy || !activeCandidateMemoryId" @click="rejectSelectedMemory">
                驳回 Candidate
              </button>
            </div>

            <div v-if="timelineError" class="review-hint">{{ timelineError }}</div>
            <div v-if="memoryTimeline" class="side-stack">
              <div class="timeline-card">
                <div class="timeline-title">Subject · {{ memoryTimeline.subject }}</div>
                <div class="timeline-meta">版本数：{{ memoryTimeline.memories?.length || 0 }} · 事件数：{{ memoryTimeline.events?.length || 0 }}</div>
              </div>

              <div class="timeline-list">
                <article v-for="item in memoryTimeline.memories" :key="item.memory_id" class="timeline-card">
                  <div class="timeline-topline">
                    <span class="memory-badge" :class="{ candidate: item.memory_layer === 'candidate' }">{{ item.memory_layer }}</span>
                    <span class="category-badge">{{ item.status }}</span>
                  </div>
                  <div class="timeline-title">{{ item.summary }}</div>
                  <div class="timeline-meta">v{{ item.version }} · {{ item.updated_at || item.created_at }}</div>
                </article>
              </div>

              <div class="event-list">
                <article v-for="item in memoryTimeline.events" :key="item.event_id" class="event-card">
                  <div class="event-meta">{{ item.event_type }} · v{{ item.version }} · {{ item.created_at }}</div>
                </article>
              </div>
            </div>
          </template>
        </section>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";

import {
  adoptArchiveMemory,
  getArchiveMemoryTimeline,
  rejectArchiveMemory,
} from "../api/archive.js";
import { buildChapterContext, getChapterContextOptions } from "../api/novel.js";
import { getWorldlineAgents, listWorldlineSessions } from "../api/worldline.js";
import { useProjectCatalog } from "../composables/useProjectCatalog.js";
import { buildWriterWorkbenchColumns, resolveWriterWorkbenchMode } from "./writer/writerWorkbenchLayout.js";
import {
  buildWriterRequestPayload,
  deriveWriterDefaults,
  findContextItem,
  resolveWriterPovOptions,
} from "./writer/writerWorkbenchState.js";

const scopeOptions = [
  { value: "project_chapter", label: "原著章节" },
  { value: "worldline_branch", label: "世界线分支" },
];

const { projects, refreshProjects } = useProjectCatalog();
const workbenchMode = ref(resolveWriterWorkbenchMode(window.innerWidth));
const projectId = ref("");
const scopeType = ref("project_chapter");
const chapterId = ref("");
const chapterOrder = ref(0);
const povCharacter = ref("");
const writingGoal = ref("");
const sceneFocus = ref("");
const includeCandidates = ref(false);
const sessionId = ref("");
const branchId = ref("main");
const chapterOptions = ref([]);
const projectPovs = ref([]);
const sessionOptions = ref([]);
const worldlineAgents = ref([]);
const contextPack = ref(null);
const selectedItem = ref(null);
const memoryTimeline = ref(null);
const reviewBusy = ref(false);
const timelineError = ref("");
const busy = ref(false);
const message = ref("请选择项目并生成上下文包");
const error = ref("");

const gridTemplateColumns = computed(() => buildWriterWorkbenchColumns(workbenchMode.value));
const povOptions = computed(() => resolveWriterPovOptions(scopeType.value, projectPovs.value, worldlineAgents.value));
const canSubmit = computed(() => {
  if (!projectId.value || !povCharacter.value) {
    return false;
  }
  return scopeType.value === "worldline_branch" ? !!sessionId.value : !!(chapterId.value || chapterOrder.value);
});
const contextScopeSummary = computed(() => {
  if (!contextPack.value) return "";
  const scope = contextPack.value.context_scope;
  return scope.scope_type === "worldline_branch"
    ? `会话 ${scope.session_id} · 分支 ${scope.branch_id} · POV ${scope.pov_character}`
    : `项目 ${scope.project_id} · 章节 ${scope.chapter_id || scope.chapter_order} · POV ${scope.pov_character}`;
});
const canLoadTimeline = computed(() => Boolean(selectedItem.value?.archive_id && (selectedItem.value?.normalized_subject || selectedItem.value?.source_ref)));
const activeCandidateMemoryId = computed(() => {
  const item = memoryTimeline.value?.memories?.find((entry) => entry.memory_layer === "candidate" && entry.status === "active");
  return item?.memory_id || "";
});

function handleResize() {
  workbenchMode.value = resolveWriterWorkbenchMode(window.innerWidth);
}

async function handleProjectChange() {
  contextPack.value = null;
  selectedItem.value = null;
  memoryTimeline.value = null;
  timelineError.value = "";
  if (!projectId.value) {
    chapterOptions.value = [];
    projectPovs.value = [];
    sessionOptions.value = [];
    worldlineAgents.value = [];
    return;
  }
  await refreshProjectData();
}

async function refreshProjectData() {
  if (!projectId.value) {
    return;
  }
  try {
    const [optionsResponse, sessionsResponse] = await Promise.all([
      getChapterContextOptions(projectId.value),
      listWorldlineSessions({ projectId: projectId.value }),
    ]);
    chapterOptions.value = optionsResponse.data?.chapters || [];
    projectPovs.value = optionsResponse.data?.pov_characters || [];
    const defaults = deriveWriterDefaults(optionsResponse.data || {});
    if (!chapterId.value && defaults.chapterId) {
      chapterId.value = defaults.chapterId;
      chapterOrder.value = defaults.chapterOrder;
    }
    if (!povCharacter.value && defaults.povCharacter) {
      povCharacter.value = defaults.povCharacter;
    }
    sessionOptions.value = (sessionsResponse.data?.sessions || []).map((item) => ({
      session_id: item.session_id,
      label: `${item.session_scope === "global" ? "全局" : "项目"} · ${item.session_id.slice(0, 8)} · ${item.current_world?.title || "当前世界"}`,
    }));
    message.value = "项目数据已刷新";
  } catch (err) {
    error.value = err.message || "读取项目上下文失败";
  }
}

async function handleSessionChange() {
  worldlineAgents.value = [];
  if (!sessionId.value) {
    return;
  }
  try {
    const response = await getWorldlineAgents(sessionId.value, branchId.value);
    worldlineAgents.value = response.data?.agents || [];
    if (!povOptions.value.includes(povCharacter.value)) {
      povCharacter.value = povOptions.value[0] || "";
    }
  } catch (err) {
    error.value = err.message || "读取世界线角色失败";
  }
}

function updateScopeType(value) {
  scopeType.value = value;
  selectedItem.value = null;
  memoryTimeline.value = null;
  timelineError.value = "";
  if (value === "project_chapter" && !povOptions.value.includes(povCharacter.value)) {
    povCharacter.value = projectPovs.value[0] || "";
  }
  if (value === "worldline_branch" && sessionId.value) {
    void handleSessionChange();
  }
}

async function generatePack(options = {}) {
  if (!canSubmit.value) {
    return;
  }
  try {
    const previousItem = options.preserveSelection ? selectedItem.value : null;
    busy.value = true;
    error.value = "";
    message.value = "正在生成 Chapter Context Pack";
    const chapter = chapterOptions.value.find((item) => item.chapter_id === chapterId.value);
    chapterOrder.value = chapter?.order || chapterOrder.value;
    const response = await buildChapterContext(buildWriterRequestPayload({
      scopeType: scopeType.value,
      projectId: projectId.value,
      chapterId: chapterId.value,
      chapterOrder: chapterOrder.value,
      sessionId: sessionId.value,
      branchId: branchId.value,
      povCharacter: povCharacter.value,
      writingGoal: writingGoal.value,
      sceneFocus: sceneFocus.value,
      includeCandidates: includeCandidates.value,
    }));
    contextPack.value = response.data;
    selectedItem.value = previousItem ? findContextItem(response.data, previousItem) : null;
    memoryTimeline.value = null;
    timelineError.value = "";
    message.value = "上下文包已生成";
  } catch (err) {
    error.value = err.message || "生成上下文包失败";
  } finally {
    busy.value = false;
  }
}

function selectContextItem(item) {
  selectedItem.value = item;
  memoryTimeline.value = null;
  timelineError.value = "";
}

async function loadSelectedTimeline() {
  if (!canLoadTimeline.value) {
    return;
  }
  try {
    reviewBusy.value = true;
    timelineError.value = "";
    const response = await getArchiveMemoryTimeline(selectedItem.value.archive_id, {
      normalizedSubject: selectedItem.value.normalized_subject,
      memoryId: selectedItem.value.source_kind === "agent_memory" ? selectedItem.value.source_ref : "",
    });
    memoryTimeline.value = response.data;
  } catch (err) {
    timelineError.value = err.message || "读取时间线失败";
  } finally {
    reviewBusy.value = false;
  }
}

async function adoptSelectedMemory() {
  if (!activeCandidateMemoryId.value || !selectedItem.value?.archive_id) {
    return;
  }
  try {
    reviewBusy.value = true;
    timelineError.value = "";
    await adoptArchiveMemory(selectedItem.value.archive_id, activeCandidateMemoryId.value);
    await generatePack({ preserveSelection: true });
    if (selectedItem.value?.archive_id) {
      await loadSelectedTimeline();
    }
  } catch (err) {
    timelineError.value = err.message || "采纳失败";
  } finally {
    reviewBusy.value = false;
  }
}

async function rejectSelectedMemory() {
  if (!activeCandidateMemoryId.value || !selectedItem.value?.archive_id) {
    return;
  }
  try {
    reviewBusy.value = true;
    timelineError.value = "";
    await rejectArchiveMemory(selectedItem.value.archive_id, activeCandidateMemoryId.value);
    await generatePack({ preserveSelection: true });
    if (selectedItem.value?.archive_id) {
      await loadSelectedTimeline();
    }
  } catch (err) {
    timelineError.value = err.message || "驳回失败";
  } finally {
    reviewBusy.value = false;
  }
}

onMounted(async () => {
  window.addEventListener("resize", handleResize);
  try {
    await refreshProjects();
  } catch (err) {
    error.value = err.message || "读取项目列表失败";
  }
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
});
</script>

<style scoped src="./WriterWorkbenchView.css"></style>
````

## `frontend/src/views/WriterWorkbenchView.css`

````css
.writer-stage {
  display: grid;
  gap: var(--space-lg);
}

.writer-stage.desktop {
  grid-template-columns: minmax(280px, 340px) minmax(0, 1fr) minmax(280px, 360px);
}

.writer-stage.stacked {
  grid-template-columns: 1fr;
}

.writer-panel {
  padding: 18px;
  position: relative;
  overflow: hidden;
}

.writer-panel::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(135deg, rgba(176, 125, 75, 0.06), transparent 45%),
    linear-gradient(180deg, rgba(61, 90, 128, 0.03), transparent 55%);
  pointer-events: none;
}

.writer-panel > * {
  position: relative;
  z-index: 1;
}

.panel-kicker {
  color: var(--accent-copper-deep);
  letter-spacing: 0.12em;
  font-size: 12px;
  margin-bottom: 8px;
}

.panel-title {
  font-size: 24px;
  margin-bottom: 6px;
}

.panel-subtitle,
.panel-status,
.panel-empty,
.trace-meta,
.timeline-meta,
.review-hint {
  color: var(--text-sub);
}

.scope-switch {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.scope-chip {
  padding: 10px 14px;
  border-radius: 999px;
  border: 1px solid var(--line-medium);
  background: rgba(255, 255, 255, 0.75);
  color: var(--text-main);
  cursor: pointer;
  text-align: center;
}

.scope-chip.active {
  background: var(--accent-copper);
  border-color: var(--accent-copper);
  color: #fff;
}

.writer-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.inline-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.inline-check {
  display: flex;
  gap: 10px;
  align-items: center;
  color: var(--text-sub);
  font-size: 14px;
}

.panel-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.context-sections {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.context-block {
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.88);
  padding: 14px;
}

.context-block-header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  margin-bottom: 10px;
}

.context-block-title {
  font-size: 18px;
}

.context-list,
.scene-list,
.trace-list,
.timeline-list,
.event-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.context-item,
.trace-item,
.timeline-card,
.event-card {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fff;
  padding: 12px;
}

.context-item.clickable {
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.context-item.clickable:hover,
.context-item.clickable.active {
  transform: translateY(-1px);
  border-color: var(--accent-copper);
  box-shadow: var(--shadow-sm);
}

.context-topline,
.trace-topline,
.timeline-topline {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  margin-bottom: 6px;
}

.context-summary,
.scene-title,
.timeline-title {
  font-weight: 600;
}

.context-why,
.scene-copy,
.event-copy,
.timeline-copy {
  color: var(--text-sub);
  font-size: 14px;
}

.context-meta,
.trace-topline,
.trace-copy,
.timeline-meta,
.event-meta {
  font-size: 12px;
}

.memory-badge,
.category-badge,
.score-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(176, 125, 75, 0.12);
  color: var(--accent-copper-deep);
}

.memory-badge.candidate {
  background: rgba(61, 90, 128, 0.12);
  color: var(--accent-blue);
}

.warning-badge {
  color: var(--accent-seal);
}

.prompt-block {
  white-space: pre-wrap;
  font-size: 14px;
  background: linear-gradient(180deg, rgba(244, 239, 226, 0.8), rgba(255, 255, 255, 0.92));
}

.side-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.review-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 12px;
}

@media (max-width: 1280px) {
  .inline-grid {
    grid-template-columns: 1fr;
  }
}
````

## `frontend/src/views/WorldlineWorkbenchView.vue`

````vue
<template>
  <div ref="stageRef" class="worldline-stage" :class="[workbenchMode, { resizing }]" :style="stageStyle">
    <aside class="stage-controls stack">
      <WorldlineControlPanel
        :selected-archives="selectedArchives"
        :archive-project-filter="archiveProjectFilter"
        :variables-text="variablesText"
        :single-variable="singleVariable"
        :create-mode="autoEvolution.createMode.value"
        :goal-text="autoEvolution.goalText.value"
        :max-steps="autoEvolution.maxSteps.value"
        :session-id="sessionId"
        :session-scope="sessionScope"
        :task="autoEvolution.currentTask.value"
        :feedback="feedback"
        :error="error"
        :busy="busy"
        @update:selected-archives="updateSelectedArchives"
        @update:archive-project-filter="updateArchiveProjectFilter"
        @update:variables-text="updateVariablesText"
        @update:single-variable="updateSingleVariable"
        @update:create-mode="updateCreateMode"
        @update:goal-text="updateGoalText"
        @update:max-steps="updateMaxSteps"
        @create-session="createSession"
        @start-auto-evolve="startAutoEvolve"
        @advance-step="stepForward"
        @inject-variable="injectVariable"
      />
      <WorldlineInspirationPanel
        v-if="sessionId"
        :session-id="sessionId"
        :inspiration-prompt="inspirationPrompt"
        :inspiration-result="inspirationResult"
        :inspiration-error="inspirationError"
        :inspiration-busy="inspirationBusy"
        @update:inspiration-prompt="updateInspirationPrompt"
        @generate-inspiration="generateInspirationPlan"
      />
    </aside>
    <button
      class="stage-divider"
      type="button"
      aria-label="拖拽调整左右栏宽度"
      aria-orientation="vertical"
      @pointerdown.prevent="beginResize"
    >
      <span></span>
    </button>
    <main class="stage-performance stack">
      <div v-if="!sessionId" class="empty-stage workbench-card">
        <div class="empty-icon">⏳</div>
        <h3 class="title-ancient">等待开启世界线</h3>
        <p>请在左侧选择角色档案并设定初始变量，以启动当前世界线会话。</p>
      </div>
      <section v-else class="performance-main">
        <WorldlineDirectorPanel
          :session-id="sessionId"
          :current-world="currentWorld"
          :timeline="timeline"
          :task-snapshot="autoEvolution.currentTask.value"
        />
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref } from "vue";

import {
  advanceWorldlineStep,
  createWorldlineSession,
  generatePlotInspiration,
  getWorldlineSession,
  getWorldlineTimeline,
  injectWorldlineVariable,
} from "../api/worldline";
import WorldlineControlPanel from "./worldline/WorldlineControlPanel.vue";
import WorldlineDirectorPanel from "./worldline/WorldlineDirectorPanel.vue";
import WorldlineInspirationPanel from "./worldline/WorldlineInspirationPanel.vue";
import { useWorldlineAutoEvolution } from "./worldline/useWorldlineAutoEvolution.js";
import { useWorldlineWorkbenchLayout } from "../composables/useWorldlineWorkbenchLayout.js";

const selectedArchives = ref([]);
const archiveProjectFilter = ref("");
const variablesText = ref("主要势力 A 提前结盟\n主角亲族在第 3 节点失踪");
const singleVariable = ref("");
const sessionId = ref("");
const sessionScope = ref("");
const currentWorld = ref(null);
const timeline = ref([]);
const feedback = ref("等待操作");
const error = ref("");
const busy = ref(false);
const inspirationPrompt = ref("希望在下一幕引入关键误判，引发阵营站队重组。");
const inspirationBusy = ref(false);
const inspirationResult = ref(null);
const inspirationError = ref("");

const { beginResize, resizing, stageRef, stageStyle, workbenchMode } = useWorldlineWorkbenchLayout();
const autoEvolution = useWorldlineAutoEvolution({
  refreshWorldline: async () => { await loadWorldline(); },
  setFeedback: (message) => { feedback.value = message; },
  setError: (message) => { error.value = message; },
});

function parseVariables(text) {
  return text.split("\n").map((value) => value.trim()).filter(Boolean);
}

function resolveCurrentWorld(data) {
  return data?.current_world || null;
}

async function createSession() {
  if (!selectedArchives.value.length) {
    error.value = "请先选择至少一个角色档案。";
    return;
  }
  try {
    busy.value = true;
    error.value = "";
    const res = await createWorldlineSession({
      archive_ids: selectedArchives.value.map((item) => item.archive_id),
      variables: parseVariables(variablesText.value),
    });
    sessionId.value = res.data.session_id;
    sessionScope.value = res.data.session_scope || "";
    feedback.value = "会话已启动";
    await loadWorldline();
    if (autoEvolution.prepareAfterSessionCreate(currentWorld.value)) {
      await startAutoEvolve();
    }
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

function updateSelectedArchives(value) { selectedArchives.value = value; }
function updateArchiveProjectFilter(value) { archiveProjectFilter.value = value; }
function updateVariablesText(value) { variablesText.value = value; }
function updateSingleVariable(value) { singleVariable.value = value; }
function updateInspirationPrompt(value) { inspirationPrompt.value = value; }
function updateCreateMode(value) { autoEvolution.createMode.value = value; }
function updateGoalText(value) { autoEvolution.goalText.value = value; }
function updateMaxSteps(value) { autoEvolution.maxSteps.value = value; }

async function loadWorldline() {
  if (!sessionId.value) {
    return;
  }
  try {
    const [sessionRes, timelineRes] = await Promise.all([
      getWorldlineSession(sessionId.value),
      getWorldlineTimeline(sessionId.value),
    ]);
    currentWorld.value = resolveCurrentWorld(sessionRes.data);
    timeline.value = timelineRes.data?.events || [];
    autoEvolution.syncWorld(currentWorld.value);
  } catch (err) {
    error.value = err.message;
  }
}

async function stepForward() {
  try {
    busy.value = true;
    error.value = "";
    const res = await advanceWorldlineStep({ session_id: sessionId.value, steps: 1 });
    feedback.value = res.data.message || "推进完成";
    await loadWorldline();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

async function startAutoEvolve() {
  if (!sessionId.value) {
    return;
  }
  try {
    busy.value = true;
    error.value = "";
    const tasks = await autoEvolution.startForSession(sessionId.value);
    feedback.value = tasks.length ? "当前世界自动演化已启动" : "当前模式无需自动演化";
    await loadWorldline();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

async function injectVariable() {
  if (!singleVariable.value.trim()) {
    return;
  }
  try {
    busy.value = true;
    error.value = "";
    const res = await injectWorldlineVariable({
      session_id: sessionId.value,
      variable: singleVariable.value.trim(),
    });
    feedback.value = res.data.message || "变量注入成功";
    singleVariable.value = "";
    await loadWorldline();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

async function generateInspirationPlan() {
  if (!sessionId.value) {
    return;
  }
  try {
    inspirationBusy.value = true;
    inspirationError.value = "";
    const res = await generatePlotInspiration({
      session_id: sessionId.value,
      creator_prompt: inspirationPrompt.value.trim(),
      focus_question: "下一步走向",
    });
    inspirationResult.value = res.data?.result || res.data || null;
  } catch (err) {
    inspirationError.value = err.message;
  } finally {
    inspirationBusy.value = false;
  }
}
</script>

<style scoped src="./WorldlineWorkbenchView.css"></style>
````

## `frontend/src/views/WorldlineWorkbenchView.css`

````css
.worldline-stage {
  display: grid;
  grid-template-columns: minmax(0, var(--worldline-left-pane-width)) 16px minmax(0, 1fr);
  gap: 0;
  height: calc(100vh - 120px);
}

.stage-controls {
  min-width: 0;
  overflow-y: auto;
  padding-right: var(--space-md);
  padding-bottom: var(--space-lg);
}

.stage-divider {
  border: none;
  padding: 0;
  margin: 0 var(--space-xs);
  background: transparent;
  cursor: col-resize;
  position: relative;
}

.stage-divider span {
  position: absolute;
  inset: 0;
}

.stage-divider::before {
  content: "";
  position: absolute;
  top: var(--space-lg);
  bottom: var(--space-lg);
  left: 50%;
  width: 4px;
  transform: translateX(-50%);
  border-radius: var(--radius-full);
  background: linear-gradient(180deg, #eadfc7 0%, #c9b08b 100%);
}

.worldline-stage.resizing .stage-divider::before,
.stage-divider:hover::before {
  background: linear-gradient(180deg, #d9bf92 0%, #8f6e41 100%);
}

.stage-performance {
  min-width: 0;
  overflow-y: auto;
  padding-left: var(--space-md);
  padding-bottom: var(--space-lg);
}

.empty-stage {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--space-xl);
  background: var(--bg-panel-soft);
  border-style: dashed;
}

.empty-icon {
  font-size: 64px;
  margin-bottom: var(--space-md);
}

.performance-main {
  min-width: 0;
}

.performance-main :deep(.director-panel) {
  min-height: calc(100vh - 280px);
}

.worldline-stage.stacked {
  grid-template-columns: 1fr;
  height: auto;
}

.worldline-stage.stacked .stage-controls,
.worldline-stage.stacked .stage-performance {
  padding: 0;
}

.worldline-stage.stacked .stage-divider {
  display: none;
}
````

## `frontend/src/views/worldline/WorldlineControlPanel.vue`

````vue
<template>
  <article class="workbench-card panel">
    <header class="panel-header">
      <div>
        <p class="panel-kicker mono">WORLDLINE WORKFLOW</p>
        <h2 class="card-title">世界线控制台</h2>
      </div>
      <span class="status-tag" :class="sessionStatus.tone">{{ sessionStatus.label }}</span>
    </header>
    <p class="description">从全局主档案库选取角色与组织，按步骤创建并推进当前世界线。</p>

    <section class="panel-section source-section">
      <div class="section-head">
        <div>
          <p class="section-index mono">01 / 源档案</p>
          <h3 class="section-title">选择进入世界线的角色与组织</h3>
        </div>
        <p class="section-copy">先确定参与推演的对象，再进入初始变量配置。</p>
      </div>
      <ArchiveLibraryPicker
        :model-value="selectedArchives"
        :project-filter="archiveProjectFilter"
        @update:model-value="emit('update:selectedArchives', $event)"
        @update:project-filter="emit('update:archiveProjectFilter', $event)"
      />
    </section>

    <section class="panel-section">
      <div class="section-head">
        <div>
          <p class="section-index mono">02 / 创建会话</p>
          <h3 class="section-title">确认初始变量并启动世界线</h3>
        </div>
        <p class="section-copy">每行输入一条变量，作为本次推演的初始扰动。</p>
      </div>

      <div class="session-summary">
        <div v-for="item in sessionSummary" :key="item.label" class="summary-card">
          <span class="summary-label">{{ item.label }}</span>
          <strong class="summary-value">{{ item.value }}</strong>
        </div>
        <div class="summary-card session-code">
          <span class="summary-label">会话编号</span>
          <strong class="summary-value mono">{{ sessionId || "未创建会话" }}</strong>
        </div>
      </div>

      <div class="setup-grid">
        <div class="field">
          <label>初始变量（每行一个）</label>
          <textarea
            :value="variablesText"
            rows="4"
            @input="emitUpdate('variablesText', $event.target.value)"
          ></textarea>
          <p class="field-hint">例如让主要势力提前结盟、某位关键角色提前失踪、或情报被错误释放。</p>

          <div class="mode-grid">
            <button
              v-for="item in createModeOptions"
              :key="item.value"
              class="mode-chip"
              type="button"
              :class="{ active: createMode === item.value }"
              @click="emitUpdate('createMode', item.value)"
            >
              <strong>{{ item.label }}</strong>
              <span>{{ item.copy }}</span>
            </button>
          </div>

          <div v-if="showContinuousSettings" class="auto-config-grid">
            <div class="field compact">
              <label>最大自动步数</label>
              <input
                :value="maxSteps"
                min="1"
                type="number"
                @input="emitUpdate('maxSteps', Number($event.target.value))"
              />
            </div>
            <div class="field compact">
              <label>最终条件</label>
              <input
                :value="goalText"
                placeholder="例如：主角公开宗门证据"
                @input="emitUpdate('goalText', $event.target.value)"
              />
            </div>
          </div>
          <p v-else-if="createMode === 'first_round'" class="field-hint mode-note">
            首轮自动固定执行 1 步，步数输入只在“持续自动”模式下生效。
          </p>
          <p v-if="showContinuousSettings" class="field-hint mode-note">
            持续自动会按你填写的步数上限推进；如果提前达成目标或剧情自然收束，会提前停止。
          </p>
        </div>

        <div class="action-box">
          <p class="action-box-title">准备完成后启动世界线</p>
          <p class="section-copy">创建后，右侧当前世界摘要与时空轨迹会自动刷新到当前会话。</p>
          <p class="section-copy">{{ sessionScopeHint }}</p>
          <button class="btn primary create-btn" :disabled="busy || !selectedArchives.length" @click="createSession">
            {{ createActionLabel }}
          </button>
        </div>
      </div>
    </section>

    <WorldlineAutoTaskPanel :task="task" />

    <section class="panel-section runtime-section" :class="{ inactive: !sessionId }">
      <div class="section-head">
        <div>
          <p class="section-index mono">{{ runtimeSectionIndex }}</p>
          <h3 class="section-title">在当前世界线中推进与注入</h3>
        </div>
        <p class="section-copy">{{ runtimeHint }}</p>
      </div>

      <div class="runtime-grid">
        <div class="action-box runtime-box">
          <p class="action-box-title">推进剧情</p>
          <p class="section-copy">基于当前世界状态向前演化一步，观察关系与事件如何变化。</p>
          <button class="btn" :disabled="!sessionId || busy" @click="stepForward">推进一步</button>
          <button
            v-if="createMode !== 'manual'"
            class="btn"
            :disabled="!sessionId || busy"
            @click="$emit('start-auto-evolve')"
          >
            按当前模式自动推进
          </button>
        </div>

        <div class="action-box runtime-box">
          <div class="field">
            <label>临时注入变量</label>
            <div class="inject-row">
              <input
                :value="singleVariable"
                placeholder="例如：二号角色获得预知能力"
                @input="emitUpdate('singleVariable', $event.target.value)"
              />
              <button class="btn" :disabled="!sessionId || busy" @click="injectVariable">注入变量</button>
            </div>
            <p class="field-hint">适合在会话中途添加新的扰动条件，测试它如何继续改写当前世界。</p>
          </div>
        </div>
      </div>

      <div class="feedback-panel" :class="{ error: !!error }">
        <span class="feedback-label mono">STATUS</span>
        <p class="feedback">{{ error || feedback }}</p>
      </div>
    </section>
  </article>
</template>

<script setup>
import { computed } from "vue";

import ArchiveLibraryPicker from "../../components/ArchiveLibraryPicker.vue";
import { formatSessionScope } from "../../utils/chineseDisplay.js";
import WorldlineAutoTaskPanel from "./WorldlineAutoTaskPanel.vue";
import {
  buildWorldlineSessionSummary,
  resolveWorldlineSessionStatus,
} from "./worldlineControlPanelViewModel.js";

const createModeOptions = Object.freeze([
  { value: "manual", label: "手动", copy: "创建后由你推进与注入。" },
  { value: "first_round", label: "首轮自动", copy: "创建后固定先跑 1 步，适合先看第一轮反应。" },
  { value: "continuous", label: "持续自动", copy: "按你填写的步数上限持续推进。" },
]);

const props = defineProps({
  selectedArchives: { type: Array, default: () => [] },
  archiveProjectFilter: { type: String, default: "" },
  variablesText: { type: String, default: "" },
  singleVariable: { type: String, default: "" },
  createMode: { type: String, default: "manual" },
  goalText: { type: String, default: "" },
  maxSteps: { type: Number, default: 6 },
  sessionId: { type: String, default: "" },
  sessionScope: { type: String, default: "" },
  task: { type: Object, default: null },
  feedback: { type: String, default: "" },
  error: { type: String, default: "" },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits([
  "update:selectedArchives",
  "update:archiveProjectFilter",
  "update:variablesText",
  "update:singleVariable",
  "update:createMode",
  "update:goalText",
  "update:maxSteps",
  "create-session",
  "start-auto-evolve",
  "advance-step",
  "inject-variable",
]);

const sessionStatus = computed(() => resolveWorldlineSessionStatus({
  sessionId: props.sessionId,
  error: props.error,
}));

const sessionSummary = computed(() => buildWorldlineSessionSummary({
  selectedArchives: props.selectedArchives,
  variablesText: props.variablesText,
  sessionId: props.sessionId,
  sessionScope: props.sessionScope,
}));

const sessionScopeHint = computed(() => (
  props.sessionId ? `当前会话范围：${formatSessionScope(props.sessionScope)}` : "创建后会在这里显示会话范围。"
));

const showContinuousSettings = computed(() => props.createMode === "continuous");
const createActionLabel = computed(() => (
  props.createMode === "manual" ? "创建世界线会话" : "创建会话并启动自动演化"
));
const runtimeSectionIndex = computed(() => (
  props.task || props.createMode !== "manual" ? "04 / 会话控制" : "03 / 会话控制"
));
const runtimeHint = computed(() => (
  props.sessionId ? `当前作用域：${formatSessionScope(props.sessionScope)}` : "创建会话后即可推进剧情或注入新的变量。"
));

function emitUpdate(field, value) {
  emit(`update:${field}`, value);
}

function createSession() {
  emit("create-session");
}

function stepForward() {
  emit("advance-step");
}

function injectVariable() {
  emit("inject-variable");
}
</script>

<style scoped src="./WorldlineControlPanel.css"></style>
````

## `frontend/src/views/worldline/WorldlineDirectorPanel.vue`

````vue
<template>
  <article class="workbench-card panel director-panel">
    <header class="director-header">
      <div>
        <p class="director-kicker mono">DIRECTOR CONSOLE</p>
        <h2 class="card-title">世界线导演台</h2>
        <p class="director-copy">先看当前世界推进到了哪里，再看这一步是谁在推动剧情、局势如何被改写。</p>
      </div>
      <div class="focus-pill">
        <span class="mono">{{ worldSummary.stepLabel }}</span>
        <strong>{{ worldSummary.title }}</strong>
      </div>
    </header>

    <section class="director-section">
      <div class="section-head">
        <div>
          <p class="section-index mono">01 / 当前世界</p>
          <h3 class="section-title">世界状态总览</h3>
        </div>
        <p class="section-copy">自动演化进度、待处理项和最新事件会在这里同步浮出水面。</p>
      </div>

      <article class="lane-card active">
        <div class="lane-head">
          <strong>{{ worldSummary.title }}</strong>
          <span class="lane-status">{{ worldSummary.statusLabel }}</span>
        </div>
        <div class="lane-meta">
          <span class="mono">{{ worldSummary.stepLabel }}</span>
          <span class="mono">待处理 {{ worldSummary.pendingCount }}</span>
        </div>
        <div class="lane-progress" aria-hidden="true">
          <div class="lane-progress-fill" :style="{ width: `${worldSummary.progress}%` }"></div>
        </div>
        <div class="lane-event">{{ worldSummary.latestEventTitle }}</div>
        <p class="spotlight-copy">{{ worldSummary.latestEventSummary }}</p>
        <div class="chip-row">
          <span v-for="driver in worldSummary.drivers" :key="driver" class="driver-chip">
            {{ driver }}
          </span>
          <span v-if="!worldSummary.drivers.length" class="driver-chip muted">等待新驱动者</span>
        </div>
      </article>
    </section>

    <section class="director-section narrative-shell">
      <div class="section-head">
        <div>
          <p class="section-index mono">02 / 当前主叙事</p>
          <h3 class="section-title">谁在推动剧情</h3>
        </div>
        <p class="section-copy">驱动者、最新事件、关系变动和待处理项按同一条观看路径组织。</p>
      </div>

      <div class="narrative-grid">
        <article class="narrative-card spotlight">
          <div class="spotlight-head">
            <div>
              <p class="mono spotlight-step">{{ focusNarrative.stepLabel }}</p>
              <h3>{{ focusNarrative.latestEvent.title }}</h3>
            </div>
            <span class="spotlight-status">{{ focusNarrative.statusLabel }}</span>
          </div>
          <p class="spotlight-copy">{{ focusNarrative.latestEvent.digest }}</p>
          <div class="story-block">
            <span class="story-label">核心偏移</span>
            <p>{{ focusNarrative.coreChange }}</p>
          </div>
          <div class="story-block">
            <span class="story-label">本步变量触发</span>
            <div class="chip-row">
              <span
                v-for="variable in focusNarrative.latestEvent.variableEffects"
                :key="`${focusNarrative.worldId}_${variable.name}`"
                class="driver-chip"
              >
                {{ variable.name }}
              </span>
              <span v-if="!focusNarrative.latestEvent.variableEffects.length" class="driver-chip muted">本步没有新增变量</span>
            </div>
          </div>
          <div class="story-block">
            <span class="story-label">当前驱动者</span>
            <div class="chip-row">
              <span v-for="driver in focusNarrative.latestEvent.drivers" :key="driver" class="driver-chip active">
                {{ driver }}
              </span>
              <span v-if="!focusNarrative.latestEvent.drivers.length" class="driver-chip muted">暂无明确驱动者</span>
            </div>
          </div>
        </article>

        <article class="narrative-card">
          <div class="block-head">
            <h4>本步执行动作</h4>
            <span class="mono">
              {{ focusNarrative.latestEvent.actionEffects.length || focusNarrative.dispatchActors.length }}
              {{ focusNarrative.latestEvent.actionEffects.length ? "条" : "位" }}
            </span>
          </div>
          <div v-if="focusNarrative.latestEvent.actionEffects.length" class="dispatch-list">
            <article
              v-for="action in focusNarrative.latestEvent.actionEffects"
              :key="`${action.actor}_${action.action}`"
              class="dispatch-card"
              :class="{ driver: focusNarrative.latestEvent.drivers.includes(action.actor) }"
            >
              <div class="dispatch-head">
                <strong>{{ action.actor }}</strong>
                <span>执行中</span>
              </div>
              <p class="dispatch-meta">{{ action.target || "当前世界" }}</p>
              <p class="dispatch-drive">{{ action.action }}</p>
              <p v-if="action.intent" class="dispatch-meta">动机：{{ action.intent }}</p>
            </article>
          </div>
          <div v-else-if="focusNarrative.dispatchActors.length" class="dispatch-list">
            <article
              v-for="actor in focusNarrative.dispatchActors"
              :key="actor.name"
              class="dispatch-card"
              :class="{ driver: actor.isDriver }"
            >
              <div class="dispatch-head">
                <strong>{{ actor.name }}</strong>
                <span>{{ actor.status }}</span>
              </div>
              <p class="dispatch-meta">{{ actor.role }}</p>
              <p class="dispatch-drive">{{ actor.drive }}</p>
            </article>
          </div>
          <p v-else class="mini-empty">{{ focusNarrative.emptyMessage }}</p>
        </article>

        <article class="narrative-card">
          <div class="block-head">
            <h4>关系与待处理</h4>
            <span class="mono">持续演化</span>
          </div>
          <div class="pending-grid">
            <div class="pending-box">
              <strong>{{ focusNarrative.pending.variableCount }}</strong>
              <span>待处理变量</span>
              <p>{{ joinText(focusNarrative.pending.variableNames, "暂无待处理变量") }}</p>
            </div>
            <div class="pending-box">
              <strong>{{ focusNarrative.pending.actionCount }}</strong>
              <span>待处理动作</span>
              <p>{{ joinText(focusNarrative.pending.actionLabels, "暂无待处理动作") }}</p>
            </div>
          </div>
          <div class="relation-list">
            <div
              v-for="relation in focusNarrative.relationChanges"
              :key="`${relation.source}_${relation.target}_${relation.label}`"
              class="relation-card"
            >
              <strong>{{ relation.source }} → {{ relation.target }}</strong>
              <span>{{ relation.label }}</span>
              <p>{{ relation.note }}</p>
            </div>
            <p v-if="!focusNarrative.relationChanges.length" class="mini-empty">当前回合还没有显式关系改写。</p>
          </div>
        </article>

        <article class="narrative-card">
          <div class="block-head">
            <h4>局势中的组织</h4>
            <span class="mono">{{ focusNarrative.worldForces.length }} 个焦点</span>
          </div>
          <div v-if="focusNarrative.worldForces.length" class="force-list">
            <article v-for="item in focusNarrative.worldForces" :key="item.name" class="force-card">
              <div class="dispatch-head">
                <strong>{{ item.name }}</strong>
                <span>{{ item.status }}</span>
              </div>
              <p class="dispatch-meta">{{ item.role }}</p>
              <p class="dispatch-drive">{{ item.summary }}</p>
            </article>
          </div>
          <p v-else class="mini-empty">暂无组织级局势摘要。</p>
        </article>
      </div>
    </section>

    <section class="director-section">
      <div class="section-head">
        <div>
          <p class="section-index mono">03 / 世界状态变更流</p>
          <h3 class="section-title">局势如何被改写</h3>
        </div>
        <p class="section-copy">每一步都记录变量影响、关系张力和状态变化，不再只是大段摘要文案。</p>
      </div>

      <div v-if="worldShiftFeed.items.length" class="shift-feed">
        <article v-for="item in worldShiftFeed.items" :key="item.eventId || item.step" class="shift-card">
          <div class="shift-head">
            <div>
              <p class="mono spotlight-step">{{ item.stepLabel }}</p>
              <h4>{{ item.title }}</h4>
            </div>
            <div class="chip-row">
              <span v-for="driver in item.drivers" :key="`${item.eventId}_${driver}`" class="driver-chip active">
                {{ driver }}
              </span>
            </div>
          </div>
          <p class="spotlight-copy">{{ item.summary }}</p>
          <div class="shift-grid">
            <div class="shift-box">
              <span class="story-label">变量影响</span>
              <p v-for="variable in item.variableEffects" :key="`${item.eventId}_${variable.name}`">
                {{ variable.name }}：{{ variable.description }}
              </p>
              <p v-if="!item.variableEffects.length" class="mini-empty">本步没有新增变量扰动。</p>
            </div>
            <div class="shift-box">
              <span class="story-label">执行动作</span>
              <p v-for="action in item.actionEffects" :key="`${item.eventId}_${action.actor}_${action.action}`">
                {{ action.actor }}：{{ action.action }}
              </p>
              <p v-if="!item.actionEffects.length" class="mini-empty">本步没有新增动作落地。</p>
            </div>
            <div class="shift-box">
              <span class="story-label">关系变化</span>
              <p v-for="relation in item.relationChanges" :key="`${item.eventId}_${relation.source}_${relation.target}`">
                {{ relation.source }} → {{ relation.target }} · {{ relation.label }}
              </p>
              <p v-if="!item.relationChanges.length" class="mini-empty">本步没有显式关系波动。</p>
            </div>
            <div class="shift-box">
              <span class="story-label">状态变化</span>
              <p v-for="state in item.stateChanges" :key="`${item.eventId}_${state.entityName}`">
                {{ state.entityName }} · {{ state.status }} · {{ state.reason }}
              </p>
              <p v-if="!item.stateChanges.length" class="mini-empty">本步没有新增状态变更。</p>
            </div>
          </div>
        </article>
      </div>
      <div v-else class="empty-shift">{{ worldShiftFeed.emptyMessage }}</div>
    </section>
  </article>
</template>

<script setup>
import { computed } from "vue";

import {
  buildWorldlineCurrentWorldSummary,
  buildWorldlineFocusNarrative,
  buildWorldlineWorldShiftFeed,
} from "./worldlineDirectorPanelViewModel.js";

const props = defineProps({
  sessionId: { type: String, default: "" },
  currentWorld: { type: Object, default: null },
  timeline: { type: Array, default: () => [] },
  taskSnapshot: { type: Object, default: null },
});

const worldSummary = computed(() => buildWorldlineCurrentWorldSummary({
  currentWorld: props.currentWorld,
  taskSnapshot: props.taskSnapshot,
  timeline: props.timeline,
}));

const focusNarrative = computed(() => buildWorldlineFocusNarrative({
  currentWorld: props.currentWorld,
  taskSnapshot: props.taskSnapshot,
  timeline: props.timeline,
}));

const worldShiftFeed = computed(() => buildWorldlineWorldShiftFeed(props.timeline));

function joinText(items = [], emptyText) {
  return items.length ? items.join(" / ") : emptyText;
}
</script>

<style scoped src="./WorldlineDirectorPanel.css"></style>
````

## `frontend/src/views/CharacterConsoleView.vue`

````vue
<template>
  <div class="console-stage">
    <aside class="stage-selection stack">
      <SessionCommandPanel
        :project-filter="projectFilter"
        :project-session-options="projectSessionOptions"
        :sessions="sessions"
        :session-id="sessionId"
        :session-label="sessionLabel"
        :active-session="activeSession"
        :selected-agent="selectedAgent"
        :action="action"
        :busy="busy"
        :error="error"
        :message="message"
        @update:project-filter="updateProjectFilter"
        @update:session-id="updateSessionId"
        @update:action="updateAction"
        @submit-action="submitAction"
      />

      <WorldlineAgentRoster
        :session-id="sessionId"
        :selected-agent-ref="selectedAgent?.agent_id || chatActor"
        @select="handleAgentSelect"
      />
    </aside>

    <main class="stage-interaction stack">
      <div v-if="!selectedAgent" class="empty-interaction workbench-card">
        <div class="empty-icon">🎭</div>
        <h3 class="title-ancient">请选择交互对象</h3>
        <p>在左侧名录中点选一个角色或组织，开始对话或下达指令。</p>
      </div>

      <template v-else>
        <AgentDialoguePanel
          :session-id="sessionId"
          :selected-agent="selectedAgent"
          :chat-mode="chatMode"
          :chat-message="chatMessage"
          :chat-reply="chatReply"
          :dialogues="agentDialogues"
          :chat-error="chatError"
          :busy="chatBusy"
          @update:chat-mode="updateChatMode"
          @update:chat-message="updateChatMessage"
          @submit="submitChat"
        />

        <InteractionLogPanel :logs="logs" />
      </template>
    </main>

    <aside class="stage-context stack">
      <AgentDetailPanel :selected-agent="selectedAgent" />
      <AgentHistoryPanel
        :session-id="sessionId"
        :selected-agent="selectedAgent"
        :snapshots="agentSnapshots"
        :actions="agentActions"
        :dialogues="agentDialogues"
        :session-memories="agentSessionMemories"
        :long-term-memories="agentLongTermMemories"
        :error="historyError"
      />
    </aside>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";

import {
  chatWithWorldlineAgent,
  getWorldlineAgentActions,
  getWorldlineAgentDialogues,
  getWorldlineAgentHistory,
  getWorldlineAgentMemory,
  getWorldlineSession,
  issueAgentAction,
  listWorldlineSessions,
} from "../api/worldline";
import AgentDetailPanel from "./character-console/AgentDetailPanel.vue";
import AgentDialoguePanel from "./character-console/AgentDialoguePanel.vue";
import AgentHistoryPanel from "./character-console/AgentHistoryPanel.vue";
import InteractionLogPanel from "./character-console/InteractionLogPanel.vue";
import WorldlineAgentRoster from "./character-console/WorldlineAgentRoster.vue";
import SessionCommandPanel from "./character-console/SessionCommandPanel.vue";
import { buildProjectSessionOptions } from "./shared/worldlineSelectorState.js";

const projectFilter = ref("");
const sessions = ref([]);
const sessionId = ref("");
const action = ref("");
const busy = ref(false);
const message = ref("等待指令");
const error = ref("");
const logs = ref([]);
const chatActor = ref("");
const chatMode = ref("template");
const chatMessage = ref("");
const chatBusy = ref(false);
const chatReply = ref(null);
const chatError = ref("");
const selectedAgent = ref(null);
const agentSnapshots = ref([]);
const agentActions = ref([]);
const agentDialogues = ref([]);
const agentSessionMemories = ref([]);
const agentLongTermMemories = ref([]);
const historyError = ref("");
const sessionMap = ref({});

const activeSession = computed(() => sessionMap.value[sessionId.value] || null);
const projectSessionOptions = computed(() => buildProjectSessionOptions(sessions.value));

function nowTime() {
  return new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

function sessionLabel(session) {
  return `${session.session_scope === "global" ? "全局会话" : "卷宗会话"} · ${session.session_id.slice(0, 8)}`;
}

async function updateProjectFilter(value) {
  projectFilter.value = value;
  await loadSessions();
}

async function updateSessionId(value) {
  sessionId.value = value;
  await handleSessionChange();
}

function updateAction(value) {
  action.value = value;
}

function updateChatMessage(value) {
  chatMessage.value = value;
}

function updateChatMode(value) {
  chatMode.value = value || "template";
}

async function loadSessions() {
  const filters = projectFilter.value && projectFilter.value !== "__global__" ? { projectId: projectFilter.value } : {};
  const response = await listWorldlineSessions(filters);
  let items = response.data?.sessions || [];
  if (projectFilter.value === "__global__") {
    items = items.filter((item) => item.session_scope === "global");
  }
  sessions.value = items;
  sessionMap.value = Object.fromEntries(items.map((item) => [item.session_id, item]));
  if (!items.some((item) => item.session_id === sessionId.value)) {
    sessionId.value = items[0]?.session_id || "";
    await handleSessionChange();
  }
}

async function handleSessionChange() {
  selectedAgent.value = null;
  chatActor.value = "";
  chatReply.value = null;
  clearAgentHistory();
  if (!sessionId.value) {
    return;
  }
  const res = await getWorldlineSession(sessionId.value);
  const session = res.data;
  sessionMap.value = { ...sessionMap.value, [session.session_id]: session };
}

function handleAgentSelect(agent) {
  selectedAgent.value = agent;
  chatActor.value = agent.agent_id;
  void loadAgentHistory();
}

function clearAgentHistory() {
  historyError.value = "";
  agentSnapshots.value = [];
  agentActions.value = [];
  agentDialogues.value = [];
  agentSessionMemories.value = [];
  agentLongTermMemories.value = [];
}

async function loadAgentHistory() {
  if (!sessionId.value || !selectedAgent.value?.agent_id) {
    clearAgentHistory();
    return;
  }
  try {
    historyError.value = "";
    const filters = { agent_id: selectedAgent.value.agent_id, limit: 20 };
    const [historyRes, actionRes, dialogueRes, memoryRes] = await Promise.all([
      getWorldlineAgentHistory(sessionId.value, filters),
      getWorldlineAgentActions(sessionId.value, filters),
      getWorldlineAgentDialogues(sessionId.value, filters),
      getWorldlineAgentMemory(sessionId.value, filters),
    ]);
    agentSnapshots.value = historyRes.data?.snapshots || [];
    agentActions.value = actionRes.data?.items || [];
    agentDialogues.value = dialogueRes.data?.items || [];
    agentSessionMemories.value = memoryRes.data?.session_memories || [];
    agentLongTermMemories.value = memoryRes.data?.long_term_memories || [];
  } catch (err) {
    clearAgentHistory();
    historyError.value = err.message || "读取历史失败";
  }
}

async function submitAction() {
  if (!sessionId.value || !selectedAgent.value || !action.value.trim()) {
    return;
  }
  try {
    busy.value = true;
    error.value = "";
    const res = await issueAgentAction({
      session_id: sessionId.value,
      agent_id: selectedAgent.value.agent_id,
      action: action.value.trim(),
    });
    message.value = res.data.message || "动作成功";
    logs.value.unshift({ time: nowTime(), text: `[动作][${selectedAgent.value.display_name}] ${action.value}` });
    action.value = "";
    await loadAgentHistory();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

async function submitChat() {
  if (!sessionId.value || !selectedAgent.value || !chatMessage.value.trim()) {
    return;
  }
  try {
    chatBusy.value = true;
    chatError.value = "";
    const res = await chatWithWorldlineAgent({
      session_id: sessionId.value,
      agent_id: chatActor.value,
      message: chatMessage.value.trim(),
      mode: chatMode.value,
    });
    chatReply.value = res.data?.result || res.data || null;
    logs.value.unshift({ time: nowTime(), text: `[对话][${selectedAgent.value.display_name}] ${chatMessage.value}` });
    await loadAgentHistory();
  } catch (err) {
    chatError.value = err.message || "对话失败";
  } finally {
    chatBusy.value = false;
  }
}

onMounted(async () => {
  await loadSessions();
});
</script>

<style scoped>
.console-stage {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr) 320px;
  gap: var(--space-lg);
  height: calc(100vh - 120px);
}

.stage-selection,
.stage-context {
  overflow-y: auto;
  padding-right: var(--space-xs);
}

.stage-interaction {
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.empty-interaction {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--space-xl);
  background: var(--bg-panel-soft);
}
</style>
````

## `frontend/src/views/LlmFacilityView.vue`

````vue
<template>
  <div class="facility-stage stack">
    <!-- Header: Stats & Operations -->
    <header class="facility-header workbench-card">
      <div class="header-main">
        <h2 class="title-ancient">全局设施面板</h2>
        <div class="header-actions">
          <button class="btn subtle small" :disabled="loading" @click="reloadSettings">
            {{ loading ? "同步中..." : "刷新状态" }}
          </button>
        </div>
      </div>
      <div class="stats-row">
        <div class="stat-item"><label>渠道</label><strong class="mono">{{ channels.length }}</strong></div>
        <div class="stat-item"><label>模型</label><strong class="mono">{{ modelCount }}</strong></div>
        <div class="stat-item"><label>绑定</label><strong class="mono">{{ boundModuleCount }}</strong></div>
      </div>
      <div v-if="statusText || errorText" class="message-row">
        <span v-if="statusText" class="status-tag ok">{{ statusText }}</span>
        <span v-if="errorText" class="status-tag danger">{{ errorText }}</span>
      </div>
    </header>

    <div class="facility-grid container-7-5">
      <!-- Channel Management -->
      <LlmChannelPanel
        :channels="channels"
        :submitting="channelBusy"
        :syncing-key="syncingChannelKey"
        :deleting-key="deletingChannelKey"
        @create-channel="handleCreateChannel"
        @update-channel="handleUpdateChannel"
        @sync-channel="handleSyncChannel"
        @delete-channel="handleDeleteChannel"
      />

      <!-- Module Bindings -->
      <LlmModuleBindingsPanel
        :modules="modules"
        :channels="channels"
        :saving-key="savingModuleKey"
        :removing-key="removingModuleKey"
        @save-binding="handleSaveBinding"
        @remove-binding="handleRemoveBinding"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import {
  createLlmChannel,
  deleteLlmModuleBinding,
  deleteLlmChannel,
  getLlmSettings,
  syncLlmChannelModels,
  updateLlmChannel,
  updateLlmModuleBinding,
} from "../api/llm.js";
import LlmChannelPanel from "./llm-facility/LlmChannelPanel.vue";
import LlmModuleBindingsPanel from "./llm-facility/LlmModuleBindingsPanel.vue";

const channels = ref([]);
const modules = ref([]);
const loading = ref(false);
const errorText = ref("");
const statusText = ref("");
const submittingChannelKey = ref("");
const syncingChannelKey = ref("");
const deletingChannelKey = ref("");
const savingModuleKey = ref("");
const removingModuleKey = ref("");

const channelBusy = computed(() => !!submittingChannelKey.value);
const modelCount = computed(() => channels.value.reduce((sum, channel) => sum + (channel.models?.length || 0), 0));
const boundModuleCount = computed(() => modules.value.filter((item) => item.binding).length);

async function reloadSettings() {
  try {
    loading.value = true;
    errorText.value = "";
    const response = await getLlmSettings();
    channels.value = response.data.channels || [];
    modules.value = response.data.modules || [];
  } catch (error) {
    errorText.value = error.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

async function handleCreateChannel(payload, resetForm) {
  try {
    submittingChannelKey.value = "creating";
    await createLlmChannel(payload);
    resetForm?.();
    statusText.value = "渠道已创建";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "创建失败";
  } finally {
    submittingChannelKey.value = "";
  }
}

async function handleUpdateChannel(channelKey, payload, resetForm) {
  try {
    submittingChannelKey.value = channelKey;
    await updateLlmChannel(channelKey, payload);
    resetForm?.();
    statusText.value = "渠道已更新";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "更新失败";
  } finally {
    submittingChannelKey.value = "";
  }
}

async function handleDeleteChannel(channelKey) {
  if (!window.confirm("确认删除？")) return;
  try {
    deletingChannelKey.value = channelKey;
    await deleteLlmChannel(channelKey);
    statusText.value = "渠道已删除";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "删除失败";
  } finally {
    deletingChannelKey.value = "";
  }
}

async function handleSyncChannel(channelKey) {
  try {
    syncingChannelKey.value = channelKey;
    await syncLlmChannelModels(channelKey);
    statusText.value = "已同步";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "同步失败";
  } finally {
    syncingChannelKey.value = "";
  }
}

async function handleSaveBinding(moduleKey, payload) {
  try {
    savingModuleKey.value = moduleKey;
    await updateLlmModuleBinding(moduleKey, payload);
    statusText.value = "绑定已保存";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "保存失败";
  } finally {
    savingModuleKey.value = "";
  }
}

async function handleRemoveBinding(moduleKey) {
  if (!window.confirm("确认解绑？")) return;
  try {
    removingModuleKey.value = moduleKey;
    await deleteLlmModuleBinding(moduleKey);
    statusText.value = "绑定已解绑";
    await reloadSettings();
  } catch (error) {
    errorText.value = error.message || "解绑失败";
  } finally {
    removingModuleKey.value = "";
  }
}

onMounted(() => { reloadSettings(); });
</script>

<style scoped>
.facility-stage {
  max-width: 1200px;
  margin: 0 auto;
}

.facility-header {
  padding: var(--space-md) var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.header-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.stats-row {
  display: flex;
  gap: var(--space-xl);
  padding-top: var(--space-sm);
  border-top: 1px solid var(--line-soft);
}

.stat-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stat-item label {
  font-size: 11px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}

.stat-item strong {
  font-size: 18px;
  color: var(--text-main);
}

.message-row {
  display: flex;
  gap: var(--space-sm);
}

@media (max-width: 900px) {
  .facility-grid { grid-template-columns: 1fr; }
}
</style>
````

## `frontend/src/composables/useProjectCatalog.js`

````js
import { computed, reactive } from "vue";

import { listProjects } from "../api/project.js";

const DEFAULT_PROJECT_LIMIT = 30;

export function createProjectCatalogStore(loadProjects, defaultLimit = DEFAULT_PROJECT_LIMIT) {
  const state = reactive({
    lastLimit: defaultLimit,
    projects: [],
  });
  const projects = computed(() => state.projects);
  const latestProject = computed(() => state.projects[0] || null);

  async function refreshProjects(limit = state.lastLimit) {
    state.lastLimit = limit;
    const response = await loadProjects(limit);
    state.projects = Array.isArray(response?.data) ? response.data : [];
    return state.projects;
  }

  return {
    projects,
    latestProject,
    refreshProjects,
  };
}

const sharedProjectCatalogStore = createProjectCatalogStore((limit) => listProjects(limit));

export function useProjectCatalog() {
  return sharedProjectCatalogStore;
}
````

## `frontend/src/composables/useSeedUpload.js`

````js
import { reactive } from "vue";
import { getTask, uploadStorySeed } from "../api/project";
import {
  applyStructuredView,
  buildFailedTask,
  buildUploadingTask,
  DEFAULT_LLM_ACTIVITY,
  DEFAULT_TASK_METRICS,
  resetStructuredView,
} from "./seedUploadTaskState";

const DEFAULT_GOAL = "提取全部有名角色、组织和关系，用于世界线推演。";
let activeUploadPromise = null;
let activeUploadRequest = null;
const TASK_POLL_INTERVAL_MS = 1200;
const state = reactive({
  projectName: "我的小说项目",
  analysisGoal: DEFAULT_GOAL,
  additionalContext: "",
  files: [],
  dragActive: false,
  uploadBusy: false,
  uploadPhase: "idle",
  progressPercent: 0,
  statusText: "等待上传",
  stageLabel: "",
  uploadedBytes: 0,
  totalBytes: 0,
  taskId: "",
  taskStatus: "",
  result: null,
  error: "",
  completedProjectId: "",
  lastUploadedFiles: [],
  activeStage: { key: "", label: "", progress: 0, status: "pending" },
  taskMetrics: { ...DEFAULT_TASK_METRICS },
  llmActivity: { ...DEFAULT_LLM_ACTIVITY },
  timeline: [],
  taskStartedAt: "",
});

function fileKey(file) {
  return `${file.name}_${file.size}_${file.lastModified}`;
}

function isSupported(file) {
  return /\.(txt|md|markdown|pdf)$/i.test(file.name || "");
}

function hasFile(existingFiles, incomingFile) {
  return existingFiles.some((item) => fileKey(item) === fileKey(incomingFile));
}

function appendFiles(nextFiles) {
  const merged = [...state.files];
  for (const file of nextFiles) {
    if (!isSupported(file) || hasFile(merged, file)) {
      continue;
    }
    merged.push(file);
  }
  state.files = merged;
}

function removeFile(file) {
  state.files = state.files.filter((item) => fileKey(item) !== fileKey(file));
}

function formatSize(size) {
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function markUploadStart() {
  const startedAt = new Date().toISOString();
  state.uploadBusy = true;
  state.uploadPhase = "uploading";
  state.progressPercent = 0;
  state.statusText = "正在上传文件...";
  state.stageLabel = "文件上传";
  state.uploadedBytes = 0;
  state.totalBytes = 0;
  state.taskId = "";
  state.taskStatus = "";
  state.result = null;
  state.error = "";
  state.lastUploadedFiles = state.files.map((item) => item.name);
  state.taskStartedAt = startedAt;
  applyStructuredView(
    state,
    buildUploadingTask(startedAt, 0, "开始上传文件", "文件正在发送到后端，稍后将切换到后台分析日志。"),
  );
}

function updateProgress(progress) {
  if (progress.phase !== "uploading") {
    return;
  }
  state.uploadPhase = "uploading";
  state.progressPercent = Math.max(0, Math.min(99, progress.percent));
  state.uploadedBytes = progress.loaded;
  state.totalBytes = progress.total;
  state.stageLabel = "文件上传";
  state.statusText = `正在上传文件... ${state.progressPercent}%`;
  applyStructuredView(
    state,
    buildUploadingTask(
      state.taskStartedAt,
      state.progressPercent,
      "文件上传中",
      `${formatSize(progress.loaded)} / ${formatSize(progress.total || 0)}`,
    ),
  );
}

function beginTaskProcessing(data) {
  state.uploadPhase = "processing";
  state.taskId = data?.task_id || "";
  state.taskStatus = "processing";
  state.completedProjectId = data?.project_id || "";
  state.progressPercent = 0;
  state.stageLabel = "后台分析";
  state.statusText = "文件已上传，后台正在分析小说...";
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

function updateTaskProgress(task) {
  state.uploadPhase = "processing";
  state.taskStatus = task.status || "processing";
  const view = applyStructuredView(state, task);
  state.progressPercent = Math.max(0, Math.min(99, view.activeStage.progress));
  state.stageLabel = view.activeStage.label;
  state.statusText = task.message || view.activeStage.label;
}

async function waitForTaskCompletion(taskId) {
  while (true) {
    const response = await getTask(taskId);
    const task = response.data || {};
    if (task.status === "completed") {
      return task;
    }
    if (task.status === "failed") {
      throw new Error(task.error || task.message || "后台分析失败");
    }
    updateTaskProgress(task);
    await sleep(TASK_POLL_INTERVAL_MS);
  }
}

function finishUpload(projectData, taskData) {
  state.uploadBusy = false;
  state.uploadPhase = "success";
  state.taskStatus = "completed";
  state.result = {
    project_id: projectData?.project_id || "",
    project_name: projectData?.project_name || "",
    task_id: projectData?.task_id || "",
    task_result: taskData?.result || {},
    task_message: taskData?.message || "",
  };
  state.completedProjectId = projectData?.project_id || "";
  const view = applyStructuredView(state, taskData);
  state.progressPercent = Math.max(0, Math.min(100, view.activeStage.progress));
  state.stageLabel = view.activeStage.label;
  state.statusText = taskData?.message || view.activeStage.label;
  activeUploadPromise = null;
  activeUploadRequest = null;
}

function failUpload(message) {
  state.uploadBusy = false;
  state.uploadPhase = "error";
  state.taskStatus = "failed";
  state.error = message;
  const view = applyStructuredView(state, buildFailedTask(state.taskStartedAt, state.progressPercent, message));
  state.stageLabel = view.activeStage.label;
  state.statusText = message;
  activeUploadPromise = null;
  activeUploadRequest = null;
}

async function submitUpload() {
  if (state.uploadBusy && activeUploadPromise) {
    return activeUploadPromise;
  }
  if (!state.analysisGoal.trim()) {
    throw new Error("请先填写分析目标。");
  }
  if (!state.files.length) {
    throw new Error("请至少选择一个小说文件。");
  }
  markUploadStart();
  try {
    activeUploadPromise = uploadStorySeed({
      projectName: state.projectName.trim() || "我的小说项目",
      analysisGoal: state.analysisGoal.trim(),
      additionalContext: state.additionalContext.trim(),
      files: state.files,
      onProgress: updateProgress,
      onRequest: (xhr) => {
        activeUploadRequest = xhr;
      },
    });
    const response = await activeUploadPromise;
    beginTaskProcessing(response.data);
    if (!response.data?.task_id) {
      throw new Error("上传成功但未返回 task_id");
    }
    const taskData = await waitForTaskCompletion(response.data.task_id);
    finishUpload(response.data, taskData);
    return state.result;
  } catch (error) {
    failUpload(error.message || "上传失败");
    throw error;
  }
}

function clearNotice() {
  if (state.uploadBusy) {
    return;
  }
  state.uploadPhase = "idle";
  state.progressPercent = 0;
  state.statusText = "等待上传";
  state.stageLabel = "";
  state.taskId = "";
  state.taskStatus = "";
  state.result = null;
  state.error = "";
  resetStructuredView(state);
}

export function useSeedUpload() {
  return {
    state,
    fileKey,
    appendFiles,
    removeFile,
    formatSize,
    submitUpload,
    clearNotice,
  };
}
````

## `frontend/src/composables/useArchiveLibraryLayout.js`

````js
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import {
  ARCHIVE_LIBRARY_DIVIDER_SIZE_PX,
  ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP,
  ARCHIVE_LIBRARY_LAYOUT_STORAGE_KEY,
  ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO,
  clampArchiveLibrarySplitRatio,
  resolveArchiveLibraryLayoutMode,
  restoreArchiveLibrarySplitRatio,
} from "../views/shared/archiveLibraryLayout.js";

const DRAG_CURSOR = "col-resize";

export function useArchiveLibraryLayout() {
  const stageRef = ref(null);
  const splitRatio = ref(ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO);
  const layoutMode = ref(resolveArchiveLibraryLayoutMode(window.innerWidth));
  const resizing = ref(false);

  const stageStyle = computed(() => ({
    "--archive-library-divider-size": `${ARCHIVE_LIBRARY_DIVIDER_SIZE_PX}px`,
    "--archive-library-left-pane-ratio": String(splitRatio.value),
    "--archive-library-right-pane-ratio": String(1 - splitRatio.value),
  }));

  let resizeObserver = null;

  function syncLayoutFromElement() {
    applyContainerWidth(resolveContainerWidth(stageRef.value));
  }

  function applyContainerWidth(containerWidth) {
    const previousMode = layoutMode.value;
    const nextMode = resolveArchiveLibraryLayoutMode(containerWidth);
    layoutMode.value = nextMode;
    if (nextMode !== ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP) {
      splitRatio.value = ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO;
      return;
    }
    if (previousMode !== ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP) {
      splitRatio.value = readStoredRatio(containerWidth);
      return;
    }
    splitRatio.value = clampArchiveLibrarySplitRatio(splitRatio.value, containerWidth);
  }

  function beginResize(event) {
    if (layoutMode.value !== ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP) {
      return;
    }
    resizing.value = true;
    setDragDocumentState(true);
    updateFromPointer(event);
  }

  function updateFromPointer(event) {
    const nextRatio = resolvePointerRatio(event.clientX, stageRef.value);
    if (nextRatio === null) {
      return;
    }
    updateSplitRatio(nextRatio);
  }

  function handlePointerMove(event) {
    if (!resizing.value) {
      return;
    }
    updateFromPointer(event);
  }

  function stopResize() {
    if (!resizing.value) {
      return;
    }
    resizing.value = false;
    setDragDocumentState(false);
  }

  function updateSplitRatio(nextRatio) {
    const containerWidth = resolveContainerWidth(stageRef.value);
    const ratio = clampArchiveLibrarySplitRatio(nextRatio, containerWidth);
    splitRatio.value = ratio;
    window.localStorage.setItem(ARCHIVE_LIBRARY_LAYOUT_STORAGE_KEY, String(ratio));
  }

  onMounted(() => {
    splitRatio.value = readStoredRatio(resolveContainerWidth(stageRef.value));
    syncLayoutFromElement();
    resizeObserver = new ResizeObserver(syncLayoutFromElement);
    if (stageRef.value) {
      resizeObserver.observe(stageRef.value);
    }
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopResize);
  });

  onBeforeUnmount(() => {
    stopResize();
    resizeObserver?.disconnect();
    window.removeEventListener("pointermove", handlePointerMove);
    window.removeEventListener("pointerup", stopResize);
  });

  return {
    beginResize,
    layoutMode,
    resizing,
    stageRef,
    stageStyle,
  };
}

function readStoredRatio(containerWidth) {
  return restoreArchiveLibrarySplitRatio(
    window.localStorage.getItem(ARCHIVE_LIBRARY_LAYOUT_STORAGE_KEY),
    containerWidth,
  );
}

function resolveContainerWidth(element) {
  const width = element?.getBoundingClientRect?.().width;
  return Number.isFinite(width) && width > 0 ? width : window.innerWidth;
}

function resolvePointerRatio(clientX, element) {
  const rect = element?.getBoundingClientRect?.();
  if (!rect) {
    return null;
  }
  const availableWidth = rect.width - ARCHIVE_LIBRARY_DIVIDER_SIZE_PX;
  if (availableWidth <= 0) {
    return null;
  }
  const rawLeftWidth = clientX - rect.left - (ARCHIVE_LIBRARY_DIVIDER_SIZE_PX / 2);
  return rawLeftWidth / availableWidth;
}

function setDragDocumentState(active) {
  document.body.style.cursor = active ? DRAG_CURSOR : "";
  document.body.style.userSelect = active ? "none" : "";
}
````

## `frontend/src/composables/useWorldlineWorkbenchLayout.js`

````js
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import {
  clampWorldlineLeftPaneWidth,
  resolveWorldlineWorkbenchMode,
  restoreWorldlineLeftPaneWidth,
  WORLDLINE_LEFT_PANE_DEFAULT_WIDTH,
  WORLDLINE_LEFT_PANE_STORAGE_KEY,
} from "../views/shared/worldlineWorkbenchLayout.js";

const DRAG_CURSOR = "col-resize";

export function useWorldlineWorkbenchLayout() {
  const stageRef = ref(null);
  const leftPaneWidth = ref(WORLDLINE_LEFT_PANE_DEFAULT_WIDTH);
  const resizing = ref(false);
  const workbenchMode = ref(resolveWorldlineWorkbenchMode(window.innerWidth));

  const stageStyle = computed(() => ({
    "--worldline-left-pane-width": `${leftPaneWidth.value}px`,
  }));

  function syncLayoutState() {
    workbenchMode.value = resolveWorldlineWorkbenchMode(window.innerWidth);
    const storage = window.localStorage.getItem(WORLDLINE_LEFT_PANE_STORAGE_KEY);
    leftPaneWidth.value = restoreWorldlineLeftPaneWidth(storage, window.innerWidth);
  }

  function updatePaneWidth(nextWidth) {
    const width = clampWorldlineLeftPaneWidth(nextWidth, window.innerWidth);
    leftPaneWidth.value = width;
    window.localStorage.setItem(WORLDLINE_LEFT_PANE_STORAGE_KEY, String(width));
  }

  function beginResize(event) {
    resizing.value = true;
    setDragDocumentState(true);
    updateFromPointer(event);
  }

  function stopResize() {
    if (!resizing.value) {
      return;
    }
    resizing.value = false;
    setDragDocumentState(false);
  }

  function handlePointerMove(event) {
    if (!resizing.value) {
      return;
    }
    updateFromPointer(event);
  }

  function updateFromPointer(event) {
    const rect = stageRef.value?.getBoundingClientRect();
    if (!rect) {
      return;
    }
    updatePaneWidth(event.clientX - rect.left);
  }

  onMounted(() => {
    syncLayoutState();
    window.addEventListener("resize", syncLayoutState);
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopResize);
  });

  onBeforeUnmount(() => {
    stopResize();
    window.removeEventListener("resize", syncLayoutState);
    window.removeEventListener("pointermove", handlePointerMove);
    window.removeEventListener("pointerup", stopResize);
  });

  return {
    stageRef,
    stageStyle,
    leftPaneWidth,
    resizing,
    workbenchMode,
    beginResize,
  };
}

function setDragDocumentState(active) {
  document.body.style.cursor = active ? DRAG_CURSOR : "";
  document.body.style.userSelect = active ? "none" : "";
}
````

## `frontend/src/api/project.js`

````js
import { del, get, post, uploadForm } from "./http.js";

export function buildProjectDeletePath(projectId) {
  return `/api/project/${projectId}`;
}

export function listProjects(limit = 20) {
  return get(`/api/project/list?limit=${limit}`);
}

export function getProject(projectId) {
  return get(`/api/project/${projectId}`);
}

export function getProjectGraph(projectId) {
  return get(`/api/project/${projectId}/graph`);
}

export function deleteProject(projectId) {
  return del(buildProjectDeletePath(projectId));
}

export function buildGraph(projectId, graphName = "Novel Story Graph") {
  return post("/api/project/build-graph", {
    project_id: projectId,
    graph_name: graphName,
  });
}

export function getTask(taskId) {
  return get(`/api/project/task/${taskId}`);
}

export function uploadStorySeed({
  projectName,
  analysisGoal,
  additionalContext,
  files = [],
  onProgress,
  onRequest,
}) {
  const formData = new FormData();
  formData.append("project_name", projectName);
  formData.append("analysis_goal", analysisGoal);
  formData.append("additional_context", additionalContext || "");
  for (const file of files) {
    formData.append("files", file);
  }
  return uploadForm("/api/project/seed/extract", formData, { onProgress, onRequest });
}
````

## `frontend/src/api/novel.js`

````js
import { get, post } from "./http.js";

export function generateArchiveCandidates({ projectId, graphId, entityTypes }) {
  return post("/api/novel/archives/candidates", {
    project_id: projectId,
    graph_id: graphId,
    entity_types: entityTypes,
  });
}

export function generateArchives({
  projectId,
  graphId,
  entityTypes,
  useLlm = false,
  tierOverrides = [],
  candidateSnapshot = [],
}) {
  return post("/api/novel/archives/generate", {
    project_id: projectId,
    graph_id: graphId,
    entity_types: entityTypes,
    use_llm: useLlm,
    tier_overrides: tierOverrides,
    candidate_snapshot: candidateSnapshot,
  });
}

export function generateParallelWorldConfig({
  projectId,
  graphId,
  variables = [],
  entityTypes,
  branchCount,
  focusQuestion,
  useLlm = false,
}) {
  return post("/api/novel/parallel-world/config", {
    project_id: projectId,
    graph_id: graphId,
    variables,
    entity_types: entityTypes,
    branch_count: branchCount,
    focus_question: focusQuestion,
    use_llm: useLlm,
  });
}

export function runSeedAnalysis({
  projectId,
  graphId,
  analysisGoal,
  maxCharacters = 120,
  maxOrganizations = 80,
}) {
  const payload = {
    project_id: projectId,
    graph_id: graphId,
    analysis_goal: analysisGoal,
    max_characters: maxCharacters,
    max_organizations: maxOrganizations,
  };
  return post("/api/novel/seed-analysis", payload);
}

export function getChapterContextOptions(projectId) {
  return get(`/api/novel/chapter-context/options?project_id=${encodeURIComponent(projectId)}`);
}

export function buildChapterContext(payload) {
  return post("/api/novel/chapter-context", payload);
}
````

## `frontend/src/api/archive.js`

````js
import { get, post } from "./http.js";

export function buildArchiveLibraryListPath({
  q = "",
  projectId = "",
  entityType = "",
  importanceTier = "",
  limit,
  offset,
} = {}) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (projectId) params.set("project_id", projectId);
  if (entityType) params.set("entity_type", entityType);
  if (importanceTier) params.set("importance_tier", importanceTier);
  if (limit !== undefined) params.set("limit", String(limit));
  if (offset !== undefined) params.set("offset", String(offset));
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/api/archive/library${suffix}`;
}

export function buildArchiveLibraryDetailPath(archiveId) {
  return `/api/archive/library/${archiveId}`;
}

export function buildArchiveMemoryPath(archiveId, {
  includeCandidates,
  include_candidates: rawIncludeCandidates,
  layer,
  status,
} = {}) {
  const params = new URLSearchParams();
  const resolvedIncludeCandidates = includeCandidates ?? rawIncludeCandidates;
  if (resolvedIncludeCandidates !== undefined) {
    params.set("include_candidates", String(Boolean(resolvedIncludeCandidates)));
  }
  if (layer) {
    params.set("layer", layer);
  }
  if (status) {
    params.set("status", status);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/api/archive/library/${archiveId}/memory${suffix}`;
}

export function buildArchiveMemoryTimelinePath(archiveId, {
  memoryId,
  memory_id: rawMemoryId,
  normalizedSubject,
  normalized_subject: rawNormalizedSubject,
} = {}) {
  const params = new URLSearchParams();
  const resolvedMemoryId = memoryId || rawMemoryId;
  const resolvedSubject = normalizedSubject || rawNormalizedSubject;
  if (resolvedMemoryId) params.set("memory_id", resolvedMemoryId);
  if (resolvedSubject) params.set("normalized_subject", resolvedSubject);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/api/archive/library/${archiveId}/memory/timeline${suffix}`;
}

export function listArchiveLibrary(filters = {}) {
  return get(buildArchiveLibraryListPath(filters));
}

export function getArchiveLibraryDetail(archiveId) {
  return get(buildArchiveLibraryDetailPath(archiveId));
}

export function listArchiveMemory(archiveId, filters = {}) {
  return get(buildArchiveMemoryPath(archiveId, filters));
}

export function getArchiveMemoryTimeline(archiveId, filters = {}) {
  return get(buildArchiveMemoryTimelinePath(archiveId, filters));
}

export function adoptArchiveMemory(archiveId, memoryId) {
  return post(`/api/archive/library/${archiveId}/memory/${memoryId}/adopt`, {});
}

export function rejectArchiveMemory(archiveId, memoryId) {
  return post(`/api/archive/library/${archiveId}/memory/${memoryId}/reject`, {});
}

export function reindexArchiveLibrary() {
  return post("/api/archive/library/reindex", {});
}
````

## `frontend/src/api/worldline.js`

````js
import { get, post } from "./http.js";

export function createWorldlineSession(payload) {
  return post("/api/worldline/session/create", payload);
}

export function startWorldlineAutoEvolve({ session_id: sessionId, ...payload }) {
  const { branch_ids, ...singleWorldPayload } = payload;
  void branch_ids;
  return post(`/api/worldline/session/${sessionId}/auto-evolve`, singleWorldPayload);
}

export function buildWorldlineSessionListPath({ projectId } = {}) {
  const params = new URLSearchParams();
  if (projectId) {
    params.set("project_id", projectId);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return `/api/worldline/session/list${suffix}`;
}

export function getWorldlineSession(sessionId) {
  return get(`/api/worldline/session/${sessionId}`);
}

export function listWorldlineSessions(filters = {}) {
  return get(buildWorldlineSessionListPath(filters));
}

export function advanceWorldlineStep({ session_id: sessionId, ...payload }) {
  return post(`/api/worldline/session/${sessionId}/step`, payload);
}

export function injectWorldlineVariable({ session_id: sessionId, ...payload }) {
  return post(`/api/worldline/session/${sessionId}/inject-variable`, payload);
}

export function issueAgentAction({ session_id: sessionId, ...payload }) {
  return post(`/api/worldline/session/${sessionId}/agent-action`, payload);
}

export function getWorldlineTimeline(sessionId, branchId) {
  void branchId;
  return get(`/api/worldline/session/${sessionId}/timeline`);
}

export function getWorldlineAgents(sessionId, branchId) {
  const suffix = buildWorldlineQuery({ branchId });
  return get(`/api/worldline/session/${sessionId}/agents${suffix}`);
}

export function getWorldlineAgentHistory(sessionId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-history${suffix}`);
}

export function getWorldlineAgentMemory(sessionId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-memory${suffix}`);
}

export function getWorldlineAgentMemoryContext(sessionId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-memory-context${suffix}`);
}

export function getWorldlineAgentActions(sessionId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-actions${suffix}`);
}

export function getWorldlineAgentDialogues(sessionId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/agent-dialogues${suffix}`);
}

export function getWorldlineRelationHistory(sessionId, filters = {}) {
  const suffix = buildWorldlineQuery(filters);
  return get(`/api/worldline/session/${sessionId}/relation-history${suffix}`);
}

function buildWorldlineQuery({
  branchId,
  branch_id: rawBranchId,
  agentId,
  agent_id: rawAgentId,
  status,
  limit,
  message,
} = {}) {
  const params = new URLSearchParams();
  const resolvedBranchId = branchId || rawBranchId;
  const resolvedAgentId = agentId || rawAgentId;
  if (resolvedBranchId) {
    params.set("branch_id", resolvedBranchId);
  }
  if (resolvedAgentId) {
    params.set("agent_id", resolvedAgentId);
  }
  if (status) {
    params.set("status", status);
  }
  if (typeof limit === "number" && Number.isFinite(limit)) {
    params.set("limit", String(limit));
  }
  if (message) {
    params.set("message", message);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return suffix;
}

export function chatWithWorldlineAgent({ session_id: sessionId, ...payload }) {
  return post(`/api/worldline/session/${sessionId}/agent-dialogue`, payload);
}

export function generatePlotInspiration(payload) {
  return post("/api/novel/plot/inspiration", payload);
}
````

## `frontend/src/api/llm.js`

````js
import { del, get, patch, post, put } from "./http.js";

export function buildLlmChannelPath(channelKey = "") {
  return channelKey ? `/api/llm/channels/${channelKey}` : "/api/llm/channels";
}

export function buildLlmChannelSyncModelsPath(channelKey) {
  return `/api/llm/channels/${channelKey}/sync-models`;
}

export function buildLlmModuleBindingPath(moduleKey) {
  return `/api/llm/module-bindings/${moduleKey}`;
}

export function getLlmSettings() {
  return get("/api/llm/settings");
}

export function createLlmChannel(payload) {
  return post(buildLlmChannelPath(), payload);
}

export function updateLlmChannel(channelKey, payload) {
  return patch(buildLlmChannelPath(channelKey), payload);
}

export function deleteLlmChannel(channelKey) {
  return del(buildLlmChannelPath(channelKey));
}

export function syncLlmChannelModels(channelKey) {
  return post(buildLlmChannelSyncModelsPath(channelKey), {});
}

export function updateLlmModuleBinding(moduleKey, payload) {
  return put(buildLlmModuleBindingPath(moduleKey), payload);
}

export function deleteLlmModuleBinding(moduleKey) {
  return del(buildLlmModuleBindingPath(moduleKey));
}
````

## `frontend/tests/vite-config.test.mjs`

````mjs
import test from "node:test";
import assert from "node:assert/strict";

import config from "../vite.config.js";

test("dev server proxies api requests to backend", () => {
  assert.equal(config.server?.port, 3891);
  assert.equal(config.server?.strictPort, true);
  assert.equal(config.server?.proxy?.["/api"]?.target, "http://127.0.0.1:5101");
});
````

## `frontend/tests/overview-layout.test.mjs`

````mjs
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const overviewViewSource = readFileSync(new URL("../src/views/OverviewView.vue", import.meta.url), "utf8");
const uploadPanelSource = readFileSync(new URL("../src/views/overview/SeedUploadPanel.vue", import.meta.url), "utf8");
const pipelineSource = readFileSync(new URL("../src/views/overview/PipelineVisualization.vue", import.meta.url), "utf8");

test("overview stage does not keep the legacy centered max width", () => {
  assert.doesNotMatch(overviewViewSource, /\.overview-stage\s*\{[^}]*max-width:\s*1200px;/s);
});

test("seed upload container does not keep the legacy narrow max width", () => {
  assert.doesNotMatch(uploadPanelSource, /\.upload-container\s*\{[^}]*max-width:\s*900px;/s);
});

test("pipeline visualization uses a wrapping grid instead of horizontal scrolling", () => {
  assert.match(pipelineSource, /\.pipeline-flow\s*\{[^}]*display:\s*grid;/s);
  assert.match(pipelineSource, /\.pipeline-flow\s*\{[^}]*grid-template-columns:\s*repeat\(auto-fit,\s*minmax\(/s);
  assert.doesNotMatch(pipelineSource, /\.pipeline-flow\s*\{[^}]*overflow-x:\s*auto;/s);
});
````

## `frontend/tests/archive-library-layout.test.mjs`

````mjs
import test from "node:test";
import assert from "node:assert/strict";

import {
  ARCHIVE_LIBRARY_DESKTOP_BREAKPOINT,
  ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP,
  ARCHIVE_LIBRARY_LAYOUT_MODE_STACKED,
  ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO,
  ARCHIVE_LIBRARY_SPLIT_MAX_RATIO,
  ARCHIVE_LIBRARY_SPLIT_MIN_RATIO,
  clampArchiveLibrarySplitRatio,
  resolveArchiveLibraryLayoutMode,
  restoreArchiveLibrarySplitRatio,
} from "../src/views/shared/archiveLibraryLayout.js";

test("resolveArchiveLibraryLayoutMode keeps wide containers in desktop mode", () => {
  assert.equal(
    resolveArchiveLibraryLayoutMode(ARCHIVE_LIBRARY_DESKTOP_BREAKPOINT),
    ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP,
  );
  assert.equal(resolveArchiveLibraryLayoutMode(960), ARCHIVE_LIBRARY_LAYOUT_MODE_STACKED);
});

test("restoreArchiveLibrarySplitRatio returns the default ratio when storage is empty", () => {
  assert.equal(restoreArchiveLibrarySplitRatio(null, 1440), ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO);
});

test("clampArchiveLibrarySplitRatio enforces desktop ratio limits", () => {
  assert.equal(
    clampArchiveLibrarySplitRatio(0.1, 1440),
    ARCHIVE_LIBRARY_SPLIT_MIN_RATIO,
  );
  assert.equal(
    clampArchiveLibrarySplitRatio(0.9, 1440),
    ARCHIVE_LIBRARY_SPLIT_MAX_RATIO,
  );
});

test("restoreArchiveLibrarySplitRatio clamps persisted values into the allowed range", () => {
  assert.equal(restoreArchiveLibrarySplitRatio("0.46", 1440), 0.46);
  assert.equal(
    restoreArchiveLibrarySplitRatio("0.9", 1440),
    ARCHIVE_LIBRARY_SPLIT_MAX_RATIO,
  );
});

test("stacked mode always falls back to the default ratio", () => {
  assert.equal(restoreArchiveLibrarySplitRatio("0.56", 960), ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO);
  assert.equal(clampArchiveLibrarySplitRatio(0.56, 960), ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO);
});

test("restoreArchiveLibrarySplitRatio falls back to the default ratio for invalid values", () => {
  assert.equal(
    restoreArchiveLibrarySplitRatio("not-a-number", 1440),
    ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO,
  );
});
````

## `frontend/tests/worldline-workbench-layout.test.mjs`

````mjs
import test from "node:test";
import assert from "node:assert/strict";

import {
  clampWorldlineLeftPaneWidth,
  resolveWorldlineWorkbenchMode,
  restoreWorldlineLeftPaneWidth,
  WORLDLINE_WORKBENCH_DESKTOP_BREAKPOINT,
  WORLDLINE_LEFT_PANE_DEFAULT_WIDTH,
  WORLDLINE_LEFT_PANE_MAX_WIDTH,
  WORLDLINE_LEFT_PANE_MIN_WIDTH,
} from "../src/views/shared/worldlineWorkbenchLayout.js";

test("restoreWorldlineLeftPaneWidth returns the default width when storage is empty", () => {
  assert.equal(restoreWorldlineLeftPaneWidth(null, 1600), WORLDLINE_LEFT_PANE_DEFAULT_WIDTH);
});

test("desktop breakpoint keeps wide screens in fixed three-column mode", () => {
  assert.equal(resolveWorldlineWorkbenchMode(WORLDLINE_WORKBENCH_DESKTOP_BREAKPOINT), "desktop");
  assert.equal(resolveWorldlineWorkbenchMode(1200), "stacked");
});

test("clampWorldlineLeftPaneWidth enforces the desktop minimum width", () => {
  assert.equal(clampWorldlineLeftPaneWidth(120, 1600), WORLDLINE_LEFT_PANE_MIN_WIDTH);
});

test("clampWorldlineLeftPaneWidth enforces the viewport-derived maximum width", () => {
  assert.equal(clampWorldlineLeftPaneWidth(1200, 1200), 780);
  assert.equal(clampWorldlineLeftPaneWidth(1200, 2000), WORLDLINE_LEFT_PANE_MAX_WIDTH);
});

test("restoreWorldlineLeftPaneWidth clamps valid persisted values", () => {
  assert.equal(restoreWorldlineLeftPaneWidth("900", 1600), 900);
  assert.equal(restoreWorldlineLeftPaneWidth("900", 1200), 780);
});

test("restoreWorldlineLeftPaneWidth falls back to the default width for invalid values", () => {
  assert.equal(restoreWorldlineLeftPaneWidth("not-a-number", 1600), WORLDLINE_LEFT_PANE_DEFAULT_WIDTH);
});
````

## `frontend/tests/writer-workbench-layout.test.mjs`

````mjs
import test from "node:test";
import assert from "node:assert/strict";

import {
  WRITER_WORKBENCH_DESKTOP_BREAKPOINT,
  WRITER_WORKBENCH_MODE_DESKTOP,
  WRITER_WORKBENCH_MODE_STACKED,
  buildWriterWorkbenchColumns,
  resolveWriterWorkbenchMode,
} from "../src/views/writer/writerWorkbenchLayout.js";

test("writer workbench uses desktop mode above the breakpoint", () => {
  assert.equal(resolveWriterWorkbenchMode(WRITER_WORKBENCH_DESKTOP_BREAKPOINT), WRITER_WORKBENCH_MODE_DESKTOP);
  assert.equal(resolveWriterWorkbenchMode(1200), WRITER_WORKBENCH_MODE_STACKED);
});

test("writer workbench columns reflect the current mode", () => {
  assert.equal(
    buildWriterWorkbenchColumns(WRITER_WORKBENCH_MODE_DESKTOP),
    "minmax(280px, 340px) minmax(0, 1fr) minmax(280px, 360px)",
  );
  assert.equal(buildWriterWorkbenchColumns(WRITER_WORKBENCH_MODE_STACKED), "1fr");
});
````

