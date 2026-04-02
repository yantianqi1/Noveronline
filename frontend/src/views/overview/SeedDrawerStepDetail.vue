<template>
  <div class="step-detail">
    <!-- Loading state -->
    <div v-if="loading" class="detail-loading mono">正在加载 trace...</div>

    <!-- No trace available -->
    <div v-else-if="!trace" class="detail-empty mono">
      <template v-if="step.status === 'active'">步骤执行中...</template>
      <template v-else-if="!step.hasTrace">此步骤无 LLM 调用记录</template>
      <template v-else>无法加载 trace 数据</template>
    </div>

    <!-- Single call: direct display -->
    <template v-else-if="trace.calls.length === 1">
      <div class="call-section">
        <div class="call-header mono">
          <span>{{ trace.calls[0].module_label || trace.calls[0].module_key }}</span>
          <span>{{ trace.calls[0].model }}</span>
          <span>{{ trace.calls[0].elapsed_ms }}ms</span>
        </div>
        <div class="call-block">
          <div class="block-label">提示词</div>
          <div class="block-content mono">
            <div v-for="(msg, i) in trace.calls[0].messages" :key="i" class="msg-item">
              <span class="msg-role">{{ msg.role }}</span>
              <pre class="msg-text">{{ msg.content }}</pre>
            </div>
          </div>
        </div>
        <div class="call-block">
          <div class="block-label">返回内容</div>
          <pre class="block-content mono response-text">{{ trace.calls[0].response_text }}</pre>
        </div>
        <div v-if="trace.calls[0].error" class="call-error mono">{{ trace.calls[0].error }}</div>
      </div>
    </template>

    <!-- Multiple calls: numbered list -->
    <template v-else>
      <div v-for="(call, idx) in trace.calls" :key="call.call_id || idx" class="call-section">
        <div class="call-header mono">
          <span class="call-index">#{{ idx + 1 }}</span>
          <span>{{ call.module_label || call.module_key }}</span>
          <span>{{ call.model }}</span>
          <span>{{ call.elapsed_ms }}ms</span>
        </div>
        <details class="call-details">
          <summary class="call-summary">查看完整 prompt / response</summary>
          <div class="call-block">
            <div class="block-label">提示词</div>
            <div class="block-content mono">
              <div v-for="(msg, i) in call.messages" :key="i" class="msg-item">
                <span class="msg-role">{{ msg.role }}</span>
                <pre class="msg-text">{{ msg.content }}</pre>
              </div>
            </div>
          </div>
          <div class="call-block">
            <div class="block-label">返回内容</div>
            <pre class="block-content mono response-text">{{ call.response_text }}</pre>
          </div>
          <div v-if="call.error" class="call-error mono">{{ call.error }}</div>
        </details>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, watch } from "vue";
import { getStepTrace } from "../../api/project.js";

const props = defineProps({
  taskId: { type: String, default: "" },
  step: { type: Object, required: true },
});

const loading = ref(false);
const trace = ref(null);
const cache = new Map();

async function fetchTrace() {
  if (!props.taskId || !props.step.stepId || !props.step.hasTrace) {
    trace.value = null;
    return;
  }

  const cacheKey = `${props.taskId}:${props.step.stepId}`;
  if (cache.has(cacheKey)) {
    trace.value = cache.get(cacheKey);
    return;
  }

  loading.value = true;
  try {
    const resp = await getStepTrace(props.taskId, props.step.stepId);
    const data = resp?.data || null;
    if (data) cache.set(cacheKey, data);
    trace.value = data;
  } catch {
    trace.value = null;
  } finally {
    loading.value = false;
  }
}

watch(
  () => props.step.stepId,
  () => fetchTrace(),
  { immediate: true },
);
</script>

<style scoped>
.step-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.detail-loading,
.detail-empty {
  font-size: 12px;
  color: var(--text-dim);
  padding: var(--space-sm);
}

.call-section {
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.call-section + .call-section {
  margin-top: var(--space-sm);
}

.call-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xs) var(--space-sm);
  background: var(--bg-paper);
  font-size: 11px;
  color: var(--text-dim);
  flex-wrap: wrap;
}

.call-index {
  font-weight: 700;
  color: var(--accent-copper);
}

.call-details {
  padding: 0;
}

.call-summary {
  padding: var(--space-xs) var(--space-sm);
  font-size: 12px;
  color: var(--text-sub);
  cursor: pointer;
  user-select: none;
}

.call-summary:hover {
  color: var(--accent-copper);
}

.call-block {
  padding: var(--space-sm);
}

.block-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-sub);
  margin-bottom: var(--space-xs);
}

.block-content {
  font-size: 12px;
  line-height: 1.6;
  max-height: 300px;
  overflow-y: auto;
  background: var(--bg-paper);
  border-radius: var(--radius-sm);
  padding: var(--space-sm);
}

.response-text {
  white-space: pre-wrap;
  word-break: break-word;
}

.msg-item {
  margin-bottom: var(--space-xs);
}

.msg-role {
  display: inline-block;
  font-size: 10px;
  font-weight: 700;
  color: var(--accent-copper);
  text-transform: uppercase;
  margin-bottom: 2px;
}

.msg-text {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  font-size: 12px;
}

.call-error {
  padding: var(--space-xs) var(--space-sm);
  font-size: 12px;
  color: var(--accent-seal);
  background: rgba(155, 67, 38, 0.05);
}
</style>
