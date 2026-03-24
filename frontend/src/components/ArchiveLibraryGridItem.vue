<template>
  <article class="museum-item" :class="{ active, selected }" @click="$emit('select')">
    <div class="item-head">
      <h4 class="item-name">{{ item.entity_name }}</h4>
      <span class="status-tag mono" :class="entityTone">{{ formatEntityType(item.entity_type) }}</span>
    </div>

    <div class="item-meta">
      <span class="project-tag">{{ item.project_name }}</span>
      <span class="tier-tag">{{ formatImportanceTier(item.importance_tier) }}</span>
    </div>

    <p class="item-desc">{{ summaryText }}</p>

    <button class="item-toggle" type="button" @click.stop="$emit('toggle')">
      <span class="check-box" :class="{ checked: selected }"></span>
      <span>{{ selected ? "已加入会话" : "加入会话" }}</span>
    </button>
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

defineEmits(["select", "toggle"]);

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

.item-meta {
  flex-wrap: wrap;
  font-size: 12px;
}

.item-name {
  margin: 0;
  font-size: 18px;
  line-height: 1.3;
  font-family: "ZCOOL XiaoWei", serif;
  color: var(--text-main);
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

.item-toggle {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  margin-top: auto;
  border: 1px solid rgba(176, 125, 75, 0.2);
  border-radius: var(--radius-full);
  padding: 8px 12px;
  background: rgba(176, 125, 75, 0.1);
  color: var(--text-sub);
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}

.museum-item.active .item-toggle,
.item-toggle:hover {
  background: rgba(176, 125, 75, 0.14);
  border-color: rgba(176, 125, 75, 0.32);
  color: var(--text-main);
}

.check-box {
  width: 16px;
  height: 16px;
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
  font-size: 11px;
}
</style>
