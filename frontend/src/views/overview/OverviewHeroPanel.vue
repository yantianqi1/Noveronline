<template>
  <section class="hero-panel workbench-card">
    <div class="hero-code mono">总览指挥台</div>
    <h1 class="title-ancient hero-title">让当前任务成为首页中心</h1>
    <p class="hero-description">
      {{ heroIntro }}
      <span v-if="projects.length" class="project-summary">
        当前共收录 <strong class="mono">{{ projects.length }}</strong> 卷，
        最近焦点卷宗是 <strong>「{{ latestProjectName }}」</strong>。
      </span>
    </p>

    <div class="hero-strip">
      <div class="hero-pill">
        <span class="mono">最新状态</span>
        <strong>{{ latestProjectStatus }}</strong>
      </div>
      <div class="hero-pill">
        <span class="mono">当前阶段</span>
        <strong>{{ activeStageLabel || "等待启动" }}</strong>
      </div>
      <div class="hero-pill">
        <span class="mono">导语</span>
        <strong>{{ overviewNote }}</strong>
      </div>
    </div>

    <div class="hero-actions">
      <button class="btn primary" @click="$emit('start-new')">开始分析新小说</button>
      <button class="btn subtle" @click="$emit('refresh')">刷新状态</button>
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
const heroIntro = computed(() => {
  if (!props.projects.length) {
    return "总览页不再平铺全部流程，而是先把最重要的入口、状态和当前任务聚合到同一块。";
  }
  return "把当前工作进度、最近卷宗和下一步入口收束到一屏之内，避免首页继续被横向摊平。";
});
const overviewNote = computed(() => {
  if (props.uploadPhase === "processing") {
    return "后台正在推进";
  }
  if (!latestProject.value) {
    return "可直接投放第一份文本";
  }
  if (!latestProject.value.graph_id) {
    return "优先消费档案与图谱";
  }
  return "可继续转入世界线与写作台";
});
</script>

<style scoped>
.hero-panel {
  padding: var(--space-xl);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 243, 236, 0.97)),
    radial-gradient(circle at 0% 0%, rgba(61, 90, 128, 0.08), transparent 36%);
}

.hero-code,
.hero-error {
  color: var(--text-dim);
  font-size: 12px;
}

.hero-title {
  margin-top: 10px;
  font-size: 42px;
  line-height: 1.15;
  color: var(--bg-ink);
}

.hero-description {
  margin: var(--space-md) 0 0;
  font-size: 17px;
  color: var(--text-sub);
  line-height: 1.8;
}

.project-summary {
  display: block;
  margin-top: var(--space-sm);
  color: var(--text-main);
}

.hero-strip {
  margin-top: var(--space-lg);
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--space-md);
}

.hero-pill {
  min-height: 96px;
  border-radius: 16px;
  border: 1px solid rgba(113, 128, 150, 0.16);
  background: rgba(255, 255, 255, 0.72);
  padding: 14px 16px;
}

.hero-pill span {
  display: block;
  font-size: 11px;
  color: var(--text-dim);
}

.hero-pill strong {
  display: block;
  margin-top: 8px;
  font-size: 18px;
  line-height: 1.5;
  color: var(--text-main);
}

.hero-actions {
  display: flex;
  gap: var(--space-md);
  margin-top: var(--space-lg);
  flex-wrap: wrap;
}

.hero-error {
  margin-top: var(--space-md);
  padding: var(--space-sm) var(--space-md);
  border-radius: 12px;
  background: rgba(229, 62, 62, 0.08);
  color: var(--accent-seal);
}

@media (max-width: 980px) {
  .hero-title {
    font-size: 34px;
  }

  .hero-strip {
    grid-template-columns: 1fr;
  }
}
</style>
