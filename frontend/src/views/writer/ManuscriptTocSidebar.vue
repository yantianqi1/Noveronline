<template>
  <div class="toc-sidebar">
    <div class="toc-header">
      <div class="toc-title">目录</div>
      <div class="toc-stats">{{ totalWords }} 字 · {{ totalBlocks }} 段</div>
    </div>
    <div class="toc-list">
      <div
        class="toc-item"
        :class="{ active: selectedTag === null }"
        @click="$emit('select', null)"
      >
        <span class="toc-item-label">全部</span>
        <span class="toc-item-meta">{{ totalBlocks }} 段</span>
      </div>
      <div
        v-for="ch in chapters"
        :key="ch.tag"
        class="toc-item"
        :class="{ active: selectedTag === ch.tag }"
        @click="$emit('select', ch.tag)"
      >
        <span class="toc-item-label">{{ ch.tag }}</span>
        <span class="toc-item-meta">{{ ch.blockCount }} 段 · {{ ch.wordCount }} 字</span>
      </div>
      <div
        v-if="hasUntagged"
        class="toc-item"
        :class="{ active: selectedTag === '__untagged__' }"
        @click="$emit('select', '__untagged__')"
      >
        <span class="toc-item-label toc-item-label--muted">未归类</span>
        <span class="toc-item-meta">{{ untaggedCount }} 段</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  chapters: { type: Array, default: () => [] },
  selectedTag: { type: [String, null], default: null },
  totalWords: { type: Number, default: 0 },
  totalBlocks: { type: Number, default: 0 },
  untaggedCount: { type: Number, default: 0 },
});

defineEmits(["select"]);

const hasUntagged = computed(() => props.untaggedCount > 0);
</script>

<style scoped>
.toc-sidebar {
  display: flex;
  flex-direction: column;
  border-right: 1px solid var(--border-subtle, #2d2d44);
  background: var(--surface-secondary, #1a1a2e);
  min-height: 0;
  overflow: hidden;
}

.toc-header {
  padding: 10px 12px 8px;
  border-bottom: 1px solid var(--border-subtle, #2d2d44);
}

.toc-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary, #e0e0e0);
}

.toc-stats {
  font-size: 11px;
  color: var(--text-tertiary, #888);
  margin-top: 4px;
}

.toc-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
}

.toc-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  cursor: pointer;
  border-left: 3px solid transparent;
  transition: background 0.15s, border-color 0.15s;
}

.toc-item:hover {
  background: var(--surface-hover, #252540);
}

.toc-item.active {
  background: var(--surface-hover, #252540);
  border-left-color: var(--accent-copper, #c09060);
}

.toc-item-label {
  font-size: 13px;
  color: var(--text-primary, #e0e0e0);
  font-weight: 500;
}

.toc-item-label--muted {
  color: var(--text-tertiary, #888);
  font-style: italic;
}

.toc-item-meta {
  font-size: 11px;
  color: var(--text-tertiary, #888);
  white-space: nowrap;
  margin-left: 8px;
}
</style>
