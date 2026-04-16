/**
 * Graph build stage metadata — Chinese labels, icons, formatting helpers.
 * Ported from src-vue/views/story-graph/buildStageMeta.js.
 */

export const BUILD_STAGE_ORDER = [
  "load_artifacts",
  "collect_entities",
  "merge_nodes",
  "build_relationships",
  "build_events",
  "build_artifacts_rules",
  "persist",
  "finalize",
] as const;

export type BuildStageKey = (typeof BUILD_STAGE_ORDER)[number] | "failed";

export interface StageMeta {
  icon: string;
  title: string;
  description: string;
}

export const BUILD_STAGE_META: Record<string, StageMeta> = {
  load_artifacts: {
    icon: "\uD83D\uDCC2",
    title: "\u8BFB\u53D6\u9605\u8BFB\u7B14\u8BB0",
    description: "\u8BFB\u53D6\u7AE0\u8282\u4E8B\u5B9E\u3001\u4E8B\u4EF6\u7EBF\u7D22\u4E0E\u5DF2\u6709\u6545\u4E8B\u8BB0\u5FC6",
  },
  collect_entities: {
    icon: "\uD83D\uDD0D",
    title: "\u6536\u96C6\u5019\u9009\u5B9E\u4F53",
    description: "\u4ECE\u5B9E\u4F53\u6CE8\u518C\u8868\u3001\u4E8B\u4EF6\u65F6\u95F4\u7EBF\u3001\u4E16\u754C\u89C4\u5219\u4E2D\u626B\u51FA\u5019\u9009",
  },
  merge_nodes: {
    icon: "\uD83E\uDEA2",
    title: "\u5408\u5E76\u540C\u540D\u8282\u70B9",
    description: "\u6309\u89C4\u8303\u5316\u540D\u79F0\u53BB\u91CD\u3001\u5408\u5E76\u522B\u540D\u4E0E\u8BC1\u636E",
  },
  build_relationships: {
    icon: "\uD83D\uDC9E",
    title: "\u62BD\u53D6\u89D2\u8272\u5173\u7CFB",
    description: "\u6574\u7406\u89D2\u8272\u4E4B\u95F4\u7684\u5173\u7CFB\u3001\u7ACB\u573A\u548C\u51B2\u7A81",
  },
  build_events: {
    icon: "\u26A1",
    title: "\u4E32\u8054\u4E8B\u4EF6\u7EBF",
    description: "\u628A\u4E8B\u4EF6\u3001\u53C2\u4E0E\u8005\u548C\u573A\u666F\u8FDE\u6210\u53EF\u9605\u8BFB\u7684\u6545\u4E8B\u8109\u7EDC",
  },
  build_artifacts_rules: {
    icon: "\uD83D\uDCDC",
    title: "\u5173\u8054\u5668\u7269\u4E0E\u4E16\u754C\u89C4\u5219",
    description: "\u6CD5\u5668\u3001\u77E5\u8BC6\u3001\u89C4\u5219\u4E0E\u89D2\u8272/\u7EC4\u7EC7\u7684\u5F52\u5C5E\u8FB9",
  },
  persist: {
    icon: "\uD83D\uDCBE",
    title: "\u4FDD\u5B58\u56FE\u8C31",
    description: "\u4FDD\u5B58\u672C\u6B21\u8BC6\u522B\u5230\u7684\u5B9E\u4F53\u3001\u5173\u7CFB\u548C\u4E8B\u4EF6",
  },
  finalize: {
    icon: "\u2728",
    title: "\u6C47\u603B\u56FE\u8C31\u4FE1\u606F",
    description: "\u7EDF\u8BA1\u5B9E\u4F53\u7C7B\u578B\uFF0C\u751F\u6210\u56FE\u8C31\u6982\u8981",
  },
  failed: {
    icon: "\u26A0",
    title: "\u6784\u5EFA\u5931\u8D25",
    description: "\u53D1\u751F\u5F02\u5E38\uFF0C\u5DF2\u56DE\u6EDA\u9879\u76EE\u72B6\u6001",
  },
};

export function describeStage(stageKey: string): StageMeta {
  return (
    BUILD_STAGE_META[stageKey] || {
      icon: "\u2022",
      title: stageKey || "\u672A\u77E5\u9636\u6BB5",
      description: "",
    }
  );
}

const COUNT_LABELS: Record<string, string> = {
  artifacts_loaded: "\u8D44\u6599",
  block_count: "\u5206\u5757",
  entities: "\u5B9E\u4F53",
  candidates: "\u5019\u9009",
  nodes: "\u8282\u70B9",
  merged_aliases: "\u5408\u5E76\u522B\u540D",
  edges: "\u5173\u8054",
  relationships: "\u5173\u7CFB",
  events: "\u4E8B\u4EF6",
  artifacts: "\u5668\u7269\u7EBF\u7D22",
  rules: "\u89C4\u5219\u7EBF\u7D22",
  entity_types: "\u5B9E\u4F53\u7C7B\u578B",
};

export function formatCounts(counts: Record<string, unknown> = {}): string {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(counts)) {
    if (value === null || value === undefined) continue;
    const label = COUNT_LABELS[key];
    if (!label || typeof value === "object") continue;
    parts.push(`${label} ${value}`);
  }
  return parts.join(" \u00B7 ");
}

export function formatElapsed(ms = 0): string {
  const seconds = Math.floor((ms || 0) / 1000);
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}:${String(s).padStart(2, "0")}` : `${s}s`;
}
