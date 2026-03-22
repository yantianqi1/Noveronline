<template>
  <article class="workbench-card panel">
    <h2 class="card-title">分支总览</h2>
    <div class="branch-list">
      <button
        v-for="item in branches"
        :key="item.branch_id"
        class="branch-item"
        :class="{ active: branchId === item.branch_id }"
        @click="$emit('select-branch', item.branch_id)"
      >
        <strong>{{ item.title || item.branch_name || item.branch_id }}</strong>
        <span class="mono">{{ buildStepLabel(item.current_step) }}</span>
      </button>
    </div>
    <div class="toolbar-row">
      <button class="btn" :disabled="!sessionId" @click="$emit('refresh-branches')">刷新分支</button>
    </div>
  </article>
</template>

<script setup>
import { buildStepLabel } from "../../utils/chineseDisplay";

const props = defineProps({
  branches: Array,
  branchId: String,
  sessionId: String,
});

const emit = defineEmits(["select-branch", "refresh-branches"]);
</script>

<style scoped>
.branch-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.branch-item {
  border: 1px solid var(--line-soft);
  border-radius: 10px;
  background: #fffbf1;
  text-align: left;
  padding: 10px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
}

.branch-item.active {
  border-color: var(--line-strong);
  background: #fff6e4;
}

.toolbar-row {
  margin-top: 12px;
}
</style>
