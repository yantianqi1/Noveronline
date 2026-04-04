<template>
  <div class="ms-toc">
    <p class="panel-kicker mono">MANUSCRIPT</p>
    <h2 class="panel-title title-ancient">稿件目录</h2>

    <div class="toc-list">
      <div
        class="toc-entry"
        :class="{ active: !selectedTag }"
        @click="$emit('jump', null)"
      >
        <span class="toc-label">全部</span>
        <span class="toc-meta">{{ totalBlocks }} 段</span>
      </div>

      <div
        v-for="ch in chapters"
        :key="ch.tag"
        class="toc-entry"
        :class="{ active: selectedTag === ch.tag }"
        @click="$emit('jump', ch.tag)"
      >
        <template v-if="renamingTag === ch.tag">
          <input
            ref="renameInput"
            v-model="renameValue"
            class="toc-rename-input"
            @keydown.enter="commitRename(ch.tag)"
            @keydown.escape="cancelRename"
            @blur="commitRename(ch.tag)"
            @click.stop
          />
        </template>
        <template v-else>
          <span class="toc-label" @dblclick.stop="startRename(ch.tag)">{{ ch.tag }}</span>
          <span class="toc-meta">{{ ch.blockCount }} 段 · {{ ch.wordCount }} 字</span>
        </template>
      </div>

      <div
        v-if="untaggedCount > 0"
        class="toc-entry toc-entry--muted"
        :class="{ active: selectedTag === '__untagged__' }"
        @click="$emit('jump', '__untagged__')"
      >
        <span class="toc-label">未归类</span>
        <span class="toc-meta">{{ untaggedCount }} 段</span>
      </div>
    </div>

    <!-- New chapter -->
    <div class="toc-new">
      <input
        v-model="newChapterName"
        class="toc-new-input"
        placeholder="新章节名称..."
        @keydown.enter="handleCreate"
      />
      <button class="toc-new-btn" :disabled="!newChapterName.trim()" @click="handleCreate">添加</button>
    </div>

    <!-- Stats -->
    <div class="toc-stats-bar">
      <div class="toc-stat">{{ totalWords }} 字</div>
      <div class="toc-stat">{{ chapters.length }} 章</div>
      <div class="toc-stat">{{ totalBlocks }} 段</div>
    </div>

    <!-- Export -->
    <div class="toc-actions">
      <button class="btn btn-sm" @click="$emit('export', 'txt')">导出 TXT</button>
      <button class="btn btn-sm" @click="$emit('export', 'md')">导出 MD</button>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick } from "vue";

const props = defineProps({
  chapters: { type: Array, default: () => [] },
  selectedTag: { type: [String, null], default: null },
  totalWords: { type: Number, default: 0 },
  totalBlocks: { type: Number, default: 0 },
  untaggedCount: { type: Number, default: 0 },
});

const emit = defineEmits(["jump", "create-chapter", "rename-chapter", "export"]);

const newChapterName = ref("");
const renamingTag = ref(null);
const renameValue = ref("");
const renameInput = ref(null);

function handleCreate() {
  const name = newChapterName.value.trim();
  if (!name) return;
  emit("create-chapter", name);
  newChapterName.value = "";
}

function startRename(tag) {
  renamingTag.value = tag;
  renameValue.value = tag;
  nextTick(() => {
    const el = renameInput.value;
    const input = Array.isArray(el) ? el[0] : el;
    if (input) {
      input.focus();
      input.select();
    }
  });
}

function commitRename(oldTag) {
  const newTag = renameValue.value.trim();
  if (newTag && newTag !== oldTag) {
    emit("rename-chapter", oldTag, newTag);
  }
  renamingTag.value = null;
}

function cancelRename() {
  renamingTag.value = null;
}
</script>

<style scoped>
.ms-toc {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  height: 100%;
  overflow: hidden;
}

.toc-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.toc-entry {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
  border-left: 3px solid transparent;
}

.toc-entry:hover {
  background: rgba(176, 125, 75, 0.06);
}

.toc-entry.active {
  background: rgba(176, 125, 75, 0.1);
  border-left-color: var(--accent-copper, #c09060);
}

.toc-entry--muted .toc-label {
  color: var(--text-dim, #999);
  font-style: italic;
}

.toc-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-main, #1a1a1a);
}

.toc-meta {
  font-size: 11px;
  color: var(--text-dim, #999);
  white-space: nowrap;
  margin-left: 8px;
}

.toc-rename-input {
  flex: 1;
  padding: 4px 8px;
  font-size: 14px;
  border: 1px solid var(--accent-copper, #c09060);
  border-radius: 4px;
  outline: none;
  background: #fff;
  color: var(--text-main, #1a1a1a);
}

.toc-new {
  display: flex;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--line-soft, #e0dcd4);
}

.toc-new-input {
  flex: 1;
  padding: 6px 10px;
  font-size: 13px;
  border: 1px solid var(--line-medium, #d0ccc4);
  border-radius: 6px;
  outline: none;
  background: #fff;
  color: var(--text-main, #1a1a1a);
}

.toc-new-input:focus {
  border-color: var(--accent-copper, #c09060);
}

.toc-new-btn {
  padding: 6px 14px;
  font-size: 12px;
  background: var(--accent-copper, #c09060);
  border: none;
  border-radius: 6px;
  color: #fff;
  cursor: pointer;
}

.toc-new-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.toc-stats-bar {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  border-top: 1px solid var(--line-soft, #e0dcd4);
}

.toc-stat {
  font-size: 12px;
  color: var(--text-dim, #999);
}

.toc-actions {
  display: flex;
  gap: 6px;
}
</style>
