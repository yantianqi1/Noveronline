<template>
  <div ref="stageRef" class="worldline-stage" :class="[workbenchMode, { resizing, 'left-collapsed': leftCollapsed }]" :style="stageStyle">
    <!-- ① LEFT COLUMN: Archive selection / Agent roster -->
    <aside class="stage-selection">
      <div v-if="leftCollapsed" class="collapsed-rail" @click="leftCollapsed = false">
        <span class="collapsed-rail-label">演员名册</span>
        <span class="collapsed-rail-count mono">{{ preparedAgents.length || selectedArchives.length }}</span>
      </div>
      <WorldlineSelectionPanel
        v-show="!leftCollapsed"
        :selected-archives="selectedArchives"
        :archive-project-filter="archiveProjectFilter"
        :session-id="sessionId"
        :prepared-agents="preparedAgents"
        :busy="busy"
        @update:selected-archives="updateSelectedArchives"
        @update:archive-project-filter="updateArchiveProjectFilter"
        @select-agent="handleAgentFocus"
      />
    </aside>

    <!-- Divider 1: L ↔ M -->
    <button
      v-show="!leftCollapsed"
      class="stage-divider"
      type="button"
      aria-label="拖拽调整选择栏与控制栏宽度"
      aria-orientation="vertical"
      @pointerdown.prevent="beginLeftResize"
    >
      <span></span>
    </button>

    <!-- ② MIDDLE COLUMN: Session control, runtime, inspiration -->
    <section class="stage-controls stack">
      <WorldlineControlPanel
        :selected-archives="selectedArchives"
        :archive-project-filter="archiveProjectFilter"
        :show-archive-picker="showArchivePicker"
        :session-label="sessionLabel"
        :variables-text="variablesText"
        :single-variable="singleVariable"
        :create-mode="autoEvolution.createMode.value"
        :goal-text="autoEvolution.goalText.value"
        :max-steps="autoEvolution.maxSteps.value"
        :session-id="sessionId"
        :session-scope="sessionScope"
        :task="autoEvolution.currentTask.value"
        :feedback="feedback"
        :error="error"
        :busy="busy"
        :world-variables="worldVariables"
        :locked-variable-ids="lockedVariableIds"
        @update:selected-archives="updateSelectedArchives"
        @update:archive-project-filter="updateArchiveProjectFilter"
        @update:session-label="updateSessionLabel"
        @update:variables-text="updateVariablesText"
        @update:single-variable="updateSingleVariable"
        @update:create-mode="updateCreateMode"
        @update:goal-text="updateGoalText"
        @update:max-steps="updateMaxSteps"
        @create-session="createSession"
        @start-auto-evolve="startAutoEvolve"
        @advance-step="stepForward"
        @inject-variable="injectVariable"
        @toggle-lock="handleToggleLock"
        @lock-all="handleLockAll"
        @unlock-all="handleUnlockAll"
      />
      <article v-if="prepareId && !sessionId" class="workbench-card prepare-status-panel">
        <header class="prepare-status-head">
          <div>
            <p class="mono panel-kicker">PREPARE / AGENT 整备</p>
            <h3 class="card-title">LLM 整备进度</h3>
          </div>
          <n-tag :type="prepareSnapshot?.status === 'ready' ? 'success' : 'warning'" size="small">{{ prepareSnapshot?.status || "preparing" }}</n-tag>
        </header>
        <p class="prepare-copy">
          {{ prepareTaskMessage }}
        </p>
        <n-progress type="line" :percentage="prepareTaskProgress" :show-indicator="false" />
        <div class="prepare-meta">
          <span class="mono">prepare_id: {{ prepareId }}</span>
          <span v-if="prepareTaskId" class="mono">task: {{ prepareTaskId }}</span>
        </div>
      </article>
      <WorldlineInspirationPanel
        v-if="sessionId"
        :session-id="sessionId"
        :inspiration-prompt="inspirationPrompt"
        :inspiration-result="inspirationResult"
        :inspiration-error="inspirationError"
        :inspiration-busy="inspirationBusy"
        @update:inspiration-prompt="updateInspirationPrompt"
        @generate-inspiration="generateInspirationPlan"
      />
    </section>

    <!-- Divider 2: M ↔ R -->
    <button
      class="stage-divider"
      type="button"
      aria-label="拖拽调整控制栏与导演台宽度"
      aria-orientation="vertical"
      @pointerdown.prevent="beginMidResize"
    >
      <span></span>
    </button>

    <!-- ③ RIGHT COLUMN: Director panel -->
    <main class="stage-performance stack">
      <div v-if="!sessionId && !preparedAgents.length" class="empty-stage workbench-card">
        <n-empty description="请在左侧选择角色档案，在中栏设定初始变量，以启动当前世界线会话。">
          <template #icon>
            <Icon icon="icon-park-outline:hourglass-full" width="48" />
          </template>
          <template #extra>
            <span class="title-ancient">等待开启世界线</span>
          </template>
        </n-empty>
      </div>
      <article v-else-if="!sessionId" class="workbench-card agent-inspector">
        <header class="inspector-head">
          <div>
            <p class="mono panel-kicker">INSPECTION / PREPARED AGENT</p>
            <h3 class="card-title">{{ inspectorTitle }}</h3>
          </div>
          <n-button type="primary" :disabled="busy || !canStartPreparedSession" @click="startPreparedSession">
            开始推演
          </n-button>
        </header>
        <template v-if="preparedInspector">
          <p class="inspector-copy">{{ preparedInspector.public_profile?.identity || preparedInspector.runtime_seed_state?.drive || "等待选择 agent" }}</p>
          <div class="inspector-sections">
            <section v-if="preparedInspector.public_profile" class="inspector-section">
              <h4 class="inspector-section-title">公开面</h4>
              <dl class="inspector-dl">
                <template v-for="(val, key) in preparedInspector.public_profile" :key="key">
                  <dt>{{ key }}</dt>
                  <dd>{{ val }}</dd>
                </template>
              </dl>
            </section>
            <section v-if="preparedInspector.private_profile" class="inspector-section">
              <h4 class="inspector-section-title">私密面</h4>
              <dl class="inspector-dl">
                <template v-for="(val, key) in preparedInspector.private_profile" :key="key">
                  <dt>{{ key }}</dt>
                  <dd>{{ val }}</dd>
                </template>
              </dl>
            </section>
            <section v-if="preparedInspector.runtime_seed_state" class="inspector-section">
              <h4 class="inspector-section-title">运行态基底</h4>
              <dl class="inspector-dl">
                <template v-for="(val, key) in preparedInspector.runtime_seed_state" :key="key">
                  <dt>{{ key }}</dt>
                  <dd>{{ typeof val === 'object' ? JSON.stringify(val) : val }}</dd>
                </template>
              </dl>
            </section>
            <section v-if="preparedInspector.relationship_view || preparedInspector.memory_seed_summary" class="inspector-section">
              <h4 class="inspector-section-title">关系与记忆</h4>
              <p v-if="typeof preparedInspector.relationship_view === 'string'" class="inspector-text">{{ preparedInspector.relationship_view }}</p>
              <dl v-else-if="preparedInspector.relationship_view" class="inspector-dl">
                <template v-for="(val, key) in preparedInspector.relationship_view" :key="key">
                  <dt>{{ key }}</dt>
                  <dd>{{ typeof val === 'object' ? JSON.stringify(val) : val }}</dd>
                </template>
              </dl>
              <ul v-if="Array.isArray(preparedInspector.memory_seed_summary)" class="inspector-list">
                <li v-for="(item, idx) in preparedInspector.memory_seed_summary" :key="idx">
                  {{ typeof item === 'string' ? item : item.summary || JSON.stringify(item) }}
                </li>
              </ul>
            </section>
          </div>
        </template>
      </article>
      <section v-else class="performance-main">
        <WorldlineDirectorPanel
          :session-id="sessionId"
          :current-world="currentWorld"
          :timeline="timeline"
          :task-snapshot="autoEvolution.currentTask.value"
          :candidate-events="autoEvolution.candidateEvents.value"
          :stream-phase="autoEvolution.streamPhase.value"
          :thinking-info="autoEvolution.thinkingInfo.value"
          @adopt-event="handleAdoptEvent"
          @reject-event="handleRejectEvent"
          @edit-event="handleEditEvent"
          @adopt-all="handleAdoptAll"
          @reject-all="handleRejectAll"
        />
        <article v-if="runtimeAgentDetail" class="workbench-card agent-inspector runtime-inspector">
          <header class="inspector-head">
            <div>
              <p class="mono panel-kicker">INSPECTION / RUNTIME AGENT</p>
              <h3 class="card-title">{{ runtimeAgentDetail.current_agent?.display_name || "Agent 详情" }}</h3>
            </div>
          </header>
          <p class="inspector-copy">
            {{ runtimeAgentDetail.current_agent?.summary || runtimeAgentDetail.baseline_dossier?.public_profile?.identity || "当前 agent 的运行态与基线档案对比。" }}
          </p>
          <div class="inspector-sections">
            <section v-if="runtimeAgentDetail.current_agent" class="inspector-section">
              <h4 class="inspector-section-title">当前运行态</h4>
              <dl class="inspector-dl">
                <dt>状态</dt><dd>{{ runtimeAgentDetail.current_agent.status || "—" }}</dd>
                <dt>驱动力</dt><dd>{{ runtimeAgentDetail.current_agent.drive || runtimeAgentDetail.current_agent.core_drive || "—" }}</dd>
                <dt>张力</dt><dd>{{ runtimeAgentDetail.current_agent.tension || "—" }}</dd>
                <template v-if="runtimeAgentDetail.current_agent.role">
                  <dt>角色</dt><dd>{{ runtimeAgentDetail.current_agent.role }}</dd>
                </template>
                <template v-if="runtimeAgentDetail.current_agent.last_action">
                  <dt>最近行动</dt><dd>{{ runtimeAgentDetail.current_agent.last_action }}</dd>
                </template>
              </dl>
            </section>
            <section v-if="runtimeAgentDetail.baseline_dossier?.public_profile" class="inspector-section">
              <h4 class="inspector-section-title">准备态档案</h4>
              <dl class="inspector-dl">
                <template v-for="(val, key) in runtimeAgentDetail.baseline_dossier.public_profile" :key="key">
                  <dt>{{ key }}</dt>
                  <dd>{{ val }}</dd>
                </template>
              </dl>
            </section>
            <section v-if="runtimeAgentDetail.history" class="inspector-section">
              <h4 class="inspector-section-title">历史记录</h4>
              <ul v-if="Array.isArray(runtimeAgentDetail.history)" class="inspector-list">
                <li v-for="(item, idx) in runtimeAgentDetail.history.slice(-6)" :key="idx">
                  {{ typeof item === 'string' ? item : item.summary || item.action || JSON.stringify(item) }}
                </li>
              </ul>
              <dl v-else-if="typeof runtimeAgentDetail.history === 'object'" class="inspector-dl">
                <template v-for="(val, key) in runtimeAgentDetail.history" :key="key">
                  <dt>{{ key }}</dt>
                  <dd>{{ typeof val === 'object' ? JSON.stringify(val) : val }}</dd>
                </template>
              </dl>
            </section>
            <section v-if="runtimeAgentDetail.relation_history?.length" class="inspector-section">
              <h4 class="inspector-section-title">关系变化</h4>
              <ul class="inspector-list">
                <li v-for="(rel, idx) in runtimeAgentDetail.relation_history.slice(-6)" :key="idx">
                  <strong>{{ rel.source || "" }} → {{ rel.target || "" }}</strong>
                  <span v-if="rel.change"> · {{ rel.change }}</span>
                  <span v-if="rel.note"> — {{ rel.note }}</span>
                </li>
              </ul>
            </section>
          </div>
        </article>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { NButton, NEmpty, NProgress, NTag } from "naive-ui";
import { Icon } from "@iconify/vue";

import {
  adoptWorldlineEvents,
  advanceWorldlineStep,
  editWorldlineEvent,
  getPreparedWorldlineAgents,
  getPreparedWorldlineSession,
  getWorldlineAgentDetail,
  generatePlotInspiration,
  getWorldlineSession,
  getWorldlineTimeline,
  injectWorldlineVariable,
  prepareWorldlineSession,
  startPreparedWorldlineSession,
} from "../api/worldline";
import { getTask } from "../api/project.js";
import { WORLDLINE_WORKBENCH_MODE_THREE_COL } from "./shared/worldlineWorkbenchLayout.js";
import WorldlineControlPanel from "./worldline/WorldlineControlPanel.vue";
import WorldlineDirectorPanel from "./worldline/WorldlineDirectorPanel.vue";
import WorldlineInspirationPanel from "./worldline/WorldlineInspirationPanel.vue";
import WorldlineSelectionPanel from "./worldline/WorldlineSelectionPanel.vue";
import { useWorldlineAutoEvolution } from "./worldline/useWorldlineAutoEvolution.js";
import { createWorldlinePrepareTaskPoller } from "./worldline/worldlinePrepareTaskPoller.js";
import { useWorldlineWorkbenchLayout } from "../composables/useWorldlineWorkbenchLayout.js";
import { resolvePrepareTaskMessage } from "./worldline/worldlineControlPanelViewModel.js";

const selectedArchives = ref([]);
const archiveProjectFilter = ref("");
const sessionLabel = ref("");
const variablesText = ref("主要势力 A 提前结盟\n主角亲族在第 3 节点失踪");
const singleVariable = ref("");
const sessionId = ref("");
const sessionScope = ref("");
const prepareId = ref("");
const prepareTaskId = ref("");
const prepareSnapshot = ref(null);
const preparedAgents = ref([]);
const currentWorld = ref(null);
const worldVariables = ref([]);
const lockedVariableIds = ref(new Set());
const timeline = ref([]);
const feedback = ref("等待操作");
const error = ref("");
const busy = ref(false);
const inspirationPrompt = ref("希望在下一幕引入关键误判，引发阵营站队重组。");
const inspirationBusy = ref(false);
const inspirationResult = ref(null);
const inspirationError = ref("");
const focusedAgent = ref(null);
const runtimeAgentDetail = ref(null);

const { beginLeftResize, beginMidResize, resizing, stageRef, stageStyle, workbenchMode } = useWorldlineWorkbenchLayout();
const autoEvolution = useWorldlineAutoEvolution({
  refreshWorldline: async () => { await loadWorldline(); },
  setFeedback: (message) => { feedback.value = message; },
  setError: (message) => { error.value = message; },
});
const pollPrepareTask = createWorldlinePrepareTaskPoller({
  getTask,
  getPreparedSession: getPreparedWorldlineSession,
});

const leftCollapsed = ref(false);

// Auto-collapse left pane when evolution stream starts
watch(() => autoEvolution.streamPhase.value, (phase) => {
  if (phase === "connecting" || phase === "thinking") {
    leftCollapsed.value = true;
  }
});

const showArchivePicker = computed(() => workbenchMode.value !== WORLDLINE_WORKBENCH_MODE_THREE_COL);
const prepareTaskProgress = computed(() => Number(prepareSnapshot.value?.task_progress || 0));
const prepareTaskMessage = computed(() => resolvePrepareTaskMessage({
  prepareSnapshot: prepareSnapshot.value,
  error: error.value,
}));
const preparedInspector = computed(() => {
  if (!preparedAgents.value.length) {
    return null;
  }
  if (!focusedAgent.value) {
    return preparedAgents.value[0];
  }
  return preparedAgents.value.find((item) => item.agent_id === focusedAgent.value.agent_id) || preparedAgents.value[0];
});
const canStartPreparedSession = computed(() => Boolean(prepareId.value && prepareSnapshot.value?.can_start));
const inspectorTitle = computed(() => preparedInspector.value?.display_name || "等待整备完成");

function parseVariables(text) {
  return text.split("\n").map((value) => value.trim()).filter(Boolean);
}

function resolveCurrentWorld(data) {
  return data?.current_world || null;
}

async function createSession() {
  if (!selectedArchives.value.length) {
    error.value = "请先选择至少一个角色档案。";
    return;
  }
  try {
    busy.value = true;
    error.value = "";
    runtimeAgentDetail.value = null;
    sessionId.value = "";
    sessionScope.value = "";
    prepareSnapshot.value = null;
    prepareId.value = "";
    prepareTaskId.value = "";
    preparedAgents.value = [];
    const res = await prepareWorldlineSession({
      label: sessionLabel.value.trim(),
      archive_ids: selectedArchives.value.map((item) => item.archive_id),
      variables: parseVariables(variablesText.value),
    });
    prepareId.value = res.data.prepare_id;
    prepareTaskId.value = res.data.task_id;
    feedback.value = "已进入 LLM 整备阶段";
    await waitForPreparedSession(res.data.task_id, res.data.prepare_id);
  } catch (err) {
    console.error("[createSession] failed:", err);
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

function updateSelectedArchives(value) { selectedArchives.value = value; }
function updateArchiveProjectFilter(value) { archiveProjectFilter.value = value; }
function updateSessionLabel(value) { sessionLabel.value = value; }
function updateVariablesText(value) { variablesText.value = value; }
function updateSingleVariable(value) { singleVariable.value = value; }
function updateInspirationPrompt(value) { inspirationPrompt.value = value; }
function updateCreateMode(value) { autoEvolution.createMode.value = value; }
function updateGoalText(value) { autoEvolution.goalText.value = value; }
function updateMaxSteps(value) { autoEvolution.maxSteps.value = value; }

function handleToggleLock(variableId) {
  const next = new Set(lockedVariableIds.value);
  if (next.has(variableId)) {
    next.delete(variableId);
  } else {
    next.add(variableId);
  }
  lockedVariableIds.value = next;
  // Sync locked variable descriptions to autoEvolution constraints
  autoEvolution.constraints.value = worldVariables.value
    .filter((v) => next.has(v.variable_id))
    .map((v) => `${v.name}：${v.description}`);
}

function handleLockAll() {
  const next = new Set(worldVariables.value.map((v) => v.variable_id));
  lockedVariableIds.value = next;
  autoEvolution.constraints.value = worldVariables.value
    .map((v) => `${v.name}：${v.description}`);
}

function handleUnlockAll() {
  lockedVariableIds.value = new Set();
  autoEvolution.constraints.value = [];
}
async function handleAgentFocus(agent) {
  focusedAgent.value = agent;
  if (sessionId.value) {
    await loadAgentDetail(agent.agent_id);
  }
}

async function loadWorldline() {
  if (!sessionId.value) {
    return;
  }
  try {
    const [sessionRes, timelineRes] = await Promise.all([
      getWorldlineSession(sessionId.value),
      getWorldlineTimeline(sessionId.value),
    ]);
    sessionScope.value = sessionRes.data?.session_scope || "";
    currentWorld.value = resolveCurrentWorld(sessionRes.data);
    worldVariables.value = sessionRes.data?.world_variables || [];
    timeline.value = timelineRes.data?.events || [];
    autoEvolution.syncWorld(currentWorld.value);
  } catch (err) {
    error.value = err.message;
  }
}

async function stepForward() {
  try {
    busy.value = true;
    error.value = "";
    const res = await advanceWorldlineStep({ session_id: sessionId.value, steps: 1 });
    feedback.value = res.data.message || "推进完成";
    await loadWorldline();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

async function startAutoEvolve() {
  if (!sessionId.value) {
    return;
  }
  try {
    busy.value = true;
    error.value = "";
    const tasks = await autoEvolution.startForSession(sessionId.value);
    feedback.value = tasks.length ? "当前世界自动演化已启动" : "当前模式无需自动演化";
    await loadWorldline();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

async function waitForPreparedSession(taskId, nextPrepareId) {
  const snapshot = await pollPrepareTask(taskId, nextPrepareId, (value) => {
    prepareSnapshot.value = value;
  });
  prepareSnapshot.value = snapshot;
  await loadPreparedAgents(nextPrepareId);

  if (autoEvolution.createMode.value === "manual") {
    feedback.value = "LLM 整备已完成，请检查 agent 形态后开始推演。";
    return;
  }

  feedback.value = "LLM 整备已完成，正在进入自动推演。";
  await startPreparedSession();
}

async function loadPreparedAgents(nextPrepareId = prepareId.value) {
  const [snapshot, agents] = await Promise.all([
    getPreparedWorldlineSession(nextPrepareId),
    getPreparedWorldlineAgents(nextPrepareId),
  ]);
  prepareSnapshot.value = {
    ...(snapshot.data || {}),
    task_progress: prepareSnapshot.value?.task_progress || 0,
    task_message: prepareSnapshot.value?.task_message || "",
  };
  preparedAgents.value = agents.data?.agents || [];
  focusedAgent.value = preparedAgents.value[0] || null;
}

async function startPreparedSession() {
  if (!prepareId.value) {
    return;
  }
  try {
    busy.value = true;
    error.value = "";
    const res = await startPreparedWorldlineSession(prepareId.value);
    sessionId.value = res.data.session_id;
    feedback.value = "世界线会话已启动";
    await loadWorldline();
    if (focusedAgent.value?.agent_id) {
      await loadAgentDetail(focusedAgent.value.agent_id);
    }
    if (autoEvolution.prepareAfterSessionCreate(currentWorld.value)) {
      await startAutoEvolve();
    }
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

async function loadAgentDetail(agentId) {
  if (!sessionId.value || !agentId) {
    runtimeAgentDetail.value = null;
    return;
  }
  try {
    const response = await getWorldlineAgentDetail(sessionId.value, agentId);
    runtimeAgentDetail.value = response.data || null;
  } catch (err) {
    error.value = err.message;
  }
}

async function injectVariable() {
  if (!singleVariable.value.trim()) {
    return;
  }
  try {
    busy.value = true;
    error.value = "";
    const res = await injectWorldlineVariable({
      session_id: sessionId.value,
      variable: singleVariable.value.trim(),
    });
    feedback.value = res.data.message || "变量注入成功";
    singleVariable.value = "";
    await loadWorldline();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

/* ── candidate adopt / reject / edit handlers ────────────────── */

async function handleAdoptEvent({ eventId }) {
  try {
    error.value = "";
    await adoptWorldlineEvents({
      session_id: sessionId.value,
      event_ids: [eventId],
      action: "adopt",
    });
    autoEvolution.removeCandidateEvent(eventId);
    feedback.value = "事件已采纳为正史";
    await loadWorldline();
  } catch (err) {
    error.value = err.message;
  }
}

async function handleRejectEvent({ eventId }) {
  try {
    error.value = "";
    await adoptWorldlineEvents({
      session_id: sessionId.value,
      event_ids: [eventId],
      action: "reject",
    });
    autoEvolution.removeCandidateEvent(eventId);
    feedback.value = "候选事件已拒绝";
    await loadWorldline();
  } catch (err) {
    error.value = err.message;
  }
}

async function handleEditEvent({ eventId, consequence }) {
  try {
    error.value = "";
    await editWorldlineEvent({
      session_id: sessionId.value,
      event_id: eventId,
      consequence,
    });
    autoEvolution.removeCandidateEvent(eventId);
    feedback.value = "事件已编辑并采纳为正史";
    await loadWorldline();
  } catch (err) {
    error.value = err.message;
  }
}

async function handleAdoptAll() {
  const ids = autoEvolution.candidateEvents.value.map((e) => e.event_id);
  if (!ids.length) return;
  try {
    error.value = "";
    await adoptWorldlineEvents({
      session_id: sessionId.value,
      event_ids: ids,
      action: "adopt",
    });
    autoEvolution.removeCandidateEvents(ids);
    feedback.value = `已全部采纳 ${ids.length} 个候选事件`;
    await loadWorldline();
  } catch (err) {
    error.value = err.message;
  }
}

async function handleRejectAll() {
  const ids = autoEvolution.candidateEvents.value.map((e) => e.event_id);
  if (!ids.length) return;
  try {
    error.value = "";
    await adoptWorldlineEvents({
      session_id: sessionId.value,
      event_ids: ids,
      action: "reject",
    });
    autoEvolution.removeCandidateEvents(ids);
    feedback.value = `已全部拒绝 ${ids.length} 个候选事件`;
    await loadWorldline();
  } catch (err) {
    error.value = err.message;
  }
}

async function generateInspirationPlan() {
  if (!sessionId.value) {
    return;
  }
  try {
    inspirationBusy.value = true;
    inspirationError.value = "";
    const res = await generatePlotInspiration({
      session_id: sessionId.value,
      creator_prompt: inspirationPrompt.value.trim(),
      focus_question: "下一步走向",
    });
    inspirationResult.value = res.data?.result || res.data || null;
  } catch (err) {
    inspirationError.value = err.message;
  } finally {
    inspirationBusy.value = false;
  }
}

function prettyJson(value) {
  return JSON.stringify(value, null, 2);
}
</script>

<style scoped src="./WorldlineWorkbenchView.css"></style>
