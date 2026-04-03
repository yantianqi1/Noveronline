<template>
  <div class="step-detail">
    <!-- Loading state -->
    <div v-if="loading" class="detail-loading mono">正在加载 trace...</div>

    <!-- Step still running -->
    <div v-else-if="step.status === 'active'" class="detail-empty mono">步骤执行中...</div>

    <!-- No trace: show step info instead of error -->
    <div v-else-if="!trace && !step.hasTrace" class="detail-no-trace">
      <div class="no-trace-title">{{ step.title }}</div>
      <div v-if="step.detail" class="no-trace-detail mono">{{ step.detail }}</div>
      <div v-else class="no-trace-detail mono">此步骤无详细记录</div>
    </div>

    <!-- Trace load failed (hasTrace=true but fetch returned null) -->
    <div v-else-if="!trace" class="detail-empty mono">
      trace 加载失败（{{ step.stepId }}），请刷新重试
    </div>

    <!-- Artifacts (non-LLM step outputs) -->
    <template v-else-if="hasArtifacts && !hasCalls">
      <div v-for="(artifact, idx) in trace.artifacts" :key="idx" class="artifact-section">
        <div class="artifact-header">
          <span class="artifact-label">{{ artifact.label }}</span>
          <span v-if="artifact.kind === 'stat'" class="artifact-kind-badge stat">统计</span>
          <span v-else-if="artifact.kind === 'json'" class="artifact-kind-badge json">JSON</span>
        </div>
        <pre class="artifact-content mono">{{ artifact.content }}</pre>
      </div>
    </template>

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

    <!-- Artifacts alongside calls (shown below LLM calls if both exist) -->
    <template v-if="trace && hasArtifacts && hasCalls">
      <div class="artifacts-divider">处理产物</div>
      <div v-for="(artifact, idx) in trace.artifacts" :key="'a' + idx" class="artifact-section">
        <div class="artifact-header">
          <span class="artifact-label">{{ artifact.label }}</span>
          <span v-if="artifact.kind === 'stat'" class="artifact-kind-badge stat">统计</span>
          <span v-else-if="artifact.kind === 'json'" class="artifact-kind-badge json">JSON</span>
        </div>
        <pre class="artifact-content mono">{{ artifact.content }}</pre>
      </div>
    </template>
  </div>
</template>

<script setup>
import { computed, ref, watch } from "vue";
import { getStepTrace } from "../../api/project.js";

const props = defineProps({
  taskId: { type: String, default: "" },
  step: { type: Object, required: true },
});

const loading = ref(false);
const trace = ref(null);
const cache = new Map();

const hasCalls = computed(() => trace.value?.calls?.length > 0);
const hasArtifacts = computed(() => trace.value?.artifacts?.length > 0);

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
  } catch (err) {
    console.warn(`[StepTrace] 加载失败 task=${props.taskId} step=${props.step.stepId}`, err);
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

.detail-no-trace {
  padding: var(--space-sm);
}

.no-trace-title {
  font-size: 13px;
  color: var(--text-sub);
  font-weight: 600;
}

.no-trace-detail {
  margin-top: var(--space-xs);
  font-size: 12px;
  color: var(--text-dim);
  line-height: 1.5;
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

.artifact-section {
  border: 1px solid var(--line-soft);
  border-radius: var(--radius-sm);
  overflow: hidden;
}

.artifact-section + .artifact-section {
  margin-top: var(--space-sm);
}

.artifact-header {
  display: flex;
  align-items: center;
  gap: var(--space-sm);
  padding: var(--space-xs) var(--space-sm);
  background: var(--bg-paper);
}

.artifact-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-sub);
}

.artifact-kind-badge {
  font-size: 10px;
  padding: 1px 6px;
  border-radius: var(--radius-full);
}

.artifact-kind-badge.stat {
  background: rgba(56, 106, 79, 0.12);
  color: var(--accent-green);
}

.artifact-kind-badge.json {
  background: rgba(61, 90, 128, 0.12);
  color: var(--accent-blue, #3d5a80);
}

.artifact-content {
  margin: 0;
  padding: var(--space-sm);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 400px;
  overflow-y: auto;
}

.artifacts-divider {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-dim);
  padding: var(--space-xs) 0;
  border-top: 1px solid var(--line-soft);
  margin-top: var(--space-sm);
}
</style>
