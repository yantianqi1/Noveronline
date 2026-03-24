const AGENT_KIND_TEXT = Object.freeze({
  character: "角色",
  organization: "组织",
  relationship: "关系",
});

const AGENT_STATUS_TEXT = Object.freeze({
  active: "活跃",
  engaged: "已介入",
  adjusting: "调整中",
  running: "进行中",
  processing: "进行中",
  completed: "已完成",
  failed: "失败",
  pending: "待处理",
});

const BRANCH_STATUS_TEXT = Object.freeze({
  running: "推演中",
  completed: "已完成",
  failed: "失败",
  pending: "待开始",
  idle: "待启动",
  paused: "待继续",
});

const PROJECT_STATUS_TEXT = Object.freeze({
  created: "已创建",
  seed_processing: "种子分析中",
  ontology_generated: "本体已生成",
  graph_building: "图谱构建中",
  graph_completed: "图谱已完成",
  completed: "已完成",
  failed: "失败",
});

const TASK_STAGE_STATUS_TEXT = Object.freeze({
  processing: "进行中",
  completed: "已完成",
  failed: "失败",
  pending: "待开始",
  active: "进行中",
});

const RELATION_CHANGE_TEXT = Object.freeze({
  stable: "稳定",
  tension_up: "张力上升",
  relationship_shift: "关系转变",
});

const IMPORTANCE_TIER_TEXT = Object.freeze({
  protagonist: "主角",
  major: "重要角色",
  supporting: "配角",
  minor: "次要角色",
});

const ORGANIZATION_TYPE_TEXT = Object.freeze({
  organization: "组织",
  org: "组织",
  group: "团体",
  faction: "势力",
  guild: "公会",
  sect: "宗门",
  school: "学派",
  company: "公司",
});

const ENTITY_TYPE_TEXT = Object.freeze({
  Character: "角色",
  Organization: "组织",
});

const SESSION_SCOPE_TEXT = Object.freeze({
  project: "项目会话",
  global: "全局混合会话",
});

const STAGE_KEY_TEXT = Object.freeze({
  queued: "等待开始",
  extract_text: "提取上传文本",
  segment_chapters: "切分章节与叙事段",
  skeleton_timeline: "骨架时间线扫描",
  build_blocks: "组装分析块",
  anchor_generation: "生成剧情锚点",
  extract_local_facts: "提取块内事实",
  merge_story_memory: "汇总故事记忆",
  entity_resolution: "实体消歧",
  contextual_block_analysis: "分析剧情块",
  consistency_audit: "连续性审计",
  build_continuity: "章节连续性摘要",
  seed_analysis: "聚合种子分析",
  ontology: "生成小说本体",
  completed: "全部完成",
  failed: "执行失败",
});

const UPLOAD_PHASE_TEXT = Object.freeze({
  uploading: "文件上传",
  processing: "后台分析",
  success: "上传完成",
  error: "上传失败",
});

export const APP_BRAND_NAME = "Novelfish 小说工作台";
export const APP_SUBTITLE = "中文小说世界线分析与角色推演控制台";
export const CONCEPT_TOOLTIPS = Object.freeze({
  seed_analysis: "种子分析：从小说原文中提取角色、组织、关系与主线线索，作为后续推演底座。",
  worldline: "世界线：基于同一部小说，在当前世界状态上持续注入变量并向前推进。",
  skeleton_timeline: "骨架时间线：先顺序扫一遍全文，标记角色和组织在哪些章节出现，为并发分析补齐连续性。",
  archive: "档案：为角色、组织或关系生成的可复用设定卡，可供世界线和控制台继续使用。",
  variable_injection: "变量注入：向当前世界线加入一个新条件，观察它如何改变剧情链条。",
  agent: "Agent：在世界线中拥有状态、目标与可交互能力的角色、组织或关系。",
  evolution_intensity: "演化强度：控制一次世界线推进会向多远的关系范围扩散影响。",
});

export function formatAgentKind(value) {
  return AGENT_KIND_TEXT[value] || "未知类型";
}

export function formatAgentStatus(value) {
  return AGENT_STATUS_TEXT[value] || "状态未知";
}

export function formatBranchStatus(value) {
  return BRANCH_STATUS_TEXT[value] || "状态未知";
}

export function formatProjectStatus(value) {
  return PROJECT_STATUS_TEXT[value] || "状态未知";
}

export function formatTaskStageStatus(value) {
  return TASK_STAGE_STATUS_TEXT[value] || "待开始";
}

export function formatRelationChange(value) {
  return RELATION_CHANGE_TEXT[value] || "变化中";
}

export function formatImportanceTier(value) {
  if (!value) {
    return "-";
  }
  return IMPORTANCE_TIER_TEXT[value] || value;
}

export function formatOrganizationType(value) {
  if (!value) {
    return "-";
  }
  return ORGANIZATION_TYPE_TEXT[value] || value;
}

export function formatEntityType(value) {
  if (!value) {
    return "-";
  }
  return ENTITY_TYPE_TEXT[value] || ORGANIZATION_TYPE_TEXT[value] || value;
}

export function formatSessionScope(value) {
  if (!value) {
    return "未知会话";
  }
  return SESSION_SCOPE_TEXT[value] || value;
}

export function formatRoleText(value) {
  if (!value) {
    return "未设定";
  }
  if (value === "unknown") {
    return "未设定";
  }
  return (
    AGENT_KIND_TEXT[value] ||
    IMPORTANCE_TIER_TEXT[value] ||
    ORGANIZATION_TYPE_TEXT[value] ||
    value
  );
}

export function formatStageKey(value) {
  return STAGE_KEY_TEXT[value] || value || "未知阶段";
}

export function formatUploadPhase(value) {
  return UPLOAD_PHASE_TEXT[value] || "处理中";
}

export function buildStepLabel(step) {
  return `第 ${step ?? "-"} 步`;
}
