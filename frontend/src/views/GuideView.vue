<template>
  <div class="guide-stage stack">
    <!-- Header: Purpose -->
    <header class="guide-header workbench-card">
      <div class="header-main">
        <h2 class="title-ancient">帮助与术语指南</h2>
        <p class="subtitle">理解 MiroFish-Novel 的核心设计理念与操作链路。</p>
      </div>
    </header>

    <div class="guide-grid container-7-5">
      <div class="guide-main stack">
        <!-- Section: Workflow -->
        <section class="guide-section workbench-card">
          <h3 class="title-ancient">创作推演链路</h3>
          <div class="workflow-visual">
            <div v-for="(step, index) in visualSteps" :key="step.key" class="workflow-node" :class="step.state">
              <div class="node-circle">
                <span class="mono">{{ index + 1 }}</span>
              </div>
              <div class="node-content">
                <strong>{{ step.label }}</strong>
                <p>{{ step.description }}</p>
                <n-button text size="small" @click="handleStepClick(step)">跳转功能</n-button>
              </div>
            </div>
          </div>
        </section>

        <!-- Section: Concepts -->
        <section class="guide-section workbench-card">
          <h3 class="title-ancient">核心术语释义</h3>
          <div class="concept-list">
            <article v-for="item in conceptItems" :key="item.key" class="concept-item">
              <h4>{{ item.label }}</h4>
              <p>{{ item.description }}</p>
            </article>
          </div>
        </section>
      </div>

      <aside class="guide-sidebar stack">
        <!-- Section: Status Summary -->
        <section class="status-summary workbench-card">
          <h3 class="title-ancient">当前卷宗状态</h3>
          <div class="summary-details stack">
            <div class="summary-row">
              <label>最近推演</label>
              <strong>{{ latestProjectName }}</strong>
            </div>
            <div class="summary-row">
              <label>所处阶段</label>
              <n-tag :type="currentStep.key === 'done' ? 'success' : 'warning'" size="small">
                {{ currentStep.label }}
              </n-tag>
            </div>
            <p class="summary-note">{{ progressSummary }}</p>
          </div>
        </section>

        <!-- Section: FAQ or Tips -->
        <section class="tips-card workbench-card">
          <h3 class="title-ancient">使用小贴士</h3>
          <ul class="tips-list">
            <li><strong>投放文本：</strong> 支持 txt、md 与 pdf，建议优先使用纯文本以获得最高解析精度。</li>
            <li><strong>生成图谱：</strong> 图谱是后续所有推演的基础，建议在档案库完善后再行构建。</li>
            <li><strong>世界线：</strong> 每一条注入的变量都会继续改写当前世界，您可以沿着同一条主线持续推进。</li>
          </ul>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed } from "vue";
import { NButton, NTag } from "naive-ui";
import { useRouter } from "vue-router";

import { useProjectCatalog } from "../composables/useProjectCatalog";
import { useSeedUpload } from "../composables/useSeedUpload";
import { GUIDE_CONCEPT_ITEMS } from "./guide/guideContent";
import {
  buildVisualWorkflowSteps,
  buildWorkflowSummary,
  buildWorkflowTargets,
  getWorkflowStep,
  resolveWorkflowStep,
} from "./guide/workflowGuideState";

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
const latestProjectName = computed(() => latestProject.value?.name || "尚未开启");

const progressSummary = computed(() =>
  buildWorkflowSummary({
    latestProject: latestProject.value,
    uploadPhase: upload.state.uploadPhase,
    taskStatus: upload.state.taskStatus,
  }),
);
const visualSteps = computed(() => buildVisualWorkflowSteps(currentStepKey.value));

async function handleStepClick(step) {
  const target = workflowTargets[step.key];
  if (target) await router.push(target);
}
</script>

<style scoped>
.guide-stage {
  max-width: 1200px;
  margin: 0 auto;
}

.guide-header {
  padding: var(--space-md) var(--space-lg);
}

.subtitle {
  font-size: 14px;
  color: var(--text-dim);
  margin-top: 4px;
}

.guide-section {
  padding: var(--space-md);
}

.workflow-visual {
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
  margin-top: var(--space-md);
  position: relative;
}

.workflow-visual::before {
  content: '';
  position: absolute;
  left: 17px;
  top: 20px;
  bottom: 20px;
  width: 2px;
  background: var(--line-soft);
  z-index: 0;
}

.workflow-node {
  display: flex;
  gap: var(--space-md);
  position: relative;
  z-index: 1;
}

.node-circle {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: var(--bg-panel);
  border: 2px solid var(--line-medium);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.3s ease;
}

.workflow-node.done .node-circle {
  border-color: var(--accent-green);
  background: rgba(74, 109, 84, 0.1);
}

.workflow-node.active .node-circle {
  border-color: var(--accent-copper);
  background: #fff;
  box-shadow: 0 0 12px rgba(176, 125, 75, 0.3);
}

.node-content {
  flex: 1;
}

.node-content strong {
  display: block;
  font-size: 16px;
  margin-bottom: 4px;
}

.node-content p {
  font-size: 13px;
  color: var(--text-sub);
  margin-bottom: var(--space-sm);
  line-height: 1.6;
}

.concept-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-md);
  margin-top: var(--space-md);
}

.concept-item h4 {
  font-size: 16px;
  color: var(--accent-copper-deep);
  margin-bottom: var(--space-xs);
}

.concept-item p {
  font-size: 13px;
  color: var(--text-sub);
  line-height: 1.6;
}

.status-summary, .tips-card {
  padding: var(--space-md);
}

.summary-details {
  margin-top: var(--space-md);
}

.summary-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
}

.summary-row label {
  font-size: 12px;
  color: var(--text-dim);
}

.summary-note {
  font-size: 13px;
  color: var(--text-sub);
  margin-top: var(--space-sm);
  line-height: 1.5;
}

.tips-list {
  margin: var(--space-md) 0 0;
  padding-left: var(--space-md);
  list-style: square;
  color: var(--text-sub);
  font-size: 13px;
}

.tips-list li {
  margin-bottom: var(--space-sm);
}

@media (max-width: 900px) {
  .concept-list { grid-template-columns: 1fr; }
}
</style>
