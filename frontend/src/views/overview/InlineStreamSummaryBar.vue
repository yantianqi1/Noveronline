<template>
  <header class="stream-summary-bar">
    <Transition name="summary-fade" mode="out-in">
      <div :key="currentChapter.key" class="summary-content">
        <span class="chapter-label">{{ currentChapter.label }}</span>
        <div class="summary-progress">
          <div class="progress-track-mini">
            <div class="progress-fill-mini" :style="{ width: progressPercent + '%' }"></div>
          </div>
        </div>
        <span class="summary-metric mono">{{ completedSteps }}/{{ totalSteps }} 步骤</span>
        <span class="summary-metric mono">{{ formattedElapsed }}</span>
        <span class="summary-metric mono">{{ currentChapter.llmCallCount }}次LLM</span>
      </div>
    </Transition>
  </header>
</template>

<script setup>
import { computed } from "vue";
import { STAGE_TO_CHAPTER } from "./seedPipelineChapters.js";

const props = defineProps({
  chapters: { type: Array, default: () => [] },
  activeStageKey: { type: String, default: "" },
});

const currentChapterKey = computed(() => STAGE_TO_CHAPTER[props.activeStageKey] || "text_prep");

const currentChapter = computed(() => {
  return props.chapters.find((c) => c.key === currentChapterKey.value) || {
    key: "text_prep",
    label: "文本准备",
    steps: [],
    stepCount: 0,
    elapsedMs: 0,
    llmCallCount: 0,
  };
});

const totalSteps = computed(() => currentChapter.value.stepCount);
const completedSteps = computed(() =>
  currentChapter.value.steps.filter((s) => s.status === "completed").length,
);

const progressPercent = computed(() => {
  if (totalSteps.value === 0) return 0;
  return Math.round((completedSteps.value / totalSteps.value) * 100);
});

const formattedElapsed = computed(() => {
  const ms = currentChapter.value.elapsedMs;
  if (ms < 1000) return `${ms}ms`;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const min = Math.floor(sec / 60);
  const remainSec = Math.round(sec % 60);
  return `${min}m${remainSec}s`;
});
</script>

<style scoped>
.stream-summary-bar {
  border-bottom: 1px solid var(--line-soft);
  padding-bottom: var(--space-sm);
  margin-bottom: var(--space-xs);
}

.summary-content {
  display: flex;
  align-items: center;
  gap: var(--space-md);
  min-height: 28px;
  flex-wrap: wrap;
}

.chapter-label {
  font-family: "ZCOOL XiaoWei", serif;
  font-size: 15px;
  color: var(--text-main);
  white-space: nowrap;
}

.summary-progress {
  flex: 1;
  min-width: 60px;
}

.progress-track-mini {
  height: 4px;
  background: var(--bg-paper);
  border-radius: 2px;
  overflow: hidden;
}

.progress-fill-mini {
  height: 100%;
  background: var(--accent-copper);
  transition: width 0.3s ease;
  border-radius: 2px;
}

.summary-metric {
  font-size: 11px;
  color: var(--text-dim);
  white-space: nowrap;
}

.summary-fade-enter-active,
.summary-fade-leave-active {
  transition: opacity 0.2s ease;
}
.summary-fade-enter-from,
.summary-fade-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .progress-fill-mini {
    transition: none;
  }
}
</style>
