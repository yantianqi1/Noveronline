<template>
  <section class="focus-card workbench-card">
    <div class="focus-top">
      <div>
        <div class="focus-code mono">当前任务焦点</div>
        <h2 class="title-ancient">{{ focusTitle }}</h2>
      </div>
      <span class="focus-status" :class="statusClass">{{ focusStatus }}</span>
    </div>

    <p class="focus-description">{{ focusDescription }}</p>

    <div class="focus-metrics">
      <div class="metric-box">
        <span class="mono">总进度</span>
        <strong>{{ stageProgress.percent }}%</strong>
      </div>
      <div class="metric-box">
        <span class="mono">当前阶段</span>
        <strong>{{ stageLabel }}</strong>
      </div>
      <div class="metric-box">
        <span class="mono">进程密度</span>
        <strong>{{ workloadLabel }}</strong>
      </div>
      <div class="metric-box">
        <span class="mono">阶段概况</span>
        <strong>{{ completedStageLabel }}</strong>
      </div>
    </div>

    <PipelineVisualization
      :upload-phase="uploadPhase"
      :task-status="taskStatus"
      :active-stage="activeStage"
      compact
    />

    <div class="focus-actions">
      <button class="btn primary" @click="$emit('start-new')">{{ primaryActionLabel }}</button>
      <button class="btn subtle" @click="$emit('open-drawer')">查看完整卷宗</button>
    </div>

    <p v-if="errorMessage" class="focus-error mono">{{ errorMessage }}</p>
  </section>
</template>

<script setup>
import { computed } from "vue";

import PipelineVisualization from "./PipelineVisualization.vue";
import { deriveStageProgress } from "./seedUploadTaskView.js";
import { buildFullPipelineNodes } from "./overviewWorkbenchState.js";

const props = defineProps({
  projectName: { type: String, default: "" },
  uploadPhase: { type: String, default: "idle" },
  taskStatus: { type: String, default: "" },
  activeStage: { type: Object, default: () => ({}) },
  taskMetrics: { type: Object, default: () => ({}) },
  timeline: { type: Array, default: () => [] },
  statusText: { type: String, default: "" },
  errorMessage: { type: String, default: "" },
});

defineEmits(["open-drawer", "start-new"]);

const hasActiveTask = computed(() => props.uploadPhase !== "idle");
const stageProgress = computed(() =>
  deriveStageProgress(props.activeStage, props.taskMetrics, props.timeline),
);
const pipelineNodes = computed(() =>
  buildFullPipelineNodes({
    uploadPhase: props.uploadPhase,
    taskStatus: props.taskStatus,
    activeStage: props.activeStage,
  }),
);
const completedStageCount = computed(() => pipelineNodes.value.filter((item) => item.state === "done").length);
const focusTitle = computed(() =>
  hasActiveTask.value
    ? props.projectName || "当前卷宗"
    : props.projectName || "暂无运行中的种子任务",
);
const focusStatus = computed(() => (hasActiveTask.value ? "运行中" : "待命"));
const statusClass = computed(() => (hasActiveTask.value ? "running" : "idle"));
const focusDescription = computed(() => {
  if (hasActiveTask.value) {
    return props.statusText || "后台正在推进当前卷宗的种子分析流程。";
  }
  return "首页只保留一张聚焦卡，把当前任务、阶段轨道和完整卷宗入口集中在同一视觉中心。";
});
const stageLabel = computed(() => props.activeStage?.label || "等待启动");
const workloadLabel = computed(() => {
  if (stageProgress.value.detail !== "-") {
    return stageProgress.value.detail;
  }
  if (props.taskMetrics.chapterCount) {
    return `${props.taskMetrics.chapterCount} 章`;
  }
  return hasActiveTask.value ? "准备分析" : "待开始";
});
const completedStageLabel = computed(() => `${completedStageCount.value}/${pipelineNodes.value.length} 阶段`);
const primaryActionLabel = computed(() => (hasActiveTask.value ? "展开新任务面板" : "启动新任务"));
</script>

<style scoped>
.focus-card {
  padding: var(--space-xl);
  background:
    linear-gradient(180deg, rgba(255, 251, 245, 0.98), rgba(247, 241, 231, 0.98)),
    radial-gradient(circle at 100% 0%, rgba(155, 44, 44, 0.09), transparent 34%);
  box-shadow: var(--shadow-lg);
}

.focus-top,
.focus-actions {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-md);
  flex-wrap: wrap;
}

.focus-code {
  color: var(--text-dim);
  font-size: 12px;
}

.focus-top h2 {
  margin-top: 6px;
  font-size: 34px;
  line-height: 1.2;
}

.focus-status {
  border-radius: 999px;
  padding: 8px 14px;
  font-size: 12px;
  background: rgba(113, 128, 150, 0.12);
  color: var(--text-sub);
}

.focus-status.running {
  background: rgba(155, 44, 44, 0.12);
  color: var(--accent-copper-deep);
}

.focus-description {
  margin: var(--space-md) 0 0;
  color: var(--text-sub);
  line-height: 1.8;
}

.focus-metrics {
  margin-top: var(--space-lg);
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-md);
}

.metric-box {
  border: 1px solid rgba(113, 128, 150, 0.16);
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.72);
  padding: 14px 16px;
}

.metric-box span {
  display: block;
  color: var(--text-dim);
  font-size: 11px;
}

.metric-box strong {
  display: block;
  margin-top: 6px;
  font-size: 20px;
  color: var(--text-main);
}

.focus-actions {
  margin-top: var(--space-lg);
}

.focus-error {
  margin: var(--space-md) 0 0;
  padding: var(--space-sm) var(--space-md);
  border-radius: 12px;
  background: rgba(229, 62, 62, 0.08);
  color: var(--accent-seal);
}

@media (max-width: 900px) {
  .focus-top h2 {
    font-size: 28px;
  }

  .focus-metrics {
    grid-template-columns: 1fr;
  }
}
</style>
