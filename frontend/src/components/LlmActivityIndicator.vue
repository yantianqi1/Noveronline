<template>
  <div v-if="activity.state.totalActive > 0" class="llm-indicator" ref="rootRef">
    <!-- Compact pill -->
    <button class="indicator-pill" @click="togglePanel" :class="{ active: panelOpen }">
      <span class="pulse-dot"></span>
      <span class="pill-count mono">{{ activity.state.totalActive }}</span>
      <span class="pill-label">模型运行中</span>
      <span class="pill-chevron" :class="{ rotated: panelOpen }">▾</span>
    </button>

    <!-- Dropdown detail panel -->
    <Transition name="panel-drop">
      <div v-if="panelOpen" class="activity-panel workbench-card">
        <div class="panel-header">
          <span class="title-ancient panel-title">LLM 活动监控</span>
          <span class="mono panel-meta">{{ activity.state.totalActive }} 个请求</span>
        </div>

        <!-- Per-call rows -->
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
              <span class="call-status-badge" :class="call.status">
                {{ statusLabel(call.status) }}
              </span>
              <span class="call-model mono">{{ call.model }}</span>
              <span class="call-channel mono">{{ call.channel_key }}</span>
            </div>
          </div>
        </div>

        <!-- Per-channel concurrency summary -->
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
    </Transition>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from "vue";
import { useLlmActivity } from "../composables/useLlmActivity.js";

const activity = useLlmActivity();
const panelOpen = ref(false);
const rootRef = ref(null);

onMounted(() => {
  activity.mount();
  document.addEventListener("click", handleOutsideClick);
});

onUnmounted(() => {
  activity.unmount();
  document.removeEventListener("click", handleOutsideClick);
});

function handleOutsideClick(e) {
  if (rootRef.value && !rootRef.value.contains(e.target)) {
    panelOpen.value = false;
  }
}

function togglePanel() {
  panelOpen.value = !panelOpen.value;
}

const hasChannels = computed(() =>
  Object.keys(activity.state.channels).length > 0
);

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
  gap: 6px;
  padding: 6px 14px;
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
  font-size: 11px;
  transition: transform 0.2s ease;
  color: var(--text-dim);
}

.pill-chevron.rotated {
  transform: rotate(180deg);
}

/* ── Dropdown Panel ── */
.activity-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: 400px;
  max-height: 480px;
  overflow-y: auto;
  z-index: 200;
  padding: var(--space-md);
  box-shadow: var(--shadow-ink);
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: var(--space-md);
  padding-bottom: var(--space-sm);
  border-bottom: 1px solid var(--line-soft);
}

.panel-title {
  font-size: 15px;
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

.call-status-badge {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 500;
}

.call-status-badge.waiting {
  background: rgba(176, 125, 75, 0.1);
  color: var(--accent-copper-deep);
}

.call-status-badge.running {
  background: rgba(74, 109, 84, 0.1);
  color: var(--accent-green);
}

.call-status-badge.streaming {
  background: rgba(61, 90, 128, 0.1);
  color: var(--accent-blue);
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

/* ── Panel transition ── */
.panel-drop-enter-active,
.panel-drop-leave-active {
  transition: opacity 0.15s ease, transform 0.15s ease;
}

.panel-drop-enter-from,
.panel-drop-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
</style>
