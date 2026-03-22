<template>
  <section class="pipeline-shell">
    <div class="pipeline-head">
      <div>
        <h3>种子提取管线</h3>
        <p>{{ headline }}</p>
      </div>
      <div class="pipeline-legend">
        <span class="legend-chip pending">待命</span>
        <span class="legend-chip active">进行中</span>
        <span class="legend-chip done">已完成</span>
      </div>
    </div>

    <div class="pipeline-flow">
      <template v-for="(node, index) in nodes" :key="node.stage">
        <div class="pipeline-node" :class="node.state" :title="node.tooltip">
          <span class="mono node-code">{{ String(index + 1).padStart(2, "0") }}</span>
          <strong>{{ node.title }}</strong>
          <small>{{ node.detail }}</small>
        </div>
        <div v-if="index < nodes.length - 1" class="flow-arrow" :class="arrowState(index)"></div>
      </template>
    </div>
  </section>
</template>

<script setup>
import { computed } from "vue";
import { CONCEPT_TOOLTIPS } from "../../utils/chineseDisplay";
import { IDLE_TIMELINE } from "./seedUploadTaskView";

const props = defineProps({
  uploadPhase: { type: String, default: "idle" },
  taskStatus: { type: String, default: "" },
  activeStage: { type: Object, default: () => ({ key: "", label: "" }) },
});

const stageIndex = computed(() =>
  IDLE_TIMELINE.findIndex(([stage]) => stage === props.activeStage?.key),
);

const headline = computed(() => {
  if (props.uploadPhase === "uploading") {
    return "文件正在上传，上传完成后会自动进入下列后台阶段。";
  }
  if (props.taskStatus === "processing") {
    return props.activeStage?.label
      ? `当前焦点：${props.activeStage.label}`
      : "后台正在依次推进骨架扫描、事实提取与种子聚合。";
  }
  if (props.taskStatus === "completed" || props.uploadPhase === "success") {
    return "本轮管线已经走完，可继续查看种子分析、档案和世界线。";
  }
  if (props.taskStatus === "failed" || props.uploadPhase === "error") {
    return "当前轮次中断了，节点会停在最后一个失败阶段。";
  }
  return "上传后系统会从切章开始，逐步完成骨架扫描、故事记忆和种子聚合。";
});

const nodes = computed(() =>
  IDLE_TIMELINE.map(([stage, title, detail], index) => ({
    stage,
    title,
    detail,
    tooltip: CONCEPT_TOOLTIPS[stage] || detail,
    state: nodeState(index, stage),
  })),
);

function nodeState(index, stage) {
  if (props.uploadPhase === "idle" || props.uploadPhase === "uploading") {
    return "pending";
  }
  if (props.taskStatus === "completed" || props.activeStage?.key === "completed") {
    return "done";
  }
  if (props.taskStatus === "failed" || props.uploadPhase === "error") {
    if (stageIndex.value === index) {
      return "failed";
    }
    return index < stageIndex.value ? "done" : "pending";
  }
  if (stageIndex.value < 0) {
    return "pending";
  }
  if (index < stageIndex.value) {
    return "done";
  }
  if (index === stageIndex.value) {
    return "active";
  }
  return "pending";
}

function arrowState(index) {
  if (props.taskStatus === "completed" || props.activeStage?.key === "completed") {
    return "done";
  }
  if (stageIndex.value > index) {
    return "done";
  }
  return "pending";
}
</script>

<style scoped>
.pipeline-shell {
  margin-top: 16px;
  border: 1px solid var(--line-soft);
  border-radius: 16px;
  padding: 14px;
  background:
    linear-gradient(180deg, rgba(255, 252, 244, 0.95), rgba(255, 248, 235, 0.92)),
    radial-gradient(circle at 100% 0%, rgba(39, 90, 120, 0.08), transparent 26%);
}

.pipeline-head {
  display: flex;
  justify-content: space-between;
  gap: 14px;
  align-items: flex-start;
}

.pipeline-head h3 {
  margin: 0;
  font-family: "ZCOOL XiaoWei", serif;
  font-size: 22px;
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

.legend-chip {
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 12px;
}

.legend-chip.pending {
  background: rgba(159, 141, 106, 0.1);
  color: var(--text-sub);
}

.legend-chip.active {
  background: rgba(200, 124, 56, 0.16);
  color: var(--accent-copper);
}

.legend-chip.done {
  background: rgba(56, 106, 79, 0.14);
  color: var(--accent-green);
}

.pipeline-flow {
  margin-top: 16px;
  display: flex;
  align-items: center;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 4px;
}

.pipeline-node {
  min-width: 170px;
  flex: 0 0 170px;
  min-height: 126px;
  border-radius: 16px;
  border: 1px solid var(--line-soft);
  padding: 12px;
  background: rgba(255, 255, 255, 0.58);
  display: flex;
  flex-direction: column;
  gap: 8px;
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

.pipeline-node.pending {
  opacity: 0.88;
}

.pipeline-node.active {
  border-color: rgba(200, 124, 56, 0.42);
  background: linear-gradient(180deg, rgba(255, 242, 210, 0.98), rgba(255, 251, 243, 0.96));
  box-shadow: 0 12px 24px rgba(200, 124, 56, 0.12);
}

.pipeline-node.done {
  border-color: rgba(56, 106, 79, 0.24);
  background: rgba(240, 249, 243, 0.92);
}

.pipeline-node.failed {
  border-color: rgba(155, 67, 38, 0.36);
  background: rgba(255, 241, 235, 0.95);
}

.flow-arrow {
  flex: 0 0 28px;
  height: 2px;
  border-radius: 999px;
  background: rgba(159, 141, 106, 0.18);
}

.flow-arrow.done {
  background: linear-gradient(90deg, rgba(56, 106, 79, 0.65), rgba(56, 106, 79, 0.2));
}

@media (max-width: 980px) {
  .pipeline-head {
    flex-direction: column;
  }
}
</style>
