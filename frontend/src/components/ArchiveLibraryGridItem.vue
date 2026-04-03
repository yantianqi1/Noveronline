<template>
  <article class="archive-card workbench-card" :class="{ active, selected }" @click="$emit('toggle')">
    <div class="card-top">
      <div class="card-identity">
        <h4 class="card-name">{{ item.entity_name }}</h4>
        <span class="card-tier">{{ formatImportanceTier(item.importance_tier) }}</span>
      </div>
      <span class="status-tag" :class="entityTone">{{ formatEntityType(item.entity_type) }}</span>
    </div>

    <p v-if="roleText" class="card-role">{{ roleText }}</p>
    <p class="card-summary">{{ driveText }}</p>

    <div class="card-footer">
      <span class="card-project">{{ item.project_name }}</span>
      <button class="card-detail-btn" type="button" @click.stop="$emit('expand')">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M6 3l5 5-5 5" />
        </svg>
        详情
      </button>
    </div>
  </article>
</template>

<script setup>
import { computed } from "vue";

import { formatEntityType, formatImportanceTier } from "../utils/chineseDisplay.js";

const props = defineProps({
  active: { type: Boolean, default: false },
  item: { type: Object, required: true },
  selected: { type: Boolean, default: false },
});

defineEmits(["expand", "toggle"]);

const entityTone = computed(() => String(props.item.entity_type || "unknown").toLowerCase());
const roleText = computed(() => props.item.entity_role || "");
const driveText = computed(() => props.item.core_drive || (props.item.entity_role ? "" : "暂无摘要"));
</script>

<style scoped>
.archive-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px 16px;
  cursor: pointer;
  border-left: 3px solid transparent;
  transition: box-shadow 0.2s ease, border-color 0.2s ease, background 0.15s ease;
}

.archive-card:hover {
  background: var(--bg-paper);
}

.archive-card.active {
  border-left-color: var(--color-primary);
  background: var(--bg-paper-warm);
}

.archive-card.selected {
  border-left-color: var(--color-primary);
}

.archive-card.selected:not(.active) {
  background: rgba(155, 44, 44, 0.02);
}

/* ── Top row: name + tier + type badge ── */

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: var(--space-sm);
}

.card-identity {
  display: flex;
  align-items: baseline;
  gap: var(--space-sm);
  min-width: 0;
}

.card-name {
  margin: 0;
  font-size: 15px;
  line-height: 1.35;
  font-family: "ZCOOL XiaoWei", serif;
  font-weight: 700;
  color: var(--text-main);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-tier {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-dim);
  white-space: nowrap;
}

/* ── Role line (entity_role) ── */

.card-role {
  margin: 0;
  color: var(--text-sub);
  font-size: 12.5px;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
  overflow: hidden;
}

/* ── Summary (core_drive) ── */

.card-summary {
  margin: 0;
  color: var(--text-sub);
  font-size: 13px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
}

.card-summary:empty {
  display: none;
}

/* ── Footer: project + detail button ── */

.card-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-sm);
  margin-top: auto;
  padding-top: 4px;
  border-top: 1px solid var(--line-soft);
}

.card-project {
  color: var(--text-dim);
  font-size: 11.5px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.card-detail-btn {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 3px 10px;
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-full);
  background: transparent;
  color: var(--text-sub);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.15s ease, border-color 0.15s ease, background 0.15s ease;
}

.card-detail-btn svg {
  width: 12px;
  height: 12px;
}

.card-detail-btn:hover {
  color: var(--color-primary);
  border-color: var(--color-primary);
  background: rgba(155, 44, 44, 0.04);
}
</style>
