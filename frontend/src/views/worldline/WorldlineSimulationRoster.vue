<template>
  <div class="simulation-roster">
    <div class="roster-toolbar">
      <div class="roster-info">
        <p class="roster-kicker mono">AGENTS</p>
        <p v-if="agents.length" class="roster-count mono">{{ agents.length }} 对象</p>
      </div>
      <button
        class="roster-refresh"
        type="button"
        :disabled="busy"
        title="刷新名册"
        @click="loadRoster"
      >
        ↻
      </button>
    </div>

    <p v-if="error" class="roster-error">{{ error }}</p>
    <div v-else-if="!agents.length && !busy" class="roster-empty">
      <p>当前世界还没有可用对象，推进后会自动加载。</p>
    </div>

    <div v-for="group in groups" :key="group.kind" class="agent-group">
      <div class="group-label mono">{{ group.label }} · {{ group.items.length }}</div>
      <button
        v-for="agent in group.items"
        :key="agent.agent_id"
        type="button"
        class="agent-card"
        :class="{ selected: selectedIdSet.has(agent.agent_id) }"
        @click="toggleAgent(agent)"
      >
        <div class="agent-head">
          <div class="agent-check">
            <span class="check-box" :class="{ checked: selectedIdSet.has(agent.agent_id) }">
              {{ selectedIdSet.has(agent.agent_id) ? "✓" : "" }}
            </span>
          </div>
          <div class="agent-info">
            <strong>{{ agent.display_name }}</strong>
            <span class="agent-kind mono">{{ formatAgentKind(agent.agent_kind) }}</span>
          </div>
        </div>
        <div v-if="formatMeta(agent)" class="agent-meta">{{ formatMeta(agent) }}</div>
        <div v-if="resolveSummary(agent)" class="agent-summary">{{ resolveSummary(agent) }}</div>
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";

import { getWorldlineAgents } from "../../api/worldline";
import { formatAgentKind, formatAgentStatus, formatRoleText } from "../../utils/chineseDisplay";

const props = defineProps({
  sessionId: { type: String, default: "" },
  selectedAgentIds: { type: Array, default: () => [] },
  agentsOverride: { type: Array, default: () => [] },
});

const emit = defineEmits(["update:selectedAgentIds", "focus"]);

const agents = ref([]);
const busy = ref(false);
const error = ref("");

const selectedIdSet = computed(() => new Set(props.selectedAgentIds));
const hasOverride = computed(() => Array.isArray(props.agentsOverride) && props.agentsOverride.length > 0);

const groups = computed(() => [
  { kind: "character", label: "角色", items: agents.value.filter((item) => item.agent_kind === "character") },
  { kind: "organization", label: "组织", items: agents.value.filter((item) => item.agent_kind === "organization") },
  { kind: "relationship", label: "关系", items: agents.value.filter((item) => item.agent_kind === "relationship") },
].filter((group) => group.items.length));

watch(
  () => [props.sessionId, props.agentsOverride],
  async ([sessionId]) => {
    agents.value = [];
    error.value = "";
    if (hasOverride.value) {
      agents.value = props.agentsOverride;
      return;
    }
    if (sessionId) {
      await loadRoster();
    }
  },
  { immediate: true },
);

async function loadRoster() {
  if (hasOverride.value) {
    agents.value = props.agentsOverride;
    return;
  }
  if (!props.sessionId) {
    agents.value = [];
    return;
  }
  try {
    busy.value = true;
    error.value = "";
    const res = await getWorldlineAgents(props.sessionId);
    agents.value = res.data?.agents || [];
  } catch (err) {
    agents.value = [];
    error.value = err.message || "读取对象名册失败";
  } finally {
    busy.value = false;
  }
}

function toggleAgent(agent) {
  const id = agent.agent_id;
  const currentSet = new Set(props.selectedAgentIds);
  if (currentSet.has(id)) {
    currentSet.delete(id);
  } else {
    currentSet.add(id);
  }
  emit("update:selectedAgentIds", [...currentSet]);
  emit("focus", agent);
}

function formatMeta(agent) {
  const role = formatRoleText(agent.role || agent.runtime_seed_state?.role || "");
  const status = formatAgentStatus(agent.status || agent.runtime_seed_state?.status || "");
  return [role, status].filter(Boolean).join(" · ");
}

function resolveSummary(agent) {
  if (agent.summary) {
    return agent.summary;
  }
  if (agent.public_profile?.identity) {
    return agent.public_profile.identity;
  }
  return agent.runtime_seed_state?.drive || "";
}
</script>

<style scoped>
.simulation-roster {
  display: flex;
  flex-direction: column;
  gap: var(--space-sm);
}

.roster-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-sm);
}

.roster-info {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
}

.roster-kicker {
  margin: 0;
  color: var(--accent-copper);
  font-size: 11px;
  letter-spacing: 0.14em;
}

.roster-count {
  margin: 0;
  color: var(--text-dim);
  font-size: 12px;
}

.roster-refresh {
  width: 30px;
  height: 30px;
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-full);
  background: rgba(255, 250, 241, 0.92);
  color: var(--text-sub);
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.roster-refresh:hover {
  border-color: var(--accent-copper);
  color: var(--accent-copper);
}

.roster-error {
  margin: 0;
  color: var(--accent-seal);
  font-size: 13px;
}

.roster-empty {
  padding: var(--space-md);
  border-radius: var(--radius-md);
  background: rgba(255, 250, 243, 0.78);
  border: 1px dashed var(--line-soft);
  color: var(--text-sub);
  font-size: 13px;
}

.roster-empty p {
  margin: 0;
}

.agent-group + .agent-group {
  margin-top: var(--space-sm);
}

.group-label {
  color: var(--text-dim);
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.agent-card {
  width: 100%;
  margin-top: 6px;
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-md);
  background: #fffaf1;
  padding: 10px 12px;
  text-align: left;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 4px;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.agent-card:hover {
  border-color: rgba(176, 125, 75, 0.42);
  background: #fff6e8;
}

.agent-card.selected {
  border-color: var(--accent-copper);
  background: #fff1d5;
}

.agent-head {
  display: flex;
  align-items: center;
  gap: 8px;
}

.agent-check {
  flex-shrink: 0;
}

.check-box {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border: 1.5px solid var(--line-medium);
  border-radius: 5px;
  background: rgba(255, 255, 255, 0.9);
  font-size: 12px;
  font-weight: 700;
  color: transparent;
  transition: all 0.15s ease;
}

.check-box.checked {
  border-color: var(--accent-copper);
  background: var(--accent-copper);
  color: #fff;
}

.agent-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex: 1;
  min-width: 0;
}

.agent-info strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.agent-kind {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-dim);
}

.agent-meta {
  color: var(--text-sub);
  font-size: 12px;
  padding-left: 28px;
}

.agent-summary {
  color: var(--text-sub);
  font-size: 12px;
  padding-left: 28px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
</style>
