<template>
  <div ref="scrollRef" class="drawer-chat-content">
    <div v-for="chapter in chapters" :key="chapter.key" class="chapter-section">
      <!-- Completed chapter: collapsed summary card -->
      <template v-if="chapter.status === 'completed' && isChapterCollapsed(chapter.key)">
        <SeedDrawerChapterCard
          :chapter="chapter"
          @expand="collapse.expandChapter(chapter.key)"
        />
      </template>

      <!-- Active or expanded chapter -->
      <template v-else-if="chapter.status !== 'pending'">
        <div class="chapter-header">
          <span class="chapter-label-inline">{{ chapter.label }}</span>
          <button
            v-if="chapter.status === 'completed'"
            class="btn-collapse"
            @click="collapse.collapseChapter(chapter.key)"
          >
            收起
          </button>
        </div>
        <TransitionGroup name="step-list" tag="div" class="step-list">
          <SeedDrawerStepItem
            v-for="step in chapter.steps"
            :key="step.stepId"
            :step="step"
            :task-id="taskId"
            :collapsed="isStepCollapsed(step.stepId)"
            @toggle="handleStepToggle(step.stepId)"
          />
        </TransitionGroup>
      </template>

      <!-- Pending chapter: dimmed header -->
      <template v-else>
        <div class="chapter-header pending">
          <span class="chapter-label-inline">{{ chapter.label }}</span>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from "vue";
import SeedDrawerChapterCard from "./SeedDrawerChapterCard.vue";
import SeedDrawerStepItem from "./SeedDrawerStepItem.vue";

const props = defineProps({
  taskId: { type: String, default: "" },
  chapters: { type: Array, default: () => [] },
  activeStageKey: { type: String, default: "" },
  collapse: { type: Object, required: true },
});

const scrollRef = ref(null);

function isChapterCollapsed(chapterKey) {
  return props.collapse.isChapterCollapsed(chapterKey);
}

function isStepCollapsed(stepId) {
  return props.collapse.isStepCollapsed(stepId);
}

function handleStepToggle(stepId) {
  if (props.collapse.isStepCollapsed(stepId)) {
    props.collapse.expandStep(stepId);
  } else {
    props.collapse.collapseStep(stepId);
  }
}

// Auto-scroll to bottom when new steps appear
watch(
  () => props.chapters.reduce((n, ch) => n + ch.steps.length, 0),
  async () => {
    await nextTick();
    if (scrollRef.value) {
      scrollRef.value.scrollTop = scrollRef.value.scrollHeight;
    }
  },
);
</script>

<style scoped>
.drawer-chat-content {
  flex: 1;
  overflow-y: auto;
  padding: var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-lg);
}

.chapter-section {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.chapter-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--space-xs) 0;
}

.chapter-header.pending {
  opacity: 0.4;
}

.chapter-label-inline {
  font-family: "ZCOOL XiaoWei", serif;
  font-size: 14px;
  color: var(--text-sub);
}

.btn-collapse {
  border: none;
  background: transparent;
  font-size: 12px;
  color: var(--text-dim);
  cursor: pointer;
}

.btn-collapse:hover {
  color: var(--accent-copper);
}

.step-list {
  display: flex;
  flex-direction: column;
  gap: var(--space-xs);
}

/* Step list transition */
.step-list-enter-active {
  transition: all 0.25s ease-out;
}
.step-list-leave-active {
  transition: all 0.25s ease-in;
}
.step-list-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.step-list-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

@media (prefers-reduced-motion: reduce) {
  .step-list-enter-from,
  .step-list-leave-to {
    transform: none;
  }
}
</style>
