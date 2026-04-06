<template>
  <div class="writer-stage" :class="[workbenchMode, { 'manuscript-mode': viewMode === 'manuscript' || viewMode === 'outline' }]" :style="{ gridTemplateColumns: activeGridColumns }">
    <aside class="writer-panel writer-controls workbench-card">
      <!-- Manuscript TOC mode -->
      <ManuscriptTocPanel
        v-if="viewMode === 'manuscript'"
        :chapters="manuscriptChapterList"
        :selected-tag="manuscriptSelectedTag"
        :total-words="manuscriptTotalWords"
        :total-blocks="manuscriptBlocks.length"
        :untagged-count="manuscriptUntaggedCount"
        @jump="handleManuscriptJump"
        @create-chapter="handleCreateManuscriptChapter"
        @rename-chapter="handleRenameManuscriptChapter"
        @export="handleManuscriptExport"
        @back="switchViewMode('writing')"
      />
      <!-- Writing controls mode -->
      <template v-else>
      <p class="panel-status" :class="{ warning: !!error }">{{ error || message }}</p>

      <div class="writer-form">
        <div class="field">
          <label>项目</label>
          <n-select
            v-model:value="projectId"
            :options="projectSelectOptions"
            placeholder="请选择项目"
            clearable
            @update:value="handleProjectChange"
          />
        </div>

        <n-radio-group v-model:value="scopeType" @update:value="updateScopeType">
          <n-radio-button v-for="item in scopeOptions" :key="item.value" :value="item.value" :label="item.label" />
        </n-radio-group>

        <div v-if="scopeType === 'project_chapter'" class="inline-grid">
          <div class="field">
            <label>章节</label>
            <n-select
              v-model:value="chapterId"
              :options="chapterSelectOptions"
              placeholder="请选择章节"
              clearable
            />
          </div>
          <div class="field">
            <label>POV</label>
            <n-select
              v-model:value="povCharacter"
              :options="povSelectOptions"
              placeholder="请选择 POV"
              clearable
            />
          </div>
        </div>

        <div v-else class="inline-grid">
          <div class="field">
            <label>世界线会话</label>
            <n-select
              v-model:value="sessionId"
              :options="sessionSelectOptions"
              placeholder="请选择会话"
              clearable
              @update:value="handleSessionChange"
            />
          </div>
          <div class="field">
            <label>POV</label>
            <n-select
              v-model:value="povCharacter"
              :options="povSelectOptions"
              placeholder="请选择 POV"
              clearable
            />
          </div>
        </div>

        <div class="field">
          <label>场景焦点 <span class="label-hint">（可选）</span></label>
          <n-input v-model:value="sceneFocus" placeholder="例如：废塔残响、顾行舟现身" />
        </div>

        <!-- 任务类型切换 -->
        <div class="field">
          <label>任务类型</label>
          <n-radio-group v-model:value="taskType">
            <n-radio-button v-for="item in taskTypeOptions" :key="item.value" :value="item.value" :label="item.label" />
          </n-radio-group>
        </div>

        <!-- 写作预设选择 -->
        <div class="field">
          <label>写作风格预设</label>
          <div class="preset-selector">
            <n-select
              v-model:value="selectedPresetId"
              :options="presetSelectOptions"
              placeholder="选择预设"
            />
            <n-button size="small" @click="openPresetEditor(presets.find(p => p.preset_id === selectedPresetId))">编辑</n-button>
            <n-button size="small" @click="openPresetEditor(null)">新建</n-button>
          </div>
        </div>

        <div class="panel-actions">
          <n-button :disabled="busy || !projectId" :loading="busy" @click="refreshProjectData">刷新项目数据</n-button>
          <n-button :disabled="busy || !projectId" :loading="busy" @click="handleMigrate">迁移数据</n-button>
        </div>
      </div>

      <!-- 场景列表 -->
      <SceneListPanel
        v-if="chapterId"
        :scenes="scenes"
        :selected-scene-id="selectedSceneId"
        @select="handleSceneSelect"
        @add="handleAddScene"
        @delete="handleDeleteScene"
      />

      <!-- 审校规则编辑区 -->
      <div v-if="projectId" class="reviewer-rules-section">
        <div class="reviewer-rules-header" @click="reviewerRulesCollapsed = !reviewerRulesCollapsed">
          <span class="reviewer-rules-title">审校规则</span>
          <div class="reviewer-rules-badges">
            <span v-if="reviewerRulesIsCustom" class="memory-badge">自定义</span>
            <span class="collapse-arrow" :class="{ collapsed: reviewerRulesCollapsed }">&#9662;</span>
          </div>
        </div>
        <div v-show="!reviewerRulesCollapsed" class="reviewer-rules-body">
          <n-input
            v-model:value="reviewerRulesText"
            type="textarea"
            :rows="10"
            placeholder="输入审校规则提示词..."
          />
          <div class="reviewer-rules-actions">
            <n-button
              type="primary"
              :disabled="reviewerRulesSaving"
              :loading="reviewerRulesSaving"
              @click="handleSaveReviewerRules"
            >
              保存
            </n-button>
            <n-button
              :disabled="reviewerRulesSaving || !reviewerRulesIsCustom"
              @click="handleResetReviewerRules"
            >
              恢复默认
            </n-button>
          </div>
        </div>
      </div>

      </template>
    </aside>

    <main class="writer-panel writer-context workbench-card">
      <!-- Header bar: title + mode tabs -->
      <div class="writer-header-bar">
        <div class="writer-header-left">
          <span class="panel-kicker mono">WRITER</span>
          <h2 class="panel-title-inline title-ancient">工作台</h2>
          <span class="panel-hint">{{ projectId ? '' : '请选择项目' }}</span>
        </div>
        <n-radio-group :value="viewMode" @update:value="switchViewMode" size="small">
          <n-radio-button value="writing" label="写作" />
          <n-radio-button value="outline" label="大纲" />
          <n-radio-button value="manuscript" label="稿件" />
        </n-radio-group>
      </div>

      <!-- ═══ Manuscript prose view ═══ -->
      <ManuscriptProseView
        v-if="viewMode === 'manuscript'"
        ref="manuscriptProseRef"
        :blocks="manuscriptBlocks"
        @edit-save="handleManuscriptBlockSave"
        @delete="handleManuscriptBlockDelete"
      />

      <!-- ═══ Outline mode ═══ -->
      <div v-if="viewMode === 'outline'" class="outline-tab-container">
        <OutlineView
          v-if="chapterOutlineData && chapterOutlineData.length"
          :outline="chapterOutlineData"
          :chapter-id="chapterId"
          :project-id="projectId"
          :versions="outlineVersions"
          :preview-outline="outlinePreview"
          @save="handleOutlineSave"
          @load-versions="handleLoadVersions"
          @restore="handleOutlineRestore"
          @cancel-preview="outlinePreview = null; outlinePreviewVersionId = ''"
        />
        <p v-else class="panel-empty">
          当前章节暂无大纲。请在「写作」页签中选择「大纲」任务类型生成。
        </p>
      </div>

      <!-- ═══ Writing mode content ═══ -->
      <template v-if="viewMode === 'writing'">

      <!-- 上下文包折叠面板 -->
      <section v-if="contextPack" class="context-block collapsible-block">
        <div class="context-block-header clickable" @click="contextCollapsed = !contextCollapsed">
          <h3 class="context-block-title title-ancient">上下文包</h3>
          <div class="collapse-badges">
            <span class="memory-badge">必知 {{ contextPack.must_know.length }}</span>
            <span class="memory-badge warning-badge">风险 {{ contextPack.warnings.length }}</span>
            <span class="collapse-arrow" :class="{ collapsed: contextCollapsed }">▾</span>
          </div>
        </div>
        <div v-show="!contextCollapsed" class="context-sections">
          <div v-for="item in contextPack.must_know.slice(0, 4)" :key="item.item_id" class="context-mini-item">
            <span class="category-badge mini">{{ item.category }}</span>
            <span>{{ item.summary }}</span>
          </div>
          <div v-if="contextPack.must_know.length > 4" class="more-hint">
            +{{ contextPack.must_know.length - 4 }} 更多必知条目
          </div>
          <div v-if="historyRecentAnchors.length" class="history-recall-panel">
            <div class="context-subtitle">近章承接</div>
            <article
              v-for="item in historyRecentAnchors"
              :key="item.chapter_id || item.chapter_order"
              class="trace-item history-recall-card"
            >
              <div class="trace-topline">
                <span class="memory-badge">第{{ item.chapter_order }}章</span>
              </div>
              <div class="timeline-title">{{ item.title || `第${item.chapter_order}章` }}</div>
              <div class="trace-copy">{{ item.summary_text }}</div>
            </article>
          </div>
          <div v-if="historySelectionTrace.length" class="history-recall-panel">
            <div class="context-subtitle">长线回调来源</div>
            <article
              v-for="(item, index) in historySelectionTrace.slice(0, 6)"
              :key="`${item.source_ref || item.chapter_order}_${index}`"
              class="trace-item history-recall-card"
            >
              <div class="trace-topline">
                <span class="category-badge">{{ item.item_type || "history" }}</span>
                <span class="memory-badge">第{{ item.chapter_order }}章</span>
              </div>
              <div class="trace-copy">{{ item.summary_text }}</div>
              <div class="trace-meta">命中原因：{{ formatSelectionBecause(item.selected_because) }}</div>
            </article>
          </div>
        </div>
      </section>

      <!-- 稿件操作栏 -->
      <div v-if="projectId" class="manuscript-toolbar">
        <template v-if="agentSceneContent && draftPhase === 'done' && !outlineData">
          <n-select
            v-model:value="commitTargetChapterId"
            :options="commitChapterSelectOptions"
            placeholder="不归类"
            clearable
            style="max-width: 200px"
            size="small"
          />
          <n-button
            type="primary"
            size="small"
            :disabled="commitBusy"
            :loading="commitBusy"
            @click="handleCommitToManuscript()"
          >
            提交到稿件
          </n-button>
        </template>
        <n-button
          v-if="showContinueButton"
          size="small"
          @click="handleContinueNext()"
        >
          继续写下一段
        </n-button>
        <n-button
          v-if="commitDone && !worldUpdateBusy && !worldUpdateDone"
          size="small"
          type="info"
          @click="handleWorldUpdate()"
        >
          更新世界数据
        </n-button>
        <n-button
          v-if="worldUpdateBusy"
          size="small"
          type="info"
          :loading="true"
          disabled
        >
          世界数据更新中...
        </n-button>
        <span v-if="worldUpdateDone" class="world-update-done">
          {{ worldUpdateSummary }}
        </span>
      </div>

      <!-- 续写上下文面板 -->
      <ContinuationContextPanel
        v-if="continuationContext"
        :context="continuationContext"
      />

      <!-- 续写模式 banner -->
      <div v-if="taskType === 'continue' && continuationContext?.tail_text" class="continuation-banner">
        <span class="continuation-banner-label">续写模式</span>
        <span class="continuation-banner-excerpt">...{{ continuationContext.tail_text.slice(-80) }}</span>
      </div>

      <!-- 大纲视图 OR 场景编辑器 -->
      <section class="draft-output">
        <OutlineView
          v-if="outlineData"
          :outline="outlineData"
          :chapter-id="chapterId"
          :project-id="projectId"
          :versions="outlineVersions"
          :preview-outline="outlinePreview"
          @save="handleOutlineSave"
          @load-versions="handleLoadVersions"
          @restore="handleOutlineRestore"
          @cancel-preview="outlinePreview = null; outlinePreviewVersionId = ''"
        />
        <SceneEditor
          v-else
          :content="agentSceneContent"
          :streaming="agentStreaming"
          :readonly="agentStreaming"
          @update="handleSceneContentUpdate"
          @commit-selection="handleCommitSelection"
        />
      </section>

      <!-- 空态提示 -->
      <p v-if="draftPhase === 'idle' && !continuationContext" class="panel-empty">
        在下方输入框中描述你的创作意图，系统会自动收集上下文、角色记忆和文风，然后生成小说正文。
      </p>

      <!-- 创作者输入区 -->
      <div class="draft-input-area">
        <n-input
          v-model:value="authorInstruction"
          type="textarea"
          class="draft-input"
          :placeholder="inputPlaceholder"
          :rows="3"
          :disabled="draftPhase === 'writing' || draftPhase === 'collecting'"
          @keydown.ctrl.enter="handleAgentGenerate()"
          @keydown.meta.enter="handleAgentGenerate()"
        />
        <div class="draft-input-actions">
          <span class="input-hint mono">Ctrl+Enter 发送</span>
          <n-button
            type="primary"
            :disabled="!canGenerate"
            :loading="draftPhase === 'collecting' || draftPhase === 'writing'"
            @click="handleAgentGenerate()"
          >
            {{ generateButtonLabel }}
          </n-button>
        </div>
      </div>
      </template>
    </main>

    <aside v-show="viewMode === 'writing'" class="writer-panel writer-debug workbench-card" :class="{ 'debug-collapsed': debugCollapsed }">
      <n-button class="debug-collapse-toggle" quaternary @click="debugCollapsed = !debugCollapsed" :title="debugCollapsed ? '展开日志面板' : '收起日志面板'">
        <span class="debug-collapse-chevron" :class="{ flipped: debugCollapsed }"></span>
        <span v-if="debugCollapsed" class="debug-collapse-label-vertical">日志</span>
      </n-button>
      <div v-show="!debugCollapsed" class="debug-panel-content">
      <p class="panel-kicker mono">TRACE & LOG</p>
      <h2 class="panel-title title-ancient">来源与日志</h2>

      <div class="side-stack">
        <!-- Agent 时间线日志 -->
        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">Agent 时间线</h3>
          </div>
          <div v-if="agentTrace.orchestrator.status === 'idle' && !agentTrace.error" class="review-hint">生成正文后，这里会显示 Agent 的实时工作流程。</div>
          <div v-else ref="traceScrollRef" class="trace-scroll-container">
            <AgentTracePanel :state="agentTrace" />
          </div>
        </section>

        <!-- 记忆审校（保留原有功能） -->
        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">记忆审校</h3>
          </div>
          <div v-if="!selectedItem" class="review-hint">点选上下文包中的条目后，可在这里查看记忆时间线。</div>
          <template v-else>
            <div class="timeline-card">
              <div class="timeline-topline">
                <span class="category-badge">{{ selectedItem.category }}</span>
                <span class="memory-badge" :class="{ candidate: selectedItem.memory_layer === 'candidate' }">{{ selectedItem.memory_layer }}</span>
              </div>
              <div class="timeline-title">{{ selectedItem.summary }}</div>
              <div class="timeline-copy">{{ selectedItem.why_it_matters }}</div>
            </div>
            <div class="review-actions">
              <n-button :disabled="reviewBusy || !canLoadTimeline" :loading="reviewBusy" @click="loadSelectedTimeline">
                查看记忆时间线
              </n-button>
              <n-button type="primary" :disabled="reviewBusy || !activeCandidateMemoryId" :loading="reviewBusy" @click="adoptSelectedMemory">
                采纳为 Canon
              </n-button>
              <n-button :disabled="reviewBusy || !activeCandidateMemoryId" :loading="reviewBusy" @click="rejectSelectedMemory">
                驳回 Candidate
              </n-button>
            </div>
            <div v-if="timelineError" class="review-hint">{{ timelineError }}</div>
            <div v-if="memoryTimeline" class="side-stack">
              <div class="timeline-card">
                <div class="timeline-title">Subject · {{ memoryTimeline.subject }}</div>
                <div class="timeline-meta">版本数：{{ memoryTimeline.memories?.length || 0 }} · 事件数：{{ memoryTimeline.events?.length || 0 }}</div>
              </div>
              <div class="timeline-list">
                <article v-for="item in memoryTimeline.memories" :key="item.memory_id" class="timeline-card">
                  <div class="timeline-topline">
                    <span class="memory-badge" :class="{ candidate: item.memory_layer === 'candidate' }">{{ item.memory_layer }}</span>
                    <span class="category-badge">{{ item.status }}</span>
                  </div>
                  <div class="timeline-title">{{ item.summary }}</div>
                  <div class="timeline-meta">v{{ item.version }} · {{ item.updated_at || item.created_at }}</div>
                </article>
              </div>
            </div>
          </template>
        </section>
      </div>
      </div>
    </aside>

    <!-- 预设编辑弹窗 -->
    <PresetEditor
      :visible="presetEditorVisible"
      :preset="editingPreset"
      @save="handlePresetSave"
      @close="presetEditorVisible = false"
    />

    <!-- ManuscriptDrawer removed — use the "稿件" tab instead -->
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "vue";
import { useDialog, NSelect, NInput, NInputNumber, NRadioGroup, NRadioButton, NButton, NTag, NCheckbox } from "naive-ui";
import { Icon } from "@iconify/vue";

import {
  adoptArchiveMemory,
  getArchiveMemoryTimeline,
  rejectArchiveMemory,
} from "../api/archive.js";
import { getChapterContextOptions, getReviewerRules, saveReviewerRules } from "../api/novel.js";
import { getWorldlineAgents, listWorldlineSessions } from "../api/worldline.js";
import AgentTracePanel from "../components/AgentTracePanel.vue";
import SceneListPanel from "./writer/SceneListPanel.vue";
import PresetEditor from "./writer/PresetEditor.vue";
import SceneEditor from "./writer/SceneEditor.vue";
// ManuscriptDrawer removed — unified into "稿件" tab
import ManuscriptProseView from "./writer/ManuscriptProseView.vue";
import ManuscriptTocPanel from "./writer/ManuscriptTocPanel.vue";
import ContinuationContextPanel from "./writer/ContinuationContextPanel.vue";
import OutlineView from "./writer/OutlineView.vue";
import {
  runWriterAgent,
  getScenes,
  updateScene as updateSceneApi,
  deleteScene as deleteSceneApi,
  getPresets,
  createPreset,
  updatePreset,
  deletePreset,
  getChapters,
  migrateProject,
  commitToManuscript,
  getContinuationContext,
  updateChapter,
  getManuscript,
  updateManuscriptBlock,
  deleteManuscriptBlock,
  tagManuscriptBlocks,
  exportManuscript,
  getOutlineVersions,
  getOutlineVersion,
  restoreOutlineVersion,
  updateWorldData,
} from "../api/writerAgent.js";
import { useProjectCatalog } from "../composables/useProjectCatalog.js";
import { buildWriterWorkbenchColumns, resolveWriterWorkbenchMode } from "./writer/writerWorkbenchLayout.js";
import {
  deriveWriterDefaults,
  findContextItem,
  resolveWriterPovOptions,
} from "./writer/writerWorkbenchState.js";

const writerDialog = useDialog();

const scopeOptions = [
  { value: "project_chapter", label: "原著章节" },
  { value: "worldline_branch", label: "世界线分支" },
];

const { projects, refreshProjects } = useProjectCatalog();
const workbenchMode = ref(resolveWriterWorkbenchMode(window.innerWidth));
const projectId = ref("");
const scopeType = ref("project_chapter");
const chapterId = ref("");
const chapterOrder = ref(0);
const povCharacter = ref("");
const sceneFocus = ref("");
const sessionId = ref("");
const branchId = ref("main");
const chapterOptions = ref([]);
const projectPovs = ref([]);
const sessionOptions = ref([]);
const worldlineAgents = ref([]);
const contextPack = ref(null);
const contextCollapsed = ref(true);
const selectedItem = ref(null);
const memoryTimeline = ref(null);
const reviewBusy = ref(false);
const timelineError = ref("");
const busy = ref(false);
const message = ref("请选择项目，然后在输入框中开始创作");
const error = ref("");

// ─── 审校规则 ───
const reviewerRulesCollapsed = ref(true);
const reviewerRulesText = ref("");
const reviewerRulesDefault = ref("");
const reviewerRulesSaving = ref(false);
const reviewerRulesIsCustom = ref(false);

// ─── 正文生成状态 ───
const draftPhase = ref("idle"); // idle | collecting | writing | done
const authorInstruction = ref("");
const traceScrollRef = ref(null);
const draftAbortController = ref(null);

const agentTrace = reactive({
  orchestrator: { model: "", status: "idle", rounds: [], summary: null },
  writer: { model: "", status: "idle", wordCount: 0, elapsedMs: 0 },
  error: "",
});

function resetAgentTrace() {
  agentTrace.orchestrator = { model: "", status: "idle", rounds: [], summary: null };
  agentTrace.writer = { model: "", status: "idle", wordCount: 0, elapsedMs: 0 };
  agentTrace.error = "";
}

function ensureRound(roundNum) {
  while (agentTrace.orchestrator.rounds.length <= roundNum) {
    agentTrace.orchestrator.rounds.push({
      roundNum: agentTrace.orchestrator.rounds.length,
      thinking: null,
      toolCalls: [],
      promptSnapshot: null,
      elapsedMs: 0,
      status: "running",
      _thinkingExpanded: false,
      _promptExpanded: false,
    });
  }
  return agentTrace.orchestrator.rounds[roundNum];
}
const taskType = ref("write_scene"); // write_scene|continue|outline
const scenes = ref([]);
const selectedSceneId = ref("");
const presets = ref([]);
const selectedPresetId = ref("");
const presetEditorVisible = ref(false);
const editingPreset = ref(null);
const agentSceneContent = ref(""); // streaming content for SceneEditor
const agentStreaming = ref(false);
const debugCollapsed = ref(false); // right panel collapse state
const outlineData = ref(null); // structured outline from outline task (writing mode, generated)
const chapterOutlineData = ref(null); // outline loaded from DB (outline tab)
const outlineVersions = ref([]);
const outlinePreview = ref(null);
const outlinePreviewVersionId = ref("");
const involvedEntityIds = ref([]);

// ─── 稿件 (Manuscript) ───
const viewMode = ref("writing"); // writing | outline | manuscript
// manuscriptDrawerVisible removed — unified into "稿件" tab
const continuationContext = ref(null);
const showContinueButton = ref(false);
const lastCommittedBlockId = ref("");
const commitBusy = ref(false);
const commitDone = ref(false);
const commitTargetChapterId = ref("");
const worldUpdateBusy = ref(false);
const worldUpdateDone = ref(false);
const worldUpdateSummary = ref("");
const worldUpdateAbortController = ref(null);
const manuscriptBlocks = ref([]);
const manuscriptTotalWords = ref(0);
const manuscriptProseRef = ref(null);
const manuscriptSelectedTag = ref(null);

const taskTypeOptions = [
  { value: "write_scene", label: "写场景" },
  { value: "continue", label: "续写" },
  { value: "outline", label: "大纲" },
];


const gridTemplateColumns = computed(() => buildWriterWorkbenchColumns(workbenchMode.value));
const activeGridColumns = computed(() => {
  if (viewMode.value === "manuscript" || viewMode.value === "outline") {
    return workbenchMode.value === "desktop"
      ? "minmax(260px, 300px) minmax(0, 1fr)"
      : "1fr";
  }
  if (debugCollapsed.value && workbenchMode.value === "desktop") {
    return "minmax(280px, 340px) minmax(0, 1fr) 44px";
  }
  return gridTemplateColumns.value;
});

const manuscriptChapterList = computed(() => {
  const map = new Map();
  for (const b of manuscriptBlocks.value) {
    const tag = b.chapter_tag;
    if (!tag) continue;
    if (!map.has(tag)) map.set(tag, { tag, blockCount: 0, wordCount: 0 });
    const entry = map.get(tag);
    entry.blockCount++;
    entry.wordCount += b.word_count || 0;
  }
  return Array.from(map.values());
});

const manuscriptUntaggedCount = computed(() =>
  manuscriptBlocks.value.filter(b => !b.chapter_tag).length
);
const povOptions = computed(() => resolveWriterPovOptions(scopeType.value, projectPovs.value, worldlineAgents.value));
const canSubmit = computed(() => {
  if (!projectId.value || !povCharacter.value) {
    return false;
  }
  return scopeType.value === "worldline_branch" ? !!sessionId.value : !!(chapterId.value || chapterOrder.value);
});
const canGenerate = computed(() => {
  if (!canSubmit.value || !authorInstruction.value.trim()) return false;
  return draftPhase.value === "idle" || draftPhase.value === "done";
});
const inputPlaceholder = computed(() => {
  if (taskType.value === "continue" && continuationContext.value) {
    return "描述接下来的走向、情节转折或角色行动...";
  }
  return '描述你的创作意图，如"续写第三章开场，主角在废塔中发现暗门"...';
});
const generateButtonLabel = computed(() => {
  if (draftPhase.value === "collecting") return "收集中...";
  if (draftPhase.value === "writing") return "创作中...";
  return "开始创作";
});
const canLoadTimeline = computed(() => Boolean(selectedItem.value?.archive_id && (selectedItem.value?.normalized_subject || selectedItem.value?.source_ref)));
const activeCandidateMemoryId = computed(() => {
  const item = memoryTimeline.value?.memories?.find((entry) => entry.memory_layer === "candidate" && entry.status === "active");
  return item?.memory_id || "";
});
const historyRecentAnchors = computed(() => contextPack.value?.history_recall?.recent_anchors || []);
const historySelectionTrace = computed(() => contextPack.value?.history_recall?.selection_trace || []);

// ─── NSelect options arrays ───
const projectSelectOptions = computed(() =>
  projects.value.map(item => ({ label: `${item.name} · ${item.project_id}`, value: item.project_id }))
);
const chapterSelectOptions = computed(() =>
  chapterOptions.value.map(item => ({ label: `第${item.order}章 · ${item.title}`, value: item.chapter_id }))
);
const povSelectOptions = computed(() =>
  povOptions.value.map(item => ({ label: item, value: item }))
);
const sessionSelectOptions = computed(() =>
  sessionOptions.value.map(item => ({ label: item.label, value: item.session_id }))
);
const presetSelectOptions = computed(() =>
  presets.value.map(p => ({ label: p.name, value: p.preset_id }))
);
const commitChapterSelectOptions = computed(() =>
  chapterOptions.value.map(item => ({ label: `第${item.order}章 · ${item.title}`, value: item.chapter_id }))
);

watch(chapterId, async (newVal) => {
  if (newVal) {
    const chapter = chapterOptions.value.find(item => item.chapter_id === newVal);
    chapterOrder.value = chapter?.order || 0;
    await loadScenes();
    selectedSceneId.value = "";
    agentSceneContent.value = "";
  }
});

function handleResize() {
  workbenchMode.value = resolveWriterWorkbenchMode(window.innerWidth);
}

function formatSelectionBecause(reasons = []) {
  const labels = {
    pov: "POV 命中",
    scene_focus: "场景焦点命中",
    author_instruction: "创作指令命中",
    recency: "时间衰减保留",
  };
  return (Array.isArray(reasons) ? reasons : [])
    .map((item) => labels[item] || item)
    .join("、");
}

async function handleProjectChange() {
  contextPack.value = null;
  selectedItem.value = null;
  memoryTimeline.value = null;
  timelineError.value = "";
  draftPhase.value = "idle";
  resetAgentTrace();
  if (!projectId.value) {
    chapterOptions.value = [];
    projectPovs.value = [];
    sessionOptions.value = [];
    worldlineAgents.value = [];
    reviewerRulesText.value = "";
    reviewerRulesDefault.value = "";
    reviewerRulesIsCustom.value = false;
    return;
  }
  await refreshProjectData();
}

async function refreshProjectData() {
  if (!projectId.value) return;
  try {
    const [optionsResponse, sessionsResponse] = await Promise.all([
      getChapterContextOptions(projectId.value),
      listWorldlineSessions({ projectId: projectId.value }),
    ]);
    chapterOptions.value = optionsResponse.data?.chapters || [];
    projectPovs.value = optionsResponse.data?.pov_characters || [];
    const defaults = deriveWriterDefaults(optionsResponse.data || {});
    if (!chapterId.value && defaults.chapterId) {
      chapterId.value = defaults.chapterId;
      chapterOrder.value = defaults.chapterOrder;
    }
    if (!povCharacter.value && defaults.povCharacter) {
      povCharacter.value = defaults.povCharacter;
    }
    sessionOptions.value = (sessionsResponse.data?.sessions || []).map((item) => ({
      session_id: item.session_id,
      label: item.label || `${item.session_scope === "global" ? "全局" : "项目"} · ${item.session_id.slice(0, 8)}`,
    }));
    message.value = "项目数据已刷新";

    // 加载审校规则
    loadReviewerRules();

    // 加载预设和场景
    await loadPresets();
    if (chapterId.value) {
      await loadScenes();
    }
  } catch (err) {
    error.value = err.message || "读取项目上下文失败";
  }
}

// ─── 审校规则管理 ───
async function loadReviewerRules() {
  if (!projectId.value) return;
  try {
    const response = await getReviewerRules(projectId.value);
    const data = response.data || {};
    reviewerRulesDefault.value = data.default_prompt || "";
    reviewerRulesIsCustom.value = data.is_custom || false;
    reviewerRulesText.value = data.is_custom ? data.custom_prompt : data.default_prompt;
  } catch {
    // 静默失败，不影响主流程
  }
}

async function handleSaveReviewerRules() {
  if (!projectId.value || reviewerRulesSaving.value) return;
  try {
    reviewerRulesSaving.value = true;
    await saveReviewerRules(projectId.value, reviewerRulesText.value);
    reviewerRulesIsCustom.value = true;
    message.value = "审校规则已保存";
  } catch (err) {
    error.value = err.message || "保存审校规则失败";
  } finally {
    reviewerRulesSaving.value = false;
  }
}

async function handleResetReviewerRules() {
  if (!projectId.value || reviewerRulesSaving.value) return;
  try {
    reviewerRulesSaving.value = true;
    await saveReviewerRules(projectId.value, "");
    reviewerRulesText.value = reviewerRulesDefault.value;
    reviewerRulesIsCustom.value = false;
    message.value = "已恢复默认审校规则";
  } catch (err) {
    error.value = err.message || "恢复默认规则失败";
  } finally {
    reviewerRulesSaving.value = false;
  }
}

async function handleSessionChange() {
  worldlineAgents.value = [];
  if (!sessionId.value) return;
  try {
    const response = await getWorldlineAgents(sessionId.value, branchId.value);
    worldlineAgents.value = response.data?.agents || [];
    if (!povOptions.value.includes(povCharacter.value)) {
      povCharacter.value = povOptions.value[0] || "";
    }
  } catch (err) {
    error.value = err.message || "读取世界线角色失败";
  }
}

function updateScopeType(value) {
  scopeType.value = value;
  selectedItem.value = null;
  memoryTimeline.value = null;
  timelineError.value = "";
  if (value === "project_chapter" && !povOptions.value.includes(povCharacter.value)) {
    povCharacter.value = projectPovs.value[0] || "";
  }
  if (value === "worldline_branch" && sessionId.value) {
    void handleSessionChange();
  }
}

// ─── 正文生成 ───
function selectContextItem(item) {
  selectedItem.value = item;
  memoryTimeline.value = null;
  timelineError.value = "";
}

async function loadSelectedTimeline() {
  if (!canLoadTimeline.value) return;
  try {
    reviewBusy.value = true;
    timelineError.value = "";
    const response = await getArchiveMemoryTimeline(selectedItem.value.archive_id, {
      normalizedSubject: selectedItem.value.normalized_subject,
      memoryId: selectedItem.value.source_kind === "agent_memory" ? selectedItem.value.source_ref : "",
    });
    memoryTimeline.value = response.data;
  } catch (err) {
    timelineError.value = err.message || "读取时间线失败";
  } finally {
    reviewBusy.value = false;
  }
}

async function adoptSelectedMemory() {
  if (!activeCandidateMemoryId.value || !selectedItem.value?.archive_id) return;
  try {
    reviewBusy.value = true;
    timelineError.value = "";
    await adoptArchiveMemory(selectedItem.value.archive_id, activeCandidateMemoryId.value);
    if (selectedItem.value?.archive_id) {
      await loadSelectedTimeline();
    }
  } catch (err) {
    timelineError.value = err.message || "采纳失败";
  } finally {
    reviewBusy.value = false;
  }
}

async function rejectSelectedMemory() {
  if (!activeCandidateMemoryId.value || !selectedItem.value?.archive_id) return;
  try {
    reviewBusy.value = true;
    timelineError.value = "";
    await rejectArchiveMemory(selectedItem.value.archive_id, activeCandidateMemoryId.value);
    if (selectedItem.value?.archive_id) {
      await loadSelectedTimeline();
    }
  } catch (err) {
    timelineError.value = err.message || "驳回失败";
  } finally {
    reviewBusy.value = false;
  }
}

// ─── 场景管理 ───
async function loadScenes() {
  if (!projectId.value || !chapterId.value) {
    scenes.value = [];
    return;
  }
  try {
    const response = await getScenes(chapterId.value, projectId.value);
    scenes.value = response.data || [];
  } catch {
    scenes.value = [];
  }
}

async function handleSceneSelect(sceneId) {
  selectedSceneId.value = sceneId;
  const scene = scenes.value.find(s => s.scene_id === sceneId);
  if (scene) {
    agentSceneContent.value = scene.content || "";
  }
}

async function handleAddScene() {
  if (!chapterId.value) return;
  const nextOrder = scenes.value.length > 0
    ? Math.max(...scenes.value.map(s => s.scene_order)) + 1
    : 1;
  // Scene will be created when agent writes to it
  const newSceneId = `sc_${Date.now().toString(36)}`;
  scenes.value.push({
    scene_id: newSceneId,
    scene_order: nextOrder,
    title: `场景 ${nextOrder}`,
    word_count: 0,
    status: "draft",
    content: "",
  });
  selectedSceneId.value = newSceneId;
  agentSceneContent.value = "";
}

function handleDeleteScene(sceneId) {
  writerDialog.warning({
    title: "确认删除",
    content: "确定删除此场景？",
    positiveText: "删除",
    negativeText: "取消",
    async onPositiveClick() {
      try {
        await deleteSceneApi(sceneId, projectId.value);
        scenes.value = scenes.value.filter(s => s.scene_id !== sceneId);
        if (selectedSceneId.value === sceneId) {
          selectedSceneId.value = "";
          agentSceneContent.value = "";
        }
      } catch (err) {
        error.value = err.message || "删除场景失败";
      }
    },
  });
}

async function handleSceneContentUpdate(newContent) {
  agentSceneContent.value = newContent;
  if (selectedSceneId.value && projectId.value) {
    try {
      await updateSceneApi(selectedSceneId.value, {
        project_id: projectId.value,
        content: newContent,
      });
      const scene = scenes.value.find(s => s.scene_id === selectedSceneId.value);
      if (scene) {
        scene.word_count = newContent.length;
      }
    } catch {
      // silent save failure
    }
  }
}

// ─── 预设管理 ───
async function loadPresets() {
  try {
    const response = await getPresets(projectId.value);
    presets.value = response.data || [];
    if (!selectedPresetId.value && presets.value.length) {
      const defaultPreset = presets.value.find(p => p.is_default);
      selectedPresetId.value = (defaultPreset || presets.value[0]).preset_id;
    }
  } catch {
    presets.value = [];
  }
}

function openPresetEditor(preset = null) {
  editingPreset.value = preset;
  presetEditorVisible.value = true;
}

async function handlePresetSave(data) {
  try {
    if (data.preset_id) {
      await updatePreset(data.preset_id, {
        ...data,
        project_id: projectId.value,
      });
    } else {
      const result = await createPreset({
        ...data,
        project_id: projectId.value,
      });
      selectedPresetId.value = result.data?.preset_id || selectedPresetId.value;
    }
    presetEditorVisible.value = false;
    await loadPresets();
  } catch (err) {
    error.value = err.message || "保存预设失败";
  }
}

function handlePresetDelete(presetId) {
  writerDialog.warning({
    title: "确认删除",
    content: "确定删除此预设？",
    positiveText: "删除",
    negativeText: "取消",
    async onPositiveClick() {
      try {
        await deletePreset(presetId, projectId.value);
        await loadPresets();
      } catch (err) {
        error.value = err.message || "删除预设失败";
      }
    },
  });
}

// ─── Shared trace event handlers ───
function handleTraceEvent(event) {
  if (event.type === "orchestrator_status") {
    agentTrace.orchestrator.status = "running";
    if (event.model) {
      if (event.phase === "writing") {
        agentTrace.writer.model = event.model;
        agentTrace.writer.status = "running";
      } else {
        agentTrace.orchestrator.model = event.model;
      }
    }
    draftPhase.value = event.phase === "writing" ? "writing" : "collecting";
    message.value = event.message || "编排中...";
  } else if (event.type === "thinking") {
    const round = ensureRound(event.round ?? Math.max(0, agentTrace.orchestrator.rounds.length - 1));
    round.thinking = event.content;
  } else if (event.type === "tool_call") {
    const round = ensureRound(event.round ?? Math.max(0, agentTrace.orchestrator.rounds.length - 1));
    round.toolCalls.push({
      name: event.name,
      display: event.display || event.name,
      input: event.input,
      summary: null,
      fullResult: null,
      status: "pending",
      toolElapsedMs: 0,
      _expanded: false,
    });
  } else if (event.type === "tool_result") {
    const round = ensureRound(event.round ?? Math.max(0, agentTrace.orchestrator.rounds.length - 1));
    const tc = round.toolCalls.find(t => t.name === event.name && t.status === "pending");
    if (tc) {
      tc.summary = event.summary;
      tc.fullResult = event.full_result || event.summary;
      tc.status = event.status === "error" ? "error" : "done";
      tc.toolElapsedMs = event.tool_elapsed_ms || 0;
    }
  } else if (event.type === "prompt_snapshot") {
    const roundNum = event.round ?? 0;
    const round = ensureRound(roundNum);
    const charCount = (event.messages || []).reduce((sum, m) => sum + (m.content?.length || 0), 0);
    round.promptSnapshot = { messages: event.messages, charCount };
    round.elapsedMs = event.elapsed_ms || 0;
  } else if (event.type === "phase_summary") {
    agentTrace.orchestrator.rounds.forEach(r => { r.status = "done"; });
    agentTrace.orchestrator.status = "done";
    agentTrace.orchestrator.summary = {
      toolCount: event.tool_count || 0,
      roundCount: agentTrace.orchestrator.rounds.length,
      elapsedMs: event.elapsed_ms || 0,
      tokenUsage: event.token_usage || null,
    };
  } else if (event.type === "writer_token") {
    draftPhase.value = "writing";
    agentTrace.writer.status = "running";
    agentSceneContent.value += (event.token || "");
    agentTrace.writer.wordCount = agentSceneContent.value.length;
  } else if (event.type === "outline_ready") {
    draftPhase.value = "done";
    outlineData.value = event.outline;
  } else if (event.type === "error") {
    error.value = event.message || "生成失败";
    agentStreaming.value = false;
    draftPhase.value = agentSceneContent.value ? "done" : "idle";
    agentTrace.error = event.message || "生成失败";
  }
}

function handleTraceDone(event) {
  agentStreaming.value = false;
  draftPhase.value = "done";
  agentTrace.writer.status = "done";
  agentTrace.writer.elapsedMs = event.elapsed_ms || 0;
  if (event.outline_saved) {
    message.value = `大纲已保存：${event.scene_count} 个场景`;
    return;
  }
  const wc = event.word_count || agentSceneContent.value.length;
  message.value = `创作完成：${wc} 字`;
  agentTrace.writer.wordCount = wc;
  commitTargetChapterId.value = chapterId.value || "";
  loadScenes();
}

// ─── Writer Agent 生成 ───
async function handleAgentGenerate() {
  if (!projectId.value) return;

  error.value = "";
  agentStreaming.value = true;
  agentSceneContent.value = "";
  outlineData.value = null;
  draftPhase.value = "collecting";
  resetAgentTrace();
  commitDone.value = false;
  if (worldUpdateAbortController.value) {
    worldUpdateAbortController.value.abort();
    worldUpdateAbortController.value = null;
  }
  worldUpdateBusy.value = false;
  worldUpdateDone.value = false;
  worldUpdateSummary.value = "";

  const chapter = chapterOptions.value.find(item => item.chapter_id === chapterId.value);
  const currentSceneOrder = scenes.value.find(s => s.scene_id === selectedSceneId.value)?.scene_order || 1;

  const payload = {
    project_id: projectId.value,
    task_type: taskType.value,
    chapter_id: chapterId.value,
    chapter_order: chapter?.order || chapterOrder.value,
    scene_order: currentSceneOrder,
    pov_entity_id: povCharacter.value,
    involved_entity_ids: involvedEntityIds.value,
    scene_focus: sceneFocus.value,
    user_instruction: authorInstruction.value,
    preset_id: selectedPresetId.value,
    session_id: sessionId.value,
    selected_text: "",
    scene_id: selectedSceneId.value,
    last_block_id: taskType.value === "continue" ? lastCommittedBlockId.value : "",
  };

  if (draftAbortController.value) {
    draftAbortController.value.abort();
  }
  draftAbortController.value = new AbortController();

  await runWriterAgent(
    payload,
    {
      onEvent: handleTraceEvent,
      onDone: handleTraceDone,
      onError(event) {
        agentStreaming.value = false;
        draftPhase.value = agentSceneContent.value ? "done" : "idle";
        error.value = event?.message || event?.toString() || "生成失败";
      },
    },
    draftAbortController.value.signal,
  );
}

watch(
  () => agentTrace.orchestrator.rounds.length + agentTrace.writer.wordCount,
  () => {
    nextTick(() => {
      const el = traceScrollRef.value;
      if (el) el.scrollTop = el.scrollHeight;
    });
  },
);

// ─── 大纲保存 ───
async function handleOutlineSave(outline, label = "") {
  if (!projectId.value || !chapterId.value) {
    error.value = "请先选择项目和章节";
    return;
  }
  try {
    await updateChapter(chapterId.value, {
      project_id: projectId.value,
      outline_json: JSON.stringify(outline),
      outline_label: label,
    });
    if (viewMode.value === "outline") {
      chapterOutlineData.value = outline;
    } else {
      outlineData.value = outline;
    }
    message.value = "大纲已保存";
    error.value = "";
  } catch (err) {
    error.value = err.message || "保存大纲失败";
  }
}

async function handleLoadVersions(versionId) {
  if (!projectId.value || !chapterId.value) return;
  try {
    if (!versionId) {
      const resp = await getOutlineVersions(chapterId.value, projectId.value);
      outlineVersions.value = resp.data || [];
      return;
    }
    const resp = await getOutlineVersion(chapterId.value, versionId, projectId.value);
    const ver = resp.data;
    if (ver?.outline_json) {
      const parsed = typeof ver.outline_json === "string" ? JSON.parse(ver.outline_json) : ver.outline_json;
      outlinePreview.value = Array.isArray(parsed) ? parsed : null;
      outlinePreviewVersionId.value = versionId;
    }
    error.value = "";
  } catch (err) {
    error.value = err.message || "加载版本失败";
  }
}

async function handleOutlineRestore() {
  if (!outlinePreviewVersionId.value || !projectId.value || !chapterId.value) return;
  try {
    await restoreOutlineVersion(chapterId.value, outlinePreviewVersionId.value, projectId.value);
    outlinePreview.value = null;
    outlinePreviewVersionId.value = "";
    if (viewMode.value === "outline") {
      await loadChapterOutline();
    } else {
      const chapters = await getChapters(projectId.value);
      const list = chapters.data || chapters;
      const ch = list.find(c => c.chapter_id === chapterId.value);
      if (ch?.outline_json) {
        outlineData.value = typeof ch.outline_json === "string" ? JSON.parse(ch.outline_json) : ch.outline_json;
      }
    }
    const resp = await getOutlineVersions(chapterId.value, projectId.value);
    outlineVersions.value = resp.data || [];
    message.value = "已回退到历史版本";
    error.value = "";
  } catch (err) {
    error.value = err.message || "回退失败";
  }
}

// ─── 稿件操作 ───
async function handleCommitToManuscript(content = null) {
  if (!projectId.value) return;
  const text = content || agentSceneContent.value;
  if (!text.trim()) return;
  // Resolve chapter tag from commit target selector (or current chapter as fallback)
  const targetId = commitTargetChapterId.value || chapterId.value;
  const chapter = targetId ? chapterOptions.value.find(item => item.chapter_id === targetId) : null;
  const chapterTag = chapter ? `第${chapter.order}章 · ${chapter.title}` : undefined;
  try {
    commitBusy.value = true;
    const commitResult = await commitToManuscript(projectId.value, {
      content: text,
      source_scene_id: selectedSceneId.value || undefined,
      chapter_tag: chapterTag,
    });
    const blockData = commitResult?.data || commitResult;
    if (blockData?.block_id) {
      lastCommittedBlockId.value = blockData.block_id;
    }
    message.value = chapterTag ? `已提交到稿件 [${chapterTag}]` : "已提交到稿件";
    showContinueButton.value = true;
    commitDone.value = true;
  } catch (err) {
    error.value = err.message || "提交到稿件失败";
  } finally {
    commitBusy.value = false;
  }
}

async function handleCommitSelection(selectedText) {
  await handleCommitToManuscript(selectedText);
}

async function handleContinueNext() {
  // Clear workspace and load continuation context
  agentSceneContent.value = "";
  draftPhase.value = "idle";
  showContinueButton.value = false;
  taskType.value = "continue";

  try {
    const res = await getContinuationContext(projectId.value, {
      lastBlockId: lastCommittedBlockId.value,
    });
    continuationContext.value = res.data || res;
  } catch (err) {
    error.value = err.message || "加载续写上下文失败";
  }
}

async function handleWorldUpdate() {
  if (!projectId.value || !agentSceneContent.value) return;
  // Abort any previous world update
  if (worldUpdateAbortController.value) {
    worldUpdateAbortController.value.abort();
  }
  worldUpdateAbortController.value = new AbortController();
  resetAgentTrace();
  worldUpdateBusy.value = true;
  worldUpdateDone.value = false;
  worldUpdateSummary.value = "";
  try {
    await updateWorldData(
      {
        project_id: projectId.value,
        content: agentSceneContent.value,
        chapter_order: chapterOrder.value || 0,
      },
      {
        onEvent: handleTraceEvent,
        onDone(event) {
          worldUpdateBusy.value = false;
          worldUpdateDone.value = true;
          worldUpdateSummary.value = "世界数据已更新";
          agentTrace.orchestrator.status = "done";
        },
        onError(event) {
          worldUpdateBusy.value = false;
          error.value = event.message || "世界数据更新失败";
        },
      },
      worldUpdateAbortController.value.signal,
    );
  } catch (err) {
    worldUpdateBusy.value = false;
    error.value = err.message || "世界数据更新失败";
  }
}

function handleManuscriptUpdated() {
  // Refresh continuation context if it's visible
  if (continuationContext.value) {
    getContinuationContext(projectId.value, {
      lastBlockId: lastCommittedBlockId.value,
    }).then(res => {
      continuationContext.value = res.data || res;
    }).catch(() => {});
  }
  // Refresh manuscript view if active
  if (viewMode.value === "manuscript") {
    loadManuscriptBlocks();
  }
}

// ─── 稿件模式 ───
async function loadManuscriptBlocks() {
  if (!projectId.value) {
    manuscriptBlocks.value = [];
    manuscriptTotalWords.value = 0;
    return;
  }
  try {
    const res = await getManuscript(projectId.value);
    const payload = res.data || res;
    manuscriptBlocks.value = payload.blocks || [];
    manuscriptTotalWords.value = payload.total_words || 0;
  } catch (e) {
    console.error("Failed to load manuscript", e);
  }
}

function switchViewMode(mode) {
  viewMode.value = mode;
  if (mode === "manuscript") {
    loadManuscriptBlocks();
  } else if (mode === "outline") {
    loadChapterOutline();
  }
}

async function loadChapterOutline() {
  if (!projectId.value || !chapterId.value) {
    chapterOutlineData.value = null;
    return;
  }
  try {
    const chapters = await getChapters(projectId.value);
    const list = chapters.data || chapters;
    const ch = list.find(c => c.chapter_id === chapterId.value);
    if (ch && ch.outline_json) {
      const parsed = typeof ch.outline_json === "string" ? JSON.parse(ch.outline_json) : ch.outline_json;
      chapterOutlineData.value = Array.isArray(parsed) ? parsed : null;
    } else {
      chapterOutlineData.value = null;
    }
  } catch (e) {
    console.error("Failed to load chapter outline", e);
    chapterOutlineData.value = null;
  }
}

function handleManuscriptJump(tag) {
  manuscriptSelectedTag.value = tag;
  if (tag && manuscriptProseRef.value) {
    manuscriptProseRef.value.scrollToChapter(tag);
  }
}

async function handleManuscriptBlockSave(block, newContent) {
  try {
    await updateManuscriptBlock(block.block_id, {
      project_id: projectId.value,
      content: newContent,
    });
  } catch (e) {
    console.error("Manuscript block save failed", e);
  }
}

function handleManuscriptBlockDelete(blockId) {
  writerDialog.warning({
    title: "确认删除",
    content: "确定要删除这段稿件内容吗？此操作不可撤销。",
    positiveText: "删除",
    negativeText: "取消",
    onPositiveClick: async () => {
      try {
        await deleteManuscriptBlock(blockId, projectId.value);
        await loadManuscriptBlocks();
        message.value = "稿件段落已删除";
      } catch (e) {
        error.value = e.message || "删除稿件失败";
      }
    },
  });
}

function handleCreateManuscriptChapter(name) {
  // Chapter is just a tag — it will appear once a block is tagged with it.
  // For now, we create a placeholder by tagging the first untagged block,
  // or just show the name for future use.
  // Since chapters are just tags on blocks, there's nothing to persist
  // until blocks are committed. We just note it for the UI.
  message.value = `章节「${name}」已创建，提交内容时将自动归入此章节`;
}

async function handleRenameManuscriptChapter(oldTag, newTag) {
  // Re-tag all blocks with oldTag to newTag
  const blockIds = manuscriptBlocks.value
    .filter(b => b.chapter_tag === oldTag)
    .map(b => b.block_id);
  if (!blockIds.length) return;
  try {
    await tagManuscriptBlocks(projectId.value, {
      block_ids: blockIds,
      chapter_tag: newTag,
    });
    await loadManuscriptBlocks();
    message.value = `章节已重命名: ${oldTag} → ${newTag}`;
  } catch (e) {
    error.value = e.message || "重命名章节失败";
  }
}

async function handleManuscriptExport(fmt) {
  try {
    const blob = await exportManuscript(projectId.value, fmt);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `manuscript.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    error.value = e.message || "导出失败";
  }
}

// ─── 数据迁移 ───
async function handleMigrate() {
  if (!projectId.value) return;
  try {
    busy.value = true;
    message.value = "正在迁移数据到 novel.sqlite3...";
    await migrateProject(projectId.value);
    message.value = "数据迁移完成";
    await loadScenes();
    await loadPresets();
  } catch (err) {
    error.value = err.message || "迁移失败";
  } finally {
    busy.value = false;
  }
}

onMounted(async () => {
  window.addEventListener("resize", handleResize);
  try {
    await refreshProjects();
  } catch (err) {
    error.value = err.message || "读取项目列表失败";
  }
});

onUnmounted(() => {
  window.removeEventListener("resize", handleResize);
  if (draftAbortController.value) {
    draftAbortController.value.abort();
  }
});
</script>

<style scoped src="./WriterWorkbenchView.css"></style>
