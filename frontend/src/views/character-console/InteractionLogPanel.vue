<template>
  <article class="workbench-card panel">
    <h2 class="card-title">交互日志</h2>
    <div class="logs">
      <div v-for="(item, idx) in logs" :key="idx" class="log-item">
        <div class="mono">{{ item.time }}</div>
        <div>{{ item.text }}</div>
      </div>
      <n-empty v-if="!logs.length" description="暂无日志，执行第一条动作后会记录在这里。" />
    </div>
  </article>
</template>

<script setup>
import { NEmpty } from "naive-ui";

defineProps({
  logs: { type: Array, default: () => [] },
});
</script>

<style scoped>
.panel {
  padding: 10px;
}

.logs {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 460px;
  overflow: auto;
}

.log-item {
  border: 1px solid var(--line-soft);
  border-radius: 8px;
  padding: 8px;
  background: #fffbf3;
  display: grid;
  gap: 5px;
}
</style>
