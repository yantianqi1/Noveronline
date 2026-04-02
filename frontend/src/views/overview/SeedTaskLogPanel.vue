<template>
  <aside class="task-log-panel">
    <header class="log-head">
      <div>
        <div class="panel-code mono">阶段一卷宗</div>
        <h2>{{ heading }}</h2>
      </div>
      <p>{{ description }}</p>
    </header>
    <SeedTaskStageCard
      :active-stage="activeStage"
      :task-status="taskStatus"
      :task-metrics="taskMetrics"
      :timeline="timeline"
      :started-at="taskStartedAt"
    />
    <SeedTaskLlmCard :llm-activity="llmActivity" :active-workers="taskMetrics.activeWorkers" />
    <SeedTaskTimeline :events="displayTimeline" :title="timelineTitle" :hint-text="timelineHint" />
  </aside>
</template>

<script setup>
import { computed } from "vue";

import SeedTaskLlmCard from "./SeedTaskLlmCard.vue";
import SeedTaskStageCard from "./SeedTaskStageCard.vue";
import SeedTaskTimeline from "./SeedTaskTimeline.vue";
import { buildIdleLogPreview } from "./seedUploadTaskView";

const props = defineProps({
  uploadPhase: { type: String, default: "idle" },
  taskStatus: { type: String, default: "" },
  activeStage: { type: Object, required: true },
  taskMetrics: { type: Object, required: true },
  llmActivity: { type: Object, required: true },
  timeline: { type: Array, required: true },
  taskStartedAt: { type: String, default: "" },
});

const displayTimeline = computed(() => (props.timeline.length ? props.timeline : buildIdleLogPreview()));
const heading = computed(() => {
  if (props.uploadPhase === "error" || props.taskStatus === "failed") return "阶段日志已中断";
  if (props.uploadPhase === "success" || props.taskStatus === "completed") return "阶段日志卷宗";
  if (props.uploadPhase === "idle") return "第一阶段工作流预览";
  return "第一阶段实时卷宗";
});
const description = computed(() => {
  if (props.uploadPhase === "idle") return "上传后，这里会持续记录每个阶段、每个分析块与当前引擎动作。";
  return "右栏会追踪当前动作、处理对象与结构化阶段进度。";
});
const timelineTitle = computed(() => (props.uploadPhase === "idle" ? "即将执行的流程" : "结构化阶段日志"));
const timelineHint = computed(() => (props.uploadPhase === "idle" ? "上传后自动切换为实时日志" : "默认贴底追踪最新事件"));
</script>

<style scoped>
.task-log-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-width: 0;
}

.log-head {
  padding: 4px 2px 0;
}

.panel-code,
.log-head p {
  color: var(--text-sub);
}

.panel-code {
  font-size: 11px;
  letter-spacing: 0.08em;
}

.log-head h2 {
  margin: 6px 0 0;
  font-size: 26px;
  font-family: "ZCOOL XiaoWei", serif;
}

.log-head p {
  margin: 8px 0 0;
  line-height: 1.6;
}

@media (max-width: 768px) {
  .log-head {
    position: sticky;
    top: 0;
    z-index: 1;
    background: linear-gradient(180deg, rgba(244, 239, 226, 0.98), rgba(244, 239, 226, 0.9));
    backdrop-filter: blur(10px);
  }
}
</style>
