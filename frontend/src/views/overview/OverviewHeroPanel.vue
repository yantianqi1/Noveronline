<template>
  <section class="hero-panel workbench-card">
    <div class="hero-row">
      <div class="hero-left">
        <h1 class="title-ancient hero-title">总览</h1>
        <p v-if="!projects.length" class="hero-intro">上传一部小说，开始你的第一次分析。</p>
        <p v-else class="hero-intro">
          共 <strong class="mono">{{ projects.length }}</strong> 卷，焦点：<strong>{{ latestProjectName }}</strong>
        </p>
      </div>
      <div class="hero-pills">
        <span class="pill"><em class="mono">状态</em>{{ latestProjectStatus }}</span>
        <span class="pill"><em class="mono">阶段</em>{{ activeStageLabel || "等待启动" }}</span>
      </div>
    </div>

    <div class="hero-actions">
      <button class="btn primary" @click="$emit('start-new')">开始分析新小说</button>
      <button class="btn subtle" @click="$emit('refresh')">刷新</button>
    </div>

    <p v-if="errorMessage" class="hero-error mono">{{ errorMessage }}</p>
  </section>
</template>

<script setup>
import { computed } from "vue";

import { formatProjectStatus } from "../../utils/chineseDisplay";

const props = defineProps({
  projects: { type: Array, default: () => [] },
  uploadPhase: { type: String, default: "idle" },
  activeStageLabel: { type: String, default: "" },
  errorMessage: { type: String, default: "" },
});

defineEmits(["refresh", "start-new"]);

const latestProject = computed(() => props.projects[0] || null);
const latestProjectName = computed(() => latestProject.value?.name || "未命名卷宗");
const latestProjectStatus = computed(() =>
  latestProject.value ? formatProjectStatus(latestProject.value.status) : "等待投放小说",
);
</script>

<style scoped>
.hero-panel {
  padding: 16px 20px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 243, 236, 0.97)),
    radial-gradient(circle at 0% 0%, rgba(61, 90, 128, 0.08), transparent 36%);
}

.hero-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  flex-wrap: wrap;
}

.hero-title {
  font-size: 26px;
  line-height: 1.2;
  color: var(--bg-ink);
  margin: 0;
}

.hero-intro {
  margin: 4px 0 0;
  font-size: 14px;
  color: var(--text-sub);
}

.hero-pills {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 8px;
  border: 1px solid rgba(113, 128, 150, 0.16);
  background: rgba(255, 255, 255, 0.72);
  font-size: 14px;
  color: var(--text-main);
  white-space: nowrap;
}

.pill em {
  font-style: normal;
  font-size: 11px;
  color: var(--text-dim);
}

.hero-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
  flex-wrap: wrap;
}

.hero-error {
  margin-top: 8px;
  padding: 6px 12px;
  border-radius: 8px;
  background: rgba(229, 62, 62, 0.08);
  color: var(--accent-seal);
  font-size: 12px;
}

@media (max-width: 980px) {
  .hero-row {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
