<template>
  <section v-if="task" class="panel-section auto-section">
    <div class="section-head">
      <div>
        <p class="section-index mono">03 / 自动演化</p>
        <h3 class="section-title">当前世界自动推进</h3>
      </div>
      <p class="section-copy">SSE 流式推进后，候选事件会出现在右侧导演台等待审核。</p>
    </div>

    <article class="task-card" :class="task.status || 'idle'">
      <div class="task-head">
        <strong>{{ task.branch_title || "当前世界" }}</strong>
        <span class="mono task-status-label">{{ resolveStatusLabel(task.status) }}</span>
      </div>
      <div class="progress-row">
        <div class="progress-track">
          <div class="progress-fill" :class="{ pulsing: isStreaming }" :style="{ width: `${task.progress || 0}%` }"></div>
        </div>
        <span class="mono">{{ task.progress || 0 }}%</span>
      </div>
      <p class="task-copy">{{ task.error || task.message || "等待任务状态..." }}</p>
      <p v-if="task.stop_reason" class="task-foot mono">stop: {{ task.stop_reason }}</p>
    </article>
  </section>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  task: { type: Object, default: null },
});

const isStreaming = computed(() => {
  const status = props.task?.status;
  return status === "pending" || status === "processing";
});

function resolveStatusLabel(status = "") {
  const labels = {
    idle: "待命",
    pending: "连接中",
    processing: "演化中",
    completed: "已完成",
    failed: "失败",
  };
  return labels[status] || "处理中";
}
</script>

<style scoped>
.auto-section {
  gap: 14px;
}

.task-card {
  border: 1px solid var(--line-soft);
  border-radius: 14px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.92);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.task-card.processing {
  border-color: rgba(176, 125, 75, 0.32);
}

.task-card.completed {
  border-color: rgba(61, 90, 128, 0.22);
}

.task-card.failed {
  border-color: rgba(155, 67, 38, 0.24);
}

.task-head,
.progress-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.task-status-label {
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(245, 230, 200, 0.85);
  color: #724e1f;
  font-size: 0.82rem;
}

.task-meta,
.task-copy,
.task-foot {
  margin: 0;
  color: var(--text-sub);
}

.progress-track {
  flex: 1;
  height: 8px;
  border-radius: 999px;
  background: rgba(176, 125, 75, 0.14);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #c9954a 0%, #8f6e41 100%);
  transition: width 0.4s ease;
}

.progress-fill.pulsing {
  animation: bar-pulse 1.8s ease-in-out infinite;
}

@keyframes bar-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}
</style>
