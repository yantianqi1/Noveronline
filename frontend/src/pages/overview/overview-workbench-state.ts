/**
 * Overview workbench state helpers — ported from
 * src-vue/views/overview/overviewWorkbenchState.js
 *
 * Pipeline node building, rail window generation, and next-action logic.
 */

import { IDLE_TIMELINE } from "@/lib/seed-upload-task-view";
import type { ActiveStage } from "@/lib/seed-upload-task-state";

/* ---------- Constants ---------- */

const PREVIOUS_WINDOW_COUNT = 1;
const NEXT_WINDOW_COUNT = 2;
const IDLE_PREVIEW_COUNT = 4;

const CONCEPT_TOOLTIPS: Record<string, string> = {
  smart_segmentation:
    "智能分段：按令牌预算将章节分组为阅读段，确保每段在模型上下文窗口内完整可读。",
  sequential_reading:
    "顺序深度阅读：LLM逐段精读小说，提取角色、关系和剧情，维持跨段记忆。",
  global_integration:
    "全局整合：整合全部阅读笔记，聚合角色、组织与关系为统一种子分析。",
  agent_profiles:
    "角色Agent档案：为重要角色生成可用于对话和模拟的完整档案。",
};

/* ---------- Types ---------- */

export interface PipelineNode {
  stage: string;
  title: string;
  detail: string;
  tooltip: string;
  sequence: number;
  state: "pending" | "active" | "done" | "failed";
}

export interface RailItem extends PipelineNode {
  kind: "node";
}

export interface RailSummary {
  kind: "summary";
  state: string;
  count: number;
  label: string;
}

export type RailEntry = RailItem | RailSummary;

export interface NextAction {
  label: string;
  description: string;
  type: "command" | "route";
  command?: string;
  to?: string;
  tone: string;
}

export interface PipelineContext {
  uploadPhase?: string;
  taskStatus?: string;
  activeStage?: ActiveStage;
}

interface ProjectLike {
  id: string;
  status: string;
  graph_id?: string;
}

/* ---------- Pipeline building ---------- */

function createBaseNodes(): Omit<PipelineNode, "state">[] {
  return IDLE_TIMELINE.map(([stage, title, detail], index) => ({
    stage,
    title,
    detail,
    tooltip: CONCEPT_TOOLTIPS[stage] || detail,
    sequence: index + 1,
  }));
}

function resolveActiveStageIndex(activeStage?: ActiveStage): number {
  return IDLE_TIMELINE.findIndex(([stage]) => stage === activeStage?.key);
}

function resolveNodeState({
  uploadPhase,
  taskStatus,
  activeIndex,
  index,
  activeStage,
}: {
  uploadPhase: string;
  taskStatus: string;
  activeIndex: number;
  index: number;
  activeStage?: ActiveStage;
}): PipelineNode["state"] {
  if (uploadPhase === "idle" || uploadPhase === "uploading") return "pending";
  if (
    taskStatus === "completed" ||
    activeStage?.key === "completed" ||
    uploadPhase === "success"
  )
    return "done";
  if (taskStatus === "failed" || uploadPhase === "error") {
    if (activeIndex === index) return "failed";
    return index < activeIndex ? "done" : "pending";
  }
  if (activeIndex < 0) return "pending";
  if (index < activeIndex) return "done";
  if (index === activeIndex) return "active";
  return "pending";
}

export function buildFullPipelineNodes(context: PipelineContext = {}): PipelineNode[] {
  const {
    uploadPhase = "idle",
    taskStatus = "",
    activeStage,
  } = context;
  const activeIndex = resolveActiveStageIndex(activeStage);
  return createBaseNodes().map((node, index) => ({
    ...node,
    state: resolveNodeState({ uploadPhase, taskStatus, activeIndex, index, activeStage }),
  }));
}

export function buildPipelineRailWindow(
  context: PipelineContext = {},
): { items: RailEntry[] } {
  const nodes = buildFullPipelineNodes(context);
  const activeIndex = resolveActiveStageIndex(context.activeStage);
  if (
    context.uploadPhase === "idle" ||
    context.uploadPhase === "uploading" ||
    activeIndex < 0
  ) {
    return buildIdleRail(nodes);
  }
  return buildFocusedRail(nodes, activeIndex);
}

function buildIdleRail(nodes: PipelineNode[]): { items: RailEntry[] } {
  const previewNodes: RailEntry[] = nodes.slice(0, IDLE_PREVIEW_COUNT).map((node) => ({
    ...node,
    state: "pending" as const,
    kind: "node" as const,
  }));
  const items: RailEntry[] = [...previewNodes];
  const hiddenCount = Math.max(0, nodes.length - previewNodes.length);
  if (hiddenCount > 0) {
    items.push(buildSummary("pending", hiddenCount, `后续 ${hiddenCount} 阶段`));
  }
  return { items };
}

function buildFocusedRail(
  nodes: PipelineNode[],
  activeIndex: number,
): { items: RailEntry[] } {
  const start = Math.max(0, activeIndex - PREVIOUS_WINDOW_COUNT);
  const end = Math.min(nodes.length - 1, activeIndex + NEXT_WINDOW_COUNT);
  const items: RailEntry[] = [];
  if (start > 0) {
    items.push(buildSummary("done", start, `已完成 ${start} 阶段`));
  }
  for (let index = start; index <= end; index += 1) {
    const node = nodes[index];
    if (node) items.push({ kind: "node" as const, stage: node.stage, title: node.title, detail: node.detail, tooltip: node.tooltip, sequence: node.sequence, state: node.state });
  }
  const hiddenCount = Math.max(0, nodes.length - end - 1);
  if (hiddenCount > 0) {
    items.push(buildSummary("pending", hiddenCount, `后续 ${hiddenCount} 阶段`));
  }
  return { items };
}

function buildSummary(state: string, count: number, label: string): RailSummary {
  return { kind: "summary", state, count, label };
}

/* ---------- Next actions ---------- */

function commandAction(
  label: string,
  description: string,
  command: string,
  tone = "default",
): NextAction {
  return { label, description, type: "command", command, tone };
}

function routeAction(
  label: string,
  description: string,
  to: string,
  tone = "default",
): NextAction {
  return { label, description, type: "route", to, tone };
}

export function buildOverviewNextActions(project: ProjectLike | null): NextAction[] {
  if (!project) {
    return [
      commandAction(
        "启动新任务",
        "直接投放小说文本，开启一轮新的种子分析。",
        "upload",
        "primary",
      ),
      routeAction("帮助指南", "查看完整操作路线和页面职责，快速建立使用节奏。", "/guide"),
      routeAction(
        "档案库",
        "先浏览已有档案结构，了解角色和组织如何被归档。",
        "/assets",
      ),
      routeAction(
        "设施面板",
        "检查模型渠道和模块绑定，确保新任务可以直接运行。",
        "/llm-facility",
      ),
    ];
  }
  if (project.graph_id) {
    return [
      routeAction(
        "世界线工作台",
        "基于当前世界继续推演剧情、变量与角色行动。",
        "/worldline",
        "primary",
      ),
      routeAction("写作台", "将现有上下文转入正文创作和多 Agent 草稿生成。", "/writer"),
      routeAction(
        "档案库",
        "回看角色、组织和记忆档案，补足写作上下文。",
        `/assets?project_id=${project.id}`,
      ),
      routeAction("故事图谱", "检查图谱关系结构，确认当前卷宗的关联网络。", "/story-graph"),
    ];
  }
  if (String(project.status || "").includes("completed")) {
    return [
      routeAction(
        "档案库",
        "先消费最新种子分析成果，查看角色和组织候选。",
        `/assets?project_id=${project.id}`,
        "primary",
      ),
      routeAction("故事图谱", "继续进入图谱工作台，补足关系可视化。", "/story-graph"),
      commandAction(
        "启动新任务",
        "并行投放另一份小说文本，继续扩充当前工作台。",
        "upload",
      ),
      routeAction("帮助指南", "查看完整流程与后续推荐路径。", "/guide"),
    ];
  }
  if (project.status === "failed") {
    return [
      commandAction(
        "启动新任务",
        "重新投放文本或调整参数后再发起一轮分析。",
        "upload",
        "primary",
      ),
      routeAction(
        "设施面板",
        "优先检查模型绑定和渠道配置，排除失败原因。",
        "/llm-facility",
      ),
      routeAction("帮助指南", "回看标准流程，确认输入与前置设置完整。", "/guide"),
      routeAction(
        "档案库",
        "查看之前已完成的卷宗和档案，避免当前工作中断。",
        "/assets",
      ),
    ];
  }
  return [
    routeAction(
      "档案库",
      "查看当前卷宗已经沉淀下来的档案与候选结果。",
      `/assets?project_id=${project.id}`,
      "primary",
    ),
    routeAction(
      "故事图谱",
      "进入图谱视图检查关系网络是否已可消费。",
      "/story-graph",
    ),
    commandAction("启动新任务", "保持总览入口可用，随时追加新的种子任务。", "upload"),
    routeAction("帮助指南", "补全对工作台和分析链路的理解。", "/guide"),
  ];
}
