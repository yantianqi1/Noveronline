<template>
  <div class="shell">
    <aside class="left-nav workbench-card">
      <div class="brand">
        <div class="seal">MF</div>
        <div>
          <div class="brand-name">{{ APP_BRAND_NAME }}</div>
          <div class="brand-sub mono">{{ APP_SUBTITLE }}</div>
        </div>
      </div>
      <section class="nav-section">
        <div class="section-label mono">主导航</div>
        <nav class="nav-list">
          <RouterLink v-for="item in navItems" :key="item.path" :to="item.path" class="nav-item">
            <span class="mono nav-code">{{ item.code }}</span>
            <span class="nav-copy">
              <strong>{{ item.label }}</strong>
              <small>{{ item.hint }}</small>
            </span>
          </RouterLink>
        </nav>
      </section>
    </aside>
    <main class="main-stage">
      <header class="top-head">
        <h1>{{ APP_BRAND_NAME }}</h1>
        <p>{{ APP_SUBTITLE }}</p>
        <div v-if="showUploadStatus" class="upload-shell-card">
          <div class="upload-shell-top">
            <strong>{{ upload.state.statusText }}</strong>
            <button class="shell-close" :disabled="upload.state.uploadBusy" @click="upload.clearNotice">收起</button>
          </div>
          <div class="upload-shell-meta">
            <span class="mono">{{ upload.state.completedProjectId || "最新上传任务" }}</span>
            <span>{{ upload.state.lastUploadedFiles.length }} 个文件</span>
            <span>{{ upload.state.stageLabel || formatUploadPhase(upload.state.uploadPhase) }}</span>
          </div>
          <div class="upload-shell-track">
            <div class="upload-shell-bar" :style="{ width: `${upload.state.progressPercent}%` }"></div>
          </div>
        </div>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted } from "vue";

import { useProjectCatalog } from "./composables/useProjectCatalog";
import { useSeedUpload } from "./composables/useSeedUpload";
import { APP_BRAND_NAME, APP_SUBTITLE, formatUploadPhase } from "./utils/chineseDisplay";

const navItems = [
  { path: "/", label: "总览页", code: "00", hint: "从这里开始" },
  { path: "/guide", label: "使用教程", code: "01", hint: "四步上手与术语说明" },
  { path: "/archive-library", label: "全局档案库", code: "02", hint: "查看角色档案" },
  { path: "/story-graph", label: "故事图谱工作台", code: "03", hint: "浏览实体关系" },
  { path: "/worldline", label: "世界线工作台", code: "04", hint: "平行世界推演" },
  { path: "/character-console", label: "角色控制台", code: "05", hint: "与角色对话 / 下达指令" },
  { path: "/llm-facility", label: "全局设施面板", code: "06", hint: "模型与能力设施" },
];
const upload = useSeedUpload();
const { refreshProjects } = useProjectCatalog();
const showUploadStatus = computed(() => upload.state.uploadPhase !== "idle");

onMounted(() => {
  refreshProjects().catch((error) => {
    console.error(error);
  });
});
</script>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  min-height: 100vh;
  gap: 14px;
  padding: 14px;
}

.left-nav {
  padding: 16px;
  position: sticky;
  top: 14px;
  height: calc(100vh - 28px);
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 18px;
  background:
    linear-gradient(180deg, rgba(255, 247, 233, 0.94), rgba(248, 239, 223, 0.94)),
    repeating-linear-gradient(
      45deg,
      rgba(159, 141, 106, 0.05) 0,
      rgba(159, 141, 106, 0.05) 10px,
      rgba(255, 255, 255, 0) 10px,
      rgba(255, 255, 255, 0) 20px
    );
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.seal {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  border: 1px solid var(--accent-copper);
  display: grid;
  place-items: center;
  color: var(--accent-copper);
  font-family: "JetBrains Mono", monospace;
  font-weight: 700;
  background: #fffaf0;
}

.brand-name {
  font-family: "ZCOOL XiaoWei", serif;
  font-size: 24px;
}

.brand-sub {
  font-size: 12px;
  color: var(--text-sub);
}

.nav-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-label {
  font-size: 12px;
  letter-spacing: 0.08em;
  color: var(--text-sub);
}

.nav-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.nav-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  text-decoration: none;
  border: 1px solid transparent;
  border-radius: 12px;
  padding: 11px;
  color: var(--text-main);
  transition: all 120ms ease;
}

.nav-item.router-link-active {
  border-color: var(--line-strong);
  background: rgba(255, 252, 244, 0.92);
}

.nav-item:hover {
  border-color: var(--line-soft);
}

.nav-code {
  font-size: 12px;
  color: var(--text-sub);
  padding-top: 2px;
}

.nav-copy {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.nav-copy strong {
  font-size: 14px;
}

.nav-copy small {
  color: var(--text-sub);
  line-height: 1.4;
}

.main-stage {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.top-head {
  border: 1px solid var(--line-soft);
  border-radius: var(--radius);
  padding: 18px 20px;
  background: rgba(255, 251, 241, 0.86);
}

.top-head h1 {
  margin: 0;
  font-family: "ZCOOL XiaoWei", serif;
  font-size: 34px;
  letter-spacing: 0.02em;
}

.top-head p {
  margin: 8px 0 0;
  color: var(--text-sub);
}

.upload-shell-card {
  margin-top: 14px;
  border: 1px solid var(--line-soft);
  border-radius: 14px;
  background: rgba(255, 249, 239, 0.92);
  padding: 12px;
}

.upload-shell-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.upload-shell-meta {
  margin-top: 8px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--text-sub);
}

.upload-shell-track {
  margin-top: 10px;
  height: 8px;
  border-radius: 999px;
  overflow: hidden;
  background: #efdfc3;
}

.upload-shell-bar {
  height: 100%;
  background: linear-gradient(90deg, #c87c38, #d7a860);
}

.shell-close {
  border: none;
  background: transparent;
  color: var(--text-sub);
  cursor: pointer;
}

@media (max-width: 980px) {
  .shell {
    grid-template-columns: 1fr;
  }

  .left-nav {
    position: static;
    height: auto;
  }
}
</style>
