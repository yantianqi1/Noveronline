<template>
  <Transition name="drawer-fade">
    <div v-if="open" class="drawer-shell" @click.self="$emit('close')">
      <aside class="drawer-panel">
        <div class="drawer-head">
          <div>
            <div class="drawer-code mono">完整卷宗</div>
            <h3 class="title-ancient">{{ projectName || "当前种子任务" }}</h3>
          </div>
          <button class="btn subtle" @click="$emit('close')">收起</button>
        </div>

        <PipelineVisualization
          :upload-phase="uploadPhase"
          :task-status="taskStatus"
          :active-stage="activeStage"
        />

        <div class="drawer-log">
          <SeedTaskLogPanel
            :upload-phase="uploadPhase"
            :task-status="taskStatus"
            :active-stage="activeStage"
            :task-metrics="taskMetrics"
            :llm-activity="llmActivity"
            :timeline="timeline"
            :task-started-at="taskStartedAt"
          />
        </div>
      </aside>
    </div>
  </Transition>
</template>

<script setup>
import PipelineVisualization from "./PipelineVisualization.vue";
import SeedTaskLogPanel from "./SeedTaskLogPanel.vue";

defineProps({
  open: { type: Boolean, default: false },
  projectName: { type: String, default: "" },
  uploadPhase: { type: String, default: "idle" },
  taskStatus: { type: String, default: "" },
  activeStage: { type: Object, required: true },
  taskMetrics: { type: Object, required: true },
  llmActivity: { type: Object, required: true },
  timeline: { type: Array, required: true },
  taskStartedAt: { type: String, default: "" },
});

defineEmits(["close"]);
</script>

<style scoped>
.drawer-shell {
  position: fixed;
  inset: 0;
  background: rgba(45, 55, 72, 0.28);
  backdrop-filter: blur(6px);
  display: flex;
  justify-content: flex-end;
  z-index: 1200;
}

.drawer-panel {
  width: min(560px, 100vw);
  height: 100vh;
  background: linear-gradient(180deg, rgba(250, 249, 246, 0.98), rgba(245, 241, 234, 0.99));
  border-left: 1px solid var(--line-soft);
  box-shadow: -12px 0 40px rgba(45, 55, 72, 0.12);
  padding: var(--space-lg);
  overflow-y: auto;
}

.drawer-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-md);
}

.drawer-code {
  font-size: 12px;
  color: var(--text-dim);
}

.drawer-head h3 {
  margin-top: 6px;
  font-size: 28px;
}

.drawer-log {
  margin-top: var(--space-lg);
}

.drawer-fade-enter-active,
.drawer-fade-leave-active {
  transition: opacity 0.24s ease;
}

.drawer-fade-enter-from,
.drawer-fade-leave-to {
  opacity: 0;
}

@media (max-width: 768px) {
  .drawer-panel {
    width: 100vw;
    border-left: none;
  }
}
</style>
