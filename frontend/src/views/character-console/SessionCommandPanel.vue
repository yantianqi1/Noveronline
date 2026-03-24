<template>
  <article class="workbench-card panel">
    <h2 class="card-title">角色与关系控制台</h2>
    <p>先选择世界线会话，再从右侧名册点选对象并下达动作或发起对话。</p>

    <div class="field">
      <label>会话范围</label>
      <select :value="projectFilter" @change="emitUpdate('projectFilter', $event.target.value)">
        <option v-for="item in projectSessionOptions" :key="item.value" :value="item.value">
          {{ item.label }}
        </option>
      </select>
    </div>
    <div class="field">
      <label>世界线会话</label>
      <select :value="sessionId" @change="emitUpdate('sessionId', $event.target.value)">
        <option value="">请选择会话</option>
        <option v-for="item in sessions" :key="item.session_id" :value="item.session_id">
          {{ sessionLabel(item) }}
        </option>
      </select>
    </div>

    <div v-if="activeSession" class="session-summary">
      <strong>{{ formatSessionScope(activeSession.session_scope) }}</strong>
      <div class="mono">{{ activeSession.session_id }}</div>
      <p>{{ activeSession.simulation_goal || "暂无会话目标" }}</p>
    </div>

    <div v-if="selectedAgent" class="selected-agent">
      <strong>{{ selectedAgent.display_name }}</strong>
      <div class="mono">{{ formatAgentKind(selectedAgent.agent_kind) }} · {{ formatAgentStatus(selectedAgent.status) }}</div>
      <p>{{ selectedAgent.summary }}</p>
      <div v-if="summaryLines.length" class="agent-highlights">
        <div v-for="line in summaryLines" :key="line">{{ line }}</div>
      </div>
    </div>

    <div class="field">
      <label>动作指令</label>
      <textarea
        :value="action"
        placeholder="例如：以家族名义公开承认旧约，要求盟友在 3 天内给出立场。"
        @input="emitUpdate('action', $event.target.value)"
      ></textarea>
    </div>
    <div class="toolbar-row">
      <button class="btn primary" :disabled="busy || !sessionId || !selectedAgent" @click="$emit('submitAction')">执行动作</button>
    </div>
    <p class="status-text" :class="{ error: !!error }">{{ error || message }}</p>
  </article>
</template>

<script setup>
import { computed } from "vue";

import { formatAgentKind, formatAgentStatus, formatSessionScope } from "../../utils/chineseDisplay.js";
import { buildSelectedAgentSummaryLines } from "./agentDetailPresentation.js";

const props = defineProps({
  projectFilter: { type: String, default: "" },
  projectSessionOptions: { type: Array, default: () => [] },
  sessions: { type: Array, default: () => [] },
  sessionId: { type: String, default: "" },
  sessionLabel: { type: Function, required: true },
  activeSession: { type: Object, default: null },
  selectedAgent: { type: Object, default: null },
  action: { type: String, default: "" },
  busy: { type: Boolean, default: false },
  error: { type: String, default: "" },
  message: { type: String, default: "" },
});

const emit = defineEmits(["update:projectFilter", "update:sessionId", "update:action", "submitAction"]);
const summaryLines = computed(() => buildSelectedAgentSummaryLines(props.selectedAgent));

function emitUpdate(field, value) {
  emit(`update:${field}`, value);
}
</script>

<style scoped>
.panel {
  padding: 16px;
}

.panel p {
  color: var(--text-sub);
}

.session-summary,
.selected-agent {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fffaf1;
  margin-top: 12px;
  padding: 12px;
}

.selected-agent p,
.session-summary p {
  margin: 6px 0 0;
}

.agent-highlights {
  margin-top: 8px;
  display: grid;
  gap: 4px;
  color: var(--text-main);
}

.status-text.error {
  color: #9b4326;
}
</style>
