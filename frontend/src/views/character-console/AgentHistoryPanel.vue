<template>
  <article class="workbench-card panel">
    <h2 class="card-title">对象历史</h2>
    <p>展示对象在当前分支的快照、动作与对话历史。</p>

    <n-empty v-if="!sessionId || !selectedAgent" description="选择对象后自动加载历史。" />
    <n-tag v-else-if="error" type="error">{{ error }}</n-tag>
    <n-tabs v-else type="line" size="small" style="margin-top: 10px">
      <n-tab-pane :name="'snapshots'" :tab="`快照 · ${snapshots.length}`">
        <n-empty v-if="!snapshots.length" description="暂无快照" size="small" />
        <div v-for="item in snapshots" :key="item.snapshot_id" class="history-item">
          <div class="mono">v{{ item.state_version }} · {{ formatTime(item.created_at) }}</div>
          <div>{{ item.status }} · {{ item.reason }}</div>
        </div>
      </n-tab-pane>

      <n-tab-pane :name="'actions'" :tab="`动作 · ${actions.length}`">
        <n-empty v-if="!actions.length" description="暂无动作" size="small" />
        <div v-for="item in actions" :key="item.action_event_id" class="history-item">
          <div class="mono">{{ item.status }} · {{ formatTime(item.created_at) }}</div>
          <div>{{ item.action }}</div>
        </div>
      </n-tab-pane>

      <n-tab-pane :name="'dialogues'" :tab="`对话 · ${dialogues.length}`">
        <n-empty v-if="!dialogues.length" description="暂无对话" size="small" />
        <div v-for="item in dialogues" :key="item.dialogue_id" class="history-item">
          <div class="mono">{{ item.generator_mode }} · {{ formatTime(item.created_at) }}</div>
          <div>Q: {{ item.message }}</div>
          <div>A: {{ item.reply }}</div>
        </div>
      </n-tab-pane>

      <n-tab-pane :name="'memories'" :tab="`记忆 · ${sessionMemories.length + longTermMemories.length}`">
        <n-empty v-if="!sessionMemories.length && !longTermMemories.length" description="暂无记忆" size="small" />
        <div v-for="item in sessionMemories" :key="item.memory_id" class="history-item">
          <div class="mono">session · {{ item.memory_type }} · {{ formatTime(item.updated_at) }}</div>
          <div>{{ item.summary }}</div>
        </div>
        <div v-for="item in longTermMemories" :key="item.memory_id" class="history-item">
          <div class="mono">long_term · {{ item.memory_type }} · {{ formatTime(item.updated_at) }}</div>
          <div>{{ item.summary }}</div>
        </div>
      </n-tab-pane>
    </n-tabs>
  </article>
</template>

<script setup>
import { NEmpty, NTabs, NTabPane, NTag } from "naive-ui";

defineProps({
  sessionId: { type: String, default: "" },
  selectedAgent: { type: Object, default: null },
  snapshots: { type: Array, default: () => [] },
  actions: { type: Array, default: () => [] },
  dialogues: { type: Array, default: () => [] },
  sessionMemories: { type: Array, default: () => [] },
  longTermMemories: { type: Array, default: () => [] },
  error: { type: String, default: "" },
});

function formatTime(value) {
  if (!value) {
    return "--";
  }
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN", { hour12: false });
}
</script>

<style scoped>
.panel {
  padding: 10px;
}

.panel p {
  color: var(--text-sub);
}

.history-item + .history-item {
  margin-top: 8px;
  border-top: 1px dashed var(--line-soft);
  padding-top: 8px;
}

</style>
