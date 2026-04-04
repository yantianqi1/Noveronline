<template>
  <div v-if="hasContent" class="continuation-panel">
    <div class="continuation-header" @click="collapsed = !collapsed">
      <span class="continuation-title">续写上下文</span>
      <span class="continuation-toggle">{{ collapsed ? '&#x25B6;' : '&#x25BC;' }}</span>
    </div>

    <!-- Continuation anchor — always visible, not affected by collapse -->
    <div v-if="context.tail_text" class="ctx-anchor">
      <div class="ctx-anchor-top">
        <span class="ctx-anchor-label">续写起点</span>
        <span v-if="anchorRef" class="ctx-anchor-ref">{{ anchorRef }}</span>
      </div>
      <div class="ctx-anchor-text">{{ truncatedTail }}</div>
      <div class="ctx-anchor-meta">
        <span v-if="context.last_pov" class="ctx-meta-tag">POV: {{ context.last_pov }}</span>
        <span v-if="context.last_location" class="ctx-meta-tag">&#x1F4CD; {{ context.last_location }}</span>
        <span v-if="context.narrative_note" class="ctx-meta-tag">{{ context.narrative_note }}</span>
      </div>
    </div>

    <div v-show="!collapsed" class="continuation-body">
      <!-- Recent summaries -->
      <div v-if="context.recent_summaries && context.recent_summaries.length" class="ctx-section">
        <div class="ctx-label">近期段落</div>
        <div v-for="s in context.recent_summaries" :key="s.block_order" class="ctx-summary-item">
          <span class="ctx-order">{{ s.chapter_tag ? `[${s.chapter_tag}]` : '' }} #{{ s.block_order }}</span>
          <span class="ctx-text">{{ s.summary }}</span>
        </div>
      </div>

      <!-- Active threads -->
      <div v-if="context.active_threads && context.active_threads.length" class="ctx-section">
        <div class="ctx-label">活跃伏笔</div>
        <div v-for="(t, i) in context.active_threads" :key="i" class="ctx-thread-item">
          {{ t }}
        </div>
      </div>

      <!-- Stats -->
      <div class="ctx-section ctx-stats">
        {{ context.total_words || 0 }} 字 &middot; {{ context.total_blocks || 0 }} 段
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";

const props = defineProps({
  context: { type: Object, default: () => ({}) },
});

const collapsed = ref(true);

const hasContent = computed(() => {
  const c = props.context;
  return (
    (c.recent_summaries && c.recent_summaries.length) ||
    (c.active_threads && c.active_threads.length) ||
    c.tail_text
  );
});

const truncatedTail = computed(() => {
  const text = props.context.tail_text || "";
  if (text.length <= 300) return text;
  // Find a sentence boundary near the truncation point
  const start = text.length - 300;
  const slice = text.slice(start);
  // Try to start at a sentence boundary (。！？)
  const boundaryMatch = slice.match(/^[^。！？]*[。！？]/);
  if (boundaryMatch && boundaryMatch.index + boundaryMatch[0].length < 60) {
    return "..." + slice.slice(boundaryMatch.index + boundaryMatch[0].length);
  }
  return "..." + slice;
});

const anchorRef = computed(() => {
  const c = props.context;
  const parts = [];
  if (c.last_chapter_tag) parts.push(c.last_chapter_tag);
  if (c.last_block_order) parts.push(`#${c.last_block_order}`);
  return parts.join(" ");
});
</script>

<style scoped>
.continuation-panel {
  background: var(--surface-secondary, #1a1a2e);
  border: 1px solid var(--border-subtle, #2d2d44);
  border-radius: 8px;
  margin-bottom: 12px;
  font-size: 13px;
}

.continuation-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;
}

.continuation-title {
  flex: 1;
  font-weight: 600;
  color: var(--text-primary, #e0e0e0);
}

.continuation-toggle {
  font-size: 10px;
  color: var(--text-tertiary, #888);
}

/* ─── Continuation anchor (always visible) ─── */
.ctx-anchor {
  margin: 0 12px 8px;
  padding: 10px 12px;
  border-left: 3px solid var(--accent-primary, #7c6cff);
  background: var(--surface-tertiary, #252540);
  border-radius: 0 6px 6px 0;
}

.ctx-anchor-top {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.ctx-anchor-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--accent-primary, #7c6cff);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.ctx-anchor-ref {
  font-size: 11px;
  color: var(--text-tertiary, #888);
  font-family: var(--font-mono, monospace);
}

.ctx-anchor-text {
  color: var(--text-primary, #e0e0e0);
  line-height: 1.7;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-all;
}

.ctx-anchor-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

/* ─── Body (collapsible) ─── */
.continuation-body {
  padding: 4px 12px 10px;
}

.ctx-section {
  margin-bottom: 8px;
}

.ctx-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary, #aaa);
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.ctx-summary-item {
  display: flex;
  gap: 8px;
  padding: 2px 0;
  line-height: 1.5;
}

.ctx-order {
  flex-shrink: 0;
  color: var(--text-tertiary, #888);
  font-size: 11px;
  min-width: 40px;
}

.ctx-text {
  color: var(--text-primary, #e0e0e0);
}

.ctx-thread-item {
  padding: 2px 0 2px 12px;
  color: var(--accent-warning, #f0c040);
  font-size: 12px;
  line-height: 1.5;
}

.ctx-thread-item::before {
  content: "\2022 ";
  margin-left: -10px;
}

.ctx-meta-tag {
  background: var(--surface-tertiary, #252540);
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  color: var(--text-secondary, #aaa);
}

.ctx-stats {
  font-size: 11px;
  color: var(--text-tertiary, #888);
  text-align: right;
}
</style>
