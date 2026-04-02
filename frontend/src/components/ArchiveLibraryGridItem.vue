<template>
  <article class="museum-item" :class="{ active, selected }" @click="$emit('toggle')">
    <div class="item-head">
      <h4 class="item-name">{{ item.entity_name }}</h4>
      <div class="item-badges">
        <span class="selection-badge mono" :class="{ selected }">
          {{ selected ? "已选" : "点击选中" }}
        </span>
        <span class="status-tag mono" :class="entityTone">{{ formatEntityType(item.entity_type) }}</span>
      </div>
    </div>

    <div class="item-meta">
      <span class="project-tag">{{ item.project_name }}</span>
      <span class="tier-tag">{{ formatImportanceTier(item.importance_tier) }}</span>
    </div>

    <p class="item-desc">{{ summaryText }}</p>

    <div class="item-actions">
      <span class="selection-copy">{{ selected ? "再次点击可移出当前世界线" : "点击卡片即可加入当前世界线" }}</span>
      <button class="detail-toggle" type="button" @click.stop="$emit('expand')">展开详情</button>
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
const summaryText = computed(() => props.item.core_drive || props.item.entity_role || "档案尚简。");
</script>

<style scoped>
.museum-item {
  display: grid;
  gap: 12px;
  min-height: 168px;
  padding: 16px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(248, 243, 234, 0.92));
  border: 1px solid rgba(159, 141, 106, 0.18);
  border-radius: 20px;
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
  box-shadow: 0 10px 28px rgba(44, 42, 39, 0.04);
}

.museum-item:hover {
  transform: translateY(-2px);
  border-color: rgba(176, 125, 75, 0.48);
  box-shadow: 0 16px 32px rgba(176, 125, 75, 0.1);
}

.museum-item.active {
  border-color: var(--accent-copper);
  background:
    linear-gradient(180deg, rgba(244, 239, 226, 0.95), rgba(255, 255, 255, 0.98));
  box-shadow: 0 18px 34px rgba(176, 125, 75, 0.14);
}

.museum-item.selected {
  box-shadow: inset 0 0 0 1px rgba(176, 125, 75, 0.22);
}

.item-head,
.item-meta {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}

.item-head {
  align-items: flex-start;
}

.item-badges {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.item-meta {
  flex-wrap: wrap;
  font-size: 12px;
}

.item-name {
  margin: 0;
  font-size: 20px;
  line-height: 1.3;
  font-family: "ZCOOL XiaoWei", serif;
  font-weight: 700;
  color: #1a1815;
  letter-spacing: 0.04em;
}

.project-tag {
  color: var(--text-dim);
}

.tier-tag {
  color: var(--accent-copper-deep);
  font-weight: 600;
}

.item-desc {
  margin: 0;
  color: var(--text-sub);
  font-size: 13px;
  line-height: 1.72;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}

.item-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: auto;
}

.selection-badge,
.detail-toggle {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: var(--radius-full);
}

.selection-badge {
  border: 1px solid rgba(159, 141, 106, 0.22);
  background: rgba(255, 255, 255, 0.86);
  color: var(--text-sub);
  letter-spacing: 0.08em;
}

.selection-badge.selected,
.museum-item.selected .selection-badge {
  background: rgba(176, 125, 75, 0.14);
  border-color: rgba(176, 125, 75, 0.32);
  color: var(--accent-copper-deep);
}

.selection-copy {
  color: var(--text-dim);
  font-size: 12px;
  line-height: 1.5;
}

.detail-toggle {
  border: 1px solid rgba(176, 125, 75, 0.2);
  background: rgba(176, 125, 75, 0.1);
  color: var(--text-main);
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease;
}

.detail-toggle:hover,
.museum-item.active .detail-toggle {
  background: rgba(176, 125, 75, 0.16);
  border-color: rgba(176, 125, 75, 0.34);
}
</style>
