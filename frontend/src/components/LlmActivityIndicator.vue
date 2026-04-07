<template>
  <div v-if="activity.state.totalActive > 0" class="llm-indicator">
    <n-popover trigger="click" placement="bottom-end" :width="400" raw :show-arrow="false">
      <template #trigger>
        <button class="indicator-pill">
          <span class="pulse-dot"></span>
          <span class="pill-count mono">{{ activity.state.totalActive }}</span>
          <span class="pill-label">模型运行中</span>
          <Icon icon="icon-park-outline:down" width="12" class="pill-chevron" />
        </button>
      </template>

      <div class="activity-panel">
        <div class="panel-header">
          <span class="title-ancient panel-title">LLM 活动监控</span>
          <span class="mono panel-meta">{{ activity.state.totalActive }} 个请求</span>
        </div>

        <div class="call-list">
          <div
            v-for="call in activity.state.calls"
            :key="call.call_id"
            class="call-row"
          >
            <div class="call-top">
              <span class="call-label">{{ call.module_label }}</span>
              <span class="call-elapsed mono">{{ formatElapsed(call.elapsed_ms) }}</span>
            </div>
            <div class="call-bottom">
              <n-tag size="small" :bordered="false" :type="statusTagType(call.status)">
                {{ statusLabel(call.status) }}
              </n-tag>
              <span class="call-model mono">{{ call.model }}</span>
              <span class="call-channel mono">{{ call.channel_key }}</span>
            </div>
          </div>
        </div>

        <div class="channel-section" v-if="hasChannels">
          <div class="channel-header">渠道并发</div>
          <div
            v-for="(snap, key) in activity.state.channels"
            :key="key"
            class="channel-row"
          >
            <span class="channel-key mono">{{ key }}</span>
            <div class="concurrency-bar-wrap">
              <div
                class="concurrency-bar"
                :style="{ width: concurrencyPct(snap) + '%' }"
                :class="{ saturated: snap.inflight >= snap.limit }"
              ></div>
            </div>
            <span class="concurrency-label mono">
              {{ snap.inflight }}/{{ snap.limit }}
              <span v-if="snap.waiting > 0" class="waiting-badge">+{{ snap.waiting }} 等待</span>
            </span>
          </div>
        </div>
      </div>
    </n-popover>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted } from "vue";
import { NPopover, NTag } from "naive-ui";
import { Icon } from "@iconify/vue";
import { useLlmActivity } from "../composables/useLlmActivity.js";

const activity = useLlmActivity();

onMounted(() => { activity.mount(); });
onUnmounted(() => { activity.unmount(); });

const hasChannels = computed(() =>
  Object.keys(activity.state.channels).length > 0
);

function statusTagType(status) {
  return { waiting: "warning", running: "success", streaming: "info" }[status] ?? "default";
}

function formatElapsed(ms) {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function statusLabel(status) {
  return { waiting: "等待槽位", running: "运行中", streaming: "流式输出" }[status] ?? status;
}

function concurrencyPct(snap) {
  if (!snap.limit) return 0;
  return Math.min(100, Math.round((snap.inflight / snap.limit) * 100));
}
</script>

<style scoped>
.llm-indicator {
  position: relative;
}

/* ── Pill ── */
.indicator-pill {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  background: rgba(176, 125, 75, 0.08);
  border: 1px solid rgba(176, 125, 75, 0.25);
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--accent-copper-deep);
  font-size: 13px;
  font-family: inherit;
  transition: all 0.2s ease;
  white-space: nowrap;
}

.indicator-pill:hover,
.indicator-pill.active {
  background: rgba(176, 125, 75, 0.14);
  border-color: rgba(176, 125, 75, 0.45);
}

.pulse-dot {
  width: 7px;
  height: 7px;
  background: var(--accent-copper);
  border-radius: 50%;
  animation: indicator-pulse 2s infinite;
}

@keyframes indicator-pulse {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(176, 125, 75, 0.7); }
  70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(176, 125, 75, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(176, 125, 75, 0); }
}

.pill-count {
  font-weight: 700;
  font-size: 14px;
}

.pill-label {
  font-size: 12px;
  color: var(--text-sub);
}

.pill-chevron {
  color: var(--text-dim);
}

/* ── Dropdown Panel ── */
.activity-panel {
  max-height: 420px;
  overflow-y: auto;
  padding: 10px;
  background: var(--bg-panel, #fff);
  border-radius: 8px;
  box-shadow: var(--shadow-ink);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid var(--line-soft);
}

.panel-title {
  font-size: 13px;
  color: var(--bg-ink);
}

.panel-meta {
  font-size: 12px;
  color: var(--text-dim);
}

/* ── Call rows ── */
.call-list {
  display: flex;
  flex-direction: column;
}

.call-row {
  padding: var(--space-sm) 0;
  border-bottom: 1px solid var(--line-soft);
}

.call-row:last-child {
  border-bottom: none;
}

.call-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.call-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-main);
}

.call-elapsed {
  font-size: 12px;
  color: var(--text-dim);
}

.call-bottom {
  display: flex;
  gap: var(--space-sm);
  margin-top: 4px;
  align-items: center;
}


.call-model {
  font-size: 11px;
  color: var(--text-sub);
}

.call-channel {
  font-size: 11px;
  color: var(--text-dim);
}

/* ── Channel section ── */
.channel-section {
  margin-top: var(--space-md);
  padding-top: var(--space-sm);
  border-top: 1px solid var(--line-soft);
}

.channel-header {
  font-size: 11px;
  color: var(--text-dim);
  letter-spacing: 0.15em;
  margin-bottom: var(--space-sm);
}

.channel-row {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: 4px 0;
}

.channel-key {
  font-size: 12px;
  color: var(--text-sub);
  min-width: 80px;
  flex-shrink: 0;
}

.concurrency-bar-wrap {
  flex: 1;
  height: 4px;
  background: var(--bg-paper);
  border-radius: 2px;
  overflow: hidden;
}

.concurrency-bar {
  height: 100%;
  background: var(--accent-copper);
  border-radius: 2px;
  transition: width 0.5s ease;
}

.concurrency-bar.saturated {
  background: #c0392b;
}

.concurrency-label {
  font-size: 11px;
  color: var(--text-sub);
  white-space: nowrap;
}

.waiting-badge {
  color: var(--accent-copper-deep);
  font-weight: 500;
}

</style>
