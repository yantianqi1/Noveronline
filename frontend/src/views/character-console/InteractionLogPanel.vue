<template>
  <article class="workbench-card panel">
    <h2 class="card-title">交互日志</h2>
    <div class="logs">
      <div v-for="(item, idx) in logs" :key="idx" class="log-item">
        <div class="mono">{{ item.time }}</div>
        <div>{{ item.text }}</div>
      </div>
      <div v-if="!logs.length" class="empty">暂无日志，执行第一条动作后会记录在这里。</div>
    </div>
  </article>
</template>

<script setup>
defineProps({
  logs: { type: Array, default: () => [] },
});
</script>

<style scoped>
.panel {
  padding: 16px;
}

.logs {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 460px;
  overflow: auto;
}

.log-item {
  border: 1px solid var(--line-soft);
  border-radius: 10px;
  padding: 10px;
  background: #fffbf3;
  display: grid;
  gap: 5px;
}
</style>
