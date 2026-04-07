<template>
  <Transition name="thinking-drop">
    <div v-if="visible && thinkingInfo" class="thinking-overlay">
      <div class="thinking-dots" aria-hidden="true">
        <span class="dot"></span>
        <span class="dot"></span>
        <span class="dot"></span>
      </div>
      <div class="thinking-body">
        <p class="thinking-agent">{{ thinkingInfo.agent || "system" }} 正在决策</p>
        <p v-if="thinkingInfo.question" class="thinking-question">{{ thinkingInfo.question }}</p>
        <div v-if="thinkingInfo.factors?.length" class="chip-row">
          <n-tag v-for="factor in thinkingInfo.factors" :key="factor" size="small" round>{{ factor }}</n-tag>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { NTag } from "naive-ui";

defineProps({
  visible: { type: Boolean, default: false },
  thinkingInfo: { type: Object, default: null },
});
</script>

<style scoped>
.thinking-overlay {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding: 12px 14px;
  border-radius: 10px;
  background: rgba(255, 252, 245, 0.92);
  backdrop-filter: blur(8px);
  border: 1px solid rgba(201, 149, 74, 0.35);
  box-shadow: 0 8px 24px rgba(118, 88, 43, 0.08);
  margin-top: 10px;
  max-height: 360px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: rgba(201, 149, 74, 0.3) transparent;
}

.thinking-dots {
  display: flex;
  gap: 5px;
  align-items: center;
  padding-top: 6px;
  flex-shrink: 0;
}

.dot {
  display: block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #c9954a;
  animation: thinking-bounce 1.4s ease-in-out infinite;
}

.dot:nth-child(2) {
  animation-delay: 0.16s;
}

.dot:nth-child(3) {
  animation-delay: 0.32s;
}

.thinking-body {
  flex: 1;
  min-width: 0;
}

.thinking-agent {
  font-size: 1.05rem;
  font-weight: 700;
  color: #5a3d13;
  letter-spacing: 0.02em;
}

.thinking-question {
  margin: 6px 0 0;
  color: var(--text-sub, #6e6050);
  font-size: 0.9rem;
  line-height: 1.5;
  word-break: break-word;
}

.chip-row {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 10px;
}

</style>
