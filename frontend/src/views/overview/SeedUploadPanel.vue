<template>
  <article class="upload-panel workbench-card">
    <header class="upload-header">
      <div>
        <div class="panel-code mono">启动新任务</div>
        <h2 class="title-ancient">卷宗投放</h2>
        <p class="subtitle">上传文本、填写分析目标，然后把新的种子任务送入后台管线。</p>
      </div>
      <button class="btn subtle small" @click="panelExpanded = !panelExpanded">
        {{ panelExpanded ? "收起面板" : "展开面板" }}
      </button>
    </header>

    <div v-if="!panelExpanded" class="collapsed-summary">
      <span>{{ collapsedSummary }}</span>
      <button class="btn subtle small" @click="panelExpanded = true">继续编辑</button>
    </div>

    <Transition name="panel-fold">
      <SeedUploadFormFields v-if="panelExpanded" />
    </Transition>

    <div v-if="upload.state.error" class="status-error mono">{{ upload.state.error }}</div>
  </article>
</template>

<script setup>
import { computed, ref, watch } from "vue";

import { useSeedUpload } from "../../composables/useSeedUpload";
import SeedUploadFormFields from "./SeedUploadFormFields.vue";

const props = defineProps({
  initiallyExpanded: { type: Boolean, default: true },
});

const emit = defineEmits(["uploaded"]);
const upload = useSeedUpload();
const panelExpanded = ref(props.initiallyExpanded);

const collapsedSummary = computed(() => {
  if (upload.state.uploadBusy) {
    return "后台已有任务运行中。展开面板可查看当前输入并继续调整。";
  }
  if (upload.state.files.length) {
    return `已准备 ${upload.state.files.length} 份文件，项目名：${upload.state.projectName || "未命名卷宗"}`;
  }
  return "当前未展开上传表单。展开后可直接发起新的种子分析。";
});

let lastEmittedProjectId = "";

watch(
  () => props.initiallyExpanded,
  (value) => {
    panelExpanded.value = value;
  },
  { immediate: true },
);

watch(
  () => upload.state.result?.project_id,
  (projectId) => {
    if (!projectId || projectId === lastEmittedProjectId) {
      return;
    }
    lastEmittedProjectId = projectId;
    emit("uploaded", upload.state.result);
  },
  { immediate: true },
);
</script>

<style scoped>
.upload-panel {
  width: 100%;
  padding: var(--space-xl);
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(249, 246, 238, 0.96)),
    radial-gradient(circle at 100% 0%, rgba(61, 90, 128, 0.05), transparent 26%);
}

.upload-header,
.collapsed-summary {
  display: flex;
  justify-content: space-between;
  gap: var(--space-md);
  align-items: flex-start;
}

.panel-code {
  color: var(--text-dim);
  font-size: 12px;
}

.subtitle {
  color: var(--text-dim);
  font-size: 14px;
  margin: 6px 0 0;
  line-height: 1.7;
}

.collapsed-summary {
  margin-top: var(--space-lg);
  padding: var(--space-md);
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px dashed rgba(113, 128, 150, 0.22);
}

.status-error {
  margin-top: var(--space-md);
  padding: var(--space-md);
  background: rgba(155, 67, 38, 0.05);
  border-radius: var(--radius-md);
  color: var(--accent-seal);
  font-size: 13px;
}

.slide-enter-active,
.slide-leave-active,
.panel-fold-enter-active,
.panel-fold-leave-active {
  transition: all 0.24s ease;
}

.slide-enter-from,
.slide-leave-to,
.panel-fold-enter-from,
.panel-fold-leave-to {
  opacity: 0;
  max-height: 0;
  overflow: hidden;
}

@media (max-width: 768px) {
  .upload-header,
  .collapsed-summary {
    flex-direction: column;
  }
}
</style>
