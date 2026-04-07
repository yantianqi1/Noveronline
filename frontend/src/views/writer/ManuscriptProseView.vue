<template>
  <div class="prose-view">
    <div ref="scrollRef" class="prose-scroll">
      <template v-if="groupedChapters.length">
        <div
          v-for="chapter in groupedChapters"
          :key="chapter.chapter_id"
          :ref="el => setChapterRef(chapter.chapter_id, el)"
          class="prose-chapter"
        >
          <div v-if="chapter.chapter_id !== '__untagged__'" class="chapter-heading">
            <h2 class="chapter-title">{{ chapter.title }}</h2>
            <span class="chapter-stats">{{ chapter.wordCount }} 字</span>
          </div>
          <div v-else class="chapter-heading chapter-heading--muted">
            <h2 class="chapter-title">未归类</h2>
            <span class="chapter-stats">{{ chapter.wordCount }} 字</span>
          </div>

          <div
            v-for="block in chapter.blocks"
            :key="block.block_id"
            class="prose-paragraph"
            :class="{ 'prose-paragraph--editing': editingId === block.block_id }"
            @mouseenter="hoveredId = block.block_id"
            @mouseleave="hoveredId = null"
            @click="handleBlockClick(block.block_id)"
          >
            <!-- Hover action bar -->
            <div
              v-if="hoveredId === block.block_id && editingId !== block.block_id"
              class="block-hover-bar"
              @click.stop
            >
              <n-select
                v-if="chapters.length > 0"
                size="tiny"
                :value="block.chapter_id || '__unassign__'"
                :options="moveTargetOptions"
                :consistent-menu-width="false"
                @update:value="val => onMoveBlock(block.block_id, val)"
                style="width: 110px"
                title="移动到章节"
              />
              <n-button text size="tiny" type="error" @click="$emit('delete', block.block_id)">删除</n-button>
            </div>
            <!-- Edit mode -->
            <template v-if="editingId === block.block_id">
              <textarea
                ref="editorRef"
                class="prose-inline-editor"
                :value="block.content"
                @input="e => onInput(block, e.target.value)"
                @click.stop
              ></textarea>
              <div class="prose-editor-footer">
                <span class="prose-editor-wc">{{ block.word_count }} 字</span>
                <n-button size="tiny" type="primary" @click.stop="finishEdit">完成</n-button>
              </div>
            </template>
            <!-- Read mode -->
            <p v-else class="prose-content">{{ block.content }}</p>
          </div>

          <!-- Empty chapter placeholder -->
          <div v-if="chapter.blocks.length === 0 && chapter.chapter_id !== '__untagged__'" class="prose-empty-chapter">
            暂无段落，在写作模式中创作并提交到此章节。
          </div>
        </div>
      </template>
      <div v-else class="prose-empty">
        尚无稿件内容，在写作模式中创作并提交到稿件。
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, watch } from "vue";
import { NSelect, NButton } from "naive-ui";

const props = defineProps({
  blocks: { type: Array, default: () => [] },
  chapters: { type: Array, default: () => [] },
});

const emit = defineEmits(["edit-save", "delete", "move-block"]);

const scrollRef = ref(null);
const editingId = ref(null);
const editorRef = ref(null);
const hoveredId = ref(null);
const chapterRefs = {};

const moveTargetOptions = computed(() => [
  ...props.chapters.map(c => ({ label: c.title || '未命名', value: c.chapter_id })),
  { label: '未归类', value: '__unassign__' },
]);

let saveTimer = null;
let pendingSave = null;

// Group blocks by chapter_id, using real chapter list to preserve empty chapters
const groupedChapters = computed(() => {
  const map = new Map();
  // Initialize from real chapter list
  for (const ch of props.chapters) {
    map.set(ch.chapter_id, {
      chapter_id: ch.chapter_id,
      title: ch.title || `第${ch.order}章`,
      order: ch.order,
      wordCount: 0,
      blocks: [],
    });
  }
  // Assign blocks to chapters
  for (const b of props.blocks) {
    const cid = b.chapter_id || "__untagged__";
    if (!map.has(cid)) {
      map.set(cid, {
        chapter_id: cid,
        title: cid === "__untagged__" ? "未归类" : (b.chapter_tag || "未归类"),
        order: Infinity,
        wordCount: 0,
        blocks: [],
      });
    }
    const ch = map.get(cid);
    ch.blocks.push(b);
    ch.wordCount += b.word_count || 0;
  }
  return [...map.values()].sort((a, b) => a.order - b.order);
});

function setChapterRef(id, el) {
  if (el) chapterRefs[id] = el;
}

function scrollToChapter(chapterId) {
  const el = chapterRefs[chapterId];
  if (el) {
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function handleBlockClick(blockId) {
  if (editingId.value === blockId) return;
  flushSave();
  editingId.value = blockId;
  nextTick(() => {
    const textarea = editorRef.value;
    const el = Array.isArray(textarea) ? textarea[0] : textarea;
    if (el) {
      el.focus();
      el.style.height = "auto";
      el.style.height = el.scrollHeight + "px";
    }
  });
}

function onInput(block, value) {
  block.content = value;
  block.word_count = value.length;
  // Auto-resize textarea
  nextTick(() => {
    const textarea = editorRef.value;
    const el = Array.isArray(textarea) ? textarea[0] : textarea;
    if (el) {
      el.style.height = "auto";
      el.style.height = el.scrollHeight + "px";
    }
  });
  // Debounced save
  pendingSave = { block, value };
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    if (pendingSave) {
      emit("edit-save", pendingSave.block, pendingSave.value);
      pendingSave = null;
    }
  }, 800);
}

function flushSave() {
  if (pendingSave) {
    clearTimeout(saveTimer);
    emit("edit-save", pendingSave.block, pendingSave.value);
    pendingSave = null;
  }
}

function finishEdit() {
  flushSave();
  editingId.value = null;
}

function onMoveBlock(blockId, targetValue) {
  const targetChapterId = targetValue === "__unassign__" ? null : targetValue;
  emit("move-block", blockId, targetChapterId);
}

// Close editor on outside click
function handleOutsideClick(e) {
  if (!editingId.value) return;
  const scrollEl = scrollRef.value;
  if (scrollEl && !scrollEl.querySelector(".prose-paragraph--editing")?.contains(e.target)) {
    finishEdit();
  }
}

watch(editingId, (val) => {
  if (val) {
    document.addEventListener("click", handleOutsideClick, true);
  } else {
    document.removeEventListener("click", handleOutsideClick, true);
  }
});

defineExpose({ scrollToChapter });
</script>

<style scoped>
.prose-view {
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.prose-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 40px 32px 80px;
  display: flex;
  flex-direction: column;
  align-items: center;
}

.prose-chapter {
  width: 100%;
  max-width: 720px;
  margin-bottom: 48px;
}

.chapter-heading {
  margin-bottom: 28px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--line-soft, #e0dcd4);
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.chapter-heading--muted .chapter-title {
  color: var(--text-dim, #999);
  font-style: italic;
}

.chapter-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-main, #1a1a1a);
  margin: 0;
  font-family: "Noto Serif SC", "Source Han Serif CN", "SimSun", serif;
}

.chapter-stats {
  font-size: 12px;
  color: var(--text-dim, #999);
}

.prose-paragraph {
  position: relative;
  margin-bottom: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: text;
  transition: background 0.15s;
}

.block-hover-bar {
  position: absolute;
  top: 4px;
  right: 4px;
  z-index: 2;
  display: flex;
  gap: 4px;
  padding: 2px 4px;
  background: var(--surface-secondary, #f5f0e8);
  border: 1px solid var(--line-soft, #e0dcd4);
  border-radius: 4px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  align-items: center;
}


.prose-paragraph:hover:not(.prose-paragraph--editing) {
  background: rgba(176, 125, 75, 0.04);
}

.prose-paragraph--editing {
  background: rgba(176, 125, 75, 0.06);
  padding: 8px;
  border-radius: 8px;
}

.prose-content {
  font-size: 16px;
  line-height: 1.9;
  color: var(--text-main, #1a1a1a);
  white-space: pre-wrap;
  font-family: "Noto Serif SC", "Source Han Serif CN", "SimSun", serif;
  margin: 0;
}

.prose-inline-editor {
  width: 100%;
  border: 1px solid var(--accent-copper, #c09060);
  border-radius: 6px;
  padding: 12px 14px;
  font-size: 16px;
  line-height: 1.9;
  color: var(--text-main, #1a1a1a);
  font-family: "Noto Serif SC", "Source Han Serif CN", "SimSun", serif;
  background: #fff;
  resize: none;
  outline: none;
  overflow: hidden;
}

.prose-editor-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
}

.prose-editor-wc {
  font-size: 11px;
  color: var(--text-dim, #999);
}


.prose-empty {
  text-align: center;
  color: var(--text-dim, #999);
  padding: 120px 0;
  font-size: 15px;
  max-width: 720px;
}

.prose-empty-chapter {
  text-align: center;
  color: var(--text-dim, #bbb);
  padding: 24px 0;
  font-size: 13px;
  font-style: italic;
}
</style>
