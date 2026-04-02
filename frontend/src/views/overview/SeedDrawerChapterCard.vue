<template>
  <div class="chapter-card" @click="$emit('expand')">
    <span class="check-icon">✓</span>
    <span class="chapter-card-label">{{ chapter.label }}</span>
    <span class="chapter-card-stats mono">
      {{ chapter.stepCount }}个步骤 · {{ formattedElapsed }} · {{ chapter.llmCallCount }}次LLM调用
    </span>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  chapter: { type: Object, required: true },
});

defineEmits(["expand"]);

const formattedElapsed = computed(() => {
  const ms = props.chapter.elapsedMs;
  if (ms < 1000) return `${ms}ms`;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const min = Math.floor(sec / 60);
  const remainSec = Math.round(sec % 60);
  return `${min}m${remainSec}s`;
});
</script>

<style scoped>
.chapter-card {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-sm) var(--space-md);
  background: var(--bg-paper-warm, var(--bg-paper));
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: background 0.15s ease;
}

.chapter-card:hover {
  background: #fff;
}

.check-icon {
  color: var(--accent-green);
  font-size: 14px;
  flex-shrink: 0;
}

.chapter-card-label {
  font-family: "ZCOOL XiaoWei", serif;
  font-size: 14px;
  color: var(--text-main);
}

.chapter-card-stats {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-dim);
  white-space: nowrap;
}
</style>
