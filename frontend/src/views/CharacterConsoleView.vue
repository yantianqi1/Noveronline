<template>
  <div class="console-stage">
    <aside class="stage-selection stack">
      <SessionCommandPanel
        :project-filter="projectFilter"
        :project-session-options="projectSessionOptions"
        :sessions="sessions"
        :session-id="sessionId"
        :session-label="sessionLabel"
        :active-session="activeSession"
        :selected-agent="selectedAgent"
        :action="action"
        :busy="busy"
        :error="error"
        :message="message"
        @update:project-filter="updateProjectFilter"
        @update:session-id="updateSessionId"
        @update:action="updateAction"
        @submit-action="submitAction"
      />

      <WorldlineAgentRoster
        :session-id="sessionId"
        :selected-agent-ref="selectedAgent?.agent_id || chatActor"
        @select="handleAgentSelect"
      />
    </aside>

    <main class="stage-interaction stack">
      <div v-if="!selectedAgent" class="empty-interaction workbench-card">
        <n-empty description="在左侧名录中点选一个角色或组织，开始对话或下达指令。">
          <template #icon>
            <Icon icon="icon-park-outline:masks" width="48" />
          </template>
          <template #extra>
            <span class="title-ancient">请选择交互对象</span>
          </template>
        </n-empty>
      </div>

      <template v-else>
        <AgentDialoguePanel
          :session-id="sessionId"
          :selected-agent="selectedAgent"
          :chat-mode="chatMode"
          :chat-message="chatMessage"
          :chat-reply="chatReply"
          :dialogues="agentDialogues"
          :chat-error="chatError"
          :busy="chatBusy"
          @update:chat-mode="updateChatMode"
          @update:chat-message="updateChatMessage"
          @submit="submitChat"
        />

        <InteractionLogPanel :logs="logs" />
      </template>
    </main>

    <aside class="stage-context stack">
      <AgentDetailPanel :selected-agent="selectedAgent" />
      <AgentHistoryPanel
        :session-id="sessionId"
        :selected-agent="selectedAgent"
        :snapshots="agentSnapshots"
        :actions="agentActions"
        :dialogues="agentDialogues"
        :session-memories="agentSessionMemories"
        :long-term-memories="agentLongTermMemories"
        :error="historyError"
      />
    </aside>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { NEmpty } from "naive-ui";
import { Icon } from "@iconify/vue";

import {
  chatWithWorldlineAgent,
  getWorldlineAgentActions,
  getWorldlineAgentDialogues,
  getWorldlineAgentHistory,
  getWorldlineAgentMemory,
  getWorldlineSession,
  issueAgentAction,
  listWorldlineSessions,
} from "../api/worldline";
import AgentDetailPanel from "./character-console/AgentDetailPanel.vue";
import AgentDialoguePanel from "./character-console/AgentDialoguePanel.vue";
import AgentHistoryPanel from "./character-console/AgentHistoryPanel.vue";
import InteractionLogPanel from "./character-console/InteractionLogPanel.vue";
import WorldlineAgentRoster from "./character-console/WorldlineAgentRoster.vue";
import SessionCommandPanel from "./character-console/SessionCommandPanel.vue";
import { buildProjectSessionOptions } from "./shared/worldlineSelectorState.js";

const projectFilter = ref("");
const sessions = ref([]);
const sessionId = ref("");
const action = ref("");
const busy = ref(false);
const message = ref("等待指令");
const error = ref("");
const logs = ref([]);
const chatActor = ref("");
const chatMode = ref("template");
const chatMessage = ref("");
const chatBusy = ref(false);
const chatReply = ref(null);
const chatError = ref("");
const selectedAgent = ref(null);
const agentSnapshots = ref([]);
const agentActions = ref([]);
const agentDialogues = ref([]);
const agentSessionMemories = ref([]);
const agentLongTermMemories = ref([]);
const historyError = ref("");
const sessionMap = ref({});

const activeSession = computed(() => sessionMap.value[sessionId.value] || null);
const projectSessionOptions = computed(() => buildProjectSessionOptions(sessions.value));

function nowTime() {
  return new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

function sessionLabel(session) {
  return `${session.session_scope === "global" ? "全局会话" : "卷宗会话"} · ${session.session_id.slice(0, 8)}`;
}

async function updateProjectFilter(value) {
  projectFilter.value = value;
  await loadSessions();
}

async function updateSessionId(value) {
  sessionId.value = value;
  await handleSessionChange();
}

function updateAction(value) {
  action.value = value;
}

function updateChatMessage(value) {
  chatMessage.value = value;
}

function updateChatMode(value) {
  chatMode.value = value || "template";
}

async function loadSessions() {
  const filters = projectFilter.value && projectFilter.value !== "__global__" ? { projectId: projectFilter.value } : {};
  const response = await listWorldlineSessions(filters);
  let items = response.data?.sessions || [];
  if (projectFilter.value === "__global__") {
    items = items.filter((item) => item.session_scope === "global");
  }
  sessions.value = items;
  sessionMap.value = Object.fromEntries(items.map((item) => [item.session_id, item]));
  if (!items.some((item) => item.session_id === sessionId.value)) {
    sessionId.value = items[0]?.session_id || "";
    await handleSessionChange();
  }
}

async function handleSessionChange() {
  selectedAgent.value = null;
  chatActor.value = "";
  chatReply.value = null;
  clearAgentHistory();
  if (!sessionId.value) {
    return;
  }
  const res = await getWorldlineSession(sessionId.value);
  const session = res.data;
  sessionMap.value = { ...sessionMap.value, [session.session_id]: session };
}

function handleAgentSelect(agent) {
  selectedAgent.value = agent;
  chatActor.value = agent.agent_id;
  void loadAgentHistory();
}

function clearAgentHistory() {
  historyError.value = "";
  agentSnapshots.value = [];
  agentActions.value = [];
  agentDialogues.value = [];
  agentSessionMemories.value = [];
  agentLongTermMemories.value = [];
}

async function loadAgentHistory() {
  if (!sessionId.value || !selectedAgent.value?.agent_id) {
    clearAgentHistory();
    return;
  }
  try {
    historyError.value = "";
    const filters = { agent_id: selectedAgent.value.agent_id, limit: 20 };
    const [historyRes, actionRes, dialogueRes, memoryRes] = await Promise.all([
      getWorldlineAgentHistory(sessionId.value, filters),
      getWorldlineAgentActions(sessionId.value, filters),
      getWorldlineAgentDialogues(sessionId.value, filters),
      getWorldlineAgentMemory(sessionId.value, filters),
    ]);
    agentSnapshots.value = historyRes.data?.snapshots || [];
    agentActions.value = actionRes.data?.items || [];
    agentDialogues.value = dialogueRes.data?.items || [];
    agentSessionMemories.value = memoryRes.data?.session_memories || [];
    agentLongTermMemories.value = memoryRes.data?.long_term_memories || [];
  } catch (err) {
    clearAgentHistory();
    historyError.value = err.message || "读取历史失败";
  }
}

async function submitAction() {
  if (!sessionId.value || !selectedAgent.value || !action.value.trim()) {
    return;
  }
  try {
    busy.value = true;
    error.value = "";
    const res = await issueAgentAction({
      session_id: sessionId.value,
      agent_id: selectedAgent.value.agent_id,
      action: action.value.trim(),
    });
    message.value = res.data.message || "动作成功";
    logs.value.unshift({ time: nowTime(), text: `[动作][${selectedAgent.value.display_name}] ${action.value}` });
    action.value = "";
    await loadAgentHistory();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

async function submitChat() {
  if (!sessionId.value || !selectedAgent.value || !chatMessage.value.trim()) {
    return;
  }
  try {
    chatBusy.value = true;
    chatError.value = "";
    const res = await chatWithWorldlineAgent({
      session_id: sessionId.value,
      agent_id: chatActor.value,
      message: chatMessage.value.trim(),
      mode: chatMode.value,
    });
    chatReply.value = res.data?.result || res.data || null;
    logs.value.unshift({ time: nowTime(), text: `[对话][${selectedAgent.value.display_name}] ${chatMessage.value}` });
    await loadAgentHistory();
  } catch (err) {
    chatError.value = err.message || "对话失败";
  } finally {
    chatBusy.value = false;
  }
}

onMounted(async () => {
  await loadSessions();
});
</script>

<style scoped>
.console-stage {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr) 320px;
  gap: var(--space-lg);
  height: calc(100vh - 120px);
}

.stage-selection,
.stage-context {
  overflow-y: auto;
  padding-right: var(--space-xs);
}

.stage-interaction {
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.empty-interaction {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--space-xl);
  background: var(--bg-panel-soft);
}
</style>
