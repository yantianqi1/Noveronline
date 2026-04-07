<template>
  <Transition name="stream">
    <section v-if="visible" class="workflow-stream">
      <InlineStreamSummaryBar
        v-if="showSummaryBar"
        :chapters="chapters"
        :active-stage-key="activeStageKey"
      />
      <InlineStreamChatContent
        :task-id="taskId"
        :chapters="chapters"
        :active-stage-key="activeStageKey"
        :collapse="collapse"
      />
    </section>
  </Transition>
</template>

<script setup>
import { computed, watch } from "vue";
import { buildChapterViewModel } from "./seedPipelineChapters.js";
import { useSeedDrawerCollapse } from "../../composables/useSeedDrawerCollapse.js";
import InlineStreamSummaryBar from "./InlineStreamSummaryBar.vue";
import InlineStreamChatContent from "./InlineStreamChatContent.vue";

const props = defineProps({
  taskId: { type: String, default: "" },
  timeline: { type: Array, default: () => [] },
  activeStageKey: { type: String, default: "" },
  taskStatus: { type: String, default: "" },
  uploadPhase: { type: String, default: "idle" },
});

const visible = computed(() => props.uploadPhase !== "idle");

const chapters = computed(() =>
  buildChapterViewModel(props.timeline, props.activeStageKey),
);

const showSummaryBar = computed(() =>
  props.taskStatus === "processing" || chapters.value.some((c) => c.status === "active"),
);

const collapse = useSeedDrawerCollapse();

// 新任务时清空旧折叠状态
watch(
  () => props.taskId,
  () => {
    collapse.reset();
  },
);

// 当步骤完成时触发自动折叠
watch(
  () => props.timeline.length,
  () => {
    for (const ch of chapters.value) {
      for (const step of ch.steps) {
        if (step.status === "completed") {
          collapse.onStepCompleted(step.stepId, ch.key);
        }
      }
    }
  },
);
</script>

<style scoped>
.workflow-stream {
  border-radius: 10px;
  border: 1px solid var(--line-soft);
  background: rgba(255, 255, 255, 0.68);
  padding: var(--space-md);
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

/* 从右侧弹性滑入 */
.stream-enter-active {
  transition: opacity 0.5s cubic-bezier(0.34, 1.56, 0.64, 1),
              transform 0.5s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.stream-leave-active {
  transition: opacity 0.3s cubic-bezier(0.55, 0, 1, 0.45),
              transform 0.3s cubic-bezier(0.55, 0, 1, 0.45);
}
.stream-enter-from {
  opacity: 0;
  transform: translateX(60px) scale(0.97);
}
.stream-leave-to {
  opacity: 0;
  transform: translateX(40px) scale(0.98);
}

@media (max-width: 768px) {
  .workflow-stream {
    border-radius: 12px;
    padding: var(--space-md);
  }
}

@media (prefers-reduced-motion: reduce) {
  .stream-enter-active,
  .stream-leave-active {
    transition: opacity 0.15s ease;
  }
  .stream-enter-from,
  .stream-leave-to {
    transform: none;
  }
}
</style>
