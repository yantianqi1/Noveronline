<template>
  <div class="scene-editor">
    <div v-if="streaming" class="scene-editor-content scene-editor-content--streaming">
      <div class="streaming-text" v-text="content"></div>
      <span class="streaming-cursor">▊</span>
    </div>
    <n-input
      v-else
      type="textarea"
      class="scene-editor-textarea"
      :value="content"
      @update:value="$emit('update', $event)"
      :readonly="readonly"
      placeholder="场景内容将在此处显示..."
      :autosize="{ minRows: 16 }"
    />

    <!-- Floating toolbar on text selection -->
    <div
      v-if="showToolbar"
      class="scene-floating-toolbar"
      :style="{ top: toolbarPos.top + 'px', left: toolbarPos.left + 'px' }"
    >
      <n-button size="tiny" quaternary class="scene-floating-btn" @click="handleCommitSelection">提交选中</n-button>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from "vue";
import { NInput, NButton } from "naive-ui";

defineProps({
  content: { type: String, default: "" },
  streaming: { type: Boolean, default: false },
  readonly: { type: Boolean, default: false },
});

const emit = defineEmits(["update", "commit-selection"]);

const showToolbar = ref(false);
const toolbarPos = ref({ top: 0, left: 0 });
let selectedText = "";

function handleSelectionChange() {
  const sel = window.getSelection();
  if (sel && sel.toString().trim().length > 0) {
    selectedText = sel.toString();
    const range = sel.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    toolbarPos.value = {
      top: rect.top - 40,
      left: rect.left + rect.width / 2 - 60,
    };
    showToolbar.value = true;
  } else {
    showToolbar.value = false;
  }
}

function handleCommitSelection() {
  if (selectedText.trim()) {
    emit("commit-selection", selectedText);
    showToolbar.value = false;
  }
}

onMounted(() => {
  document.addEventListener("selectionchange", handleSelectionChange);
});

onBeforeUnmount(() => {
  document.removeEventListener("selectionchange", handleSelectionChange);
});
</script>

<style scoped>
.scene-editor {
  position: relative;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.scene-editor-content {
  flex: 1;
  padding: 14px;
  font-size: 14px;
  line-height: 1.7;
  color: #333;
}
.scene-editor-textarea {
  flex: 1;
}
.scene-editor-textarea :deep(.n-input__textarea-el) {
  padding: 14px;
  font-size: 14px;
  line-height: 1.7;
  min-height: 400px;
}
.scene-editor-content--streaming {
  overflow-y: auto;
  white-space: pre-wrap;
  word-wrap: break-word;
}
.streaming-cursor {
  animation: blink 1s step-end infinite;
  color: #409eff;
}
@keyframes blink {
  50% { opacity: 0; }
}
.scene-floating-toolbar {
  position: fixed;
  display: flex;
  gap: 4px;
  background: #333;
  border-radius: 6px;
  padding: 4px 6px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
  z-index: 100;
}
.scene-floating-btn {
  color: #fff !important;
}
</style>
