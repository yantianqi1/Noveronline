<template>
  <section class="log-card stage-card">
    <div class="stage-top">
      <div>
        <div class="section-code mono">当前阶段</div>
        <h3>{{ activeStage.label || "等待上传" }}</h3>
      </div>
      <span class="stage-status mono" :class="statusClass">{{ statusText }}</span>
    </div>
    <div class="stage-metrics">
      <div class="metric-box">
        <span class="metric-label mono">进度</span>
        <strong>{{ activeStage.progress || 0 }}%</strong>
      </div>
      <div class="metric-box">
        <span class="metric-label mono">耗时</span>
        <strong>{{ elapsedText }}</strong>
      </div>
      <div class="metric-box">
        <span class="metric-label mono">分析块</span>
        <strong>{{ blockSummary }}</strong>
      </div>
      <div class="metric-box">
        <span class="metric-label mono">章节数</span>
        <strong>{{ chapterSummary }}</strong>
      </div>
    </div>
    <div class="stage-track">
      <div class="stage-bar" :style="{ width: `${activeStage.progress || 0}%` }"></div>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { formatElapsedDuration } from "./seedUploadTaskView";
import { formatTaskStageStatus } from "../../utils/chineseDisplay";

const props = defineProps({
  activeStage: { type: Object, required: true },
  taskStatus: { type: String, default: "" },
  taskMetrics: { type: Object, required: true },
  startedAt: { type: String, default: "" },
});

const now = ref(Date.now());
let timerId = 0;

const resolvedStatus = computed(() => {
  if (props.activeStage.status === "failed" || props.taskStatus === "failed") return "failed";
  if (props.activeStage.status === "completed" || props.taskStatus === "completed") return "completed";
  if (props.activeStage.status === "processing" || props.taskStatus === "processing") return "processing";
  return "pending";
});
const statusText = computed(() => formatTaskStageStatus(resolvedStatus.value));
const statusClass = computed(() => {
  if (resolvedStatus.value === "processing") return "running";
  if (resolvedStatus.value === "completed") return "done";
  return resolvedStatus.value;
});
const elapsedText = computed(() => formatElapsedDuration(props.startedAt, now.value));
const blockSummary = computed(() => {
  if (!props.taskMetrics.totalBlocks) return "-";
  return `${props.taskMetrics.completedBlocks}/${props.taskMetrics.totalBlocks}`;
});
const chapterSummary = computed(() => (props.taskMetrics.chapterCount ? String(props.taskMetrics.chapterCount) : "-"));

onMounted(() => {
  timerId = window.setInterval(() => {
    now.value = Date.now();
  }, 1000);
});

onBeforeUnmount(() => {
  window.clearInterval(timerId);
});
</script>

<style scoped>
.log-card {
  border: 1px solid var(--line-soft);
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(255, 251, 242, 0.98), rgba(255, 247, 233, 0.98));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
  padding: 14px;
}

.stage-top,
.stage-metrics {
  display: flex;
  gap: 10px;
}

.stage-top {
  align-items: flex-start;
  justify-content: space-between;
}

.stage-top h3 {
  margin: 4px 0 0;
  font-size: 20px;
  font-family: "ZCOOL XiaoWei", serif;
}

.section-code,
.metric-label {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--text-sub);
}

.stage-status {
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 11px;
}

.stage-status.running {
  background: rgba(143, 79, 31, 0.12);
  color: var(--accent-copper);
}

.stage-status.done {
  background: rgba(56, 106, 79, 0.14);
  color: var(--accent-green);
}

.stage-status.failed {
  background: rgba(155, 67, 38, 0.14);
  color: #9b4326;
}

.stage-status.pending {
  background: rgba(39, 90, 120, 0.1);
  color: var(--accent-blue);
}

.stage-metrics {
  margin-top: 14px;
  flex-wrap: wrap;
}

.metric-box {
  min-width: 120px;
  flex: 1 1 120px;
  border: 1px solid rgba(159, 141, 106, 0.35);
  border-radius: 12px;
  background: rgba(255, 252, 245, 0.8);
  padding: 10px 12px;
}

.metric-box strong {
  display: block;
  margin-top: 6px;
  font-size: 18px;
}

.stage-track {
  margin-top: 14px;
  height: 9px;
  border-radius: 999px;
  overflow: hidden;
  background: #eddcbd;
}

.stage-bar {
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #9a5824 0%, #d2a25e 58%, #ebd7b0 100%);
  transition: width 180ms ease;
}
</style>
