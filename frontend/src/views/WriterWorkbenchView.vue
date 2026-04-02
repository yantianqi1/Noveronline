<template>
  <div class="writer-stage" :class="workbenchMode" :style="{ gridTemplateColumns: gridTemplateColumns }">
    <aside class="writer-panel writer-controls workbench-card">
      <p class="panel-kicker mono">WRITER CONTEXT</p>
      <h2 class="panel-title title-ancient">写作工作台</h2>
      <p class="panel-subtitle">选择范围与 POV，然后在输入框中开始创作。</p>
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

        <label class="inline-check">
          <input v-model="includeCandidates" type="checkbox" />
          <span>附带 candidate 设定</span>
        </label>

        <div class="panel-actions">
          <button class="btn" :disabled="busy || !projectId" @click="refreshProjectData">刷新项目数据</button>
        </div>
      </div>

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
    </aside>

    <main class="writer-panel writer-context workbench-card">
      <p class="panel-kicker mono">NOVEL DRAFT</p>
      <h2 class="panel-title title-ancient">创作与正文</h2>

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

      <!-- Agent 进度面板 -->
      <AgentProgressPanel
        v-if="draftPhase !== 'idle'"
        :agents="agentPhases"
        :revision-count="revisionCount"
        :unresolved-issues="unresolvedIssues"
        :final-score="finalScore"
      />

      <!-- 生成的正文显示区 -->
      <section v-if="draftText" class="draft-output">
        <!-- 可编辑模式 -->
        <textarea
          v-if="isEditable"
          v-model="draftText"
          class="draft-text draft-text-editable"
          ref="draftTextRef"
        ></textarea>
        <!-- 只读模式（流式接收中） -->
        <div v-else class="draft-text" ref="draftTextRef">{{ draftText }}</div>
        <div v-if="draftResult" class="draft-meta mono">
          {{ draftText.length }} 字 · {{ draftResult.model_name || '模型' }} · {{ draftResult.elapsed_seconds }}s
          <span v-if="isEditable" class="draft-editable-hint">（可直接编辑正文）</span>
        </div>
      </section>

      <!-- 审校暂停态：操作区 -->
      <section v-if="draftPhase === 'review_paused'" class="review-paused-actions">
        <div class="review-paused-hint">审校发现问题，请查看下方审校报告后选择操作</div>
        <div class="review-paused-buttons">
          <button class="btn primary" @click="handleRevise">继续修订</button>
          <button class="btn" @click="handleAcceptDraft">接受当前版本</button>
        </div>
      </section>

      <!-- 审校报告（内联于中间列，获得更大宽度） -->
      <section v-if="reviewResult" class="context-block review-report-block review-report-inline">
        <div class="context-block-header">
          <h3 class="context-block-title title-ancient">审校报告</h3>
          <div class="review-header-badges">
            <span class="memory-badge" :class="{ 'warning-badge': reviewResult.issues?.length }">
              {{ reviewResult.issues?.length || 0 }} 项
            </span>
            <span v-if="reviewResult.score != null" class="memory-badge" :class="reviewResult.pass ? '' : 'warning-badge'">
              {{ reviewResult.pass ? '通过' : '未通过' }} · {{ reviewResult.score }}分
            </span>
          </div>
        </div>

        <!-- 总体评价 -->
        <div class="review-overall" v-if="isEditable" @click="$event.target.tagName === 'DIV' && $refs.overallInput?.focus()">
          <textarea
            ref="overallInput"
            v-model="reviewResult.overall_assessment"
            class="review-inline-edit review-overall-text"
            rows="2"
          ></textarea>
        </div>
        <div v-else class="review-overall">
          <div class="review-overall-text">{{ reviewResult.overall_assessment }}</div>
        </div>

        <!-- 问题列表 -->
        <div v-if="reviewResult.issues?.length" class="review-issues-list review-issues-grid">
          <div
            v-for="(issue, index) in reviewResult.issues"
            :key="index"
            class="review-issue-card"
            :class="'severity-' + (issue.severity || 'medium')"
          >
            <!-- 问题头部：维度 + 严重度 + 操作 -->
            <div class="review-issue-header">
              <span v-if="!isEditable" class="review-issue-dimension">{{ issue.dimension || '其他' }}</span>
              <input
                v-else
                v-model="issue.dimension"
                class="review-inline-edit review-issue-dimension-edit"
                placeholder="维度"
              />
              <div class="review-issue-header-right">
                <span v-if="!isEditable" class="review-issue-severity-tag" :class="'tag-' + issue.severity">
                  {{ { high: '严重', medium: '建议', low: '轻微' }[issue.severity] || issue.severity }}
                </span>
                <select v-else v-model="issue.severity" class="review-severity-select" :class="'tag-' + issue.severity">
                  <option value="high">严重</option>
                  <option value="medium">建议</option>
                  <option value="low">轻微</option>
                </select>
                <button
                  v-if="isEditable"
                  class="review-issue-delete"
                  @click="reviewResult.issues.splice(index, 1)"
                  title="删除"
                >&times;</button>
              </div>
            </div>

            <!-- 问题描述 -->
            <div class="review-issue-body">
              <textarea
                v-if="isEditable"
                v-model="issue.description"
                class="review-inline-edit review-issue-desc"
                rows="1"
                placeholder="问题描述..."
              ></textarea>
              <div v-else class="review-issue-desc">{{ issue.description }}</div>
            </div>

            <!-- 修改建议 -->
            <div v-if="issue.suggestion || isEditable" class="review-issue-suggestion">
              <span class="review-suggestion-label">建议：</span>
              <textarea
                v-if="isEditable"
                v-model="issue.suggestion"
                class="review-inline-edit review-issue-suggestion-text"
                rows="1"
                placeholder="修改建议..."
              ></textarea>
              <span v-else class="review-issue-suggestion-text">{{ issue.suggestion }}</span>
            </div>
          </div>
        </div>
        <div v-else class="review-hint">未发现一致性问题。</div>

        <!-- 保留建议 -->
        <div v-if="reviewResult.keep?.length" class="review-keep-section">
          <div class="review-keep-title">值得保留</div>
          <div v-for="(item, i) in reviewResult.keep" :key="'k' + i" class="review-keep-item">{{ item }}</div>
        </div>
      </section>

      <!-- 空态提示 -->
      <p v-if="draftPhase === 'idle' && !draftText" class="panel-empty">
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
          @keydown.ctrl.enter="handleGenerate"
          @keydown.meta.enter="handleGenerate"
        ></textarea>
        <div class="draft-input-actions">
          <span class="input-hint mono">Ctrl+Enter 发送</span>
          <button
            class="btn primary"
            :disabled="!canGenerate"
            @click="handleGenerate"
          >
            {{ generateButtonLabel }}
          </button>
          <button
            v-if="draftText && draftPhase === 'done'"
            class="btn"
            @click="copyDraftText"
          >
            复制正文
          </button>
        </div>
      </div>
    </main>

    <aside class="writer-panel writer-debug workbench-card">
      <p class="panel-kicker mono">TRACE & LOG</p>
      <h2 class="panel-title title-ancient">来源与日志</h2>

      <div class="side-stack">
        <!-- Agent 运行日志 -->
        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">Agent 日志</h3>
          </div>
          <div v-if="!agentLog.length" class="review-hint">生成正文后，这里会显示各 Agent 的运行情况。</div>
          <div v-else class="trace-list">
            <article v-for="(entry, index) in agentLog" :key="index" class="trace-item">
              <div class="trace-topline">
                <span class="category-badge">{{ entry.agent }}</span>
              </div>
              <div class="trace-copy">{{ entry.message }}</div>
            </article>
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
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";

import {
  adoptArchiveMemory,
  getArchiveMemoryTimeline,
  rejectArchiveMemory,
} from "../api/archive.js";
import { buildChapterContext, generateDraft, getChapterContextOptions, getReviewerRules, reviseDraft, saveReviewerRules } from "../api/novel.js";
import { getWorldlineAgents, listWorldlineSessions } from "../api/worldline.js";
import AgentProgressPanel from "../components/AgentProgressPanel.vue";
import { useProjectCatalog } from "../composables/useProjectCatalog.js";
import { buildWriterWorkbenchColumns, resolveWriterWorkbenchMode } from "./writer/writerWorkbenchLayout.js";
import {
  buildWriterRequestPayload,
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
const draftPhase = ref("idle"); // idle | collecting | writing | reviewing | review_paused | done
const draftText = ref("");
const draftResult = ref(null);
const reviewResult = ref(null);
const authorInstruction = ref("");
const agentLog = ref([]);
const agentPhases = ref([]);
const draftAbortController = ref(null);
const draftTextRef = ref(null);
const previousDraftText = ref(""); // 用于修订模式
const revisionCount = ref(0);
const unresolvedIssues = ref([]);
const finalScore = ref(null);
// 上下文快照（用于修订时重用）
const contextPackSnapshot = ref(null);
const memoryBundleSnapshot = ref(null);
const styleHintsSnapshot = ref(null);

const gridTemplateColumns = computed(() => buildWriterWorkbenchColumns(workbenchMode.value));
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
  if (draftText.value && draftPhase.value === "done") {
    return '输入修订意见，如"对话不够紧张，加重冲突感"...';
  }
  return '描述你的创作意图，如"续写第三章开场，主角在废塔中发现暗门"...';
});
const generateButtonLabel = computed(() => {
  if (draftPhase.value === "collecting") return "收集中...";
  if (draftPhase.value === "writing") return "创作中...";
  if (draftPhase.value === "reviewing") return "审校中...";
  if (draftPhase.value === "review_paused") return "审校中...";
  if (draftText.value && draftPhase.value === "done") return "修订再生成";
  return "开始创作";
});
const isEditable = computed(() => draftPhase.value === "done" || draftPhase.value === "review_paused");
const canLoadTimeline = computed(() => Boolean(selectedItem.value?.archive_id && (selectedItem.value?.normalized_subject || selectedItem.value?.source_ref)));
const activeCandidateMemoryId = computed(() => {
  const item = memoryTimeline.value?.memories?.find((entry) => entry.memory_layer === "candidate" && entry.status === "active");
  return item?.memory_id || "";
});
const historyRecentAnchors = computed(() => contextPack.value?.history_recall?.recent_anchors || []);
const historySelectionTrace = computed(() => contextPack.value?.history_recall?.selection_trace || []);

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
  draftText.value = "";
  draftResult.value = null;
  reviewResult.value = null;
  draftPhase.value = "idle";
  agentLog.value = [];
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
      label: `${item.session_scope === "global" ? "全局" : "项目"} · ${item.session_id.slice(0, 8)} · ${item.current_world?.title || "当前世界"}`,
    }));
    message.value = "项目数据已刷新";

    // 加载审校规则
    loadReviewerRules();
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

async function handleGenerate() {
  if (!canGenerate.value) return;

  const isRevision = !!(draftText.value && draftPhase.value === "done");

  // 准备请求
  const chapter = chapterOptions.value.find((item) => item.chapter_id === chapterId.value);
  chapterOrder.value = chapter?.order || chapterOrder.value;
  const payload = {
    ...buildWriterRequestPayload({
      scopeType: scopeType.value,
      projectId: projectId.value,
      chapterId: chapterId.value,
      chapterOrder: chapterOrder.value,
      sessionId: sessionId.value,
      branchId: branchId.value,
      povCharacter: povCharacter.value,
      writingGoal: "",
      sceneFocus: sceneFocus.value,
      includeCandidates: includeCandidates.value,
    }),
    author_instruction: authorInstruction.value,
  };

  if (isRevision) {
    payload.revision_context = {
      previous_text: draftText.value,
      revision_instruction: authorInstruction.value,
    };
  }

  // 重置状态
  previousDraftText.value = isRevision ? draftText.value : "";
  draftText.value = "";
  draftResult.value = null;
  reviewResult.value = null;
  error.value = "";
  draftPhase.value = "collecting";
  agentLog.value = [];
  revisionCount.value = 0;
  unresolvedIssues.value = [];
  finalScore.value = null;
  initAgentPhases();

  // 取消之前的请求
  if (draftAbortController.value) {
    draftAbortController.value.abort();
  }
  draftAbortController.value = new AbortController();

  await generateDraft(
    payload,
    {
      onEvent(event) {
        if (event.type === "agent_status") {
          // 新的标准 Agent 状态事件
          updateAgentStatus(event.agent, event.status, event.message, event.detail);
          if (event.status === "done" || event.status === "error") {
            agentLog.value.push({
              agent: event.agent,
              message: event.message,
            });
          }
          // 处理 error 状态作为终止信号
          if (event.status === "error") {
            draftPhase.value = draftText.value ? "done" : "idle";
            error.value = event.message || "Agent 执行失败";
          }
        } else if (event.type === "text_clear") {
          // 审校打回重写时，清空已有文本，避免追加
          draftText.value = "";
        } else if (event.type === "context_ready") {
          contextPack.value = event.context_pack || contextPack.value;
          contextCollapsed.value = true;
        } else if (event.type === "text_chunk") {
          // 兼容新旧格式：新格式 data.chunk, 旧格式 content
          const chunk = event.data?.chunk || event.content || "";
          if (chunk) {
            draftText.value += chunk;
            nextTick(() => {
              if (draftTextRef.value) {
                draftTextRef.value.scrollTop = draftTextRef.value.scrollHeight;
              }
            });
          }
        } else if (event.type === "phase") {
          // 向后兼容旧格式
          if (event.phase === "writing") {
            draftPhase.value = "writing";
          } else if (event.phase === "review") {
            draftPhase.value = "reviewing";
          } else {
            draftPhase.value = "collecting";
          }
        } else if (event.type === "agent_done") {
          // 向后兼容旧格式
          agentLog.value.push({
            agent: event.agent,
            message: event.message,
          });
        }
      },
      onDone(event) {
        draftResult.value = event;
        reviewResult.value = event.review || null;
        revisionCount.value = event.revision_count || 0;
        unresolvedIssues.value = event.data?.unresolved_issues || [];
        finalScore.value = event.review?.score ?? null;

        // 保存上下文快照，用于后续修订
        if (event.context_summary) {
          contextPackSnapshot.value = contextPack.value;
        }

        // 审校暂停式逻辑：审校不通过时暂停，等待用户操作
        const reviewPassed = event.review?.pass !== false;
        if (reviewPassed) {
          draftPhase.value = "done";
        } else {
          draftPhase.value = "review_paused";
        }

        // 标记所有 agent 为 done
        for (const p of agentPhases.value) {
          if (p.status !== "done" && p.status !== "error") {
            p.status = "done";
          }
        }
        const revisionNote = revisionCount.value > 0 ? `，修订 ${revisionCount.value} 次` : "";
        const statusLabel = reviewPassed ? "创作完成" : "审校完成（待修订）";
        message.value = `${statusLabel}：${event.char_count} 字${revisionNote}`;
        authorInstruction.value = "";
      },
      onError(event) {
        draftPhase.value = draftText.value ? "done" : "idle";
        const msg = event?.message || event?.toString() || "生成失败";
        error.value = msg;
      },
    },
    draftAbortController.value.signal,
  );
}

// ─── 审校暂停式修订 ───
function buildRevisionInstruction() {
  // 从审校报告构造修订指令
  if (!reviewResult.value?.issues?.length) return "请优化正文";
  const lines = ["请根据以下审校意见修改正文：", ""];
  for (const issue of reviewResult.value.issues) {
    const severity = { high: "【必须修改】", medium: "【建议修改】", low: "【可选】" }[issue.severity] || "【修改】";
    lines.push(`${severity}[${issue.dimension || "其他"}] ${issue.description}`);
    if (issue.suggestion) lines.push(`   建议：${issue.suggestion}`);
  }
  if (reviewResult.value.keep?.length) {
    lines.push("", "以下部分请保留：");
    for (const item of reviewResult.value.keep) {
      lines.push(`- ${item}`);
    }
  }
  return lines.join("\n");
}

async function handleRevise() {
  if (!draftText.value || draftPhase.value !== "review_paused") return;

  const payload = {
    project_id: projectId.value,
    previous_text: draftText.value,
    revision_instruction: buildRevisionInstruction(),
    author_instruction: authorInstruction.value || "",
    context_pack_snapshot: contextPackSnapshot.value || {},
    memory_bundle_snapshot: memoryBundleSnapshot.value || {},
    style_hints_snapshot: styleHintsSnapshot.value || {},
  };

  // 重置进度
  draftText.value = "";
  draftResult.value = null;
  error.value = "";
  draftPhase.value = "writing";
  initAgentPhases();
  // 只保留 writer + reviewer
  agentPhases.value = agentPhases.value.filter((a) =>
    ["writer_agent", "reviewer_agent"].includes(a.id),
  );

  if (draftAbortController.value) {
    draftAbortController.value.abort();
  }
  draftAbortController.value = new AbortController();

  await reviseDraft(
    payload,
    {
      onEvent(event) {
        if (event.type === "agent_status") {
          updateAgentStatus(event.agent, event.status, event.message, event.detail);
          if (event.status === "done" || event.status === "error") {
            agentLog.value.push({ agent: event.agent, message: event.message });
          }
          if (event.status === "error") {
            draftPhase.value = draftText.value ? "done" : "idle";
            error.value = event.message || "修订失败";
          }
        } else if (event.type === "text_clear") {
          draftText.value = "";
        } else if (event.type === "text_chunk") {
          const chunk = event.data?.chunk || event.content || "";
          if (chunk) {
            draftText.value += chunk;
            nextTick(() => {
              if (draftTextRef.value) {
                draftTextRef.value.scrollTop = draftTextRef.value.scrollHeight;
              }
            });
          }
        }
      },
      onDone(event) {
        draftResult.value = event;
        reviewResult.value = event.review || null;
        revisionCount.value += (event.revision_count || 0);
        unresolvedIssues.value = event.data?.unresolved_issues || [];
        finalScore.value = event.review?.score ?? null;

        const reviewPassed = event.review?.pass !== false;
        draftPhase.value = reviewPassed ? "done" : "review_paused";

        for (const p of agentPhases.value) {
          if (p.status !== "done" && p.status !== "error") {
            p.status = "done";
          }
        }
        const statusLabel = reviewPassed ? "修订完成" : "修订审校完成（待继续修订）";
        message.value = `${statusLabel}：${event.char_count} 字`;
        authorInstruction.value = "";
      },
      onError(event) {
        draftPhase.value = draftText.value ? "done" : "idle";
        error.value = event?.message || event?.toString() || "修订失败";
      },
    },
    draftAbortController.value.signal,
  );
}

function handleAcceptDraft() {
  draftPhase.value = "done";
  message.value = `已接受当前版本：${draftText.value.length} 字`;
}

function copyDraftText() {
  if (draftText.value) {
    navigator.clipboard.writeText(draftText.value).then(() => {
      message.value = "正文已复制到剪贴板";
    });
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
