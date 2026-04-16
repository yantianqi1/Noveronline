/**
 * Workflow guide state — step resolution & visual step building.
 *
 * Ported from src-vue/views/guide/workflowGuideState.js.
 */

import type { Project } from "@/types/project";

export interface WorkflowStep {
  key: string;
  label: string;
  description: string;
}

export interface VisualWorkflowStep extends WorkflowStep {
  state: "done" | "active" | "upcoming";
}

export interface WorkflowContext {
  latestProject: Project | null;
  uploadPhase: string;
  taskStatus: string;
}

export const WORKFLOW_STEPS: readonly WorkflowStep[] = Object.freeze([
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

export const WORKFLOW_TARGETS: Readonly<Record<string, { path: string; hash?: string }>> =
  Object.freeze({
    upload: Object.freeze({ path: "/", hash: "#seed-upload" }),
    seed: Object.freeze({ path: "/", hash: "#seed-analysis" }),
    archive: Object.freeze({ path: "/assets" }),
    worldline: Object.freeze({ path: "/worldline" }),
    writing: Object.freeze({ path: "/writer" }),
  });

export function getWorkflowStep(stepKey: string): WorkflowStep {
  return WORKFLOW_STEPS.find((step) => step.key === stepKey) || WORKFLOW_STEPS[0]!;
}

export function resolveWorkflowStep({
  latestProject = null,
  uploadPhase = "idle",
  taskStatus = "",
}: Partial<WorkflowContext> = {}): string {
  if (uploadPhase === "uploading") {
    return "upload";
  }
  if (uploadPhase === "processing" || taskStatus === "processing") {
    return "seed";
  }
  if (!latestProject) {
    return "upload";
  }
  const status = latestProject.status?.toLowerCase() || "";
  if (status === "graph_completed") {
    return "writing";
  }
  if (status === "ontology_generated") {
    return "archive";
  }
  if (status === "seed_processing" || status === "seed_completed") {
    return "seed";
  }
  return "upload";
}

export function buildVisualWorkflowSteps(currentStepKey: string): VisualWorkflowStep[] {
  const currentIndex = WORKFLOW_STEPS.findIndex((step) => step.key === currentStepKey);
  return WORKFLOW_STEPS.map((step, index) => ({
    ...step,
    state:
      index < currentIndex ? "done" : index === currentIndex ? "active" : "upcoming",
  }));
}

export function buildWorkflowSummary({
  latestProject = null,
  uploadPhase = "idle",
  taskStatus = "",
}: Partial<WorkflowContext> = {}): string {
  if (uploadPhase === "processing" || taskStatus === "processing") {
    return "后台正在分析小说，当前重点是等种子链路跑完。";
  }
  if (!latestProject) {
    return "还没有项目时，从上传小说文本开始就好。";
  }
  return `最近项目「${latestProject.name}」会从这里继续往下走。`;
}
