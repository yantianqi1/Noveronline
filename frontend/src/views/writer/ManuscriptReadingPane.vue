<template>
  <div class="reading-pane">
    <div class="reading-header">
      <h2 class="reading-chapter-title">{{ chapterTitle }}</h2>
      <div class="reading-stats">{{ totalWords }} 字 · {{ blocks.length }} 段</div>
    </div>
    <div class="reading-scroll">
      <template v-if="blocks.length">
        <div
          v-for="block in blocks"
          :key="block.block_id"
          class="prose-block"
          :class="{ 'prose-block--editing': editingId === block.block_id }"
          @mouseenter="hoveredId = block.block_id"
          @mouseleave="hoveredId = null"
        >
          <!-- Floating action bar on hover -->
          <div
            v-if="hoveredId === block.block_id && editingId !== block.block_id"
            class="block-hover-actions"
          >
            <span class="block-order-hint">#{{ block.block_order }}</span>
            <button class="hover-btn" @click="startEdit(block.block_id)">编辑</button>
            <button class="hover-btn hover-btn--danger" @click="$emit('delete', block.block_id)">删除</button>
          </div>

          <!-- Edit mode -->
          <textarea
            v-if="editingId === block.block_id"
            ref="editorRef"
            class="prose-editor"
            :value="block.content"
            @input="e => $emit('edit-input', block, e.target.value)"
          ></textarea>
          <div v-if="editingId === block.block_id" class="prose-editor-bar">
            <span class="editor-hint">{{ block.word_count }} 字</span>
            <button class="hover-btn" @click="editingId = null">完成</button>
          </div>

          <!-- Read mode -->
          <div v-else class="prose-text">{{ block.content }}</div>
        </div>
      </template>
      <div v-else class="reading-empty">尚无稿件内容</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";

defineProps({
  blocks: { type: Array, default: () => [] },
  chapterTitle: { type: String, default: "" },
  totalWords: { type: Number, default: 0 },
});

defineEmits(["delete", "edit-input"]);

const hoveredId = ref(null);
const editingId = ref(null);

function startEdit(blockId) {
  editingId.value = blockId;
}

defineExpose({ editingId });
</script>

<style scoped>
.reading-pane {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.reading-header {
  padding: 20px 32px 16px;
  border-bottom: 1px solid var(--border-subtle, #2d2d44);
}

.reading-chapter-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary, #e0e0e0);
  margin: 0;
}

.reading-stats {
  font-size: 12px;
  color: var(--text-tertiary, #888);
  margin-top: 4px;
}

.reading-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 24px 32px 40px;
}

.prose-block {
  position: relative;
  padding: 2px 0 12px;
  border-bottom: 1px dashed transparent;
  transition: border-color 0.2s;
}

.prose-block:hover {
  border-bottom-color: var(--border-subtle, #2d2d44);
}

.prose-block + .prose-block {
  margin-top: 8px;
}

.prose-block--editing {
  border-bottom-color: var(--border-active, #4060c0);
}

.prose-text {
  font-size: 15px;
  line-height: 1.9;
  color: var(--text-primary, #e0e0e0);
  white-space: pre-wrap;
  font-family: "Noto Serif SC", "Source Han Serif CN", serif, inherit;
}

.block-hover-actions {
  position: absolute;
  top: 0;
  right: 0;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 2px 6px;
  background: var(--surface-tertiary, #252540);
  border: 1px solid var(--border-subtle, #2d2d44);
  border-radius: 4px;
  z-index: 2;
}

.block-order-hint {
  font-size: 10px;
  color: var(--text-tertiary, #888);
  margin-right: 4px;
}

.hover-btn {
  background: none;
  border: none;
  font-size: 11px;
  color: var(--text-secondary, #aaa);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 3px;
}
.hover-btn:hover {
  background: var(--surface-hover, #303050);
  color: var(--text-primary, #e0e0e0);
}
.hover-btn--danger { color: #e05050; }
.hover-btn--danger:hover { color: #ff6060; background: rgba(224, 80, 80, 0.1); }

.prose-editor {
  width: 100%;
  min-height: 160px;
  background: var(--surface-tertiary, #252540);
  border: 1px solid var(--border-active, #4060c0);
  border-radius: 6px;
  padding: 12px 16px;
  font-size: 15px;
  line-height: 1.9;
  color: var(--text-primary, #e0e0e0);
  resize: vertical;
  font-family: inherit;
}

.prose-editor-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}

.editor-hint {
  font-size: 11px;
  color: var(--text-tertiary, #888);
}

.reading-empty {
  text-align: center;
  color: var(--text-tertiary, #888);
  padding: 80px 0;
  font-size: 14px;
}
</style>
