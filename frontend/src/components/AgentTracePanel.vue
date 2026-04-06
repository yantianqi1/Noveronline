<template>
  <div class="agent-trace-panel">
    <!-- Orchestrator Section -->
    <div v-if="state.orchestrator.status !== 'idle'" class="trace-section">
      <div class="trace-section-header">
        <span class="trace-section-title">编排层</span>
        <span v-if="state.orchestrator.model" class="trace-model-badge">{{ state.orchestrator.model }}</span>
        <span class="trace-status-dot" :class="state.orchestrator.status"></span>
      </div>

      <!-- Round Cards -->
      <div
        v-for="round in state.orchestrator.rounds"
        :key="round.roundNum"
        class="round-card"
        :class="{ active: round.status === 'running' }"
      >
        <div class="round-header">
          <span class="round-label">Round {{ round.roundNum + 1 }}</span>
          <span v-if="round.elapsedMs" class="round-elapsed">{{ (round.elapsedMs / 1000).toFixed(1) }}s</span>
        </div>

        <!-- Thinking Block -->
        <div v-if="round.thinking" class="thinking-block">
          <span class="thinking-icon">💭</span>
          <div class="thinking-content">
            <template v-if="!round._thinkingExpanded">
              <span class="thinking-preview">{{ truncate(round.thinking, 120) }}</span>
              <button v-if="round.thinking.length > 120" class="expand-btn" @click="round._thinkingExpanded = true">[更多]</button>
            </template>
            <template v-else>
              <pre class="thinking-full">{{ round.thinking }}</pre>
              <button class="expand-btn" @click="round._thinkingExpanded = false">[收起]</button>
            </template>
          </div>
        </div>

        <!-- Tool Calls -->
        <div v-if="round.toolCalls.length" class="tool-call-group">
          <div
            v-for="(tc, idx) in round.toolCalls"
            :key="idx"
            class="tool-call-item"
          >
            <div class="tool-call-row" @click="tc._expanded = !tc._expanded">
              <span class="tool-call-icon">↗</span>
              <span class="tool-call-display">{{ tc.display || tc.name }}</span>
              <span class="tool-call-status" :class="tc.status">
                <template v-if="tc.status === 'done'">✓</template>
                <template v-else-if="tc.status === 'error'">✗</template>
                <template v-else><span class="tool-spinner"></span></template>
              </span>
              <span v-if="tc.toolElapsedMs" class="tool-elapsed">{{ (tc.toolElapsedMs / 1000).toFixed(1) }}s</span>
              <span v-if="tc.fullResult" class="expand-indicator">{{ tc._expanded ? '▼' : '▶' }}</span>
            </div>
            <!-- Expanded Result -->
            <div v-if="tc._expanded && tc.fullResult" class="tool-result-panel">
              <pre class="tool-result-content">{{ tc.fullResult }}</pre>
            </div>
          </div>
        </div>

        <!-- Prompt Snapshot -->
        <div v-if="round.promptSnapshot" class="prompt-snapshot-toggle">
          <div class="prompt-snapshot-header" @click="round._promptExpanded = !round._promptExpanded">
            <span class="prompt-snapshot-icon">📋</span>
            <span class="prompt-snapshot-label">提示词快照 ({{ round.promptSnapshot.charCount.toLocaleString() }} 字)</span>
            <span class="expand-indicator">{{ round._promptExpanded ? '▼' : '▶' }}</span>
          </div>
          <div v-if="round._promptExpanded" class="prompt-snapshot-detail">
            <div
              v-for="(msg, mIdx) in round.promptSnapshot.messages"
              :key="mIdx"
              class="prompt-msg"
            >
              <div class="prompt-role">{{ msg.role }}</div>
              <pre class="prompt-content">{{ msg.content }}</pre>
            </div>
          </div>
        </div>
      </div>

      <!-- Phase Summary Bar -->
      <div v-if="state.orchestrator.summary" class="phase-summary-bar">
        <span class="phase-summary-icon">■</span>
        <span class="phase-summary-text">
          收集完成 · {{ state.orchestrator.summary.toolCount }} 次工具调用
          · {{ state.orchestrator.summary.roundCount }} 轮对话
          · {{ (state.orchestrator.summary.elapsedMs / 1000).toFixed(1) }}s
          <template v-if="state.orchestrator.summary.tokenUsage?.total_tokens">
            · ~{{ state.orchestrator.summary.tokenUsage.total_tokens.toLocaleString() }} tokens
          </template>
        </span>
      </div>
    </div>

    <!-- Writer Section -->
    <div v-if="state.writer.status !== 'idle'" class="trace-section writer-section">
      <div class="trace-section-header">
        <span class="trace-section-title">写作层</span>
        <span v-if="state.writer.model" class="trace-model-badge">{{ state.writer.model }}</span>
        <span class="trace-status-dot" :class="state.writer.status"></span>
      </div>
      <div class="writer-progress">
        <span class="writer-icon" :class="{ streaming: state.writer.status === 'running' }">✍</span>
        <span v-if="state.writer.status === 'running'">正在写作... {{ state.writer.wordCount.toLocaleString() }} 字</span>
        <span v-else-if="state.writer.status === 'done'">
          写作完成 · {{ state.writer.wordCount.toLocaleString() }} 字
          <template v-if="state.writer.elapsedMs"> · {{ (state.writer.elapsedMs / 1000).toFixed(1) }}s</template>
        </span>
        <span v-else-if="state.writer.status === 'error'">写作失败</span>
      </div>
    </div>

    <!-- Error -->
    <div v-if="state.error" class="trace-error">
      <span class="trace-error-icon">✗</span>
      <span class="trace-error-msg">{{ state.error }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  state: {
    type: Object,
    required: true,
  },
});

function truncate(text, maxLen) {
  if (!text || text.length <= maxLen) return text;
  return text.slice(0, maxLen) + "...";
}
</script>

<style scoped>
.agent-trace-panel {
  font-family: var(--font-mono, "SF Mono", "Fira Code", monospace);
  font-size: 12px;
  line-height: 1.5;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* Section */
.trace-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.trace-section-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
}
.trace-section-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary, #e0e0e0);
}
.trace-model-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 3px;
  background: rgba(110, 168, 254, 0.15);
  color: #6ea8fe;
  font-weight: 500;
}
.trace-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.trace-status-dot.running {
  background: #6ea8fe;
  animation: dot-pulse 1.5s ease-in-out infinite;
}
.trace-status-dot.done { background: #75b798; }
.trace-status-dot.error { background: #ea868f; }
.trace-status-dot.idle { background: #555; }

@keyframes dot-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

/* Round Card */
.round-card {
  border: 1px solid var(--border-subtle, #2d2d44);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: var(--surface-primary, #12121e);
  transition: border-color 0.2s;
}
.round-card.active {
  border-left: 3px solid #6ea8fe;
}
.round-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.round-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-sub, #888);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.round-elapsed {
  font-size: 11px;
  color: var(--text-sub, #888);
}

/* Thinking */
.thinking-block {
  display: flex;
  gap: 6px;
  align-items: flex-start;
}
.thinking-icon {
  flex-shrink: 0;
  margin-top: 1px;
}
.thinking-content {
  flex: 1;
  min-width: 0;
}
.thinking-preview {
  color: #999;
  font-style: italic;
}
.thinking-full {
  color: #999;
  font-style: italic;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  font-family: inherit;
  font-size: inherit;
}
.expand-btn {
  background: none;
  border: none;
  color: #6ea8fe;
  cursor: pointer;
  font-size: 11px;
  padding: 0 2px;
  font-family: inherit;
}
.expand-btn:hover { text-decoration: underline; }

/* Tool Calls */
.tool-call-group {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tool-call-item {
  display: flex;
  flex-direction: column;
}
.tool-call-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 4px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}
.tool-call-row:hover {
  background: var(--surface-hover, rgba(255, 255, 255, 0.04));
}
.tool-call-icon {
  flex-shrink: 0;
  color: #6ea8fe;
  width: 14px;
  text-align: center;
}
.tool-call-display {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-primary, #e0e0e0);
}
.tool-call-status {
  flex-shrink: 0;
  font-size: 12px;
  width: 16px;
  text-align: center;
}
.tool-call-status.done { color: #75b798; }
.tool-call-status.error { color: #ea868f; }
.tool-call-status.pending { color: #6ea8fe; }
.tool-spinner {
  display: inline-block;
  width: 10px;
  height: 10px;
  border: 1.5px solid rgba(110, 168, 254, 0.3);
  border-top-color: #6ea8fe;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
.tool-elapsed {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--text-sub, #888);
  width: 36px;
  text-align: right;
}
.expand-indicator {
  flex-shrink: 0;
  font-size: 10px;
  color: var(--text-sub, #888);
  width: 12px;
  text-align: center;
}
.tool-result-panel {
  margin: 4px 0 4px 20px;
  border: 1px solid var(--border-subtle, #2d2d44);
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.2);
  max-height: 300px;
  overflow-y: auto;
}
.tool-result-content {
  padding: 8px 12px;
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: var(--text-primary, #e0e0e0);
  white-space: pre-wrap;
  word-break: break-all;
  font-family: inherit;
}

/* Prompt Snapshot */
.prompt-snapshot-toggle {
  margin-top: 2px;
}
.prompt-snapshot-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 3px 4px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.15s;
}
.prompt-snapshot-header:hover {
  background: var(--surface-hover, rgba(255, 255, 255, 0.04));
}
.prompt-snapshot-icon { flex-shrink: 0; }
.prompt-snapshot-label {
  color: #c09060;
  font-weight: 500;
  font-size: 11px;
}
.prompt-snapshot-detail {
  margin: 4px 0 0 20px;
  border: 1px solid var(--border-subtle, #2d2d44);
  border-radius: 6px;
  background: var(--surface-primary, #12121e);
  max-height: 400px;
  overflow-y: auto;
}
.prompt-msg {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border-subtle, #2d2d44);
}
.prompt-msg:last-child { border-bottom: none; }
.prompt-role {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  color: #6ea8fe;
  margin-bottom: 4px;
  letter-spacing: 0.5px;
}
.prompt-content {
  font-size: 12px;
  line-height: 1.6;
  color: var(--text-primary, #e0e0e0);
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
  font-family: inherit;
}

/* Phase Summary */
.phase-summary-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  background: rgba(184, 115, 51, 0.08);
  border: 1px solid rgba(184, 115, 51, 0.2);
}
.phase-summary-icon {
  color: var(--accent-copper, #b87333);
}
.phase-summary-text {
  color: var(--accent-copper, #b87333);
  font-weight: 600;
  font-size: 12px;
}

/* Writer Section */
.writer-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  color: var(--text-primary, #e0e0e0);
}
.writer-icon {
  font-size: 14px;
}
.writer-icon.streaming {
  animation: dot-pulse 1.5s ease-in-out infinite;
}

/* Error */
.trace-error {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  background: rgba(234, 134, 143, 0.1);
  border: 1px solid rgba(234, 134, 143, 0.3);
}
.trace-error-icon { color: #ea868f; font-weight: bold; }
.trace-error-msg { color: #ea868f; }
</style>
