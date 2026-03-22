<template>
  <article class="workbench-card panel upload-panel">
    <div class="upload-layout">
      <section class="upload-main">
        <header class="upload-head">
          <h2 class="card-title">上传小说文本</h2>
          <p>把小说正文、设定集或大纲拖进来，系统会创建项目并生成第一轮种子分析。</p>
        </header>

        <PipelineVisualization
          :upload-phase="upload.state.uploadPhase"
          :task-status="upload.state.taskStatus"
          :active-stage="upload.state.activeStage"
        />

        <div class="field"><label>项目名称</label><input v-model="upload.state.projectName" placeholder="例如：天穹秘约" /></div>
        <div class="field">
          <label>分析目标</label>
          <textarea v-model="upload.state.analysisGoal" placeholder="例如：提取全部有名角色、组织和关系，用于平行世界推演。"></textarea>
        </div>
        <div class="field">
          <label>补充说明</label>
          <textarea v-model="upload.state.additionalContext" placeholder="可选：补充作品风格、重点角色、世界观信息。"></textarea>
        </div>

        <div
          class="dropzone"
          :class="{ active: upload.state.dragActive, busy: upload.state.uploadBusy }"
          @dragenter.prevent="upload.state.dragActive = true"
          @dragover.prevent="upload.state.dragActive = true"
          @dragleave.prevent="upload.state.dragActive = false"
          @drop.prevent="handleDrop"
          @click="openPicker"
        >
          <input
            ref="fileInputRef"
            class="hidden-input"
            type="file"
            multiple
            accept=".txt,.md,.markdown,.pdf"
            @change="handleChange"
          />
          <strong>拖拽文件到这里</strong>
          <span>或点击选择 `txt / md / markdown / pdf`</span>
        </div>

        <div v-if="showProgress" class="progress-card">
          <div class="progress-top">
            <strong>{{ upload.state.statusText }}</strong>
            <span class="mono">{{ upload.state.progressPercent }}%</span>
          </div>
          <p class="progress-stage mono">阶段：{{ upload.state.activeStage.label || upload.state.stageLabel || "后台分析" }}</p>
          <div class="progress-track"><div class="progress-bar" :style="{ width: `${upload.state.progressPercent}%` }"></div></div>
          <p v-if="upload.state.totalBytes" class="progress-meta mono">
            {{ upload.formatSize(upload.state.uploadedBytes) }} / {{ upload.formatSize(upload.state.totalBytes) }}
          </p>
          <p v-if="upload.state.taskMetrics.totalBlocks" class="progress-meta">
            当前块进度：{{ upload.state.taskMetrics.completedBlocks }}/{{ upload.state.taskMetrics.totalBlocks }}
          </p>
        </div>

        <div v-if="upload.state.files.length" class="file-list">
          <div v-for="item in upload.state.files" :key="upload.fileKey(item)" class="file-item">
            <div><strong>{{ item.name }}</strong><div class="meta mono">{{ upload.formatSize(item.size) }}</div></div>
            <button class="btn subtle" type="button" :disabled="upload.state.uploadBusy" @click.stop="upload.removeFile(item)">移除</button>
          </div>
        </div>
        <div v-else class="empty-tip">还没有选择文件。</div>

        <div class="toolbar-row">
          <button class="btn" type="button" :disabled="upload.state.uploadBusy" @click="openPicker">选择文件</button>
          <button class="btn primary" type="button" :disabled="upload.state.uploadBusy" @click="submitUpload">
            {{ upload.state.uploadBusy ? "上传中..." : "上传并生成项目" }}
          </button>
        </div>

        <div v-if="upload.state.result" class="result-card">
          <div class="seed-title">上传完成</div>
          <p class="mono">{{ upload.state.result.project_id }}</p>
          <p>{{ upload.state.result.task_message || "项目已创建，可继续做种子分析与世界线建模。" }}</p>
          <div class="result-grid">
            <div class="kpi"><span class="mono">角色</span><strong>{{ seedCharacterCount }}</strong></div>
            <div class="kpi"><span class="mono">组织</span><strong>{{ seedOrganizationCount }}</strong></div>
            <div class="kpi"><span class="mono">关系</span><strong>{{ seedRelationCount }}</strong></div>
          </div>
        </div>
        <p v-if="upload.state.error" class="seed-error">{{ upload.state.error }}</p>
      </section>

      <SeedTaskLogPanel
        class="upload-log"
        :upload-phase="upload.state.uploadPhase"
        :task-status="upload.state.taskStatus"
        :active-stage="upload.state.activeStage"
        :task-metrics="upload.state.taskMetrics"
        :llm-activity="upload.state.llmActivity"
        :timeline="upload.state.timeline"
        :task-started-at="upload.state.taskStartedAt"
      />
    </div>
  </article>
</template>

<script setup>
import { computed, ref, watch } from "vue";

import { useSeedUpload } from "../../composables/useSeedUpload";
import PipelineVisualization from "./PipelineVisualization.vue";
import SeedTaskLogPanel from "./SeedTaskLogPanel.vue";

const emit = defineEmits(["uploaded"]);
const upload = useSeedUpload();
const fileInputRef = ref(null);
const showProgress = computed(() => upload.state.uploadPhase !== "idle");
const seedCharacterCount = computed(() => upload.state.result?.task_result?.seed_analysis?.character_count || 0);
const seedOrganizationCount = computed(() => upload.state.result?.task_result?.seed_analysis?.organization_count || 0);
const seedRelationCount = computed(() => upload.state.result?.task_result?.seed_analysis?.relation_count || 0);
let lastEmittedProjectId = "";

function openPicker() {
  fileInputRef.value?.click();
}

function handleChange(event) {
  upload.appendFiles(Array.from(event.target.files || []));
  event.target.value = "";
}

function handleDrop(event) {
  upload.state.dragActive = false;
  upload.appendFiles(Array.from(event.dataTransfer?.files || []));
}

async function submitUpload() {
  try {
    await upload.submitUpload();
  } catch {
    return;
  }
}

watch(
  () => upload.state.result?.project_id,
  (projectId) => {
    if (!projectId || projectId === lastEmittedProjectId) return;
    lastEmittedProjectId = projectId;
    emit("uploaded", upload.state.result);
  },
  { immediate: true },
);
</script>

<style scoped>
.upload-panel {
  grid-column: 1 / -1;
}

.upload-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(360px, 1fr);
  gap: 18px;
}

.upload-main {
  min-width: 0;
}

.upload-head p,
.progress-meta,
.progress-stage,
.meta,
.empty-tip {
  color: var(--text-sub);
}

.progress-top,
.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.field,
.toolbar-row,
.file-list,
.empty-tip,
.progress-card,
.result-card {
  margin-top: 14px;
}

.dropzone,
.progress-card,
.result-card,
.file-item {
  border: 1px solid var(--line-soft);
  border-radius: 14px;
  background: #fff9ef;
}

.dropzone {
  margin-top: 14px;
  border-style: dashed;
  border-width: 2px;
  padding: 28px 16px;
  text-align: center;
  background: #fffaf0;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.dropzone.active {
  border-color: var(--line-strong);
  background: #fff3da;
}

.dropzone.busy {
  cursor: progress;
}

.hidden-input {
  display: none;
}

.progress-card,
.result-card,
.file-item {
  padding: 12px;
}

.progress-top,
.file-item {
  justify-content: space-between;
}

.progress-track {
  margin-top: 10px;
  height: 10px;
  border-radius: 999px;
  background: #f0e1c7;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #c87c38, #d7a860);
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.seed-title {
  font-weight: 700;
}

.result-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.kpi {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fffbf0;
  padding: 10px;
}

.kpi span {
  display: block;
  color: var(--text-sub);
  font-size: 12px;
}

.seed-error {
  margin-top: 12px;
  color: #9b4326;
}

@media (max-width: 1180px) {
  .upload-layout,
  .result-grid {
    grid-template-columns: 1fr;
  }
}
</style>
