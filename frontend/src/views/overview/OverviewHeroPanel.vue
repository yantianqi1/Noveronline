<template>
  <article class="workbench-card panel hero-panel">
    <div class="hero-head">
      <div>
        <h2 class="card-title">项目总览</h2>
        <p>{{ heroIntro }}</p>
      </div>
      <button class="btn" @click="$emit('refresh')">刷新项目列表</button>
    </div>

    <div class="kpis">
      <div class="kpi"><span class="mono">项目数</span><strong>{{ projects.length }}</strong></div>
      <div class="kpi"><span class="mono">最近项目</span><strong>{{ latestProjectName }}</strong></div>
      <div class="kpi"><span class="mono">当前状态</span><strong>{{ latestProjectStatus }}</strong></div>
    </div>
    <p class="overview-note">{{ overviewNote }}</p>
    <p v-if="errorMessage" class="seed-error">{{ errorMessage }}</p>
  </article>
</template>

<script setup>
import { computed } from "vue";
import { formatProjectStatus } from "../../utils/chineseDisplay";

const props = defineProps({
  projects: { type: Array, default: () => [] },
  uploadPhase: { type: String, default: "idle" },
  activeStageLabel: { type: String, default: "" },
  errorMessage: { type: String, default: "" },
});

defineEmits(["refresh"]);

const latestProject = computed(() => props.projects[0] || null);
const latestProjectName = computed(() => latestProject.value?.name || "还没有项目");
const latestProjectStatus = computed(() =>
  latestProject.value ? formatProjectStatus(latestProject.value.status) : "等待第一部小说进入工作台",
);
const heroIntro = computed(() => {
  if (!props.projects.length) {
    return "这里保留项目状态与实际操作区，下方可以直接上传小说文本创建第一部作品。";
  }
  return "这里集中查看项目状态，下方继续上传文本或运行种子分析。";
});
const overviewNote = computed(() => {
  if (props.uploadPhase === "processing") {
    return `后台分析正在进行，当前重点阶段：${props.activeStageLabel || "等待分析完成"}。`;
  }
  if (!latestProject.value) {
    return "还没有项目时，从下方上传小说文本开始即可。";
  }
  if (!latestProject.value.ontology && latestProject.value.status === "seed_processing") {
    return "当前项目仍在种子分析阶段，完成后就可以继续进入档案与图谱环节。";
  }
  if (!latestProject.value.graph_id) {
    return "当前项目已经有了基础分析结果，下一步适合去档案库或图谱工作台继续完善。";
  }
  return "项目基础已齐，可以进入世界线工作台继续推演。";
});
</script>

<style scoped>
.panel {
  padding: 18px;
}

.hero-panel {
  background:
    linear-gradient(180deg, rgba(255, 252, 244, 0.98), rgba(250, 242, 228, 0.92)),
    radial-gradient(circle at 100% 0%, rgba(39, 90, 120, 0.08), transparent 24%);
}

.hero-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: center;
}

.hero-head p {
  margin: 8px 0 0;
  color: var(--text-sub);
}

.overview-note,
.seed-error {
  color: var(--text-sub);
}

.kpis {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin-top: 14px;
}

.kpi {
  border: 1px solid var(--line-soft);
  border-radius: 12px;
  background: #fffbf0;
  padding: 10px;
}

.kpi span {
  color: var(--text-sub);
  font-size: 12px;
}

.kpi strong {
  display: block;
  margin-top: 8px;
  font-size: 15px;
}

.overview-note {
  margin-top: 14px;
}

@media (max-width: 1180px) {
  .kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 980px) {
  .hero-head {
    flex-direction: column;
  }
}

@media (max-width: 720px) {
  .kpis {
    grid-template-columns: 1fr;
  }
}
</style>
