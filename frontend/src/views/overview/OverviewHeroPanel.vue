<template>
  <div class="hero-container stack">
    <div class="hero-content">
      <div class="hero-text stack">
        <h1 class="title-ancient hero-title">开启小说分析之门</h1>
        <p class="hero-description">
          {{ heroIntro }}
          <span v-if="projects.length" class="project-summary">
            目前已收录 <strong class="mono">{{ projects.length }}</strong> 卷小说，
            最近正在推演 <strong class="accent-text">「{{ latestProjectName }}」</strong>。
          </span>
        </p>
        <div class="hero-actions">
          <button class="btn primary hero-btn" @click="$emit('start-new')">开始分析新小说</button>
          <button class="btn subtle" @click="$emit('refresh')">刷新状态</button>
        </div>
      </div>
      
      <div class="hero-status-card workbench-card">
        <div class="status-header">
          <span class="status-dot" :class="statusClass"></span>
          <span class="status-label">{{ latestProjectStatus }}</span>
        </div>
        <div class="status-body">
          <p class="status-note">{{ overviewNote }}</p>
        </div>
        <div v-if="errorMessage" class="status-error mono">{{ errorMessage }}</div>
      </div>
    </div>
  </div>
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
const latestProjectName = computed(() => latestProject.value?.name || "未知项目");
const statusClass = computed(() => {
  if (!latestProject.value) return 'idle';
  if (latestProject.value.status === 'failed') return 'danger';
  return latestProject.value.status?.includes('completed') ? 'ok' : 'warn';
});

const latestProjectStatus = computed(() =>
  latestProject.value ? formatProjectStatus(latestProject.value.status) : "等待投放小说",
);

const heroIntro = computed(() => {
  if (!props.projects.length) {
    return "欢迎来到 MiroFish-Novel 工作台。在这里，您可以利用 AI 力量，将长篇小说自动解构成结构化的故事图谱与持续演化的世界线。";
  }
  return "小说创作与分析是一个持续进化的过程。您可以随时投放新作品，或继续深入已有的分析卷宗。";
});

const overviewNote = computed(() => {
  if (props.uploadPhase === "processing") {
    return `后台管线正在全力运转，当前阶段：${props.activeStageLabel || "准备中"}。`;
  }
  if (!latestProject.value) {
    return "点击左侧按钮，投放您的第一部小说文本。";
  }
  if (!latestProject.value.ontology && latestProject.value.status === "seed_processing") {
    return "种子分析仍在持续。完成后，角色的关系网络与核心设定将自动呈现。";
  }
  if (!latestProject.value.graph_id) {
    return "初步分析已就绪。建议前往「档案库」或「故事图谱」查看分析结果。";
  }
  return "分析已趋完备。现在可以进入「世界线工作台」继续推进当前世界并与角色对话。";
});
</script>

<style scoped>
.hero-container {
  padding: var(--space-xl) 0;
}

.hero-content {
  display: grid;
  grid-template-columns: 1.2fr 0.8fr;
  gap: var(--space-xl);
  align-items: center;
}

.hero-title {
  font-size: 48px;
  color: var(--bg-ink);
  line-height: 1.2;
}

.hero-description {
  font-size: 18px;
  color: var(--text-sub);
  line-height: 1.8;
  max-width: 600px;
}

.project-summary {
  display: block;
  margin-top: var(--space-md);
  color: var(--text-main);
}

.accent-text {
  color: var(--accent-copper-deep);
}

.hero-actions {
  display: flex;
  gap: var(--space-md);
  margin-top: var(--space-lg);
}

.hero-btn {
  padding: 14px 32px;
  font-size: 16px;
}

.hero-status-card {
  padding: var(--space-lg);
  background: var(--bg-paper-warm);
  border-style: dashed;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.status-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  font-weight: 600;
  color: var(--text-main);
  font-size: 15px;
}

.status-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--text-dim);
}

.status-dot.ok { background: var(--accent-green); box-shadow: 0 0 8px var(--accent-green); }
.status-dot.warn { background: var(--accent-copper); box-shadow: 0 0 8px var(--accent-copper); }
.status-dot.danger { background: var(--accent-seal); box-shadow: 0 0 8px var(--accent-seal); }
.status-dot.idle { background: var(--line-strong); }

.status-note {
  font-size: 14px;
  color: var(--text-sub);
  line-height: 1.6;
}

.status-error {
  font-size: 12px;
  color: var(--accent-seal);
  background: rgba(155, 67, 38, 0.05);
  padding: var(--space-sm);
  border-radius: var(--radius-sm);
}

@media (max-width: 980px) {
  .hero-content {
    grid-template-columns: 1fr;
  }
  .hero-title {
    font-size: 36px;
  }
}
</style>
