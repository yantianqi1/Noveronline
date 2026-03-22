<template>
  <div class="worldline-stage">
    <!-- Left Stage: Configuration & Control -->
    <aside class="stage-controls stack">
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
        @update:selected-archives="updateSelectedArchives"
        @update:archive-project-filter="updateArchiveProjectFilter"
        @update:variables-text="updateVariablesText"
        @update:single-variable="updateSingleVariable"
        @create-session="createSession"
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

    <!-- Right Stage: Performance & Visualization -->
    <main class="stage-performance stack">
      <div v-if="!sessionId" class="empty-stage workbench-card">
        <div class="empty-icon">⏳</div>
        <h3 class="title-ancient">等待开启世界线</h3>
        <p>请在左侧选择角色档案并设定初始变量，以启动平行世界推演会话。</p>
      </div>

      <template v-else>
        <section class="performance-top workbench-card">
          <WorldlineBranchOverview
            :branches="branches"
            :branch-id="branchId"
            :session-id="sessionId"
            @select-branch="chooseBranch"
            @refresh-branches="loadBranches"
          />
        </section>

        <section class="performance-mid container-6-4">
          <WorldlineBranchComparison
            :comparison="comparison"
            :selected-branch-id="branchId"
            :session-id="sessionId"
          />
          <div class="timeline-container workbench-card">
            <h3 class="title-ancient">时空轨迹</h3>
            <WorldlineTimeline :timeline="timeline" />
          </div>
        </section>
      </template>
    </main>
  </div>
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
  return text.split("\n").map(v => v.trim()).filter(Boolean);
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
      archive_ids: selectedArchives.value.map(item => item.archive_id),
      variables: parseVariables(variablesText.value),
    });
    sessionId.value = res.data.session_id;
    sessionScope.value = res.data.session_scope || "";
    branchId.value = resolveSelectedBranchId(res.data.branches || [], branchId.value);
    feedback.value = `会话已启动`;
    await loadBranches();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

function updateSelectedArchives(v) { selectedArchives.value = v; }
function updateArchiveProjectFilter(v) { archiveProjectFilter.value = v; }
function updateVariablesText(v) { variablesText.value = v; }
function updateSingleVariable(v) { singleVariable.value = v; }
function updateInspirationPrompt(v) { inspirationPrompt.value = v; }

async function loadBranches() {
  if (!sessionId.value) return;
  try {
    const res = await listWorldlineBranches(sessionId.value);
    branches.value = res.data.branches || [];
    branchId.value = resolveSelectedBranchId(branches.value, branchId.value);
    await loadComparison();
    if (branchId.value) await loadTimeline();
  } catch (err) {
    error.value = err.message;
  }
}

async function loadComparison() {
  if (!sessionId.value) return;
  try {
    const res = await getWorldlineComparison(sessionId.value);
    comparison.value = res.data || null;
  } catch {
    comparison.value = null;
  }
}

async function chooseBranch(id) {
  branchId.value = id;
  await loadTimeline();
}

async function loadTimeline() {
  if (!sessionId.value || !branchId.value) return;
  try {
    const res = await getWorldlineTimeline(sessionId.value, branchId.value);
    timeline.value = res.data.events || [];
  } catch (err) {
    error.value = err.message;
  }
}

async function stepForward() {
  try {
    busy.value = true;
    const res = await advanceWorldlineStep({ session_id: sessionId.value, branch_id: branchId.value || undefined });
    feedback.value = res.data.message || "推进完成";
    await loadBranches();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

async function injectVariable() {
  if (!singleVariable.value.trim()) return;
  try {
    busy.value = true;
    const res = await injectWorldlineVariable({
      session_id: sessionId.value,
      branch_id: branchId.value || undefined,
      variable: singleVariable.value.trim(),
    });
    feedback.value = res.data.message || "变量注入成功";
    singleVariable.value = "";
    await loadBranches();
  } catch (err) {
    error.value = err.message;
  } finally {
    busy.value = false;
  }
}

async function generateInspirationPlan() {
  if (!sessionId.value) return;
  try {
    inspirationBusy.value = true;
    const res = await generatePlotInspiration({
      session_id: sessionId.value,
      branch_id: branchId.value || undefined,
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

<style scoped>
.worldline-stage {
  display: grid;
  grid-template-columns: 400px minmax(0, 1fr);
  gap: var(--space-lg);
  height: calc(100vh - 120px);
}

.stage-controls {
  overflow-y: auto;
  padding-right: var(--space-xs);
}

.stage-performance {
  min-width: 0;
  overflow-y: auto;
}

.empty-stage {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: var(--space-xl);
  background: var(--bg-panel-soft);
  border-style: dashed;
}

.empty-icon { font-size: 64px; margin-bottom: var(--space-md); }

.timeline-container {
  padding: var(--space-md);
}

@media (max-width: 1200px) {
  .worldline-stage {
    grid-template-columns: 1fr;
    height: auto;
  }
}
</style>

