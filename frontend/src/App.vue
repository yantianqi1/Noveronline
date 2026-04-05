<template>
  <div class="shell">
    <aside class="left-track" :class="{ collapsed: sidebarCollapsed }">
      <div class="brand">
        <div class="seal" @click="sidebarCollapsed = !sidebarCollapsed" title="收起/展开侧栏">
          <span class="seal-inner">MF</span>
        </div>
        <div v-show="!sidebarCollapsed" class="brand-text">
          <div class="brand-name">{{ APP_BRAND_NAME }}</div>
          <div class="brand-sub mono">{{ APP_SUBTITLE }}</div>
        </div>
      </div>

      <nav class="nav-track">
        <div class="nav-group">
          <div v-show="!sidebarCollapsed" class="group-label">主要通路</div>
          <RouterLink
            v-for="item in mainNav"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :title="sidebarCollapsed ? item.label : ''"
          >
            <span v-show="sidebarCollapsed" class="nav-icon">{{ item.icon }}</span>
            <span v-show="!sidebarCollapsed" class="nav-dot"></span>
            <span v-show="!sidebarCollapsed" class="nav-label">{{ item.label }}</span>
            <span v-show="!sidebarCollapsed" class="nav-code mono">{{ item.code }}</span>
          </RouterLink>
        </div>

        <div class="nav-group">
          <div v-show="!sidebarCollapsed" class="group-label">辅助与配置</div>
          <RouterLink
            v-for="item in subNav"
            :key="item.path"
            :to="item.path"
            class="nav-item sub"
            :title="sidebarCollapsed ? item.label : ''"
          >
            <span v-show="sidebarCollapsed" class="nav-icon">{{ item.icon }}</span>
            <span v-show="!sidebarCollapsed" class="nav-dot"></span>
            <span v-show="!sidebarCollapsed" class="nav-label">{{ item.label }}</span>
          </RouterLink>
        </div>
      </nav>

      <footer class="track-footer">
        <button class="collapse-toggle" @click="sidebarCollapsed = !sidebarCollapsed" :title="sidebarCollapsed ? '展开侧栏' : '收起侧栏'">
          <span class="collapse-chevron" :class="{ flipped: sidebarCollapsed }"></span>
          <span v-show="!sidebarCollapsed" class="collapse-label">收起侧栏</span>
        </button>
        <div v-if="upload.state.uploadPhase !== 'idle'" class="mini-status" @click="showUploadOverlay = true">
          <div class="status-pulse"></div>
          <span v-show="!sidebarCollapsed" class="mono">{{ upload.state.statusText }}</span>
        </div>
      </footer>
    </aside>

    <main class="main-stage">
      <header class="stage-header">
        <div class="breadcrumb">
          <span class="title-ancient">{{ currentNavLabel }}</span>
        </div>
        <div class="header-actions">
          <LlmActivityIndicator />
        </div>
      </header>

      <div class="stage-content">
        <RouterView v-slot="{ Component }">
          <KeepAlive>
            <component :is="Component" />
          </KeepAlive>
        </RouterView>
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

import LlmActivityIndicator from "./components/LlmActivityIndicator.vue";
import { useProjectCatalog } from "./composables/useProjectCatalog";
import { useSeedUpload } from "./composables/useSeedUpload";
import { APP_BRAND_NAME, APP_SUBTITLE, formatUploadPhase } from "./utils/chineseDisplay";

const route = useRoute();
const upload = useSeedUpload();
const { refreshProjects } = useProjectCatalog();
const showUploadOverlay = ref(false);
const sidebarCollapsed = ref(false);

const mainNav = [
  { path: "/", label: "总览", code: "00", icon: "览" },
  { path: "/story-graph", label: "故事图谱", code: "01", icon: "谱" },
  { path: "/archive-library", label: "档案库", code: "02", icon: "档" },
  { path: "/worldline", label: "世界线", code: "03", icon: "线" },
  { path: "/character-console", label: "角色控制", code: "04", icon: "控" },
  { path: "/writer", label: "写作台", code: "05", icon: "笔" },
];

const subNav = [
  { path: "/guide", label: "帮助指南", icon: "?" },
  { path: "/llm-facility", label: "设施面板", icon: "AI" },
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

// Auto-collapse sidebar when entering workbench/module routes
const workbenchPaths = new Set(["/story-graph", "/worldline", "/writer", "/character-console"]);
watch(() => route.path, (newPath, oldPath) => {
  if (workbenchPaths.has(newPath) && !workbenchPaths.has(oldPath)) {
    sidebarCollapsed.value = true;
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
  width: 220px;
  background: var(--bg-panel);
  border-right: 1px solid var(--line-soft);
  display: flex;
  flex-direction: column;
  padding: var(--space-lg);
  position: sticky;
  top: 0;
  height: 100vh;
  transition: width 0.25s ease, padding 0.25s ease;
  overflow: hidden;
}

.left-track.collapsed {
  width: 64px;
  padding: var(--space-lg) var(--space-sm);
}

.brand {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
  margin-bottom: var(--space-xl);
}

.collapsed .brand {
  align-items: center;
}

.seal {
  width: 40px;
  height: 40px;
  background: var(--color-primary);
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
  transform: rotate(-2deg);
  cursor: pointer;
  transition: transform 0.2s ease;
}

.seal:hover {
  transform: rotate(0deg) scale(1.05);
}

.seal-inner {
  color: #fff;
  font-family: var(--font-mono);
  font-weight: 700;
  font-size: 14px;
  border: 1px solid rgba(255,255,255,0.3);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
}

.brand-name {
  font-family: var(--font-heading-cn);
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.02em;
  color: var(--text-main);
}

.brand-sub {
  font-size: 11px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-family: var(--font-mono);
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
  letter-spacing: 0.1em;
  text-transform: uppercase;
  padding-left: 12px;
  font-weight: 500;
}

.nav-item {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  text-decoration: none;
  color: var(--text-sub);
  border-radius: var(--radius-md);
  transition: all 0.2s ease;
  position: relative;
  gap: var(--space-sm);
  font-size: 14px;
  white-space: nowrap;
}

.collapsed .nav-item {
  justify-content: center;
  padding: 10px 0;
}

.nav-dot {
  width: 6px;
  height: 6px;
  background: transparent;
  border-radius: 50%;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.nav-icon {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-sub);
  background: var(--bg-paper-warm);
  border-radius: var(--radius-sm);
  font-family: var(--font-heading-cn);
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.nav-item:hover .nav-icon {
  color: var(--text-main);
  background: var(--line-soft);
}

.nav-item.router-link-active .nav-icon {
  color: #fff;
  background: var(--color-primary);
}

.nav-label {
  font-size: 14px;
  font-weight: 500;
  flex: 1;
}

.nav-code {
  font-size: 10px;
  opacity: 0.4;
  font-family: var(--font-mono);
}

.nav-item:hover {
  background: var(--bg-paper-warm);
  color: var(--text-main);
}

.nav-item.router-link-active {
  background: var(--bg-paper-warm);
  color: var(--color-primary);
}

.nav-item.router-link-active .nav-dot {
  background: var(--color-primary);
}

.nav-item.router-link-active .nav-code {
  opacity: 0.8;
  color: var(--color-primary);
}

.nav-item.sub {
  padding: 8px 12px;
  font-size: 13px;
}

.nav-item.sub .nav-dot {
  width: 4px;
  height: 4px;
}

.nav-item.sub.router-link-active .nav-dot {
  background: var(--color-primary);
}

.collapsed .nav-item.sub {
  padding: 10px 0;
}

.track-footer {
  margin-top: auto;
  padding-top: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.collapse-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 14px;
  background: rgba(176, 125, 75, 0.04);
  border: 1px solid rgba(176, 125, 75, 0.15);
  border-radius: 10px;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-dim);
  transition: background 0.25s ease, border-color 0.25s ease, color 0.25s ease, box-shadow 0.25s ease;
  white-space: nowrap;
}

.collapse-toggle:hover {
  background: rgba(176, 125, 75, 0.1);
  border-color: rgba(176, 125, 75, 0.3);
  color: var(--accent-copper-deep, #8b6540);
  box-shadow: 0 1px 4px rgba(176, 125, 75, 0.1);
}

.collapsed .collapse-toggle {
  justify-content: center;
  padding: 9px 0;
}

.collapse-chevron {
  width: 7px;
  height: 7px;
  border-left: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  transform: rotate(45deg);
  transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
}

.collapse-chevron.flipped {
  transform: rotate(-135deg);
}

.collapse-label {
  font-family: var(--font-mono);
  letter-spacing: 0.04em;
}

.mini-status {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 10px 12px;
  background: rgba(155, 44, 44, 0.08);
  border: 1px solid rgba(155, 44, 44, 0.2);
  border-radius: var(--radius-md);
  cursor: pointer;
  font-size: 12px;
  color: var(--color-primary);
  font-family: var(--font-mono);
}

.mini-status:hover {
  background: rgba(155, 44, 44, 0.12);
}

.status-pulse {
  width: 8px;
  height: 8px;
  background: var(--color-primary);
  border-radius: 50%;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(155, 44, 44, 0.4); }
  70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(155, 44, 44, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(155, 44, 44, 0); }
}

.main-stage {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: var(--bg-paper);
}

.stage-header {
  height: 60px;
  padding: 0 var(--space-xl);
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--line-soft);
  background: var(--bg-panel);
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
  font-family: var(--font-heading-cn);
  font-size: 18px;
  font-weight: 700;
  color: var(--text-main);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-md);
}

.stage-content {
  padding: var(--space-xl);
  flex: 1;
  overflow-y: auto;
}

/* Overlay Styles */
.overlay {
  position: fixed;
  inset: 0;
  background: rgba(45, 55, 72, 0.4);
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
  background: var(--bg-paper-warm);
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: var(--color-primary);
  transition: width 0.3s ease;
}

.info-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-dim);
  font-family: var(--font-mono);
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
  .nav-track { display: none; }
}
</style>
