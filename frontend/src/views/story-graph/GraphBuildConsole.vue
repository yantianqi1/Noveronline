<template>
  <section class="build-console workbench-card" :class="{ failed: hasFailed }">
    <header class="console-head">
      <div class="head-main">
        <span class="head-icon">{{ headIcon }}</span>
        <div>
          <div class="head-title">{{ headTitle }}</div>
          <div class="head-sub">{{ headSub }}</div>
        </div>
      </div>
      <div class="head-meta mono">
        <span>已用时 {{ totalElapsedLabel }}</span>
        <span>{{ progressValue }}%</span>
      </div>
    </header>

    <div class="progress-track">
      <div class="progress-fill" :style="{ width: progressValue + '%' }"></div>
    </div>

    <div v-if="currentStage" class="current-stage">
      <div class="stage-headline">
        <span class="stage-icon">{{ currentMeta.icon }}</span>
        <span class="stage-title">{{ currentMeta.title }}</span>
        <span class="stage-counts mono">{{ currentCountsLabel }}</span>
      </div>
      <div v-if="currentMeta.description" class="stage-desc">{{ currentMeta.description }}</div>
      <div v-if="currentSampleLabels.length" class="stage-samples">
        <span class="sample-prefix">示例：</span>
        <span v-for="(item, idx) in currentSampleLabels" :key="idx" class="sample-chip">{{ item }}</span>
      </div>
    </div>

    <ol class="stage-timeline">
      <li
        v-for="entry in timelineEntries"
        :key="entry.key"
        class="timeline-item"
        :class="entry.statusClass"
      >
        <span class="dot">{{ entry.dot }}</span>
        <span class="title">{{ entry.title }}</span>
        <span class="meta mono">{{ entry.meta }}</span>
      </li>
    </ol>

    <div v-if="hasFailed" class="failure-box">
      <div class="failure-summary">
        ⚠ 出错于「{{ failedAfterLabel }}」：{{ failedEvent.error_summary || "构建失败" }}
      </div>
      <div class="failure-actions">
        <n-button size="small" @click="showTrace = !showTrace">
          {{ showTrace ? "收起堆栈" : "展开堆栈" }}
        </n-button>
        <n-button size="small" type="primary" @click="$emit('retry')">重试构建</n-button>
      </div>
      <pre v-if="showTrace" class="trace mono">{{ failedEvent.traceback || "" }}</pre>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from "vue";
import { NButton } from "naive-ui";
import {
  BUILD_STAGE_ORDER,
  describeStage,
  formatCounts,
  formatElapsed,
} from "./buildStageMeta.js";

const props = defineProps({
  task: { type: Object, default: () => null },
});

defineEmits(["retry"]);

const showTrace = ref(false);

const stages = computed(() => {
  const meta = props.task?.metadata || {};
  return Array.isArray(meta.stages) ? meta.stages : [];
});

const failedEvent = computed(
  () => stages.value.slice().reverse().find((e) => e.stage === "failed") || null
);

const hasFailed = computed(
  () => failedEvent.value !== null || props.task?.status === "failed"
);

const lastSuccessfulStage = computed(() => {
  const list = stages.value.filter((e) => e.stage !== "failed");
  return list.length ? list[list.length - 1] : null;
});

const currentStage = computed(() => lastSuccessfulStage.value);

const currentMeta = computed(() =>
  describeStage(currentStage.value?.stage || "")
);

const currentCountsLabel = computed(() =>
  formatCounts(currentStage.value?.counts || {})
);

const currentSampleLabels = computed(() => {
  const sample = currentStage.value?.sample || [];
  return sample
    .map((item) => {
      if (item == null) return "";
      if (typeof item === "string") return item;
      if (typeof item === "object") {
        if (item.name) {
          const aliases = Array.isArray(item.aliases) && item.aliases.length
            ? `（${item.aliases.join("、")}）`
            : "";
          return `${item.name}${aliases}`;
        }
        if (item.fact) return item.fact;
      }
      return String(item);
    })
    .filter(Boolean)
    .slice(0, 3);
});

const progressValue = computed(() => {
  if (hasFailed.value) {
    return Math.min(100, currentStage.value?.progress || 0);
  }
  if (props.task?.status === "completed") return 100;
  return Math.max(0, Math.min(100, currentStage.value?.progress || props.task?.progress || 0));
});

const totalElapsedLabel = computed(() => {
  const last = stages.value.length ? stages.value[stages.value.length - 1] : null;
  return formatElapsed(last?.elapsed_ms || 0);
});

const headIcon = computed(() => {
  if (hasFailed.value) return "⚠";
  if (props.task?.status === "completed") return "✅";
  return "⚙";
});

const headTitle = computed(() => {
  if (hasFailed.value) return "图谱构建中断";
  if (props.task?.status === "completed") return "图谱构建完成";
  return "图谱构建中…";
});

const headSub = computed(() => {
  if (currentStage.value) {
    return `当前阶段：${describeStage(currentStage.value.stage).title}`;
  }
  return "正在准备…";
});

const failedAfterLabel = computed(() => {
  const after = failedEvent.value?.failed_after || lastSuccessfulStage.value?.stage || "";
  return describeStage(after).title;
});

const timelineEntries = computed(() => {
  const eventByStage = {};
  for (const evt of stages.value) {
    if (evt.stage === "failed") continue;
    eventByStage[evt.stage] = evt;
  }
  const currentKey = currentStage.value?.stage || "";
  let reachedCurrent = false;
  return BUILD_STAGE_ORDER.map((key) => {
    const meta = describeStage(key);
    const evt = eventByStage[key];
    let statusClass;
    let dot;
    if (evt) {
      const isCurrent = key === currentKey && !(evt.progress >= 100);
      if (isCurrent) {
        statusClass = "stage-current";
        dot = "▶";
        reachedCurrent = true;
      } else {
        statusClass = "stage-done";
        dot = "✓";
      }
    } else if (!reachedCurrent && hasFailed.value && failedEvent.value?.failed_after === key) {
      statusClass = "stage-failed";
      dot = "✕";
    } else {
      statusClass = "stage-pending";
      dot = "◯";
    }
    return {
      key,
      title: meta.title,
      dot,
      statusClass,
      meta: evt
        ? `${formatElapsed(evt.elapsed_ms || 0)}　${formatCounts(evt.counts || {})}`
        : "—",
    };
  });
});
</script>

<style scoped>
.build-console {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 18px;
  border: 1px solid var(--line-soft);
  border-radius: 10px;
  background: linear-gradient(180deg, #fffaf2 0%, #fdf6e7 100%);
}

.build-console.failed {
  background: linear-gradient(180deg, #fff7f4 0%, #ffeae3 100%);
  border-color: rgba(155, 67, 38, 0.4);
}

.console-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.head-main {
  display: flex;
  align-items: center;
  gap: 10px;
}

.head-icon {
  font-size: 22px;
}

.head-title {
  font-size: 15px;
  font-weight: 600;
  color: #4a3a22;
}

.head-sub {
  font-size: 12px;
  color: #8a785a;
}

.head-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #6b5a3c;
}

.progress-track {
  position: relative;
  height: 6px;
  background: rgba(120, 90, 50, 0.12);
  border-radius: 3px;
  overflow: hidden;
}

.progress-fill {
  position: absolute;
  top: 0;
  left: 0;
  bottom: 0;
  background: linear-gradient(90deg, #c98a3b, #e0a857);
  transition: width 0.4s ease;
}

.current-stage {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 10px;
  background: #fffdf6;
  border: 1px dashed rgba(184, 138, 71, 0.4);
  border-radius: 6px;
}

.stage-headline {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.stage-icon {
  font-size: 16px;
}

.stage-title {
  font-weight: 600;
  color: #4a3a22;
}

.stage-counts {
  margin-left: auto;
  font-size: 11.5px;
  color: #8a785a;
}

.stage-desc {
  font-size: 12px;
  color: #6b5a3c;
}

.stage-samples {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #5a4a30;
}

.sample-prefix {
  color: #9a8b6f;
}

.sample-chip {
  padding: 1px 8px;
  background: rgba(201, 138, 59, 0.12);
  border-radius: 10px;
}

.stage-timeline {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 4px 12px;
}

.timeline-item {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
  padding: 2px 0;
  color: #8a785a;
}

.timeline-item .dot {
  width: 14px;
  text-align: center;
}

.timeline-item.stage-done {
  color: #4a6b3a;
}

.timeline-item.stage-current {
  color: #c98a3b;
  font-weight: 600;
  animation: pulse-current 1.6s infinite;
}

.timeline-item.stage-failed {
  color: var(--accent-seal, #9b4326);
  font-weight: 600;
}

.timeline-item .title {
  flex-shrink: 0;
}

.timeline-item .meta {
  margin-left: auto;
  font-size: 11px;
  opacity: 0.85;
}

@keyframes pulse-current {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.55; }
}

.failure-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  background: #fff;
  border: 1px solid rgba(155, 67, 38, 0.3);
  border-radius: 6px;
}

.failure-summary {
  font-size: 13px;
  color: var(--accent-seal, #9b4326);
}

.failure-actions {
  display: flex;
  gap: 8px;
}

.trace {
  max-height: 200px;
  overflow: auto;
  font-size: 11px;
  background: #fcf6ec;
  padding: 8px;
  border-radius: 4px;
  white-space: pre-wrap;
  color: #564a36;
}

.mono {
  font-family: "Courier New", monospace;
}
</style>
