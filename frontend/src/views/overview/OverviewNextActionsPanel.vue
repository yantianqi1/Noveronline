<template>
  <section class="next-actions-card workbench-card">
    <div class="panel-head">
      <div>
        <div class="panel-code mono">下一步入口</div>
        <h3 class="title-ancient">接下来去哪里</h3>
      </div>
      <span class="panel-note">不再用占位插画填空，而是给出可执行入口</span>
    </div>

    <div class="action-grid">
      <template v-for="action in actions" :key="action.label">
        <button
          v-if="action.type === 'command'"
          :class="['action-card', action.tone]"
          @click="handleCommand(action.command)"
        >
          <strong>{{ action.label }}</strong>
          <span>{{ action.description }}</span>
        </button>
        <RouterLink v-else :to="action.to" :class="['action-card', action.tone]">
          <strong>{{ action.label }}</strong>
          <span>{{ action.description }}</span>
        </RouterLink>
      </template>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";

import { buildOverviewNextActions } from "./overviewWorkbenchState.js";

const props = defineProps({
  project: { type: Object, default: null },
});

const emit = defineEmits(["start-new"]);

const actions = computed(() => buildOverviewNextActions(props.project));

function handleCommand(command) {
  if (command === "upload") {
    emit("start-new");
  }
}
</script>

<style scoped>
.next-actions-card {
  padding: var(--space-lg);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(250, 246, 239, 0.98)),
    radial-gradient(circle at 100% 0%, rgba(155, 44, 44, 0.07), transparent 28%);
}

.panel-head {
  display: flex;
  justify-content: space-between;
  gap: var(--space-lg);
  align-items: flex-start;
}

.panel-code,
.panel-note {
  color: var(--text-dim);
  font-size: 12px;
}

.panel-head h3 {
  margin-top: 6px;
  font-size: 24px;
}

.action-grid {
  margin-top: var(--space-lg);
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--space-md);
}

.action-card {
  min-height: 118px;
  border-radius: 18px;
  border: 1px solid rgba(113, 128, 150, 0.18);
  background: rgba(255, 255, 255, 0.86);
  padding: var(--space-lg);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: var(--space-sm);
  text-decoration: none;
  color: inherit;
  text-align: left;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
}

.action-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
  border-color: rgba(155, 44, 44, 0.24);
}

.action-card strong {
  font-size: 18px;
  color: var(--text-main);
}

.action-card span {
  color: var(--text-sub);
  line-height: 1.7;
}

.action-card.primary {
  background: linear-gradient(135deg, rgba(155, 44, 44, 0.96), rgba(116, 42, 42, 0.96));
  border-color: transparent;
}

.action-card.primary strong,
.action-card.primary span {
  color: #fff8f3;
}

@media (max-width: 900px) {
  .panel-head {
    flex-direction: column;
  }

  .action-grid {
    grid-template-columns: 1fr;
  }
}
</style>
