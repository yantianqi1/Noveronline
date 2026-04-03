<template>
  <div ref="containerRef" class="stream-chat-content">
    <div v-for="chapter in chapters" :key="chapter.key" class="chapter-section">
      <!-- Completed chapter: collapsed summary card -->
      <Transition name="chapter-collapse">
        <template v-if="chapter.status === 'completed' && isChapterCollapsed(chapter.key)">
          <SeedDrawerChapterCard
            :chapter="chapter"
            @expand="collapse.expandChapter(chapter.key)"
          />
        </template>
      </Transition>

      <!-- Active or expanded chapter -->
      <template v-if="chapter.status !== 'pending' && !(chapter.status === 'completed' && isChapterCollapsed(chapter.key))">
        <div :ref="el => setChapterRef(chapter.key, el)" class="chapter-header">
          <span class="chapter-label-inline">{{ chapter.label }}</span>
          <span v-if="chapter.status === 'active'" class="chapter-status-dot"></span>
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
      <template v-if="chapter.status === 'pending'">
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

const containerRef = ref(null);
const chapterRefs = new Map();
let previousActiveChapter = "";

function setChapterRef(key, el) {
  if (el) chapterRefs.set(key, el);
}

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

// 新章节开始时 scrollIntoView
watch(
  () => props.activeStageKey,
  async (newKey) => {
    // 找到新活动章节
    const activeChapter = props.chapters.find((ch) => ch.status === "active");
    if (activeChapter && activeChapter.key !== previousActiveChapter) {
      previousActiveChapter = activeChapter.key;
      await nextTick();
      const el = chapterRefs.get(activeChapter.key);
      if (el) {
        el.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }
    }
  },
);
</script>

<style scoped>
.stream-chat-content {
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

.chapter-status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-copper);
  animation: pulse-chapter 1.5s ease-in-out infinite;
  margin-left: var(--space-xs);
}

@keyframes pulse-chapter {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
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

/* 新步骤弹性出现 */
.step-list-enter-active {
  transition: opacity 0.35s cubic-bezier(0.34, 1.56, 0.64, 1),
              transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.step-list-leave-active {
  transition: opacity 0.25s cubic-bezier(0.55, 0, 1, 0.45),
              transform 0.25s cubic-bezier(0.55, 0, 1, 0.45);
}
.step-list-enter-from {
  opacity: 0;
  transform: translateY(16px) scale(0.97);
}
.step-list-leave-to {
  opacity: 0;
  transform: translateY(-6px) scale(0.99);
}

/* 章节折叠为卡片 */
.chapter-collapse-enter-active {
  transition: all 0.4s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.chapter-collapse-leave-active {
  transition: all 0.25s cubic-bezier(0.55, 0, 1, 0.45);
}
.chapter-collapse-enter-from {
  opacity: 0;
  transform: translateY(8px) scaleY(0.92);
  transform-origin: top;
}
.chapter-collapse-leave-to {
  opacity: 0;
  transform: translateY(-4px) scaleY(0.95);
  transform-origin: top;
}

@media (prefers-reduced-motion: reduce) {
  .chapter-status-dot {
    animation: none;
  }
  .step-list-enter-active,
  .step-list-leave-active,
  .chapter-collapse-enter-active,
  .chapter-collapse-leave-active {
    transition: opacity 0.15s ease;
  }
  .step-list-enter-from,
  .step-list-leave-to,
  .chapter-collapse-enter-from,
  .chapter-collapse-leave-to {
    transform: none;
  }
}
</style>
