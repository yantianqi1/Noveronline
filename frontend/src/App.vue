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
  { path: "/worldline", label: "世界线", code: "03" },
  { path: "/character-console", label: "角色控制", code: "04" },
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
