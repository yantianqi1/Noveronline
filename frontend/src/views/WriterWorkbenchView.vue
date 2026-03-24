<template>
  <div class="writer-stage" :class="workbenchMode" :style="{ gridTemplateColumns: gridTemplateColumns }">
    <aside class="writer-panel writer-controls workbench-card">
      <p class="panel-kicker mono">WRITER CONTEXT</p>
      <h2 class="panel-title title-ancient">写作工作台</h2>
      <p class="panel-subtitle">先选写作范围，再生成可直接喂给作者 Agent 的上下文包。</p>
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
          <label>写作目标</label>
          <input v-model="writingGoal" type="text" placeholder="例如：生成本章场景卡 / 生成章节大纲" />
        </div>

        <div class="field">
          <label>场景焦点</label>
          <textarea v-model="sceneFocus" rows="4" placeholder="例如：废塔残响、顾行舟现身、镜湖谷公开对峙"></textarea>
        </div>

        <label class="inline-check">
          <input v-model="includeCandidates" type="checkbox" />
          <span>附带 candidate 设定</span>
        </label>

        <div class="panel-actions">
          <button class="btn primary" :disabled="busy || !canSubmit" @click="generatePack">
            {{ busy ? "生成中..." : "生成上下文包" }}
          </button>
          <button class="btn" :disabled="busy || !projectId" @click="refreshProjectData">刷新项目数据</button>
        </div>
      </div>
    </aside>

    <main class="writer-panel writer-context workbench-card">
      <p class="panel-kicker mono">CHAPTER CONTEXT PACK</p>
      <h2 class="panel-title title-ancient">上下文与 Prompt</h2>
      <p v-if="!contextPack" class="panel-empty">生成后会在这里显示 `must_know`、`warnings`、候选场景和稳定 prompt。</p>

      <div v-else class="context-sections">
        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">范围</h3>
            <span class="memory-badge">{{ contextPack.context_scope.scope_type }}</span>
          </div>
          <div class="context-list">
            <div class="context-item">
              <div class="context-summary">
                {{ contextScopeSummary }}
              </div>
              <div class="context-why">
                目标：{{ contextPack.context_scope.writing_goal || "未填写" }}；焦点：{{ contextPack.context_scope.scene_focus || "未填写" }}
              </div>
            </div>
          </div>
        </section>

        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">必须知道</h3>
            <span class="memory-badge">{{ contextPack.must_know.length }}</span>
          </div>
          <div class="context-list">
            <article
              v-for="item in contextPack.must_know"
              :key="item.item_id"
              class="context-item clickable"
              :class="{ active: selectedItem?.item_id === item.item_id }"
              @click="selectContextItem(item)"
            >
              <div class="context-topline">
                <span class="category-badge">{{ item.category }}</span>
                <span class="memory-badge" :class="{ candidate: item.memory_layer === 'candidate' }">{{ item.memory_layer }}</span>
              </div>
              <div class="context-summary">{{ item.summary }}</div>
              <div class="context-why">{{ item.why_it_matters }}</div>
            </article>
          </div>
        </section>

        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">应该知道</h3>
            <span class="memory-badge">{{ contextPack.should_know.length }}</span>
          </div>
          <div class="context-list">
            <article
              v-for="item in contextPack.should_know"
              :key="item.item_id"
              class="context-item clickable"
              :class="{ active: selectedItem?.item_id === item.item_id }"
              @click="selectContextItem(item)"
            >
              <div class="context-topline">
                <span class="category-badge">{{ item.category }}</span>
                <span class="memory-badge" :class="{ candidate: item.memory_layer === 'candidate' }">{{ item.memory_layer }}</span>
              </div>
              <div class="context-summary">{{ item.summary }}</div>
              <div class="context-why">{{ item.why_it_matters }}</div>
            </article>
          </div>
        </section>

        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">风险提示</h3>
            <span class="memory-badge warning-badge">{{ contextPack.warnings.length }}</span>
          </div>
          <div class="context-list">
            <article v-for="item in contextPack.warnings" :key="item.item_id" class="context-item">
              <div class="context-topline">
                <span class="category-badge">{{ item.category }}</span>
                <span class="memory-badge warning-badge">{{ item.rank_score }}</span>
              </div>
              <div class="context-summary">{{ item.summary }}</div>
              <div class="context-why">{{ item.why_it_matters }}</div>
            </article>
          </div>
        </section>

        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">候选场景</h3>
            <span class="memory-badge">{{ contextPack.scene_candidates.length }}</span>
          </div>
          <div class="scene-list">
            <article v-for="item in contextPack.scene_candidates" :key="item.title + item.setup" class="context-item">
              <div class="scene-title">{{ item.title }}</div>
              <div class="scene-copy">起点：{{ item.setup }}</div>
              <div class="scene-copy">张力：{{ item.tension }}</div>
              <div class="scene-copy">为什么现在：{{ item.why_now }}</div>
            </article>
          </div>
        </section>

        <section class="context-block prompt-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">Writer Prompt Block</h3>
          </div>
          <div>{{ contextPack.writer_prompt_block }}</div>
        </section>
      </div>
    </main>

    <aside class="writer-panel writer-debug workbench-card">
      <p class="panel-kicker mono">TRACE & REVIEW</p>
      <h2 class="panel-title title-ancient">来源与审校</h2>

      <div class="side-stack">
        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">调试来源</h3>
          </div>
          <div v-if="!contextPack?.debug_trace?.length" class="review-hint">生成上下文包后，这里会显示每条信息的来源和排序分数。</div>
          <div v-else class="trace-list">
            <article v-for="item in contextPack.debug_trace" :key="item.item_id" class="trace-item">
              <div class="trace-topline">
                <span class="category-badge">{{ item.category }}</span>
                <span class="score-badge">{{ item.rank_score }}</span>
              </div>
              <div class="trace-copy">{{ item.source_kind }} · {{ item.source_ref }}</div>
            </article>
          </div>
        </section>

        <section class="context-block">
          <div class="context-block-header">
            <h3 class="context-block-title title-ancient">记忆审校</h3>
          </div>
          <div v-if="!selectedItem" class="review-hint">点选中间栏的 runtime memory 条目后，可在这里读取 timeline 并执行 adopt / reject。</div>
          <template v-else>
            <div class="timeline-card">
              <div class="timeline-topline">
                <span class="category-badge">{{ selectedItem.category }}</span>
                <span class="memory-badge" :class="{ candidate: selectedItem.memory_layer === 'candidate' }">{{ selectedItem.memory_layer }}</span>
              </div>
              <div class="timeline-title">{{ selectedItem.summary }}</div>
              <div class="timeline-copy">{{ selectedItem.why_it_matters }}</div>
              <div class="timeline-meta">{{ selectedItem.source_kind }} · {{ selectedItem.source_ref }}</div>
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

              <div class="event-list">
                <article v-for="item in memoryTimeline.events" :key="item.event_id" class="event-card">
                  <div class="event-meta">{{ item.event_type }} · v{{ item.version }} · {{ item.created_at }}</div>
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
import { computed, onMounted, onUnmounted, ref } from "vue";

import {
  adoptArchiveMemory,
  getArchiveMemoryTimeline,
  rejectArchiveMemory,
} from "../api/archive.js";
import { buildChapterContext, getChapterContextOptions } from "../api/novel.js";
import { getWorldlineAgents, listWorldlineSessions } from "../api/worldline.js";
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

const { projects, refreshProjects } = useProjectCatalog();
const workbenchMode = ref(resolveWriterWorkbenchMode(window.innerWidth));
const projectId = ref("");
const scopeType = ref("project_chapter");
const chapterId = ref("");
const chapterOrder = ref(0);
const povCharacter = ref("");
const writingGoal = ref("");
const sceneFocus = ref("");
const includeCandidates = ref(false);
const sessionId = ref("");
const branchId = ref("main");
const chapterOptions = ref([]);
const projectPovs = ref([]);
const sessionOptions = ref([]);
const worldlineAgents = ref([]);
const contextPack = ref(null);
const selectedItem = ref(null);
const memoryTimeline = ref(null);
const reviewBusy = ref(false);
const timelineError = ref("");
const busy = ref(false);
const message = ref("请选择项目并生成上下文包");
const error = ref("");

const gridTemplateColumns = computed(() => buildWriterWorkbenchColumns(workbenchMode.value));
const povOptions = computed(() => resolveWriterPovOptions(scopeType.value, projectPovs.value, worldlineAgents.value));
const canSubmit = computed(() => {
  if (!projectId.value || !povCharacter.value) {
    return false;
  }
  return scopeType.value === "worldline_branch" ? !!sessionId.value : !!(chapterId.value || chapterOrder.value);
});
const contextScopeSummary = computed(() => {
  if (!contextPack.value) return "";
  const scope = contextPack.value.context_scope;
  return scope.scope_type === "worldline_branch"
    ? `会话 ${scope.session_id} · 分支 ${scope.branch_id} · POV ${scope.pov_character}`
    : `项目 ${scope.project_id} · 章节 ${scope.chapter_id || scope.chapter_order} · POV ${scope.pov_character}`;
});
const canLoadTimeline = computed(() => Boolean(selectedItem.value?.archive_id && (selectedItem.value?.normalized_subject || selectedItem.value?.source_ref)));
const activeCandidateMemoryId = computed(() => {
  const item = memoryTimeline.value?.memories?.find((entry) => entry.memory_layer === "candidate" && entry.status === "active");
  return item?.memory_id || "";
});

function handleResize() {
  workbenchMode.value = resolveWriterWorkbenchMode(window.innerWidth);
}

async function handleProjectChange() {
  contextPack.value = null;
  selectedItem.value = null;
  memoryTimeline.value = null;
  timelineError.value = "";
  if (!projectId.value) {
    chapterOptions.value = [];
    projectPovs.value = [];
    sessionOptions.value = [];
    worldlineAgents.value = [];
    return;
  }
  await refreshProjectData();
}

async function refreshProjectData() {
  if (!projectId.value) {
    return;
  }
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
  } catch (err) {
    error.value = err.message || "读取项目上下文失败";
  }
}

async function handleSessionChange() {
  worldlineAgents.value = [];
  if (!sessionId.value) {
    return;
  }
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

async function generatePack(options = {}) {
  if (!canSubmit.value) {
    return;
  }
  try {
    const previousItem = options.preserveSelection ? selectedItem.value : null;
    busy.value = true;
    error.value = "";
    message.value = "正在生成 Chapter Context Pack";
    const chapter = chapterOptions.value.find((item) => item.chapter_id === chapterId.value);
    chapterOrder.value = chapter?.order || chapterOrder.value;
    const response = await buildChapterContext(buildWriterRequestPayload({
      scopeType: scopeType.value,
      projectId: projectId.value,
      chapterId: chapterId.value,
      chapterOrder: chapterOrder.value,
      sessionId: sessionId.value,
      branchId: branchId.value,
      povCharacter: povCharacter.value,
      writingGoal: writingGoal.value,
      sceneFocus: sceneFocus.value,
      includeCandidates: includeCandidates.value,
    }));
    contextPack.value = response.data;
    selectedItem.value = previousItem ? findContextItem(response.data, previousItem) : null;
    memoryTimeline.value = null;
    timelineError.value = "";
    message.value = "上下文包已生成";
  } catch (err) {
    error.value = err.message || "生成上下文包失败";
  } finally {
    busy.value = false;
  }
}

function selectContextItem(item) {
  selectedItem.value = item;
  memoryTimeline.value = null;
  timelineError.value = "";
}

async function loadSelectedTimeline() {
  if (!canLoadTimeline.value) {
    return;
  }
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
  if (!activeCandidateMemoryId.value || !selectedItem.value?.archive_id) {
    return;
  }
  try {
    reviewBusy.value = true;
    timelineError.value = "";
    await adoptArchiveMemory(selectedItem.value.archive_id, activeCandidateMemoryId.value);
    await generatePack({ preserveSelection: true });
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
  if (!activeCandidateMemoryId.value || !selectedItem.value?.archive_id) {
    return;
  }
  try {
    reviewBusy.value = true;
    timelineError.value = "";
    await rejectArchiveMemory(selectedItem.value.archive_id, activeCandidateMemoryId.value);
    await generatePack({ preserveSelection: true });
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
});
</script>

<style scoped src="./WriterWorkbenchView.css"></style>
