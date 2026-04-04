<template>
  <div class="prose-view">
    <div ref="scrollRef" class="prose-scroll">
      <template v-if="groupedChapters.length">
        <div
          v-for="chapter in groupedChapters"
          :key="chapter.tag"
          :ref="el => setChapterRef(chapter.tag, el)"
          class="prose-chapter"
        >
          <div v-if="chapter.tag !== '__untagged__'" class="chapter-heading">
            <h2 class="chapter-title">{{ chapter.tag }}</h2>
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
            @click="handleBlockClick(block.block_id)"
          >
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
                <button class="prose-editor-done" @click.stop="finishEdit">完成</button>
              </div>
            </template>
            <!-- Read mode -->
            <p v-else class="prose-content">{{ block.content }}</p>
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

const props = defineProps({
  blocks: { type: Array, default: () => [] },
});

const emit = defineEmits(["edit-save"]);

const scrollRef = ref(null);
const editingId = ref(null);
const editorRef = ref(null);
const chapterRefs = {};

let saveTimer = null;
let pendingSave = null;

// Group blocks by chapter_tag, preserving block_order
const groupedChapters = computed(() => {
  const map = new Map();
  for (const b of props.blocks) {
    const tag = b.chapter_tag || "__untagged__";
    if (!map.has(tag)) {
      map.set(tag, { tag, wordCount: 0, blocks: [] });
    }
    const ch = map.get(tag);
    ch.blocks.push(b);
    ch.wordCount += b.word_count || 0;
  }
  // Move __untagged__ to end
  const result = [];
  for (const [tag, ch] of map) {
    if (tag !== "__untagged__") result.push(ch);
  }
  if (map.has("__untagged__")) {
    result.push(map.get("__untagged__"));
  }
  return result;
});

function setChapterRef(tag, el) {
  if (el) chapterRefs[tag] = el;
}

function scrollToChapter(tag) {
  const el = chapterRefs[tag];
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
  margin-bottom: 4px;
  padding: 4px 8px;
  border-radius: 4px;
  cursor: text;
  transition: background 0.15s;
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

.prose-editor-done {
  background: var(--accent-copper, #c09060);
  border: none;
  border-radius: 4px;
  padding: 3px 12px;
  font-size: 12px;
  color: #fff;
  cursor: pointer;
}

.prose-editor-done:hover {
  opacity: 0.85;
}

.prose-empty {
  text-align: center;
  color: var(--text-dim, #999);
  padding: 120px 0;
  font-size: 15px;
  max-width: 720px;
}
</style>
