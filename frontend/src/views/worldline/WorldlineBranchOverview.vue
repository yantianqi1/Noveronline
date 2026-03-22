<template>
  <article class="workbench-card panel">
    <div class="header-row">
      <div>
        <h2 class="card-title">分支总览</h2>
        <p class="branch-tip">默认仅显示当前分支；勾选对比分支后，右侧会按勾选列表切换摘要。</p>
      </div>
      <span class="meta-chip mono">{{ checkedBranchIds.length ? `对比 ${checkedBranchIds.length} 条` : "当前分支" }}</span>
    </div>

    <div class="branch-list">
      <article
        v-for="item in branches"
        :key="item.branch_id"
        class="branch-item"
        :class="{ active: branchId === item.branch_id, checked: isChecked(item.branch_id) }"
      >
        <button class="branch-main" type="button" @click="$emit('select-branch', item.branch_id)">
          <strong>{{ item.title || item.branch_name || item.branch_id }}</strong>
          <span class="mono">{{ buildStepLabel(item.current_step) }}</span>
        </button>
        <button class="check-toggle" type="button" @click="$emit('toggle-branch-check', item.branch_id)">
          <span class="check-box" :class="{ checked: isChecked(item.branch_id) }"></span>
          <span>{{ isChecked(item.branch_id) ? "已加入对比" : "加入对比" }}</span>
        </button>
      </article>
    </div>

    <div class="toolbar-row">
      <button class="btn" :disabled="!sessionId" @click="$emit('refresh-branches')">刷新分支</button>
      <button class="btn subtle" :disabled="!checkedBranchIds.length" @click="$emit('clear-checked-branches')">
        清空对比
      </button>
    </div>
  </article>
</template>

<script setup>
import { buildStepLabel } from "../../utils/chineseDisplay";

const props = defineProps({
  branches: Array,
  branchId: String,
  checkedBranchIds: { type: Array, default: () => [] },
  sessionId: String,
});

defineEmits(["select-branch", "toggle-branch-check", "clear-checked-branches", "refresh-branches"]);

function isChecked(branchId) {
  return props.checkedBranchIds.includes(branchId);
}
</script>

<style scoped>
.header-row {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
}

.branch-tip {
  margin: 4px 0 0;
  color: var(--text-sub);
}

.meta-chip {
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-full);
  padding: 6px 10px;
  background: #fff8ea;
}

.branch-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.branch-item {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fffbf1;
  padding: 10px 12px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
}

.branch-item.active {
  border-color: var(--line-strong);
  background: #fff6e4;
}

.branch-item.checked {
  box-shadow: inset 0 0 0 1px rgba(176, 125, 75, 0.18);
}

.branch-main,
.check-toggle {
  border: none;
  background: transparent;
  padding: 0;
  text-align: left;
  color: inherit;
}

.branch-main {
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.check-toggle {
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--text-sub);
}

.check-box {
  width: 18px;
  height: 18px;
  border-radius: 4px;
  border: 1px solid var(--line-medium);
  background: #fff;
}

.check-box.checked {
  background: var(--accent-copper);
  border-color: var(--accent-copper);
  position: relative;
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

.toolbar-row {
  margin-top: 12px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 720px) {
  .branch-item {
    grid-template-columns: 1fr;
  }
}
</style>
