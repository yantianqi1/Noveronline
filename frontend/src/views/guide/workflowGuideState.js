export const WORKFLOW_STEPS = Object.freeze([
  {
    key: "upload",
    label: "上传小说文本",
    description: "先把正文、设定集或大纲放进项目。",
  },
  {
    key: "seed",
    label: "种子分析",
    description: "切章、抽取角色关系，整理故事种子。",
  },
  {
    key: "archive",
    label: "建立档案",
    description: "沉淀角色、组织与设定卡片。",
  },
  {
    key: "worldline",
    label: "世界线推演",
    description: "注入变量，观察当前世界如何继续演化。",
  },
  {
    key: "writing",
    label: "正文创作",
    description: "用 Agent 协同创作小说正文，可反复修订。",
  },
]);

const WORKFLOW_TARGETS = Object.freeze({
  upload: Object.freeze({ path: "/", hash: "#seed-upload" }),
  seed: Object.freeze({ path: "/", hash: "#seed-analysis" }),
  archive: Object.freeze({ path: "/archive-library" }),
  worldline: Object.freeze({ path: "/worldline" }),
  writing: Object.freeze({ path: "/writer" }),
});

export function buildWorkflowTargets() {
  return WORKFLOW_TARGETS;
}

export function getWorkflowStep(stepKey) {
  return WORKFLOW_STEPS.find((step) => step.key === stepKey) || WORKFLOW_STEPS[0];
}

export function buildWorkflowSummary({
  latestProject = null,
  uploadPhase = "idle",
  taskStatus = "",
} = {}) {
  if (uploadPhase === "processing" || taskStatus === "processing") {
    return "后台正在分析小说，当前重点是等种子链路跑完。";
  }
  if (!latestProject) {
    return "还没有项目时，从上传小说文本开始就好。";
  }
  return `最近项目「${latestProject.name}」会从这里继续往下走。`;
}

export function buildVisualWorkflowSteps(currentStepKey) {
  const currentIndex = WORKFLOW_STEPS.findIndex((step) => step.key === currentStepKey);
  return WORKFLOW_STEPS.map((step, index) => ({
    ...step,
    state: index < currentIndex ? "done" : index === currentIndex ? "active" : "upcoming",
  }));
}

export function resolveWorkflowStep({
  latestProject = null,
  uploadPhase = "idle",
  taskStatus = "",
} = {}) {
  if (uploadPhase === "uploading") {
    return "upload";
  }
  if (uploadPhase === "processing" || taskStatus === "processing") {
    return "seed";
  }
  if (!latestProject) {
    return "upload";
  }
  if (latestProject.graph_id || latestProject.status === "graph_completed") {
    return "writing";
  }
  if (latestProject.ontology || latestProject.status === "ontology_generated") {
    return "archive";
  }
  if (latestProject.status === "seed_processing" || latestProject.status === "seed_completed") {
    return "seed";
  }
  return "upload";
}
