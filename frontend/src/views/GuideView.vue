<template>
  <section class="guide-layout">
    <article class="workbench-card panel">
      <div class="progress-head">
        <div>
          <div class="section-kicker mono">使用教程</div>
          <h2 class="card-title">第一次使用怎么走</h2>
          <p>教程集中在这里，总览页只保留实际操作区。</p>
        </div>
        <div class="progress-badge">
          <span class="mono">当前进度</span>
          <strong>{{ currentStep.label }}</strong>
          <small>{{ progressSummary }}</small>
        </div>
      </div>

      <div class="progress-grid">
        <div class="progress-item">
          <span class="mono">最近项目</span>
          <strong>{{ latestProjectName }}</strong>
        </div>
        <div class="progress-item">
          <span class="mono">当前步骤</span>
          <strong>{{ currentStep.label }}</strong>
        </div>
        <div class="progress-item">
          <span class="mono">项目状态</span>
          <strong>{{ latestProjectStatus }}</strong>
        </div>
      </div>
    </article>

    <article class="workbench-card panel">
      <div class="section-head">
        <div>
          <h2 class="card-title">四步上手</h2>
          <p>按顺序走就行，每一步都能直接跳到对应功能页。</p>
        </div>
      </div>

      <div class="step-grid">
        <article v-for="(step, index) in visualSteps" :key="step.key" class="step-card" :class="step.state">
          <div class="step-top">
            <span class="step-index mono">0{{ index + 1 }}</span>
            <span class="step-state mono">{{ formatStepState(step.state) }}</span>
          </div>
          <h3>{{ step.label }}</h3>
          <p>{{ step.description }}</p>
          <button
            class="btn"
            :class="{ primary: step.state === 'active' }"
            type="button"
            @click="handleStepClick(step)"
          >
            前往{{ step.label }}
          </button>
        </article>
      </div>
    </article>

    <article class="workbench-card panel">
      <div class="section-head">
        <div>
          <h2 class="card-title">术语说明</h2>
          <p>把首页里原本混在一起的概念解释集中放到这里。</p>
        </div>
      </div>

      <div class="concept-grid">
        <article v-for="item in conceptItems" :key="item.key" class="concept-card">
          <h3>{{ item.label }}</h3>
          <p>{{ item.description }}</p>
        </article>
      </div>
    </article>
  </section>
</template>

<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";

import { useProjectCatalog } from "../composables/useProjectCatalog";
import { useSeedUpload } from "../composables/useSeedUpload";
import { formatProjectStatus } from "../utils/chineseDisplay";
import { GUIDE_CONCEPT_ITEMS } from "./guide/guideContent";
import {
  buildVisualWorkflowSteps,
  buildWorkflowSummary,
  buildWorkflowTargets,
  getWorkflowStep,
  resolveWorkflowStep,
} from "./guide/workflowGuideState";

const STEP_STATE_TEXT = Object.freeze({
  done: "已完成",
  active: "当前步骤",
  upcoming: "下一步",
});

const router = useRouter();
const upload = useSeedUpload();
const { latestProject } = useProjectCatalog();
const workflowTargets = buildWorkflowTargets();
const conceptItems = GUIDE_CONCEPT_ITEMS;

const currentStepKey = computed(() =>
  resolveWorkflowStep({
    latestProject: latestProject.value,
    uploadPhase: upload.state.uploadPhase,
    taskStatus: upload.state.taskStatus,
  }),
);
const currentStep = computed(() => getWorkflowStep(currentStepKey.value));
const latestProjectName = computed(() => latestProject.value?.name || "还没有项目");
const latestProjectStatus = computed(() =>
  latestProject.value ? formatProjectStatus(latestProject.value.status) : "等待创建第一个项目",
);
const progressSummary = computed(() =>
  buildWorkflowSummary({
    latestProject: latestProject.value,
    uploadPhase: upload.state.uploadPhase,
    taskStatus: upload.state.taskStatus,
  }),
);
const visualSteps = computed(() => buildVisualWorkflowSteps(currentStepKey.value));

function formatStepState(state) {
  return STEP_STATE_TEXT[state] || "待开始";
}

async function handleStepClick(step) {
  const target = workflowTargets[step.key];
  if (!target) {
    return;
  }
  await router.push(target);
}
</script>

<style scoped>
.guide-layout {
  display: grid;
  gap: 14px;
}

.panel {
  padding: 18px;
}

.section-kicker,
.panel p,
.progress-badge span,
.progress-badge small,
.progress-item span,
.step-state {
  color: var(--text-sub);
}

.progress-head,
.section-head {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.progress-badge {
  min-width: 240px;
  border: 1px solid rgba(159, 141, 106, 0.24);
  border-radius: 14px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.68);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.progress-grid,
.step-grid,
.concept-grid {
  margin-top: 14px;
  display: grid;
  gap: 10px;
}

.progress-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.step-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.concept-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.progress-item,
.step-card,
.concept-card {
  border: 1px solid var(--line-soft);
  border-radius: 14px;
  background: #fffbf2;
  padding: 12px;
}

.progress-item strong,
.step-card h3,
.concept-card h3 {
  display: block;
  margin: 8px 0 0;
}

.step-top {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.step-index {
  width: 36px;
  height: 36px;
  border-radius: 12px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: rgba(159, 141, 106, 0.12);
}

.step-card p,
.concept-card p {
  margin: 8px 0 14px;
  line-height: 1.6;
}

.step-card.done {
  border-color: rgba(56, 106, 79, 0.24);
  background: rgba(241, 248, 243, 0.95);
}

.step-card.done .step-index {
  background: rgba(56, 106, 79, 0.14);
  color: var(--accent-green);
}

.step-card.active {
  border-color: rgba(200, 124, 56, 0.4);
  background: linear-gradient(180deg, rgba(255, 244, 217, 0.96), rgba(255, 251, 242, 0.96));
  box-shadow: 0 12px 24px rgba(200, 124, 56, 0.08);
}

.step-card.active .step-index {
  background: rgba(200, 124, 56, 0.18);
  color: var(--accent-copper);
}

@media (max-width: 980px) {
  .progress-head,
  .section-head {
    flex-direction: column;
  }

  .progress-badge {
    min-width: 0;
    width: 100%;
  }

  .progress-grid,
  .step-grid,
  .concept-grid {
    grid-template-columns: 1fr;
  }
}
</style>
