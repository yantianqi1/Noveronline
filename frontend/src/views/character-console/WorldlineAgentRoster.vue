<template>
  <article class="workbench-card panel roster-card">
    <div class="toolbar-row">
      <div>
        <h2 class="card-title">对象名册</h2>
        <p>从当前世界线自动读取角色、组织和关系对象。</p>
      </div>
      <button class="btn" :disabled="!sessionId || busy" @click="loadRoster">刷新</button>
    </div>

    <div v-if="!sessionId" class="empty">先在左侧选择世界线会话，再读取当前世界的对象名册。</div>
    <p v-else-if="error" class="status-text error">{{ error }}</p>
    <div v-else-if="!agents.length && !busy" class="empty">当前世界还没有可用对象。</div>

    <div v-for="group in groups" :key="group.kind" class="agent-group">
      <div class="seed-title">{{ group.label }} · {{ group.items.length }}</div>
      <button
        v-for="agent in group.items"
        :key="agent.agent_id"
        class="agent-card"
        :class="{ active: selectedAgentRef === agent.agent_id || selectedAgentRef === agent.display_name }"
        @click="chooseAgent(agent)"
      >
        <div class="agent-head">
          <strong>{{ agent.display_name }}</strong>
          <span class="mono">{{ formatAgentKind(agent.agent_kind) }}</span>
        </div>
        <div class="agent-meta">{{ formatRoleText(agent.role) }} · {{ formatAgentStatus(agent.status) }}</div>
        <div class="agent-metrics mono">
          ID {{ agent.agent_id }} · v{{ agent.state_version || 0 }} · {{ agent.state_source || "unknown" }}
        </div>
        <div class="agent-metrics">
          动作 {{ formatTime(agent.last_action_at) }} · 对话 {{ formatTime(agent.last_dialogue_at) }}
        </div>
        <div class="agent-summary">{{ agent.summary }}</div>
        <div v-if="buildAgentCardHighlights(agent).length" class="agent-highlights">
          <div v-for="line in buildAgentCardHighlights(agent)" :key="`${agent.agent_id}-${line}`">
            {{ line }}
          </div>
        </div>
      </button>
    </div>
  </article>
</template>

<script setup>
import { computed, ref, watch } from "vue";

import { getWorldlineAgents } from "../../api/worldline";
import { formatAgentKind, formatAgentStatus, formatRoleText } from "../../utils/chineseDisplay";
import { buildAgentCardHighlights } from "./agentDetailPresentation.js";

const props = defineProps({
  sessionId: { type: String, default: "" },
  selectedAgentRef: { type: String, default: "" },
});

const emit = defineEmits(["select"]);

const agents = ref([]);
const busy = ref(false);
const error = ref("");

const groups = computed(() => [
  { kind: "character", label: "角色", items: agents.value.filter((item) => item.agent_kind === "character") },
  { kind: "organization", label: "组织", items: agents.value.filter((item) => item.agent_kind === "organization") },
  { kind: "relationship", label: "关系", items: agents.value.filter((item) => item.agent_kind === "relationship") },
].filter((group) => group.items.length));

watch(
  () => props.sessionId,
  async (sessionId) => {
    agents.value = [];
    error.value = "";
    if (sessionId) {
      await loadRoster();
    }
  },
  { immediate: true },
);

async function loadRoster() {
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

function chooseAgent(agent) {
  emit("select", agent);
}

function formatTime(value) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}
</script>

<style scoped>
.roster-card {
  padding: 16px;
}

.agent-group + .agent-group {
  margin-top: 14px;
}

.agent-card {
  width: 100%;
  margin-top: 8px;
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fffaf1;
  padding: 11px;
  text-align: left;
}

.agent-card.active {
  border-color: var(--accent-copper);
  background: #fff4e3;
}

.agent-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.agent-meta,
.agent-metrics,
.agent-summary,
.agent-highlights,
.empty,
.status-text {
  margin-top: 6px;
  color: var(--text-sub);
}

.agent-highlights {
  display: grid;
  gap: 4px;
  color: var(--text-main);
}

.status-text.error {
  color: #9b4326;
}
</style>
