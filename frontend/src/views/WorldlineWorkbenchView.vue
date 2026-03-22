<template>
  <section class="worldline-grid">
    <WorldlineControlPanel
      :selected-archives="selectedArchives"
      :archive-project-filter="archiveProjectFilter"
      :variables-text="variablesText"
      :single-variable="singleVariable"
      :session-id="sessionId"
      :session-scope="sessionScope"
      :feedback="feedback"
      :error="error"
      :busy="busy"
      @update:selectedArchives="updateSelectedArchives"
      @update:archiveProjectFilter="updateArchiveProjectFilter"
      @update:variablesText="updateVariablesText"
      @update:singleVariable="updateSingleVariable"
      @create-session="createSession"
      @advance-step="stepForward"
      @inject-variable="injectVariable"
    />

    <WorldlineBranchOverview
      :branches="branches"
      :branch-id="branchId"
      :session-id="sessionId"
      @select-branch="chooseBranch"
      @refresh-branches="loadBranches"
    />

    <WorldlineBranchComparison
      :comparison="comparison"
      :selected-branch-id="branchId"
      :session-id="sessionId"
    />

    <WorldlineTimeline :timeline="timeline" />

    <WorldlineInspirationPanel
      :session-id="sessionId"
      :inspiration-prompt="inspirationPrompt"
      :inspiration-result="inspirationResult"
      :inspiration-error="inspirationError"
      :inspiration-busy="inspirationBusy"
      @update:inspirationPrompt="updateInspirationPrompt"
      @generate-inspiration="generateInspirationPlan"
    />
  </section>
</template>

<script setup>
import { ref } from "vue";
import {
  advanceWorldlineStep,
  createWorldlineSession,
  generatePlotInspiration,
  getWorldlineComparison,
  getWorldlineTimeline,
  injectWorldlineVariable,
  listWorldlineBranches,
} from "../api/worldline";
import WorldlineBranchComparison from "./worldline/WorldlineBranchComparison.vue";
import WorldlineControlPanel from "./worldline/WorldlineControlPanel.vue";
import WorldlineBranchOverview from "./worldline/WorldlineBranchOverview.vue";
import WorldlineTimeline from "./worldline/WorldlineTimeline.vue";
import WorldlineInspirationPanel from "./worldline/WorldlineInspirationPanel.vue";
import { resolveSelectedBranchId } from "./shared/worldlineSelectorState.js";

const selectedArchives = ref([]);
const archiveProjectFilter = ref("");
const variablesText = ref("主要势力 A 提前结盟\n主角亲族在第 3 节点失踪");
const singleVariable = ref("");
const sessionId = ref("");
const sessionScope = ref("");
const branchId = ref("");
const branches = ref([]);
const comparison = ref(null);
const timeline = ref([]);
const feedback = ref("等待操作");
const error = ref("");
const busy = ref(false);
const inspirationPrompt = ref("希望在下一幕引入关键误判，引发阵营站队重组。");
const inspirationBusy = ref(false);
const inspirationResult = ref(null);
const inspirationError = ref("");

function parseVariables(text) {
  return text
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
}

async function createSession() {
  if (!selectedArchives.value.length) {
    error.value = "请先从全局档案库选择至少一个档案。";
    return;
  }
  try {
    busy.value = true;
    error.value = "";
    const response = await createWorldlineSession({
      archive_ids: selectedArchives.value.map((item) => item.archive_id),
      variables: parseVariables(variablesText.value),
    });
    sessionId.value = response.data.session_id;
    sessionScope.value = response.data.session_scope || "";
    branchId.value = resolveSelectedBranchId(response.data.branches || [], branchId.value);
    feedback.value = `会话创建成功: ${sessionId.value}`;
    await loadBranches();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

function updateSelectedArchives(value) {
  selectedArchives.value = value;
}

function updateArchiveProjectFilter(value) {
  archiveProjectFilter.value = value;
}

function updateVariablesText(value) {
  variablesText.value = value;
}

function updateSingleVariable(value) {
  singleVariable.value = value;
}

function updateInspirationPrompt(value) {
  inspirationPrompt.value = value;
}

async function loadBranches() {
  try {
    if (!sessionId.value) return;
    error.value = "";
    const response = await listWorldlineBranches(sessionId.value);
    branches.value = response.data.branches || [];
    branchId.value = resolveSelectedBranchId(branches.value, branchId.value);
    await loadComparison();
    if (branchId.value) {
      await loadTimeline();
    }
  } catch (err) {
    error.value = err.message;
  }
}

async function loadComparison() {
  try {
    if (!sessionId.value) {
      comparison.value = null;
      return;
    }
    const response = await getWorldlineComparison(sessionId.value);
    comparison.value = response.data || null;
  } catch (err) {
    comparison.value = null;
    error.value = err.message;
  }
}

async function chooseBranch(id) {
  branchId.value = id;
  await loadTimeline();
}

async function loadTimeline() {
  try {
    if (!sessionId.value || !branchId.value) return;
    const response = await getWorldlineTimeline(sessionId.value, branchId.value);
    timeline.value = response.data.events || [];
  } catch (err) {
    error.value = err.message;
  }
}

async function stepForward() {
  try {
    busy.value = true;
    error.value = "";
    const response = await advanceWorldlineStep({
      session_id: sessionId.value,
      branch_id: branchId.value || undefined,
    });
    feedback.value = response.data.message || "推进完成";
    await loadBranches();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

async function injectVariable() {
  try {
    busy.value = true;
    error.value = "";
    if (!singleVariable.value.trim()) {
      error.value = "请先输入变量。";
      return;
    }
    const response = await injectWorldlineVariable({
      session_id: sessionId.value,
      branch_id: branchId.value || undefined,
      variable: singleVariable.value.trim(),
    });
    feedback.value = response.data.message || "变量注入成功";
    singleVariable.value = "";
    await loadBranches();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

async function generateInspirationPlan() {
  try {
    if (!sessionId.value) return;
    inspirationBusy.value = true;
    inspirationError.value = "";
    const response = await generatePlotInspiration({
      session_id: sessionId.value,
      branch_id: branchId.value || undefined,
      creator_prompt: inspirationPrompt.value.trim(),
      focus_question: "围绕当前分支推进后续剧情",
    });
    inspirationResult.value = response.data?.result || response.data || null;
  } catch (err) {
    inspirationError.value = err.message || "剧情灵感生成失败";
    inspirationResult.value = null;
  } finally {
    inspirationBusy.value = false;
  }
}
</script>

<style scoped>
.worldline-grid {
  display: grid;
  grid-template-columns: 420px minmax(0, 1fr);
  gap: 14px;
}

.panel {
  padding: 16px;
}

.panel p {
  color: var(--text-sub);
}

.full {
  grid-column: 1 / -1;
}

@media (max-width: 1200px) {
  .worldline-grid {
    grid-template-columns: 1fr;
  }
}
</style>
