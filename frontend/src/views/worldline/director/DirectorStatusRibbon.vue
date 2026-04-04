<template>
  <span class="status-ribbon" :class="[status, confidence]">
    {{ label }}
  </span>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  status: { type: String, default: "canon" },
  confidence: { type: String, default: "" },
});

const STATUS_LABELS = { canon: "正史", candidate: "候选", rejected: "已拒绝" };
const CONFIDENCE_LABELS = { high: "高置信", medium: "中置信", low: "低置信" };

const label = computed(() => {
  if (props.confidence && CONFIDENCE_LABELS[props.confidence]) {
    return CONFIDENCE_LABELS[props.confidence];
  }
  return STATUS_LABELS[props.status] || props.status;
});
</script>

<style scoped>
.status-ribbon {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 0.76rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  white-space: nowrap;
  line-height: 1.4;
}

.canon {
  background: rgba(201, 149, 74, 0.18);
  color: #7a5a28;
  border: 1px solid rgba(201, 149, 74, 0.3);
}

.candidate {
  background: rgba(218, 180, 100, 0.16);
  color: #8b6a2f;
  border: 1px solid rgba(218, 180, 100, 0.3);
}

.rejected {
  background: rgba(160, 150, 140, 0.14);
  color: #7a7268;
  border: 1px solid rgba(160, 150, 140, 0.25);
}

/* Confidence overrides when provided */
.high {
  background: rgba(61, 128, 90, 0.14);
  color: #2a5e3f;
  border: 1px solid rgba(61, 128, 90, 0.28);
}

.medium {
  background: rgba(176, 140, 60, 0.14);
  color: #6e5124;
  border: 1px solid rgba(176, 140, 60, 0.28);
}

.low {
  background: rgba(155, 67, 38, 0.12);
  color: #8b3a1f;
  border: 1px solid rgba(155, 67, 38, 0.24);
}
</style>
