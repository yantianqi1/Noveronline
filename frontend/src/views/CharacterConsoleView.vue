<template>
  <section class="console-grid">
    <SessionCommandPanel
      :project-filter="projectFilter"
      :project-session-options="projectSessionOptions"
      :sessions="sessions"
      :session-id="sessionId"
      :session-label="sessionLabel"
      :branches="branches"
      :branch-id="branchId"
      :active-session="activeSession"
      :selected-agent="selectedAgent"
      :action="action"
      :busy="busy"
      :error="error"
      :message="message"
      @update:projectFilter="updateProjectFilter"
      @update:sessionId="updateSessionId"
      @update:branchId="updateBranchId"
      @update:action="updateAction"
      @submitAction="submitAction"
    />

    <WorldlineAgentRoster
      :session-id="sessionId"
      :branch-id="branchId"
      :selected-agent-ref="selectedAgent?.agent_id || chatActor"
      @select="handleAgentSelect"
    />

    <InteractionLogPanel :logs="logs" />

    <AgentHistoryPanel
      :session-id="sessionId"
      :selected-agent="selectedAgent"
      :snapshots="agentSnapshots"
      :actions="agentActions"
      :dialogues="agentDialogues"
      :error="historyError"
    />

    <AgentDialoguePanel
      :session-id="sessionId"
      :selected-agent="selectedAgent"
      :chat-mode="chatMode"
      :chat-message="chatMessage"
      :chat-reply="chatReply"
      :dialogues="agentDialogues"
      :chat-error="chatError"
      :busy="chatBusy"
      @update:chatMode="updateChatMode"
      @update:chatMessage="updateChatMessage"
      @submit="submitChat"
    />
  </section>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";

import {
  chatWithWorldlineAgent,
  getWorldlineAgentActions,
  getWorldlineAgentDialogues,
  getWorldlineAgentHistory,
  getWorldlineSession,
  issueAgentAction,
  listWorldlineSessions,
} from "../api/worldline";
import AgentDialoguePanel from "./character-console/AgentDialoguePanel.vue";
import AgentHistoryPanel from "./character-console/AgentHistoryPanel.vue";
import InteractionLogPanel from "./character-console/InteractionLogPanel.vue";
import WorldlineAgentRoster from "./character-console/WorldlineAgentRoster.vue";
import SessionCommandPanel from "./character-console/SessionCommandPanel.vue";
import { buildProjectSessionOptions, resolveSelectedBranchId } from "./shared/worldlineSelectorState.js";

const projectFilter = ref("");
const sessions = ref([]);
const sessionId = ref("");
const branches = ref([]);
const branchId = ref("");
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
const historyError = ref("");
const sessionMap = ref({});

const activeSession = computed(() => sessionMap.value[sessionId.value] || null);
const projectSessionOptions = computed(() => {
  const sessionOptions = buildProjectSessionOptions(sessions.value);
  if (sessionOptions.some((item) => item.value === projectFilter.value)) {
    return sessionOptions;
  }
  return sessionOptions;
});

function nowTime() {
  return new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

function sessionLabel(session) {
  return `${session.session_scope === "global" ? "全局混合会话" : "项目会话"} · ${session.session_id} · ${session.source_archive_count || 0} 档案`;
}

async function updateProjectFilter(value) {
  projectFilter.value = value;
  await loadSessions();
}

async function updateSessionId(value) {
  sessionId.value = value;
  await handleSessionChange();
}

async function updateBranchId(value) {
  branchId.value = value;
  await loadAgentHistory();
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
    branches.value = [];
    branchId.value = "";
    return;
  }
  const response = await getWorldlineSession(sessionId.value);
  const session = response.data;
  sessionMap.value = { ...sessionMap.value, [session.session_id]: session };
  branches.value = session.branches || [];
  branchId.value = resolveSelectedBranchId(branches.value, branchId.value);
}

function handleAgentSelect(agent) {
  selectedAgent.value = agent;
  chatActor.value = agent.agent_id;
  loadAgentHistory();
}

function clearAgentHistory() {
  historyError.value = "";
  agentSnapshots.value = [];
  agentActions.value = [];
  agentDialogues.value = [];
}

async function loadAgentHistory() {
  if (!sessionId.value || !selectedAgent.value?.agent_id) {
    clearAgentHistory();
    return;
  }
  try {
    historyError.value = "";
    const filters = {
      branch_id: branchId.value || undefined,
      agent_id: selectedAgent.value.agent_id,
      limit: 20,
    };
    const [historyRes, actionsRes, dialoguesRes] = await Promise.all([
      getWorldlineAgentHistory(sessionId.value, filters),
      getWorldlineAgentActions(sessionId.value, filters),
      getWorldlineAgentDialogues(sessionId.value, filters),
    ]);
    agentSnapshots.value = historyRes.data?.snapshots || [];
    agentActions.value = actionsRes.data?.items || [];
    agentDialogues.value = dialoguesRes.data?.items || [];
  } catch (err) {
    clearAgentHistory();
    historyError.value = err.message || "读取对象历史失败";
  }
}

async function submitAction() {
  if (!sessionId.value || !selectedAgent.value || !action.value.trim()) {
    error.value = "请先选择会话、对象，并填写动作指令。";
    return;
  }
  try {
    busy.value = true;
    error.value = "";
    const response = await issueAgentAction({
      session_id: sessionId.value,
      branch_id: branchId.value || undefined,
      agent_id: selectedAgent.value.agent_id,
      action: action.value.trim(),
    });
    message.value = response.data.message || "动作提交成功";
    const actorName = response.data?.agent?.display_name || selectedAgent.value?.display_name || "已选对象";
    logs.value.unshift({
      time: nowTime(),
      text: `[动作][${actorName}] ${action.value.trim()}`,
    });
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
    chatError.value = "请先选择会话、对象，并填写对话内容。";
    return;
  }
  try {
    chatBusy.value = true;
    chatError.value = "";
    const response = await chatWithWorldlineAgent({
      session_id: sessionId.value,
      branch_id: branchId.value || undefined,
      agent_id: chatActor.value,
      message: chatMessage.value.trim(),
      mode: chatMode.value,
    });
    chatReply.value = response.data?.result || response.data || null;
    logs.value.unshift({
      time: nowTime(),
      text: `[对话][${selectedAgent.value.display_name}] ${chatMessage.value.trim()}`,
    });
    await loadAgentHistory();
  } catch (err) {
    chatReply.value = null;
    chatError.value = err.message || "对象对话失败";
  } finally {
    chatBusy.value = false;
  }
}

onMounted(async () => {
  await loadSessions();
});
</script>

<style scoped>
.console-grid {
  display: grid;
  grid-template-columns: 360px 320px minmax(0, 1fr);
  gap: 14px;
}

@media (max-width: 1200px) {
  .console-grid {
    grid-template-columns: 1fr;
  }
}
</style>
