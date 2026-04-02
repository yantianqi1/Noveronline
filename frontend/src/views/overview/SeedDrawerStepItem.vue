<template>
  <div :class="['step-item', { active: step.status === 'active', expanded: !collapsed }]">
    <div class="step-header" @click="$emit('toggle')">
      <span v-if="step.status === 'active'" class="pulse-dot"></span>
      <span v-else class="step-dot"></span>
      <span class="step-title">{{ step.title }}</span>
      <span v-if="step.status === 'completed'" class="step-meta mono">
        <span v-if="step.elapsedMs">{{ formatMs(step.elapsedMs) }}</span>
        <span v-if="step.llmCallCount" class="call-badge">{{ step.llmCallCount }}次</span>
      </span>
      <span class="toggle-icon">{{ collapsed ? '▸' : '▾' }}</span>
    </div>
    <Transition name="step-expand">
      <div v-if="!collapsed" class="step-body">
        <SeedDrawerStepDetail :task-id="taskId" :step="step" />
      </div>
    </Transition>
  </div>
</template>

<script setup>
import SeedDrawerStepDetail from "./SeedDrawerStepDetail.vue";

defineProps({
  step: { type: Object, required: true },
  taskId: { type: String, default: "" },
  collapsed: { type: Boolean, default: true },
});

defineEmits(["toggle"]);

function formatMs(ms) {
  if (ms < 1000) return `${ms}ms`;
  const sec = ms / 1000;
  return sec < 60 ? `${sec.toFixed(1)}s` : `${Math.floor(sec / 60)}m${Math.round(sec % 60)}s`;
}
</script>

<style scoped>
.step-item {
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-sm);
  background: #fff;
  overflow: hidden;
  transition: border-color 0.2s ease;
}

.step-item.active {
  border-color: var(--accent-copper);
}

.step-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  cursor: pointer;
  user-select: none;
}

.step-header:hover {
  background: var(--bg-paper);
}

.step-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent-green);
  flex-shrink: 0;
}

.pulse-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent-copper);
  flex-shrink: 0;
  animation: pulse-step 1.5s ease-in-out infinite;
}

@keyframes pulse-step {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.step-title {
  font-size: 13px;
  color: var(--text-main);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.step-meta {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  font-size: 11px;
  color: var(--text-dim);
  flex-shrink: 0;
}

.call-badge {
  background: rgba(176, 125, 75, 0.1);
  color: var(--accent-copper);
  padding: 1px 6px;
  border-radius: var(--radius-full);
  font-size: 10px;
}

.toggle-icon {
  font-family: monospace;
  font-size: 12px;
  color: var(--text-dim);
  flex-shrink: 0;
}

.step-body {
  border-top: 1px solid var(--line-soft);
  padding: var(--space-md);
}

/* Expand animation */
.step-expand-enter-active {
  transition: all 0.25s ease-out;
  max-height: 600px;
  overflow: hidden;
}
.step-expand-leave-active {
  transition: all 0.25s ease-in;
  max-height: 600px;
  overflow: hidden;
}
.step-expand-enter-from {
  opacity: 0;
  max-height: 0;
}
.step-expand-leave-to {
  opacity: 0;
  max-height: 0;
}

@media (prefers-reduced-motion: reduce) {
  .pulse-dot {
    animation: none;
  }
  .step-expand-enter-active,
  .step-expand-leave-active {
    transition: opacity 0.15s ease;
    max-height: none !important;
  }
}
</style>
