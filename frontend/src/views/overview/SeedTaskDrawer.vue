<template>
  <Teleport to="body">
    <Transition name="drawer">
      <div v-if="open" class="seed-drawer-backdrop" @click.self="$emit('close')">
        <aside class="seed-drawer-panel">
          <SeedDrawerSummaryBar
            v-if="showSummaryBar"
            :chapters="chapters"
            :active-stage-key="activeStageKey"
          />
          <SeedDrawerChatContent
            :task-id="taskId"
            :chapters="chapters"
            :active-stage-key="activeStageKey"
            :collapse="collapse"
          />
          <button class="drawer-close-btn" @click="$emit('close')">×</button>
        </aside>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { computed, watch } from "vue";
import { buildChapterViewModel } from "./seedPipelineChapters.js";
import { useSeedDrawerCollapse } from "../../composables/useSeedDrawerCollapse.js";
import SeedDrawerSummaryBar from "./SeedDrawerSummaryBar.vue";
import SeedDrawerChatContent from "./SeedDrawerChatContent.vue";

const props = defineProps({
  open: Boolean,
  taskId: { type: String, default: "" },
  timeline: { type: Array, default: () => [] },
  activeStageKey: { type: String, default: "" },
  taskStatus: { type: String, default: "" },
});

defineEmits(["close"]);

const chapters = computed(() =>
  buildChapterViewModel(props.timeline, props.activeStageKey),
);

const showSummaryBar = computed(() =>
  props.taskStatus === "processing" || chapters.value.some((c) => c.status === "active"),
);

const collapse = useSeedDrawerCollapse();

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
.seed-drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 900;
  background: rgba(44, 42, 39, 0.3);
}

.seed-drawer-panel {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: min(520px, 90vw);
  background: var(--bg-panel);
  box-shadow: -4px 0 24px rgba(44, 42, 39, 0.15);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.drawer-close-btn {
  position: absolute;
  top: var(--space-md);
  right: var(--space-md);
  z-index: 10;
  border: none;
  background: transparent;
  font-size: 22px;
  color: var(--text-dim);
  cursor: pointer;
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-sm);
}

.drawer-close-btn:hover {
  background: var(--bg-paper);
  color: var(--text-main);
}

/* Slide animation */
.drawer-enter-active,
.drawer-leave-active {
  transition: opacity 0.3s ease-out;
}
.drawer-enter-active .seed-drawer-panel,
.drawer-leave-active .seed-drawer-panel {
  transition: transform 0.3s ease-out;
}
.drawer-enter-from,
.drawer-leave-to {
  opacity: 0;
}
.drawer-enter-from .seed-drawer-panel,
.drawer-leave-to .seed-drawer-panel {
  transform: translateX(100%);
}

@media (prefers-reduced-motion: reduce) {
  .drawer-enter-active .seed-drawer-panel,
  .drawer-leave-active .seed-drawer-panel {
    transition: opacity 0.2s ease;
    transform: none !important;
  }
}
</style>
