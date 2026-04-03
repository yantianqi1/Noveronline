<template>
  <div class="upload-body stack">
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
      <span class="toggle-icon">{{ showAdvanced ? "▾" : "▸" }}</span>
      <span>高级分析配置</span>
    </div>

    <Transition name="slide">
      <div v-if="showAdvanced" class="advanced-fields stack">
        <div class="field">
          <label>分析目标</label>
          <textarea
            v-model="upload.state.analysisGoal"
            placeholder="明确您的分析重点，如：重点提取支线剧情与隐藏关系。"
            :disabled="upload.state.uploadBusy"
          ></textarea>
        </div>
        <div class="field">
          <label>补充背景</label>
          <textarea
            v-model="upload.state.additionalContext"
            placeholder="提供世界观、术语表或既定设定，有助于提升分析精度。"
            :disabled="upload.state.uploadBusy"
          ></textarea>
        </div>
        <div class="field">
          <label>每段令牌上限</label>
          <input
            v-model.number="upload.state.segmentTokenLimit"
            type="number"
            min="5000"
            max="200000"
            step="5000"
            placeholder="50000"
            :disabled="upload.state.uploadBusy"
          />
          <span class="field-hint">控制每个阅读段的最大令牌数，影响分析精度和速度。默认 50000。</span>
        </div>
      </div>
    </Transition>

    <div class="upload-actions">
      <button class="btn primary large" :disabled="!canSubmit || upload.state.uploadBusy" @click="submitUpload">
        {{ upload.state.uploadBusy ? "分析进行中..." : "开始分析" }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";

import { useSeedUpload } from "../../composables/useSeedUpload";

const upload = useSeedUpload();
const fileInputRef = ref(null);
const showAdvanced = ref(false);

const canSubmit = computed(() => upload.state.projectName.trim() && upload.state.files.length > 0);

function openPicker() {
  if (upload.state.uploadBusy) {
    return;
  }
  fileInputRef.value?.click();
}

function handleChange(event) {
  upload.appendFiles(Array.from(event.target.files || []));
  event.target.value = "";
}

function handleDrop(event) {
  if (upload.state.uploadBusy) {
    return;
  }
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
</script>

<style scoped>
.upload-body {
  margin-top: var(--space-lg);
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

.slide-enter-active,
.slide-leave-active {
  transition: all 0.24s ease;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
  overflow: hidden;
}

.field-hint {
  font-size: 12px;
  color: var(--text-dim);
  margin-top: 2px;
}
</style>
