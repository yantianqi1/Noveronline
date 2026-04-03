<template>
  <div v-if="items.length" class="inspector-section">
    <button class="section-header" type="button" @click="expanded = !expanded">
      <span class="section-title">{{ title }}</span>
      <span class="section-chevron" :class="{ open: expanded }">&#9662;</span>
    </button>
    <div v-show="expanded" class="section-body">
      <div v-for="(item, idx) in items" :key="idx" class="section-item">
        <span class="item-label">{{ item.label }}</span>
        <span v-if="Array.isArray(item.value)" class="item-value">
          <span v-for="(tag, ti) in item.value" :key="ti" class="item-tag">{{ tag }}</span>
        </span>
        <span v-else class="item-value">{{ item.value }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from "vue";

defineProps({
  title: { type: String, required: true },
  items: { type: Array, default: () => [] },
});

const expanded = ref(true);
</script>

<style scoped>
.inspector-section {
  border: 1px solid var(--line-soft, #e8dfc8);
  border-radius: 8px;
  margin-bottom: 8px;
  overflow: hidden;
  background: rgba(255, 252, 244, 0.6);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 10px;
  border: none;
  background: transparent;
  cursor: pointer;
  font-family: "ZCOOL XiaoWei", serif;
  font-size: 13px;
  color: #3d3222;
}

.section-header:hover {
  background: rgba(0, 0, 0, 0.03);
}

.section-chevron {
  font-size: 10px;
  transition: transform 0.2s;
  color: #9a8b6f;
}

.section-chevron.open {
  transform: rotate(180deg);
}

.section-body {
  padding: 4px 10px 8px;
}

.section-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 4px 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
}

.section-item:last-child {
  border-bottom: none;
}

.item-label {
  font-size: 11px;
  color: #9a8b6f;
  font-weight: 500;
}

.item-value {
  font-size: 12.5px;
  color: #564a36;
  line-height: 1.5;
  word-break: break-word;
}

.item-tag {
  display: inline-block;
  background: rgba(0, 0, 0, 0.05);
  border-radius: 4px;
  padding: 1px 6px;
  margin: 1px 3px 1px 0;
  font-size: 11.5px;
  color: #564a36;
}
</style>
