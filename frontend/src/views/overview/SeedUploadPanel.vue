<template>
  <article :class="['upload-container', { stack: !hasActiveTask, 'with-active-task': hasActiveTask }]">
    <div class="upload-main workbench-card">
      <header class="upload-header">
        <h2 class="title-ancient">卷宗投放</h2>
        <p class="subtitle">将小说文本投放至此，开启自动化解构管线。</p>
      </header>

      <div class="upload-form stack">
        <div class="field">
          <label>项目/卷宗名称</label>
          <input v-model="upload.state.projectName" placeholder="例如：天穹秘约" :disabled="upload.state.uploadBusy" />
        </div>

        <div
          class="dropzone"
          :class="{ active: upload.state.dragActive, busy: upload.state.uploadBusy, hasFiles: upload.state.files.length }"
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
          <div class="drop-icon">📤</div>
          <div v-if="!upload.state.files.length" class="drop-text">
            <strong>拖拽文件到这里</strong>
            <span>或点击选择 (txt, md, pdf)</span>
          </div>
          <div v-else class="selected-files">
            <div v-for="item in upload.state.files" :key="upload.fileKey(item)" class="file-chip">
              <span class="file-name">{{ item.name }}</span>
              <button class="remove-btn" @click.stop="upload.removeFile(item)">×</button>
            </div>
          </div>
        </div>

        <div class="advanced-toggle" @click="showAdvanced = !showAdvanced">
          <span class="toggle-icon">{{ showAdvanced ? '▾' : '▸' }}</span>
          <span>高级分析配置</span>
        </div>

        <Transition name="slide">
          <div v-if="showAdvanced" class="advanced-fields stack">
            <div class="field">
              <label>分析目标</label>
              <textarea v-model="upload.state.analysisGoal" placeholder="明确您的分析重点，如：重点提取支线剧情与隐藏关系。" :disabled="upload.state.uploadBusy"></textarea>
            </div>
            <div class="field">
              <label>补充背景</label>
              <textarea v-model="upload.state.additionalContext" placeholder="提供世界观、术语表或既定设定，有助于提升分析精度。" :disabled="upload.state.uploadBusy"></textarea>
            </div>
          </div>
        </Transition>

        <div class="upload-actions">
          <button class="btn primary large" :disabled="!canSubmit || upload.state.uploadBusy" @click="submitUpload">
            {{ upload.state.uploadBusy ? "管线分析中..." : "启动管线分析" }}
          </button>
        </div>
      </div>

      <div v-if="upload.state.error" class="status-error mono">{{ upload.state.error }}</div>
    </div>

    <!-- Active Task Status Section -->
    <Transition name="fade">
      <aside v-if="hasActiveTask" class="active-task-area stack">
        <div class="task-progress-card workbench-card stack">
          <h3 class="title-ancient">实时管线状态</h3>
          <PipelineVisualization
            :upload-phase="upload.state.uploadPhase"
            :task-status="upload.state.taskStatus"
            :active-stage="upload.state.activeStage"
          />
          <div class="progress-details stack">
            <div class="progress-row">
              <strong>{{ upload.state.statusText }}</strong>
              <span class="mono">{{ upload.state.progressPercent }}%</span>
            </div>
            <div class="progress-track">
              <div class="progress-bar" :style="{ width: `${upload.state.progressPercent}%` }"></div>
            </div>
            <div class="progress-meta mono">
              <span>{{ upload.state.activeStage.label || '准备分析' }}</span>
              <span v-if="upload.state.taskMetrics.totalBlocks">
                {{ upload.state.taskMetrics.completedBlocks }}/{{ upload.state.taskMetrics.totalBlocks }} 块
              </span>
            </div>
          </div>
        </div>

        <div class="task-logs-card workbench-card">
          <div class="logs-header">
            <h3 class="title-ancient">后台日志</h3>
            <button class="btn subtle small" @click="showLogs = !showLogs">{{ showLogs ? '收起日志' : '展开日志' }}</button>
          </div>
          <SeedTaskLogPanel
            v-if="showLogs"
            :upload-phase="upload.state.uploadPhase"
            :task-status="upload.state.taskStatus"
            :active-stage="upload.state.activeStage"
            :task-metrics="upload.state.taskMetrics"
            :llm-activity="upload.state.llmActivity"
            :timeline="upload.state.timeline"
            :task-started-at="upload.state.taskStartedAt"
          />
        </div>
      </aside>
    </Transition>
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
const showAdvanced = ref(false);
const showLogs = ref(true);

const canSubmit = computed(() => upload.state.projectName.trim() && upload.state.files.length > 0);
const hasActiveTask = computed(() => upload.state.uploadPhase !== "idle");

let lastEmittedProjectId = "";

function openPicker() {
  if (upload.state.uploadBusy) return;
  fileInputRef.value?.click();
}

function handleChange(event) {
  upload.appendFiles(Array.from(event.target.files || []));
  event.target.value = "";
}

function handleDrop(event) {
  if (upload.state.uploadBusy) return;
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
.upload-container {
  width: 100%;
}

.upload-container.with-active-task {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(360px, 0.85fr);
  gap: var(--space-lg);
  align-items: start;
}

.upload-main {
  min-width: 0;
  padding: var(--space-xl);
  background-image: 
    linear-gradient(135deg, rgba(176, 125, 75, 0.02) 0%, transparent 40%),
    linear-gradient(var(--bg-panel), var(--bg-panel));
}

.upload-header {
  margin-bottom: var(--space-lg);
  text-align: center;
}

.subtitle {
  color: var(--text-dim);
  font-size: 14px;
  margin-top: 4px;
}

.dropzone {
  border: 2px dashed var(--line-medium);
  border-radius: var(--radius-lg);
  padding: var(--space-xl);
  background: var(--bg-paper-warm);
  cursor: pointer;
  transition: all 0.2s ease;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--space-md);
  text-align: center;
}

.dropzone:hover {
  border-color: var(--accent-copper);
  background: #ffffff;
}

.dropzone.active {
  border-color: var(--accent-copper-deep);
  background: rgba(176, 125, 75, 0.05);
}

.dropzone.busy {
  cursor: wait;
  opacity: 0.7;
}

.drop-icon {
  font-size: 40px;
  opacity: 0.6;
}

.drop-text strong {
  display: block;
  font-size: 16px;
  color: var(--text-main);
}

.drop-text span {
  font-size: 13px;
  color: var(--text-dim);
}

.selected-files {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-sm);
  justify-content: center;
}

.file-chip {
  background: #fff;
  border: 1px solid var(--line-medium);
  border-radius: var(--radius-full);
  padding: 4px 12px;
  font-size: 13px;
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  box-shadow: var(--shadow-sm);
}

.remove-btn {
  border: none;
  background: transparent;
  color: var(--text-dim);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}

.remove-btn:hover {
  color: var(--accent-seal);
}

.hidden-input {
  display: none;
}

.advanced-toggle {
  display: flex;
  align-items: center;
  gap: var(--space-xs);
  font-size: 13px;
  color: var(--text-sub);
  cursor: pointer;
  user-select: none;
  width: fit-content;
}

.advanced-toggle:hover {
  color: var(--accent-copper);
}

.toggle-icon {
  font-family: monospace;
  font-size: 16px;
}

.upload-actions {
  display: flex;
  justify-content: center;
  margin-top: var(--space-md);
}

.large {
  padding: 14px 48px;
  font-size: 16px;
}

.active-task-area {
  min-width: 0;
}

.task-progress-card, .task-logs-card {
  padding: var(--space-lg);
  min-width: 0;
}

.progress-row {
  display: flex;
  justify-content: space-between;
}

.progress-track {
  height: 6px;
  background: var(--bg-paper);
  border-radius: 3px;
  overflow: hidden;
}

.progress-bar {
  height: 100%;
  background: var(--accent-copper);
  transition: width 0.3s ease;
}

.progress-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--text-dim);
}

.logs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-md);
}

.status-error {
  padding: var(--space-md);
  background: rgba(155, 67, 38, 0.05);
  border-radius: var(--radius-md);
  color: var(--accent-seal);
  font-size: 13px;
  margin-top: var(--space-md);
}

.slide-enter-active, .slide-leave-active { transition: all 0.3s ease-out; max-height: 300px; overflow: hidden; }
.slide-enter-from, .slide-leave-to { max-height: 0; opacity: 0; }

@media (max-width: 1180px) {
  .upload-container.with-active-task {
    grid-template-columns: 1fr;
  }
}
</style>
