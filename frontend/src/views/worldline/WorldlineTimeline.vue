<template>
  <article class="workbench-card panel full">
    <h2 class="card-title">时间轴</h2>
    <div v-if="timeline.length" class="timeline">
      <div v-for="(event, idx) in timeline" :key="idx" class="event-row">
        <span class="index mono">#{{ idx + 1 }}</span>
        <div>
          <div class="title">{{ event.title || event.type || "事件" }}</div>
          <div class="desc">{{ event.description || event.summary || "无描述" }}</div>
        </div>
      </div>
    </div>
    <div v-else class="empty">暂无时间轴数据，等世界线引擎接口接通后会自动显示。</div>
  </article>
</template>

<script setup>
const props = defineProps({
  timeline: {
    type: Array,
    default: () => [],
  },
});
</script>

<style scoped>
.timeline {
  margin-top: 10px;
  border-left: 2px solid var(--line-soft);
  padding-left: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.event-row {
  display: grid;
  grid-template-columns: 48px minmax(0, 1fr);
  gap: 10px;
}

.index {
  color: var(--text-sub);
}

.title {
  font-weight: 700;
}

.desc {
  color: #5a4d38;
}

.empty {
  color: var(--text-sub);
  margin-top: 8px;
}
</style>
