<template>
  <section class="log-card llm-card" :class="modeClass">
    <div class="llm-top">
      <div>
        <div class="section-code mono">分析引擎</div>
        <h3>{{ engineTitle }}</h3>
      </div>
      <span class="engine-pill mono">{{ enginePill }}</span>
    </div>
    <p class="action-text">{{ llmActivity.action }}</p>
    <div class="llm-grid">
      <div class="llm-field">
        <span class="llm-label mono">模型</span>
        <strong>{{ llmActivity.model || "-" }}</strong>
      </div>
      <div class="llm-field">
        <span class="llm-label mono">对象</span>
        <strong>{{ llmActivity.targetLabel || "-" }}</strong>
      </div>
      <div class="llm-field">
        <span class="llm-label mono">并发数</span>
        <strong>{{ activeWorkers || 0 }}</strong>
      </div>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";

const props = defineProps({
  llmActivity: { type: Object, required: true },
  activeWorkers: { type: Number, default: 0 },
});

const engineTitle = computed(() => {
  if (props.llmActivity.mode === "offline") return "规则分析引擎";
  if (props.llmActivity.mode === "llm") return "大模型实时分析";
  return "等待分析引擎";
});
const enginePill = computed(() => {
  if (props.llmActivity.mode === "offline") return "规则";
  if (props.llmActivity.mode === "llm") return "大模型";
  return "待命";
});
const modeClass = computed(() => props.llmActivity.mode || "idle");
</script>

<style scoped>
.log-card {
  border: 1px solid var(--line-soft);
  border-radius: 16px;
  padding: 14px;
}

.llm-card {
  background:
    radial-gradient(circle at top right, rgba(39, 90, 120, 0.12), transparent 38%),
    linear-gradient(180deg, rgba(255, 250, 240, 0.98), rgba(250, 244, 231, 0.98));
}

.llm-card.offline {
  background:
    radial-gradient(circle at top right, rgba(56, 106, 79, 0.12), transparent 38%),
    linear-gradient(180deg, rgba(255, 250, 240, 0.98), rgba(247, 242, 232, 0.98));
}

.llm-top,
.llm-grid {
  display: flex;
  gap: 10px;
}

.llm-top {
  justify-content: space-between;
}

.llm-top h3,
.action-text {
  margin: 0;
}

.llm-top h3 {
  margin-top: 4px;
  font-size: 18px;
  font-family: "ZCOOL XiaoWei", serif;
}

.section-code,
.llm-label {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--text-sub);
}

.engine-pill {
  height: fit-content;
  border-radius: 999px;
  border: 1px solid rgba(39, 90, 120, 0.2);
  background: rgba(255, 255, 255, 0.55);
  padding: 5px 10px;
  font-size: 11px;
}

.action-text {
  margin-top: 12px;
  color: var(--text-main);
}

.llm-grid {
  margin-top: 14px;
  flex-wrap: wrap;
}

.llm-field {
  min-width: 120px;
  flex: 1 1 120px;
  border-top: 1px dashed rgba(159, 141, 106, 0.6);
  padding-top: 10px;
}

.llm-field strong {
  display: block;
  margin-top: 6px;
}
</style>
