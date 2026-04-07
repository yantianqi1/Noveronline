// Stage key → 中文文案 / 图标 / 简短描述
// 后端只发 stage key + 业务数据；前端在这里翻译，方便后续 i18n 与文案迭代。

export const BUILD_STAGE_ORDER = [
  "load_artifacts",
  "collect_entities",
  "merge_nodes",
  "build_relationships",
  "build_events",
  "build_artifacts_rules",
  "persist",
  "finalize",
];

export const BUILD_STAGE_META = {
  load_artifacts: {
    icon: "📂",
    title: "读取阅读笔记",
    description: "加载分块事实、章节连续性、故事记忆等产物",
  },
  collect_entities: {
    icon: "🔍",
    title: "收集候选实体",
    description: "从实体注册表、事件时间线、世界规则中扫出候选",
  },
  merge_nodes: {
    icon: "🪢",
    title: "合并同名节点",
    description: "按规范化名称去重、合并别名与证据",
  },
  build_relationships: {
    icon: "💞",
    title: "抽取角色关系",
    description: "从关系账本生成角色之间的边",
  },
  build_events: {
    icon: "⚡",
    title: "串联事件线",
    description: "把事件参与者、地点串联成边",
  },
  build_artifacts_rules: {
    icon: "📜",
    title: "关联器物与世界规则",
    description: "法器、知识、规则与角色/组织的归属边",
  },
  persist: {
    icon: "💾",
    title: "落盘",
    description: "写入 JSON 快照与 SQLite 索引",
  },
  finalize: {
    icon: "✨",
    title: "汇总图谱信息",
    description: "统计实体类型，生成图谱概要",
  },
  failed: {
    icon: "⚠",
    title: "构建失败",
    description: "发生异常，已回滚项目状态",
  },
};

export function describeStage(stageKey) {
  return BUILD_STAGE_META[stageKey] || {
    icon: "•",
    title: stageKey || "未知阶段",
    description: "",
  };
}

const COUNT_LABELS = {
  artifacts_loaded: "产物",
  block_count: "分块",
  entities: "实体",
  candidates: "候选",
  nodes: "节点",
  merged_aliases: "合并别名",
  edges: "边",
  relationships: "关系",
  events: "事件",
  artifacts: "器物边",
  rules: "规则边",
  entity_types: "实体类型",
};

export function formatCounts(counts = {}) {
  const parts = [];
  for (const [key, value] of Object.entries(counts)) {
    if (value === null || value === undefined) continue;
    const label = COUNT_LABELS[key] || key;
    parts.push(`${label} ${value}`);
  }
  return parts.join(" · ");
}

export function formatElapsed(ms = 0) {
  const seconds = Math.floor((ms || 0) / 1000);
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}:${String(s).padStart(2, "0")}` : `${s}s`;
}
