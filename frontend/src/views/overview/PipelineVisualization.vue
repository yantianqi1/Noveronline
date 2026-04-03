<template>
  <section class="pipeline-shell" :class="{ compact }">
    <div class="pipeline-head">
      <div>
        <h3>{{ compact ? "当前阶段轨道" : "分析流程" }}</h3>
        <p>{{ headline }}</p>
      </div>
      <div v-if="!compact" class="pipeline-legend">
        <span class="legend-chip pending">待命</span>
        <span class="legend-chip active">进行中</span>
        <span class="legend-chip done">已完成</span>
      </div>
    </div>

    <div v-if="compact" class="pipeline-flow compact">
      <template v-for="item in railItems" :key="railKey(item)">
        <article v-if="item.kind === 'node'" class="pipeline-node compact" :class="item.state" :title="item.tooltip">
          <span class="mono node-code">{{ String(item.sequence).padStart(2, "0") }}</span>
          <strong>{{ item.title }}</strong>
        </article>
        <div v-else class="pipeline-summary-pill" :class="item.state">{{ item.label }}</div>
      </template>
    </div>
    <div v-else class="pipeline-flow">
      <article v-for="node in fullNodes" :key="node.stage" class="pipeline-node" :class="node.state" :title="node.tooltip">
        <div class="node-top">
          <span class="mono node-code">{{ String(node.sequence).padStart(2, "0") }}</span>
          <span class="node-state-chip">{{ formatNodeState(node.state) }}</span>
        </div>
        <strong>{{ node.title }}</strong>
        <small>{{ node.detail }}</small>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import { buildFullPipelineNodes, buildPipelineRailWindow } from "./overviewWorkbenchState.js";

const props = defineProps({
  uploadPhase: { type: String, default: "idle" },
  taskStatus: { type: String, default: "" },
  activeStage: { type: Object, default: () => ({ key: "", label: "" }) },
  compact: { type: Boolean, default: false },
});

const fullNodes = computed(() => buildFullPipelineNodes(props));
const railItems = computed(() => buildPipelineRailWindow(props).items);
const headline = computed(() => {
  if (props.uploadPhase === "uploading") {
    return "文件正在上传，上传完成后会自动进入后台分析。";
  }
  if (props.taskStatus === "processing") {
    return props.activeStage?.label
      ? `当前焦点：${props.activeStage.label}`
      : "后台正在依次推进骨架扫描、事实提取与种子聚合。";
  }
  if (props.taskStatus === "completed" || props.uploadPhase === "success") {
    return "分析已完成，可以查看档案和分析结果。";
  }
  if (props.taskStatus === "failed" || props.uploadPhase === "error") {
    return "当前轮次中断了，完整卷宗会保留失败阶段。";
  }
  return "等待新的分析任务启动。";
});

function railKey(item) { return item.kind === "summary" ? `${item.state}_${item.count}` : item.stage; }

function formatNodeState(state) {
  if (state === "done") return "已完成";
  if (state === "active") return "当前";
  if (state === "failed") return "中断";
  return "待命";
}
</script>

<style scoped>
.pipeline-shell {
  margin-top: 16px;
  border: 1px solid var(--line-soft);
  border-radius: 18px;
  padding: 16px;
  background: linear-gradient(180deg, rgba(255, 252, 244, 0.95), rgba(255, 248, 235, 0.92)),
    radial-gradient(circle at 100% 0%, rgba(39, 90, 120, 0.08), transparent 26%);
}

.pipeline-head, .node-top { display: flex; justify-content: space-between; gap: 12px; }

.pipeline-head {
  align-items: flex-start;
}

.pipeline-head h3 {
  margin: 0;
  font-size: 22px;
  font-family: "ZCOOL XiaoWei", serif;
}

.pipeline-head p {
  margin: 8px 0 0;
  color: var(--text-sub);
}

.pipeline-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.legend-chip, .pipeline-summary-pill, .node-state-chip { border-radius: 999px; padding: 4px 10px; font-size: 12px; }

.legend-chip.pending,
.pipeline-summary-pill.pending,
.node-state-chip {
  background: rgba(159, 141, 106, 0.1);
  color: var(--text-sub);
}

.legend-chip.active {
  background: rgba(200, 124, 56, 0.16);
  color: var(--accent-copper);
}

.legend-chip.done,
.pipeline-summary-pill.done {
  background: rgba(56, 106, 79, 0.14);
  color: var(--accent-green);
}

.rail-note {
  color: var(--text-dim);
  font-size: 12px;
}

.pipeline-flow {
  margin-top: 16px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
  gap: 12px;
}

.pipeline-flow.compact {
  grid-template-columns: repeat(5, minmax(0, 1fr));
  align-items: stretch;
}

.pipeline-node {
  min-width: 0;
  min-height: 126px;
  border-radius: 16px;
  border: 1px solid var(--line-soft);
  padding: 12px;
  background: rgba(255, 255, 255, 0.58);
  display: flex;
  flex-direction: column;
  gap: 8px;
  position: relative;
  overflow: hidden;
}

.pipeline-node.compact {
  min-height: 92px;
  justify-content: space-between;
}

.pipeline-node::before {
  content: "";
  position: absolute;
  inset: 0 0 auto 0;
  height: 4px;
  background: rgba(159, 141, 106, 0.22);
}

.node-top {
  align-items: center;
}

.node-code {
  font-size: 12px;
  color: var(--text-sub);
}

.pipeline-node strong {
  font-size: 15px;
}

.pipeline-node small {
  color: var(--text-sub);
  line-height: 1.55;
}

.pipeline-summary-pill {
  min-height: 92px;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  border: 1px dashed rgba(113, 128, 150, 0.22);
  background: rgba(255, 255, 255, 0.62);
}

.pipeline-summary-pill.pending {
  color: var(--text-sub);
}

.pipeline-node.pending {
  opacity: 0.88;
}

.pipeline-node.active {
  border-color: rgba(200, 124, 56, 0.42);
  background: linear-gradient(180deg, rgba(255, 242, 210, 0.98), rgba(255, 251, 243, 0.96));
  box-shadow: 0 12px 24px rgba(200, 124, 56, 0.12);
  transform: translateY(-2px);
}

.pipeline-node.active::before {
  background: linear-gradient(90deg, rgba(200, 124, 56, 0.95), rgba(200, 124, 56, 0.25));
}

.pipeline-node.active .node-state-chip {
  color: var(--accent-copper-deep);
  background: rgba(200, 124, 56, 0.14);
}

.pipeline-node.done {
  border-color: rgba(56, 106, 79, 0.24);
  background: rgba(240, 249, 243, 0.92);
}

.pipeline-node.done::before {
  background: linear-gradient(90deg, rgba(56, 106, 79, 0.88), rgba(56, 106, 79, 0.18));
}

.pipeline-node.done .node-state-chip {
  color: var(--accent-green);
  background: rgba(56, 106, 79, 0.12);
}

.pipeline-node.failed {
  border-color: rgba(155, 67, 38, 0.36);
  background: rgba(255, 241, 235, 0.95);
}

.pipeline-node.failed::before {
  background: linear-gradient(90deg, rgba(155, 67, 38, 0.9), rgba(155, 67, 38, 0.22));
}

.pipeline-node.failed .node-state-chip,
.pipeline-summary-pill.failed {
  color: var(--accent-seal);
  background: rgba(155, 67, 38, 0.12);
}

@media (max-width: 980px) {
  .pipeline-head {
    flex-direction: column;
  }

  .pipeline-flow.compact {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
