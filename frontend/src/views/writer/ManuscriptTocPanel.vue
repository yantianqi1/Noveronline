<template>
  <div class="ms-toc">
    <div class="toc-header">
      <button class="toc-back-btn" @click="$emit('back')" title="返回写作模式"><span class="toc-back-chevron"></span></button>
      <div>
        <p class="panel-kicker mono">MANUSCRIPT</p>
        <h2 class="panel-title title-ancient">稿件目录</h2>
      </div>
    </div>

    <div class="toc-list">
      <!-- "All" entry -->
      <div
        class="toc-entry"
        :class="{ active: !selectedChapterId }"
        @click="$emit('jump', null)"
      >
        <span class="toc-label">全部</span>
        <span class="toc-meta">{{ totalBlocks }} 段</span>
      </div>

      <!-- Chapter folders -->
      <div v-for="ch in chapters" :key="ch.chapter_id" class="toc-chapter">
        <div
          class="toc-entry toc-entry--chapter"
          :class="{ active: selectedChapterId === ch.chapter_id }"
          @click="handleChapterClick(ch)"
        >
          <!-- Expand/collapse toggle -->
          <button class="toc-toggle-btn" @click.stop="toggleExpand(ch.chapter_id)">
            <span class="toc-toggle-icon" :class="{ expanded: expandedChapters.has(ch.chapter_id) }">▸</span>
          </button>

          <template v-if="renamingId === ch.chapter_id">
            <n-input
              ref="renameInput"
              v-model:value="renameValue"
              size="small"
              @keydown.enter="commitRename(ch.chapter_id)"
              @keydown.escape="cancelRename"
              @blur="commitRename(ch.chapter_id)"
              @click.stop
              style="flex: 1"
            />
          </template>
          <template v-else>
            <span class="toc-label toc-label--chapter">{{ ch.title || '未命名章节' }}</span>
            <span class="toc-meta">{{ ch.blockCount }} 段 · {{ ch.wordCount }} 字</span>
            <div class="toc-actions" @click.stop>
              <button class="toc-action-btn" @click="startRename(ch)" title="重命名">✎</button>
              <button class="toc-action-btn toc-action-btn--danger" @click="$emit('delete-chapter', ch.chapter_id)" title="删除章节">✕</button>
            </div>
          </template>
        </div>

        <!-- Child blocks (expanded) -->
        <div v-if="expandedChapters.has(ch.chapter_id)" class="toc-children">
          <div
            v-for="block in getBlocksForChapter(ch.chapter_id)"
            :key="block.block_id"
            class="toc-entry toc-entry--block"
            @click.stop="$emit('jump', ch.chapter_id)"
          >
            <span class="toc-block-label">{{ blockLabel(block) }}</span>
            <div class="toc-block-actions" @click.stop>
              <n-select
                size="tiny"
                :value="ch.chapter_id"
                :options="moveTargetOptions"
                :consistent-menu-width="false"
                @update:value="val => handleMoveBlock(block.block_id, val, ch.chapter_id)"
                style="width: 90px"
              />
            </div>
          </div>
          <div v-if="getBlocksForChapter(ch.chapter_id).length === 0" class="toc-empty-hint">
            暂无段落
          </div>
        </div>
      </div>

      <!-- Untagged section -->
      <div v-if="untaggedCount > 0" class="toc-chapter">
        <div
          class="toc-entry toc-entry--chapter toc-entry--muted"
          :class="{ active: selectedChapterId === '__untagged__' }"
          @click="$emit('jump', '__untagged__')"
        >
          <button class="toc-toggle-btn" @click.stop="toggleExpand('__untagged__')">
            <span class="toc-toggle-icon" :class="{ expanded: expandedChapters.has('__untagged__') }">▸</span>
          </button>
          <span class="toc-label">未归类</span>
          <span class="toc-meta">{{ untaggedCount }} 段</span>
        </div>

        <div v-if="expandedChapters.has('__untagged__')" class="toc-children">
          <div
            v-for="block in untaggedBlocks"
            :key="block.block_id"
            class="toc-entry toc-entry--block"
          >
            <span class="toc-block-label">{{ blockLabel(block) }}</span>
            <div class="toc-block-actions" @click.stop>
              <n-select
                size="tiny"
                value="__unassign__"
                :options="moveTargetOptions"
                :consistent-menu-width="false"
                @update:value="val => handleMoveBlock(block.block_id, val, '__unassign__')"
                style="width: 90px"
              />
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- New chapter -->
    <div class="toc-new">
      <n-input
        v-model:value="newChapterName"
        placeholder="新章节名称..."
        size="small"
        @keydown.enter="handleCreate"
      >
        <template #suffix>
          <n-button text type="primary" size="tiny" :disabled="!newChapterName.trim()" @click.stop="handleCreate">
            添加
          </n-button>
        </template>
      </n-input>
    </div>

    <!-- Stats -->
    <div class="toc-stats-bar">
      <span class="toc-stat-pill">{{ totalWords }} <small>字</small></span>
      <span class="toc-stat-pill">{{ chapters.length }} <small>章</small></span>
      <span class="toc-stat-pill">{{ totalBlocks }} <small>段</small></span>
    </div>

    <!-- Export -->
    <div class="toc-actions-bar">
      <n-button size="small" @click="$emit('export', 'txt')">导出 TXT</n-button>
      <n-button size="small" @click="$emit('export', 'md')">导出 MD</n-button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, reactive } from "vue";
import { NButton, NInput, NSelect } from "naive-ui";

const props = defineProps({
  chapters: { type: Array, default: () => [] },
  blocks: { type: Array, default: () => [] },
  selectedChapterId: { type: [String, null], default: null },
  totalWords: { type: Number, default: 0 },
  totalBlocks: { type: Number, default: 0 },
  untaggedCount: { type: Number, default: 0 },
});

const emit = defineEmits([
  "jump", "create-chapter", "rename-chapter", "delete-chapter",
  "move-block", "export", "back",
]);

const newChapterName = ref("");
const renamingId = ref(null);
const renameValue = ref("");
const renameInput = ref(null);
const expandedChapters = reactive(new Set());

const untaggedBlocks = computed(() =>
  props.blocks.filter(b => !b.chapter_id)
);

const moveTargetOptions = computed(() => [
  ...props.chapters.map(c => ({ label: c.title || '未命名', value: c.chapter_id })),
  { label: '未归类', value: '__unassign__' },
]);

function getBlocksForChapter(chapterId) {
  return props.blocks.filter(b => b.chapter_id === chapterId);
}

function blockLabel(block) {
  if (block.summary) return block.summary.slice(0, 40) + (block.summary.length > 40 ? "…" : "");
  if (block.content) return block.content.slice(0, 40) + (block.content.length > 40 ? "…" : "");
  return `段落 #${block.block_order}`;
}

function handleChapterClick(ch) {
  emit("jump", ch.chapter_id);
}

function toggleExpand(id) {
  if (expandedChapters.has(id)) {
    expandedChapters.delete(id);
  } else {
    expandedChapters.add(id);
  }
}

function handleCreate() {
  const name = newChapterName.value.trim();
  if (!name) return;
  emit("create-chapter", name);
  newChapterName.value = "";
}

function startRename(ch) {
  renamingId.value = ch.chapter_id;
  renameValue.value = ch.title || "";
  nextTick(() => {
    const el = renameInput.value;
    const comp = Array.isArray(el) ? el[0] : el;
    if (comp) {
      comp.focus();
      // n-input exposes select() on its internal input
      comp.inputElRef?.select?.();
    }
  });
}

function commitRename(chapterId) {
  const newTitle = renameValue.value.trim();
  if (newTitle) {
    emit("rename-chapter", chapterId, newTitle);
  }
  renamingId.value = null;
}

function cancelRename() {
  renamingId.value = null;
}

function handleMoveBlock(blockId, targetValue, currentValue) {
  if (targetValue === currentValue) return;
  const targetChapterId = targetValue === "__unassign__" ? null : targetValue;
  emit("move-block", blockId, targetChapterId);
}
</script>

<style scoped>
.ms-toc {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  overflow: hidden;
}

.toc-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

.toc-back-btn {
  width: 28px;
  height: 28px;
  border: 1px solid rgba(176, 125, 75, 0.15);
  border-radius: 8px;
  background: rgba(176, 125, 75, 0.04);
  color: var(--text-dim, #999);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.25s ease, border-color 0.25s ease, color 0.25s ease;
  flex-shrink: 0;
}

.toc-back-btn:hover {
  background: rgba(176, 125, 75, 0.1);
  border-color: rgba(176, 125, 75, 0.3);
  color: var(--accent-copper-deep, #8b6540);
}

.toc-back-btn:active {
  transform: scale(0.94);
}

.toc-back-chevron {
  width: 7px;
  height: 7px;
  border-left: 2px solid currentColor;
  border-bottom: 2px solid currentColor;
  transform: rotate(45deg);
  margin-left: 2px;
}

.toc-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.toc-entry {
  display: flex;
  align-items: center;
  padding: 7px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  border-left: 3px solid transparent;
  gap: 6px;
}

.toc-entry:hover {
  background: rgba(176, 125, 75, 0.06);
}

.toc-entry.active {
  background: rgba(176, 125, 75, 0.1);
  border-left-color: var(--accent-copper, #c09060);
}

.toc-entry--chapter {
  font-weight: 500;
}

.toc-entry--block {
  padding-left: 32px;
  font-size: 12px;
  color: var(--text-dim, #999);
  border-left: none;
}

.toc-entry--muted .toc-label {
  color: var(--text-dim, #999);
  font-style: italic;
}

.toc-toggle-btn {
  width: 18px;
  height: 18px;
  border: none;
  background: transparent;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  padding: 0;
  color: var(--text-dim, #999);
}

.toc-toggle-icon {
  font-size: 10px;
  transition: transform 0.15s;
  display: inline-block;
}

.toc-toggle-icon.expanded {
  transform: rotate(90deg);
}

.toc-label {
  font-size: 14px;
  color: var(--text-main, #1a1a1a);
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.toc-label--chapter {
  font-weight: 600;
}

.toc-meta {
  font-size: 11px;
  color: var(--text-dim, #999);
  white-space: nowrap;
  flex-shrink: 0;
}

.toc-actions {
  display: flex;
  gap: 2px;
  opacity: 0;
  transition: opacity 0.15s;
  flex-shrink: 0;
}

.toc-entry:hover .toc-actions {
  opacity: 1;
}

.toc-action-btn {
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  color: var(--text-dim, #999);
  cursor: pointer;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
}

.toc-action-btn:hover {
  color: var(--accent-copper, #c09060);
  background: rgba(176, 125, 75, 0.08);
}

.toc-action-btn--danger:hover {
  color: #c05050;
  background: rgba(224, 80, 80, 0.08);
}

.toc-children {
  margin-left: 8px;
  border-left: 1px solid var(--line-soft, #e0dcd4);
}

.toc-empty-hint {
  padding: 4px 32px;
  font-size: 11px;
  color: var(--text-dim, #bbb);
  font-style: italic;
}

.toc-block-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.toc-block-actions {
  opacity: 0;
  transition: opacity 0.15s;
  flex-shrink: 0;
}

.toc-entry--block:hover .toc-block-actions {
  opacity: 1;
}


.toc-new {
  display: flex;
  gap: 6px;
  padding-top: 8px;
  border-top: 1px solid var(--line-soft, #e0dcd4);
}


.toc-stats-bar {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  border-top: 1px solid var(--line-soft, #e0dcd4);
}

.toc-stat-pill {
  background: rgba(176, 125, 75, 0.08);
  border-radius: 12px;
  padding: 3px 10px;
  font-size: 12px;
  color: var(--accent-copper-deep, #8b6540);
  font-weight: 500;
}

.toc-stat-pill small {
  font-weight: 400;
  opacity: 0.7;
}

.toc-actions-bar {
  display: flex;
  gap: 6px;
}
</style>
