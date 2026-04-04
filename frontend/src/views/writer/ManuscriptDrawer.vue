<template>
  <Teleport to="body">
    <Transition name="reader">
      <div v-if="visible" class="manuscript-overlay" @click.self="$emit('close')">
        <div class="manuscript-reader">
          <!-- Top toolbar -->
          <div class="reader-toolbar">
            <span class="reader-title">稿件阅读器</span>
            <div class="reader-stats">{{ totalWords }} 字 · {{ blocks.length }} 段</div>
            <div class="reader-toolbar-spacer"></div>
            <div class="reader-toolbar-actions">
              <button class="toolbar-btn" @click="handleBatchTag">批量标注</button>
              <button class="toolbar-btn" @click="handleExport('txt')">导出 TXT</button>
              <button class="toolbar-btn" @click="handleExport('md')">导出 MD</button>
            </div>
            <button class="reader-close" @click="$emit('close')">&times;</button>
          </div>

          <!-- Two-panel body -->
          <div class="reader-body">
            <ManuscriptTocSidebar
              :chapters="chapterList"
              :selected-tag="selectedTag"
              :total-words="totalWords"
              :total-blocks="blocks.length"
              :untagged-count="untaggedCount"
              @select="handleChapterSelect"
            />
            <ManuscriptReadingPane
              ref="readingPaneRef"
              :blocks="filteredBlocks"
              :chapter-title="currentChapterTitle"
              :total-words="currentChapterWords"
              @delete="confirmDelete"
              @edit-input="handleEditInput"
            />
          </div>

          <!-- Batch tag modal -->
          <div v-if="showTagModal" class="modal-overlay" @click.self="showTagModal = false">
            <div class="modal-box">
              <div class="modal-title">批量标注章节</div>
              <div class="modal-body">
                <div class="tag-select-list">
                  <label
                    v-for="block in blocks"
                    :key="block.block_id"
                    class="tag-select-item"
                  >
                    <input type="checkbox" v-model="tagSelection" :value="block.block_id" />
                    <span>#{{ block.block_order }} ({{ block.word_count }}字)</span>
                  </label>
                </div>
                <input
                  v-model="tagInput"
                  class="tag-input"
                  placeholder="输入章节标签，如：第一章"
                />
              </div>
              <div class="modal-actions">
                <button class="toolbar-btn toolbar-btn--primary" @click="applyTag">应用</button>
                <button class="toolbar-btn" @click="showTagModal = false">取消</button>
              </div>
            </div>
          </div>

          <!-- Delete confirm -->
          <div v-if="deleteTarget" class="modal-overlay" @click.self="deleteTarget = null">
            <div class="modal-box">
              <div class="modal-title">确认删除</div>
              <div class="modal-body">确定要删除这段稿件内容吗？此操作不可撤销。</div>
              <div class="modal-actions">
                <button class="toolbar-btn toolbar-btn--danger" @click="doDelete">删除</button>
                <button class="toolbar-btn" @click="deleteTarget = null">取消</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch } from "vue";
import ManuscriptTocSidebar from "./ManuscriptTocSidebar.vue";
import ManuscriptReadingPane from "./ManuscriptReadingPane.vue";
import {
  getManuscript,
  updateManuscriptBlock,
  deleteManuscriptBlock,
  tagManuscriptBlocks,
  exportManuscript,
} from "../../api/writerAgent.js";

const props = defineProps({
  visible: { type: Boolean, default: false },
  projectId: { type: String, default: "" },
});

const emit = defineEmits(["close", "updated"]);

const blocks = ref([]);
const totalWords = ref(0);
const selectedTag = ref(null);
const deleteTarget = ref(null);
const showTagModal = ref(false);
const tagSelection = ref([]);
const tagInput = ref("");
const readingPaneRef = ref(null);

// Load blocks when reader opens
watch(() => props.visible, async (v) => {
  if (v && props.projectId) {
    selectedTag.value = null;
    await loadBlocks();
  }
});

async function loadBlocks() {
  try {
    const res = await getManuscript(props.projectId);
    const payload = res.data || res;
    blocks.value = payload.blocks || [];
    totalWords.value = payload.total_words || 0;
  } catch (e) {
    console.error("Failed to load manuscript", e);
  }
}

// Chapter list derived from blocks
const chapterList = computed(() => {
  const map = new Map();
  for (const b of blocks.value) {
    const tag = b.chapter_tag;
    if (!tag) continue;
    if (!map.has(tag)) {
      map.set(tag, { tag, blockCount: 0, wordCount: 0 });
    }
    const entry = map.get(tag);
    entry.blockCount++;
    entry.wordCount += b.word_count || 0;
  }
  return Array.from(map.values());
});

const untaggedCount = computed(() =>
  blocks.value.filter(b => !b.chapter_tag).length
);

const filteredBlocks = computed(() => {
  if (selectedTag.value === null) return blocks.value;
  if (selectedTag.value === "__untagged__") return blocks.value.filter(b => !b.chapter_tag);
  return blocks.value.filter(b => b.chapter_tag === selectedTag.value);
});

const currentChapterTitle = computed(() => {
  if (selectedTag.value === null) return "全部稿件";
  if (selectedTag.value === "__untagged__") return "未归类";
  return selectedTag.value;
});

const currentChapterWords = computed(() =>
  filteredBlocks.value.reduce((sum, b) => sum + (b.word_count || 0), 0)
);

function handleChapterSelect(tag) {
  selectedTag.value = tag;
}

// Edit handling (debounced save)
let editTimer = null;
function handleEditInput(block, value) {
  block.content = value;
  block.word_count = value.length;
  clearTimeout(editTimer);
  editTimer = setTimeout(async () => {
    try {
      await updateManuscriptBlock(block.block_id, {
        project_id: props.projectId,
        content: value,
      });
      emit("updated");
    } catch (e) {
      console.error("Save failed", e);
    }
  }, 800);
}

// Delete
function confirmDelete(blockId) {
  deleteTarget.value = blockId;
}

async function doDelete() {
  if (!deleteTarget.value) return;
  try {
    await deleteManuscriptBlock(deleteTarget.value, props.projectId);
    deleteTarget.value = null;
    await loadBlocks();
    emit("updated");
  } catch (e) {
    console.error("Delete failed", e);
  }
}

// Batch tag
function handleBatchTag() {
  tagSelection.value = [];
  tagInput.value = "";
  showTagModal.value = true;
}

async function applyTag() {
  if (!tagInput.value.trim() || !tagSelection.value.length) return;
  try {
    await tagManuscriptBlocks(props.projectId, {
      block_ids: tagSelection.value,
      chapter_tag: tagInput.value.trim(),
    });
    showTagModal.value = false;
    await loadBlocks();
    emit("updated");
  } catch (e) {
    console.error("Tag failed", e);
  }
}

// Export
async function handleExport(fmt) {
  try {
    const blob = await exportManuscript(props.projectId, fmt);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `manuscript.${fmt}`;
    a.click();
    URL.revokeObjectURL(url);
  } catch (e) {
    console.error("Export failed", e);
  }
}
</script>

<style scoped>
.manuscript-overlay {
  position: fixed;
  inset: 0;
  z-index: 200;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
}

.manuscript-reader {
  width: 90vw;
  max-width: 1400px;
  height: 88vh;
  background: var(--surface-primary, #12121e);
  border-radius: 12px;
  display: flex;
  flex-direction: column;
  box-shadow: 0 8px 48px rgba(0, 0, 0, 0.5);
  overflow: hidden;
}

/* Toolbar */
.reader-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border-subtle, #2d2d44);
}

.reader-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary, #e0e0e0);
}

.reader-stats {
  font-size: 12px;
  color: var(--text-tertiary, #888);
}

.reader-toolbar-spacer { flex: 1; }

.reader-toolbar-actions {
  display: flex;
  gap: 6px;
}

.reader-close {
  background: none;
  border: none;
  color: var(--text-tertiary, #888);
  font-size: 22px;
  cursor: pointer;
  padding: 0 4px;
  margin-left: 8px;
}
.reader-close:hover { color: var(--text-primary, #e0e0e0); }

/* Two-panel body */
.reader-body {
  flex: 1;
  display: grid;
  grid-template-columns: 260px 1fr;
  min-height: 0;
  overflow: hidden;
}

/* Toolbar buttons */
.toolbar-btn {
  background: var(--surface-tertiary, #252540);
  border: 1px solid var(--border-subtle, #2d2d44);
  border-radius: 4px;
  padding: 5px 12px;
  font-size: 12px;
  color: var(--text-secondary, #aaa);
  cursor: pointer;
}
.toolbar-btn:hover {
  color: var(--text-primary, #e0e0e0);
  background: var(--surface-hover, #303050);
}
.toolbar-btn--primary {
  background: var(--accent-copper, #c09060);
  border-color: var(--accent-copper, #c09060);
  color: #fff;
}
.toolbar-btn--primary:hover {
  background: #d0a070;
}
.toolbar-btn--danger { color: #e05050; }
.toolbar-btn--danger:hover { color: #ff6060; background: rgba(224, 80, 80, 0.1); }

/* Modals */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 210;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
}

.modal-box {
  background: var(--surface-primary, #12121e);
  border: 1px solid var(--border-subtle, #2d2d44);
  border-radius: 8px;
  padding: 20px;
  width: 400px;
  max-height: 440px;
}

.modal-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary, #e0e0e0);
  margin-bottom: 12px;
}

.modal-body {
  margin-bottom: 12px;
  color: var(--text-primary, #e0e0e0);
  font-size: 13px;
}

.modal-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.tag-select-list {
  max-height: 200px;
  overflow-y: auto;
  margin-bottom: 10px;
}

.tag-select-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 0;
  font-size: 12px;
  color: var(--text-secondary, #aaa);
  cursor: pointer;
}

.tag-input {
  width: 100%;
  background: var(--surface-tertiary, #252540);
  border: 1px solid var(--border-subtle, #2d2d44);
  border-radius: 4px;
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text-primary, #e0e0e0);
}

/* Transition */
.reader-enter-active,
.reader-leave-active {
  transition: opacity 0.25s ease;
}
.reader-enter-active .manuscript-reader,
.reader-leave-active .manuscript-reader {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.reader-enter-from,
.reader-leave-to {
  opacity: 0;
}
.reader-enter-from .manuscript-reader,
.reader-leave-to .manuscript-reader {
  transform: scale(0.96);
}
</style>
