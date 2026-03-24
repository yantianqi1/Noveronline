<template>
  <div ref="stageRef" class="worldline-stage" :class="[workbenchMode, { resizing }]" :style="stageStyle">
    <aside class="stage-controls stack">
      <WorldlineControlPanel
        :selected-archives="selectedArchives"
        :archive-project-filter="archiveProjectFilter"
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
        @update:selected-archives="updateSelectedArchives"
        @update:archive-project-filter="updateArchiveProjectFilter"
        @update:variables-text="updateVariablesText"
        @update:single-variable="updateSingleVariable"
        @update:create-mode="updateCreateMode"
        @update:goal-text="updateGoalText"
        @update:max-steps="updateMaxSteps"
        @create-session="createSession"
        @start-auto-evolve="startAutoEvolve"
        @advance-step="stepForward"
        @inject-variable="injectVariable"
      />
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
    </aside>
    <button
      class="stage-divider"
      type="button"
      aria-label="拖拽调整左右栏宽度"
      aria-orientation="vertical"
      @pointerdown.prevent="beginResize"
    >
      <span></span>
    </button>
    <main class="stage-performance stack">
      <div v-if="!sessionId" class="empty-stage workbench-card">
        <div class="empty-icon">⏳</div>
        <h3 class="title-ancient">等待开启世界线</h3>
        <p>请在左侧选择角色档案并设定初始变量，以启动当前世界线会话。</p>
      </div>
      <section v-else class="performance-main">
        <WorldlineDirectorPanel
          :session-id="sessionId"
          :current-world="currentWorld"
          :timeline="timeline"
          :task-snapshot="autoEvolution.currentTask.value"
        />
      </section>
    </main>
  </div>
</template>

<script setup>
import { ref } from "vue";

import {
  advanceWorldlineStep,
  createWorldlineSession,
  generatePlotInspiration,
  getWorldlineSession,
  getWorldlineTimeline,
  injectWorldlineVariable,
} from "../api/worldline";
import WorldlineControlPanel from "./worldline/WorldlineControlPanel.vue";
import WorldlineDirectorPanel from "./worldline/WorldlineDirectorPanel.vue";
import WorldlineInspirationPanel from "./worldline/WorldlineInspirationPanel.vue";
import { useWorldlineAutoEvolution } from "./worldline/useWorldlineAutoEvolution.js";
import { useWorldlineWorkbenchLayout } from "../composables/useWorldlineWorkbenchLayout.js";

const selectedArchives = ref([]);
const archiveProjectFilter = ref("");
const variablesText = ref("主要势力 A 提前结盟\n主角亲族在第 3 节点失踪");
const singleVariable = ref("");
const sessionId = ref("");
const sessionScope = ref("");
const currentWorld = ref(null);
const timeline = ref([]);
const feedback = ref("等待操作");
const error = ref("");
const busy = ref(false);
const inspirationPrompt = ref("希望在下一幕引入关键误判，引发阵营站队重组。");
const inspirationBusy = ref(false);
const inspirationResult = ref(null);
const inspirationError = ref("");

const { beginResize, resizing, stageRef, stageStyle, workbenchMode } = useWorldlineWorkbenchLayout();
const autoEvolution = useWorldlineAutoEvolution({
  refreshWorldline: async () => { await loadWorldline(); },
  setFeedback: (message) => { feedback.value = message; },
  setError: (message) => { error.value = message; },
});

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
    const res = await createWorldlineSession({
      archive_ids: selectedArchives.value.map((item) => item.archive_id),
      variables: parseVariables(variablesText.value),
    });
    sessionId.value = res.data.session_id;
    sessionScope.value = res.data.session_scope || "";
    feedback.value = "会话已启动";
    await loadWorldline();
    if (autoEvolution.prepareAfterSessionCreate(currentWorld.value)) {
      await startAutoEvolve();
    }
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

function updateSelectedArchives(value) { selectedArchives.value = value; }
function updateArchiveProjectFilter(value) { archiveProjectFilter.value = value; }
function updateVariablesText(value) { variablesText.value = value; }
function updateSingleVariable(value) { singleVariable.value = value; }
function updateInspirationPrompt(value) { inspirationPrompt.value = value; }
function updateCreateMode(value) { autoEvolution.createMode.value = value; }
function updateGoalText(value) { autoEvolution.goalText.value = value; }
function updateMaxSteps(value) { autoEvolution.maxSteps.value = value; }

async function loadWorldline() {
  if (!sessionId.value) {
    return;
  }
  try {
    const [sessionRes, timelineRes] = await Promise.all([
      getWorldlineSession(sessionId.value),
      getWorldlineTimeline(sessionId.value),
    ]);
    currentWorld.value = resolveCurrentWorld(sessionRes.data);
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
</script>

<style scoped src="./WorldlineWorkbenchView.css"></style>
