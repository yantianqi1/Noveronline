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
              <n-button size="small" quaternary @click="handleBatchTag">批量标注</n-button>
              <n-button size="small" quaternary @click="handleExport('txt')">导出 TXT</n-button>
              <n-button size="small" quaternary @click="handleExport('md')">导出 MD</n-button>
            </div>
            <n-button quaternary class="reader-close" @click="$emit('close')">&times;</n-button>
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
          <n-modal
            :show="showTagModal"
            preset="card"
            title="批量标注章节"
            style="width: 400px; max-width: 90vw"
            :mask-closable="true"
            @update:show="val => { if (!val) showTagModal = false }"
          >
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
            <n-input
              v-model:value="tagInput"
              placeholder="输入章节标签，如：第一章"
            />
            <template #footer>
              <div class="modal-actions">
                <n-button type="primary" @click="applyTag">应用</n-button>
                <n-button @click="showTagModal = false">取消</n-button>
              </div>
            </template>
          </n-modal>

          <!-- Delete confirm -->
          <n-modal
            :show="!!deleteTarget"
            preset="card"
            title="确认删除"
            style="width: 400px; max-width: 90vw"
            :mask-closable="true"
            @update:show="val => { if (!val) deleteTarget = null }"
          >
            <p>确定要删除这段稿件内容吗？此操作不可撤销。</p>
            <template #footer>
              <div class="modal-actions">
                <n-button type="error" @click="doDelete">删除</n-button>
                <n-button @click="deleteTarget = null">取消</n-button>
              </div>
            </template>
          </n-modal>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch } from "vue";
import { NButton, NInput, NModal } from "naive-ui";
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
  font-size: 22px;
  margin-left: 8px;
}

/* Two-panel body */
.reader-body {
  flex: 1;
  display: grid;
  grid-template-columns: 260px 1fr;
  min-height: 0;
  overflow: hidden;
}

/* Modal actions */
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
