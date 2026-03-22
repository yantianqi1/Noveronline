<template>
  <article class="workbench-card panel">
    <h2 class="card-title">对象历史</h2>
    <p>展示对象在当前分支的快照、动作与对话历史。</p>

    <div v-if="!sessionId || !selectedAgent" class="empty">选择对象后自动加载历史。</div>
    <p v-else-if="error" class="status-text error">{{ error }}</p>
    <div v-else class="history-grid">
      <section class="history-block">
        <div class="seed-title">状态快照 · {{ snapshots.length }}</div>
        <div v-if="!snapshots.length" class="empty">暂无快照</div>
        <div v-for="item in snapshots" :key="item.snapshot_id" class="history-item">
          <div class="mono">v{{ item.state_version }} · {{ formatTime(item.created_at) }}</div>
          <div>{{ item.status }} · {{ item.reason }}</div>
        </div>
      </section>

      <section class="history-block">
        <div class="seed-title">动作日志 · {{ actions.length }}</div>
        <div v-if="!actions.length" class="empty">暂无动作</div>
        <div v-for="item in actions" :key="item.action_event_id" class="history-item">
          <div class="mono">{{ item.status }} · {{ formatTime(item.created_at) }}</div>
          <div>{{ item.action }}</div>
        </div>
      </section>

      <section class="history-block">
        <div class="seed-title">对话日志 · {{ dialogues.length }}</div>
        <div v-if="!dialogues.length" class="empty">暂无对话</div>
        <div v-for="item in dialogues" :key="item.dialogue_id" class="history-item">
          <div class="mono">{{ item.generator_mode }} · {{ formatTime(item.created_at) }}</div>
          <div>Q: {{ item.message }}</div>
          <div>A: {{ item.reply }}</div>
        </div>
      </section>
    </div>
  </article>
</template>

<script setup>
defineProps({
  sessionId: { type: String, default: "" },
  selectedAgent: { type: Object, default: null },
  snapshots: { type: Array, default: () => [] },
  actions: { type: Array, default: () => [] },
  dialogues: { type: Array, default: () => [] },
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
  padding: 16px;
}

.panel p {
  color: var(--text-sub);
}

.history-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.history-block {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  padding: 10px;
  background: #fffaf1;
}

.history-item + .history-item {
  margin-top: 8px;
  border-top: 1px dashed var(--line-soft);
  padding-top: 8px;
}

.status-text.error {
  color: #9b4326;
}

@media (max-width: 1200px) {
  .history-grid {
    grid-template-columns: 1fr;
  }
}
</style>
