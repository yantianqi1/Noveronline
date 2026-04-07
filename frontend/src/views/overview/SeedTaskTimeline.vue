<template>
  <section class="log-card timeline-card">
    <div class="timeline-head">
      <div>
        <div class="section-code mono">时间轴卷宗</div>
        <h3>{{ title }}</h3>
      </div>
      <span class="timeline-hint">{{ hintText }}</span>
    </div>
    <div ref="scrollRef" class="timeline-list" @scroll="handleScroll">
      <article v-for="event in events" :key="event.id" class="timeline-item" :class="event.status">
        <div class="timeline-rail">
          <span class="timeline-dot"></span>
        </div>
        <div class="timeline-body">
          <div class="timeline-top">
            <strong>{{ event.title }}</strong>
            <span class="mono">{{ formatTimelineTimestamp(event.timestamp) }}</span>
          </div>
          <p v-if="event.detail" class="timeline-detail">{{ event.detail }}</p>
          <div class="chip-row">
            <n-tag size="small" :bordered="false">{{ formatStageKey(event.stage) }}</n-tag>
            <n-tag v-for="chip in buildEventChips(event)" :key="`${event.id}_${chip}`" size="small" :bordered="false">{{ chip }}</n-tag>
          </div>
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { nextTick, ref, watch } from "vue";
import { NTag } from "naive-ui";

import { buildEventChips, formatTimelineTimestamp } from "./seedUploadTaskView";
import { formatStageKey } from "../../utils/chineseDisplay";

const props = defineProps({
  events: { type: Array, required: true },
  title: { type: String, default: "阶段日志" },
  hintText: { type: String, default: "自动追踪最新事件" },
});

const scrollRef = ref(null);
const autoStick = ref(true);

watch(
  () => props.events.length,
  async () => {
    await nextTick();
    if (autoStick.value) {
      scrollToBottom();
    }
  },
  { immediate: true },
);

function handleScroll() {
  const node = scrollRef.value;
  if (!node) return;
  const distance = node.scrollHeight - node.scrollTop - node.clientHeight;
  autoStick.value = distance < 40;
}

function scrollToBottom() {
  const node = scrollRef.value;
  if (!node) return;
  node.scrollTop = node.scrollHeight;
}
</script>

<style scoped>
.log-card {
  border: 1px solid var(--line-soft);
  border-radius: 10px;
  background: linear-gradient(180deg, rgba(255, 252, 246, 0.98), rgba(248, 242, 229, 0.98));
  padding: 10px;
}

.timeline-head,
.timeline-top,
.chip-row {
  display: flex;
  gap: 8px;
}

.timeline-head {
  align-items: flex-start;
  justify-content: space-between;
}

.timeline-head h3 {
  margin: 4px 0 0;
  font-size: 16px;
  font-family: "ZCOOL XiaoWei", serif;
}

.section-code,
.timeline-hint {
  color: var(--text-sub);
}

.section-code {
  font-size: 11px;
  letter-spacing: 0.08em;
}

.timeline-hint {
  font-size: 12px;
}

.timeline-list {
  margin-top: 10px;
  max-height: 420px;
  overflow: auto;
  padding-right: 4px;
}

.timeline-item {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr);
  gap: 8px;
}

.timeline-item + .timeline-item {
  margin-top: 10px;
}

.timeline-rail {
  position: relative;
}

.timeline-rail::after {
  content: "";
  position: absolute;
  left: 8px;
  top: 8px;
  bottom: -22px;
  width: 1px;
  background: rgba(159, 141, 106, 0.45);
}

.timeline-item:last-child .timeline-rail::after {
  display: none;
}

.timeline-dot {
  position: relative;
  z-index: 1;
  display: block;
  width: 16px;
  height: 16px;
  border-radius: 999px;
  border: 2px solid rgba(159, 141, 106, 0.55);
  background: #fff7e9;
}

.timeline-body {
  border: 1px solid rgba(159, 141, 106, 0.28);
  border-radius: 8px;
  background: rgba(255, 251, 243, 0.86);
  padding: 10px;
}

.timeline-item.active .timeline-body {
  border-color: rgba(143, 79, 31, 0.42);
  box-shadow: 0 10px 24px rgba(143, 79, 31, 0.08);
}

.timeline-item.failed .timeline-body {
  border-color: rgba(155, 67, 38, 0.42);
}

.timeline-item.completed {
  opacity: 0.9;
}

.timeline-detail {
  margin: 8px 0 0;
  color: var(--text-sub);
}

.chip-row {
  flex-wrap: wrap;
  margin-top: 10px;
}

@media (max-width: 768px) {
  .timeline-list {
    max-height: 320px;
  }
}
</style>
