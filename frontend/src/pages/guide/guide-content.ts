/**
 * Guide page content definitions.
 *
 * Ported from src-vue/views/guide/guideContent.js.
 */

export interface ConceptItem {
  key: string;
  label: string;
  description: string;
}

export const CONCEPT_TOOLTIPS: Record<string, string> = {
  sequential_reading:
    "顺序深度阅读：LLM逐段精读小说，提取角色、关系和剧情，维持跨段记忆。",
  global_integration:
    "全局整合：整合全部阅读笔记，聚合角色、组织与关系为统一种子分析。",
  archive:
    "档案：为角色、组织或关系生成的可复用设定卡，可供世界线和控制台继续使用。",
  worldline:
    "世界线：基于同一部小说，在当前世界状态上持续注入变量并向前推进。",
  variable_injection:
    "变量注入：向当前世界线加入一个新条件，观察它如何改变剧情链条。",
  agent:
    "Agent：在世界线中拥有状态、目标与可交互能力的角色、组织或关系。",
};

export const GUIDE_CONCEPT_ITEMS: readonly ConceptItem[] = Object.freeze([
  {
    key: "sequential_reading",
    label: "顺序深度阅读",
    description: CONCEPT_TOOLTIPS.sequential_reading!,
  },
  {
    key: "global_integration",
    label: "全局整合",
    description: CONCEPT_TOOLTIPS.global_integration!,
  },
  {
    key: "archive",
    label: "档案",
    description: CONCEPT_TOOLTIPS.archive!,
  },
  {
    key: "worldline",
    label: "世界线",
    description: CONCEPT_TOOLTIPS.worldline!,
  },
  {
    key: "variable_injection",
    label: "变量注入",
    description: CONCEPT_TOOLTIPS.variable_injection!,
  },
  {
    key: "agent",
    label: "Agent",
    description: CONCEPT_TOOLTIPS.agent!,
  },
]);
