<template>
  <article class="workbench-card selection-panel" :class="sessionId || preparedAgents.length ? 'panel-active' : 'panel-ready'">
    <header class="selection-header">
      <div>
        <p class="panel-kicker mono">{{ panelKicker }}</p>
        <h2 class="card-title">{{ panelTitle }}</h2>
      </div>
      <span v-if="selectedArchives.length" class="selection-badge mono">
        {{ selectedArchives.length }} 已选
      </span>
    </header>

    <!-- Pre-session: Archive picker fills the column -->
    <div v-if="!sessionId && !preparedAgents.length" class="selection-body archive-phase">
      <ArchiveLibraryPicker
        layout-variant="worldline"
        :model-value="selectedArchives"
        :project-filter="archiveProjectFilter"
        @update:model-value="emit('update:selected-archives', $event)"
        @update:project-filter="emit('update:archive-project-filter', $event)"
      />
    </div>

    <!-- Post-session: Agent roster + collapsed archive summary -->
    <div v-else class="selection-body agent-phase">
      <!-- Compact summary of the archive selection that seeded this session -->
      <div class="archive-summary-strip">
        <span class="strip-label mono">源档案</span>
        <div class="strip-chips">
          <span
            v-for="a in selectedArchives"
            :key="a.archive_id"
            class="strip-chip"
          >
            {{ a.entity_name || a.archive_id }}
          </span>
          <span v-if="!selectedArchives.length" class="strip-chip muted">无已选档案</span>
        </div>
      </div>

      <!-- Agent roster from the live session -->
      <WorldlineSimulationRoster
        :session-id="sessionId"
        :agents-override="preparedAgents"
        :selected-agent-ids="selectedAgentIds"
        @update:selected-agent-ids="handleAgentIdsUpdate"
        @focus="handleAgentFocus"
      />
    </div>
  </article>
</template>

<script setup>
import { computed, ref } from "vue";

import ArchiveLibraryPicker from "../../components/ArchiveLibraryPicker.vue";
import WorldlineSimulationRoster from "./WorldlineSimulationRoster.vue";

const props = defineProps({
  selectedArchives: { type: Array, default: () => [] },
  archiveProjectFilter: { type: String, default: "" },
  sessionId: { type: String, default: "" },
  preparedAgents: { type: Array, default: () => [] },
  busy: { type: Boolean, default: false },
});

const emit = defineEmits([
  "update:selected-archives",
  "update:archive-project-filter",
  "select-agent",
]);

const selectedAgentIds = ref([]);
const panelKicker = computed(() => {
  if (props.sessionId) return "AGENTS / 演员名册";
  if (props.preparedAgents.length) return "PREPARE / 整备名册";
  return "SELECTION / 源档案";
});
const panelTitle = computed(() => {
  if (props.sessionId) return "当前世界线参演对象";
  if (props.preparedAgents.length) return "LLM 整备后的参演对象";
  return "选择进入世界线的角色与组织";
});

function handleAgentIdsUpdate(ids) {
  selectedAgentIds.value = ids;
}

function handleAgentFocus(agent) {
  emit("select-agent", agent);
}
</script>

<style scoped>
.selection-panel {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  min-height: 100%;
}

.selection-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-md);
}

.panel-kicker {
  margin: 0;
  color: var(--accent-copper);
  font-size: 12px;
  letter-spacing: 0.14em;
}

.selection-badge {
  flex-shrink: 0;
  padding: 5px 10px;
  border-radius: var(--radius-full);
  background: rgba(245, 226, 192, 0.96);
  color: #724e1f;
  font-size: 12px;
}

.selection-body {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}

.archive-phase {
  min-height: 500px;
}

.archive-phase :deep(.archive-museum.variant-worldline) {
  min-height: 0;
}

.archive-phase :deep(.archive-museum.variant-worldline .museum-stage) {
  min-height: 0;
}

.archive-phase :deep(.archive-museum.variant-worldline .archive-pane) {
  min-height: 0;
}

.agent-phase {
  gap: var(--space-md);
}

/* ── Archive summary strip ── */
.archive-summary-strip {
  display: flex;
  gap: var(--space-sm);
  align-items: flex-start;
  padding: 10px 14px;
  border-radius: var(--radius-md);
  background: rgba(244, 237, 220, 0.72);
  border: 1px solid rgba(176, 125, 75, 0.18);
  flex-shrink: 0;
}

.strip-label {
  font-size: 11px;
  color: var(--text-dim);
  flex-shrink: 0;
  margin-top: 2px;
}

.strip-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.strip-chip {
  font-size: 12px;
  padding: 3px 8px;
  border-radius: var(--radius-full);
  background: rgba(201, 176, 139, 0.22);
  color: var(--text-sub);
}

.strip-chip.muted {
  color: var(--text-dim);
  background: rgba(201, 176, 139, 0.12);
}
</style>
