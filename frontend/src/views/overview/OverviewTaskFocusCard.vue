<template>
  <section class="focus-card workbench-card">
    <div class="focus-top">
      <div>
        <div class="focus-code mono">任务焦点</div>
        <h2 class="focus-title">{{ focusTitle }}</h2>
      </div>
      <span class="focus-status" :class="statusClass">{{ focusStatus }}</span>
    </div>

    <div v-if="hasActiveTask" class="focus-metrics">
      <div class="metric-box">
        <span class="mono">进度</span>
        <strong>{{ stageProgress.percent }}%</strong>
      </div>
      <div class="metric-box">
        <span class="mono">阶段</span>
        <strong>{{ stageLabel }}</strong>
      </div>
    </div>
    <p v-else class="focus-idle">{{ focusDescription }}</p>

    <PipelineVisualization
      v-if="hasActiveTask"
      :upload-phase="uploadPhase"
      :task-status="taskStatus"
      :active-stage="activeStage"
      compact
    />

    <p v-if="errorMessage" class="focus-error mono">{{ errorMessage }}</p>
  </section>
</template>

<script setup>
import { computed } from "vue";

import PipelineVisualization from "./PipelineVisualization.vue";
import { deriveStageProgress } from "./seedUploadTaskView.js";

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


const hasActiveTask = computed(() => props.uploadPhase !== "idle");
const stageProgress = computed(() =>
  deriveStageProgress(props.activeStage, props.taskMetrics, props.timeline),
);
const focusTitle = computed(() =>
  hasActiveTask.value
    ? props.projectName || "当前卷宗"
    : props.projectName || "暂无运行中的任务",
);
const focusStatus = computed(() => (hasActiveTask.value ? "运行中" : "待命"));
const statusClass = computed(() => (hasActiveTask.value ? "running" : "idle"));
const focusDescription = computed(() => {
  if (hasActiveTask.value) {
    return props.statusText || "后台正在推进分析流程。";
  }
  return "暂无进行中的分析任务。";
});
const stageLabel = computed(() => props.activeStage?.label || "等待启动");
</script>

<style scoped>
.focus-card {
  padding: 16px 20px;
  background:
    linear-gradient(180deg, rgba(255, 251, 245, 0.98), rgba(247, 241, 231, 0.98)),
    radial-gradient(circle at 100% 0%, rgba(155, 44, 44, 0.09), transparent 34%);
  box-shadow: var(--shadow-lg);
}

.focus-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.focus-code {
  color: var(--text-dim);
  font-size: 11px;
}

.focus-title {
  margin-top: 2px;
  font-size: 20px;
  font-family: "ZCOOL XiaoWei", serif;
  line-height: 1.3;
}

.focus-status {
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 11px;
  background: rgba(113, 128, 150, 0.12);
  color: var(--text-sub);
}

.focus-status.running {
  background: rgba(155, 44, 44, 0.12);
  color: var(--accent-copper-deep);
}

.focus-idle {
  margin: 8px 0 0;
  color: var(--text-sub);
  font-size: 13px;
}

.focus-metrics {
  margin-top: 10px;
  display: flex;
  gap: 8px;
}

.metric-box {
  flex: 1;
  border: 1px solid rgba(113, 128, 150, 0.16);
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.72);
  padding: 8px 12px;
}

.metric-box span {
  display: block;
  color: var(--text-dim);
  font-size: 10px;
}

.metric-box strong {
  display: block;
  margin-top: 2px;
  font-size: 16px;
  color: var(--text-main);
}

.focus-error {
  margin: 8px 0 0;
  padding: 6px 12px;
  border-radius: 8px;
  background: rgba(229, 62, 62, 0.08);
  color: var(--accent-seal);
  font-size: 12px;
}
</style>
