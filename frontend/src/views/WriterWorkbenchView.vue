<template>
  <div class="writer-stage" :class="[workbenchMode, { 'manuscript-mode': viewMode === 'manuscript' }]" :style="{ gridTemplateColumns: activeGridColumns }">
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
      />
      <!-- Writing controls mode -->
      <template v-else>
      <p class="panel-status" :class="{ warning: !!error }">{{ error || message }}</p>

      <div class="writer-form">
        <div class="field">
          <label>项目</label>
          <select v-model="projectId" @change="handleProjectChange">
            <option value="">请选择项目</option>
            <option v-for="item in projects" :key="item.project_id" :value="item.project_id">
              {{ item.name }} · {{ item.project_id }}
            </option>
          </select>
        </div>

        <div class="scope-switch">
          <button
            v-for="item in scopeOptions"
            :key="item.value"
            type="button"
            class="scope-chip"
            :class="{ active: scopeType === item.value }"
            @click="updateScopeType(item.value)"
          >
            {{ item.label }}
          </button>
        </div>

        <div v-if="scopeType === 'project_chapter'" class="inline-grid">
          <div class="field">
            <label>章节</label>
            <select v-model="chapterId">
              <option value="">请选择章节</option>
              <option v-for="item in chapterOptions" :key="item.chapter_id" :value="item.chapter_id">
                第{{ item.order }}章 · {{ item.title }}
              </option>
            </select>
          </div>
          <div class="field">
            <label>POV</label>
            <select v-model="povCharacter">
              <option value="">请选择 POV</option>
              <option v-for="item in povOptions" :key="item" :value="item">{{ item }}</option>
            </select>
          </div>
        </div>

        <div v-else class="inline-grid">
          <div class="field">
            <label>世界线会话</label>
            <select v-model="sessionId" @change="handleSessionChange">
              <option value="">请选择会话</option>
              <option v-for="item in sessionOptions" :key="item.session_id" :value="item.session_id">
                {{ item.label }}
              </option>
            </select>
          </div>
          <div class="field">
            <label>POV</label>
            <select v-model="povCharacter">
              <option value="">请选择 POV</option>
              <option v-for="item in povOptions" :key="item" :value="item">{{ item }}</option>
            </select>
          </div>
        </div>

        <div class="field">
          <label>场景焦点 <span class="label-hint">（可选）</span></label>
          <input v-model="sceneFocus" type="text" placeholder="例如：废塔残响、顾行舟现身" />
        </div>

        <!-- 任务类型切换 -->
        <div class="field">
          <label>任务类型</label>
          <div class="scope-switch">
            <button
              v-for="item in taskTypeOptions"
              :key="item.value"
              type="button"
              class="scope-chip"
              :class="{ active: taskType === item.value }"
              @click="taskType = item.value"
            >
              {{ item.label }}
            </button>
          </div>
        </div>

        <!-- 写作预设选择 -->
        <div class="field">
          <label>写作风格预设</label>
          <div class="preset-selector">
            <select v-model="selectedPresetId">
              <option v-for="p in presets" :key="p.preset_id" :value="p.preset_id">
                {{ p.name }}
              </option>
            </select>
            <button class="btn btn-sm" @click="openPresetEditor(presets.find(p => p.preset_id === selectedPresetId))">编辑</button>
            <button class="btn btn-sm" @click="openPresetEditor(null)">新建</button>
          </div>
        </div>

        <label class="inline-check">
          <input v-model="includeCandidates" type="checkbox" />
          <span>附带 candidate 设定</span>
        </label>

        <div class="panel-actions">
          <button class="btn" :disabled="busy || !projectId" @click="refreshProjectData">刷新项目数据</button>
          <button class="btn" :disabled="busy || !projectId" @click="handleMigrate">迁移数据</button>
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
          <textarea
            v-model="reviewerRulesText"
            class="reviewer-rules-textarea"
            rows="10"
            placeholder="输入审校规则提示词..."
          ></textarea>
          <div class="reviewer-rules-actions">
            <button
              class="btn primary"
              :disabled="reviewerRulesSaving"
              @click="handleSaveReviewerRules"
            >
              {{ reviewerRulesSaving ? '保存中...' : '保存' }}
            </button>
            <button
              class="btn"
              :disabled="reviewerRulesSaving || !reviewerRulesIsCustom"
              @click="handleResetReviewerRules"
            >
              恢复默认
            </button>
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
        <div class="view-mode-tabs">
          <button
            class="view-mode-tab"
            :class="{ active: viewMode === 'writing' }"
            @click="switchViewMode('writing')"
          >写作</button>
          <button
            class="view-mode-tab"
            :class="{ active: viewMode === 'manuscript' }"
            @click="switchViewMode('manuscript')"
          >稿件</button>
        </div>
      </div>

      <!-- ═══ Manuscript prose view ═══ -->
      <ManuscriptProseView
        v-if="viewMode === 'manuscript'"
        ref="manuscriptProseRef"
        :blocks="manuscriptBlocks"
        @edit-save="handleManuscriptBlockSave"
      />

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
        <button
          v-if="agentSceneContent && draftPhase === 'done'"
          class="btn btn-sm primary"
          :disabled="commitBusy"
          @click="handleCommitToManuscript()"
        >
          {{ commitBusy ? '提交中...' : '提交到稿件' }}
        </button>
        <button
          v-if="showContinueButton"
          class="btn btn-sm"
          @click="handleContinueNext()"
        >
          继续写下一段
        </button>
      </div>

      <!-- 续写上下文面板 -->
      <ContinuationContextPanel
        v-if="continuationContext"
        :context="continuationContext"
      />

      <!-- Agent 进度面板 -->
      <AgentProgressPanel
        v-if="draftPhase !== 'idle'"
        :agents="agentPhases"
        :revision-count="revisionCount"
        :unresolved-issues="unresolvedIssues"
        :final-score="finalScore"
      />

      <!-- 续写模式 banner -->
      <div v-if="taskType === 'continue' && continuationContext?.tail_text" class="continuation-banner">
        <span class="continuation-banner-label">续写模式</span>
        <span class="continuation-banner-excerpt">...{{ continuationContext.tail_text.slice(-80) }}</span>
      </div>

      <!-- 场景编辑器 -->
      <section class="draft-output">
        <SceneEditor
          :content="agentSceneContent"
          :streaming="agentStreaming"
          :readonly="agentStreaming"
          @update="handleSceneContentUpdate"
          @rewrite="handleRewriteFromEditor"
          @expand="handleExpandFromEditor"
          @commit-selection="handleCommitSelection"
        />
      </section>

      <!-- 空态提示 -->
      <p v-if="draftPhase === 'idle' && !continuationContext" class="panel-empty">
        在下方输入框中描述你的创作意图，系统会自动收集上下文、角色记忆和文风，然后生成小说正文。
      </p>

      <!-- 创作者输入区 -->
      <div class="draft-input-area">
        <textarea
          v-model="authorInstruction"
          class="draft-input"
          :placeholder="inputPlaceholder"
          rows="3"
          :disabled="draftPhase === 'writing' || draftPhase === 'collecting'"
          @keydown.ctrl.enter="handleAgentGenerate()"
          @keydown.meta.enter="handleAgentGenerate()"
        ></textarea>
        <div class="draft-input-actions">
          <span class="input-hint mono">Ctrl+Enter 发送</span>
          <button
            class="btn primary"
            :disabled="!canGenerate"
            @click="handleAgentGenerate()"
          >
            {{ generateButtonLabel }}
          </button>
        </div>
      </div>
      </template>
    </main>

    <aside v-show="viewMode === 'writing'" class="writer-panel writer-debug workbench-card">
      <p class="panel-kicker mono">TRACE & LOG</p>
      <h2 class="panel-title title-ancient">来源与日志</h2>

      <div class="side-stack">
        <!-- Agent 时间线日志 -->
        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">Agent 时间线</h3>
          </div>
          <div v-if="!agentTimeline.length" class="review-hint">生成正文后，这里会显示 Agent 的实时工作流程。</div>
          <div v-else ref="timelineScrollRef" class="timeline-log">
            <template v-for="entry in agentTimeline" :key="entry.id">
              <!-- Prompt snapshot: collapsible -->
              <div v-if="entry.type === 'prompt_snapshot'" class="tl-prompt-block">
                <div class="tl-line tl-prompt_snapshot" @click="entry.collapsed = !entry.collapsed">
                  <span class="tl-ts">{{ entry.ts }}</span>
                  <span class="tl-icon">{{ entry.collapsed ? '▶' : '▼' }}</span>
                  <span class="tl-body">{{ promptSnapshotLabel(entry) }}</span>
                </div>
                <div v-if="!entry.collapsed" class="tl-prompt-detail">
                  <div
                    v-for="(msg, mIdx) in entry.messages"
                    :key="mIdx"
                    class="tl-prompt-msg"
                  >
                    <div class="tl-prompt-role">{{ msg.role }}</div>
                    <pre class="tl-prompt-content">{{ msg.content }}</pre>
                  </div>
                </div>
              </div>
              <!-- Normal timeline entry -->
              <div v-else class="tl-line" :class="'tl-' + entry.type">
                <span class="tl-ts">{{ entry.ts }}</span>
                <span class="tl-icon">{{ timelineIcon(entry.type) }}</span>
                <span class="tl-body">{{ timelineBody(entry) }}</span>
              </div>
            </template>
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
              <button class="btn" :disabled="reviewBusy || !canLoadTimeline" @click="loadSelectedTimeline">
                {{ reviewBusy ? "读取中..." : "查看记忆时间线" }}
              </button>
              <button class="btn primary" :disabled="reviewBusy || !activeCandidateMemoryId" @click="adoptSelectedMemory">
                采纳为 Canon
              </button>
              <button class="btn" :disabled="reviewBusy || !activeCandidateMemoryId" @click="rejectSelectedMemory">
                驳回 Candidate
              </button>
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
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";

import {
  adoptArchiveMemory,
  getArchiveMemoryTimeline,
  rejectArchiveMemory,
} from "../api/archive.js";
import { getChapterContextOptions, getReviewerRules, saveReviewerRules } from "../api/novel.js";
import { getWorldlineAgents, listWorldlineSessions } from "../api/worldline.js";
import AgentProgressPanel from "../components/AgentProgressPanel.vue";
import SceneListPanel from "./writer/SceneListPanel.vue";
import PresetEditor from "./writer/PresetEditor.vue";
import SceneEditor from "./writer/SceneEditor.vue";
// ManuscriptDrawer removed — unified into "稿件" tab
import ManuscriptProseView from "./writer/ManuscriptProseView.vue";
import ManuscriptTocPanel from "./writer/ManuscriptTocPanel.vue";
import ContinuationContextPanel from "./writer/ContinuationContextPanel.vue";
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
  getManuscript,
  updateManuscriptBlock,
  tagManuscriptBlocks,
  exportManuscript,
} from "../api/writerAgent.js";
import { useProjectCatalog } from "../composables/useProjectCatalog.js";
import { buildWriterWorkbenchColumns, resolveWriterWorkbenchMode } from "./writer/writerWorkbenchLayout.js";
import {
  deriveWriterDefaults,
  findContextItem,
  resolveWriterPovOptions,
} from "./writer/writerWorkbenchState.js";

const scopeOptions = [
  { value: "project_chapter", label: "原著章节" },
  { value: "worldline_branch", label: "世界线分支" },
];

const AGENT_DEFS = [
  { id: "context_agent", label: "上下文收集" },
  { id: "memory_agent", label: "记忆检索" },
  { id: "style_agent", label: "风格分析" },
  { id: "writer_agent", label: "正文创作" },
  { id: "reviewer_agent", label: "一致性审校" },
];

const { projects, refreshProjects } = useProjectCatalog();
const workbenchMode = ref(resolveWriterWorkbenchMode(window.innerWidth));
const projectId = ref("");
const scopeType = ref("project_chapter");
const chapterId = ref("");
const chapterOrder = ref(0);
const povCharacter = ref("");
const sceneFocus = ref("");
const includeCandidates = ref(false);
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
const agentTimeline = ref([]);
let timelineIdCounter = 0;
const timelineScrollRef = ref(null);
const agentPhases = ref([]);
const draftAbortController = ref(null);
const revisionCount = ref(0);
const unresolvedIssues = ref([]);
const finalScore = ref(null);
const taskType = ref("write_scene"); // write_scene|continue|rewrite|expand|outline|consistency_check
const scenes = ref([]);
const selectedSceneId = ref("");
const presets = ref([]);
const selectedPresetId = ref("");
const presetEditorVisible = ref(false);
const editingPreset = ref(null);
const agentSceneContent = ref(""); // streaming content for SceneEditor
const agentStreaming = ref(false);
const involvedEntityIds = ref([]);

// ─── 稿件 (Manuscript) ───
const viewMode = ref("writing"); // writing | manuscript
// manuscriptDrawerVisible removed — unified into "稿件" tab
const continuationContext = ref(null);
const showContinueButton = ref(false);
const lastCommittedBlockId = ref("");
const commitBusy = ref(false);
const manuscriptBlocks = ref([]);
const manuscriptTotalWords = ref(0);
const manuscriptProseRef = ref(null);
const manuscriptSelectedTag = ref(null);

const taskTypeOptions = [
  { value: "write_scene", label: "写场景" },
  { value: "continue", label: "续写" },
  { value: "rewrite", label: "改写" },
  { value: "expand", label: "扩写" },
  { value: "outline", label: "大纲" },
  { value: "consistency_check", label: "一致性检查" },
];


const gridTemplateColumns = computed(() => buildWriterWorkbenchColumns(workbenchMode.value));
const activeGridColumns = computed(() => {
  if (viewMode.value === "manuscript") {
    return workbenchMode.value === "desktop"
      ? "minmax(260px, 300px) minmax(0, 1fr)"
      : "1fr";
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
  agentTimeline.value = [];
  timelineIdCounter = 0;
  agentPhases.value = [];
  revisionCount.value = 0;
  unresolvedIssues.value = [];
  finalScore.value = null;
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
function initAgentPhases() {
  agentPhases.value = AGENT_DEFS.map((def) => ({
    ...def,
    status: "pending",
    message: "",
    issues: null,
    issuesExpanded: false,
    detail: null,
    detailExpanded: false,
  }));
}

function updateAgentStatus(agentId, status, agentMessage = "", detail = null) {
  const agent = agentPhases.value.find((a) => a.id === agentId);
  if (agent) {
    agent.status = status;
    agent.message = agentMessage;
    if (detail?.issues?.length) {
      agent.issues = detail.issues;
    }
    if (detail) {
      agent.detail = detail;
    }
  }
  // 更新 draftPhase based on agent status
  if (agentId === "writer_agent" && status === "running") {
    draftPhase.value = "writing";
  } else if (agentId === "reviewer_agent" && status === "running") {
    draftPhase.value = "reviewing";
  } else if (["context_agent", "memory_agent", "style_agent"].includes(agentId) && status === "running") {
    draftPhase.value = "collecting";
  }
}

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

async function handleDeleteScene(sceneId) {
  if (!confirm("确定删除此场景？")) return;
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

async function handlePresetDelete(presetId) {
  if (!confirm("确定删除此预设？")) return;
  try {
    await deletePreset(presetId, projectId.value);
    await loadPresets();
  } catch (err) {
    error.value = err.message || "删除预设失败";
  }
}

// ─── Writer Agent 生成 ───
async function handleAgentGenerate() {
  if (!projectId.value) return;

  error.value = "";
  agentStreaming.value = true;
  agentSceneContent.value = "";
  draftPhase.value = "collecting";
  agentTimeline.value = [];
  timelineIdCounter = 0;

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
    selected_text: taskType.value === "rewrite" || taskType.value === "expand"
      ? (window.getSelection()?.toString() || agentSceneContent.value)
      : "",
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
      onEvent(event) {
        if (event.type === "orchestrator_status") {
          draftPhase.value = event.phase === "writing" ? "writing" : "collecting";
          message.value = event.message || "编排中...";
          agentTimeline.value.push({
            id: timelineIdCounter++,
            type: "status",
            ts: event.ts || "",
            elapsedMs: event.elapsed_ms,
            message: event.message,
          });
        } else if (event.type === "thinking") {
          agentTimeline.value.push({
            id: timelineIdCounter++,
            type: "thinking",
            ts: event.ts || "",
            elapsedMs: event.elapsed_ms,
            content: event.content,
          });
        } else if (event.type === "tool_call") {
          agentTimeline.value.push({
            id: timelineIdCounter++,
            type: "tool_call",
            ts: event.ts || "",
            elapsedMs: event.elapsed_ms,
            name: event.name,
            display: event.display || event.name,
          });
        } else if (event.type === "tool_result") {
          agentTimeline.value.push({
            id: timelineIdCounter++,
            type: "tool_result",
            ts: event.ts || "",
            elapsedMs: event.elapsed_ms,
            name: event.name,
            summary: event.summary,
          });
        } else if (event.type === "prompt_snapshot") {
          agentTimeline.value.push({
            id: timelineIdCounter++,
            type: "prompt_snapshot",
            ts: event.ts || "",
            elapsedMs: event.elapsed_ms,
            phase: event.phase,
            round: event.round,
            messages: event.messages,
            collapsed: true,
          });
        } else if (event.type === "phase_summary") {
          agentTimeline.value.push({
            id: timelineIdCounter++,
            type: "summary",
            ts: event.ts || "",
            elapsedMs: event.elapsed_ms,
            message: event.message,
          });
        } else if (event.type === "writer_token") {
          draftPhase.value = "writing";
          agentSceneContent.value += (event.token || "");
          const last = agentTimeline.value[agentTimeline.value.length - 1];
          if (last?.type === "writing") {
            last.wordCount = agentSceneContent.value.length;
          } else {
            agentTimeline.value.push({
              id: timelineIdCounter++,
              type: "writing",
              ts: "",
              wordCount: agentSceneContent.value.length,
            });
          }
        } else if (event.type === "error") {
          error.value = event.message || "生成失败";
          agentStreaming.value = false;
          draftPhase.value = agentSceneContent.value ? "done" : "idle";
          agentTimeline.value.push({
            id: timelineIdCounter++,
            type: "error",
            ts: event.ts || "",
            message: event.message,
          });
        }
      },
      onDone(event) {
        agentStreaming.value = false;
        draftPhase.value = "done";
        const wc = event.word_count || agentSceneContent.value.length;
        message.value = `创作完成：${wc} 字`;
        agentTimeline.value.push({
          id: timelineIdCounter++,
          type: "done",
          ts: event.ts || "",
          elapsedMs: event.elapsed_ms,
          message: `${wc} 字`,
        });
        loadScenes();
      },
      onError(event) {
        agentStreaming.value = false;
        draftPhase.value = agentSceneContent.value ? "done" : "idle";
        error.value = event?.message || event?.toString() || "生成失败";
      },
    },
    draftAbortController.value.signal,
  );
}

// ─── 时间线日志 helpers ───
const _tlIcons = {
  status: "●", thinking: "💭", tool_call: "↗", tool_result: "↙",
  summary: "■", writing: "✍", done: "✓", error: "✗",
};
function timelineIcon(type) {
  return _tlIcons[type] || "·";
}
function promptSnapshotLabel(entry) {
  const phase = entry.phase === "writer" ? "写作层" : "编排层";
  const round = entry.round > 0 ? ` (第${entry.round + 1}轮)` : "";
  const charCount = entry.messages.reduce((sum, m) => sum + (m.content?.length || 0), 0);
  return `${phase}完整提示词${round} — ${charCount} 字`;
}
function timelineBody(entry) {
  switch (entry.type) {
    case "status": case "summary": case "error":
      return entry.message || "";
    case "thinking": {
      const c = entry.content || "";
      return c.length > 80 ? c.slice(0, 80) + "..." : c;
    }
    case "tool_call":
      return entry.display || entry.name;
    case "tool_result": {
      const s = entry.summary || "";
      const t = s.length > 60 ? s.slice(0, 60) + "..." : s;
      return `${entry.name} → ${t}`;
    }
    case "writing":
      return `streaming ${entry.wordCount || 0} 字`;
    case "done":
      return `创作完成 (${((entry.elapsedMs || 0) / 1000).toFixed(1)}s, ${entry.message || "?"})`;
    default:
      return "";
  }
}

watch(() => agentTimeline.value.length, () => {
  nextTick(() => {
    const el = timelineScrollRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
});

// ─── 改写/扩写 ───
function handleRewriteFromEditor(selectedText) {
  taskType.value = "rewrite";
  authorInstruction.value = `请改写以下文本：\n${selectedText}`;
}

function handleExpandFromEditor(selectedText) {
  taskType.value = "expand";
  authorInstruction.value = `请扩写以下文本：\n${selectedText}`;
}

// ─── 稿件操作 ───
async function handleCommitToManuscript(content = null) {
  if (!projectId.value) return;
  const text = content || agentSceneContent.value;
  if (!text.trim()) return;
  // Resolve chapter tag from current selection
  const chapter = chapterOptions.value.find(item => item.chapter_id === chapterId.value);
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
