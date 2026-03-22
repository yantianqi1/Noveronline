<template>
  <article class="museum-item" :class="{ active, selected }" @click="$emit('select')">
    <div class="item-head">
      <h4 class="item-name">{{ item.entity_name }}</h4>
      <span class="status-tag mono" :class="item.entity_type.toLowerCase()">{{ formatEntityType(item.entity_type) }}</span>
    </div>
    <div class="item-meta">
      <span class="project-tag">{{ item.project_name }}</span>
      <span class="tier-tag">{{ formatImportanceTier(item.importance_tier) }}</span>
    </div>
    <p class="item-desc">{{ item.core_drive || item.entity_role || "档案尚简。" }}</p>
    <button class="item-toggle" type="button" @click.stop="$emit('toggle')">
      <span class="check-box" :class="{ checked: selected }"></span>
      <span>{{ selected ? "已选中" : "加入会话" }}</span>
    </button>
  </article>
</template>

<script setup>
import { formatEntityType, formatImportanceTier } from "../utils/chineseDisplay.js";

defineProps({
  active: { type: Boolean, default: false },
  item: { type: Object, required: true },
  selected: { type: Boolean, default: false },
});

defineEmits(["select", "toggle"]);
</script>

<style scoped>
.museum-item {
  display: grid;
  gap: var(--space-sm);
  min-height: 164px;
  padding: var(--space-md);
  background: #fff;
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.museum-item:hover {
  transform: translateY(-2px);
  border-color: var(--line-medium);
  box-shadow: var(--shadow-sm);
}

.museum-item.active {
  border-color: var(--accent-copper);
  background: var(--bg-paper-warm);
}

.museum-item.selected {
  box-shadow: inset 0 0 0 1px rgba(176, 125, 75, 0.22);
}

.item-head,
.item-meta,
.item-toggle {
  display: flex;
  justify-content: space-between;
  gap: var(--space-sm);
}

.item-head {
  align-items: flex-start;
}

.item-meta {
  flex-wrap: wrap;
  font-size: 12px;
}

.item-name {
  margin: 0;
  font-size: 18px;
  font-family: "ZCOOL XiaoWei", serif;
  color: var(--text-main);
}

.project-tag {
  color: var(--text-dim);
}

.tier-tag {
  color: var(--accent-copper);
  font-weight: 600;
}

.item-desc {
  margin: 0;
  color: var(--text-sub);
  font-size: 13px;
  line-height: 1.6;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}

.item-toggle {
  margin-top: auto;
  align-items: center;
  border: none;
  border-radius: var(--radius-full);
  padding: 8px 12px;
  background: rgba(176, 125, 75, 0.08);
  color: var(--text-sub);
  cursor: pointer;
}

.check-box {
  width: 18px;
  height: 18px;
  border: 1px solid var(--line-medium);
  border-radius: 4px;
  background: #fff;
}

.check-box.checked {
  position: relative;
  background: var(--accent-copper);
  border-color: var(--accent-copper);
}

.check-box.checked::after {
  content: "✓";
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  color: #fff;
  font-size: 12px;
}
</style>
