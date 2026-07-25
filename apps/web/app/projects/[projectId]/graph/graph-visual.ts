import {
  BookOpen,
  Boxes,
  Building2,
  Flag,
  Gem,
  GitBranch,
  Landmark,
  MapPin,
  ScrollText,
  Users,
  Zap,
  type LucideIcon,
} from "lucide-react";

/**
 * Visual language for the Story Graph constellation — light "paper & ink"
 * edition.
 *
 * Every backend `node_type` maps to an accent colour, a soft tinted wash for
 * the card background, and an ink tone for its label, all tuned to sit on the
 * warm-paper canvas of the app theme. Characters read as vermilion seals,
 * concepts as quiet grey stamps; the "who" of the story stays warmest.
 */

export type NodeVisual = {
  /** Accent — icon, ring, seals. */
  color: string;
  /** Soft tinted wash behind the card. */
  soft: string;
  /** Quiet glow for focus. */
  halo: string;
  /** Ink text tone for the type label. */
  ink: string;
  label: string;
  icon: LucideIcon;
};

const DEFAULT_NODE: NodeVisual = {
  color: "#6b675c",
  soft: "rgba(107,103,92,0.06)",
  halo: "rgba(107,103,92,0.14)",
  ink: "#6b675c",
  label: "概念",
  icon: Boxes,
};

const NODE_VISUALS: Record<string, NodeVisual> = {
  character: {
    color: "#8f211b",
    soft: "rgba(143,33,27,0.07)",
    halo: "rgba(143,33,27,0.20)",
    ink: "#7a1a15",
    label: "角色",
    icon: Users,
  },
  organization: {
    color: "#9a6b23",
    soft: "rgba(181,133,74,0.10)",
    halo: "rgba(181,133,74,0.22)",
    ink: "#7d5a1f",
    label: "组织",
    icon: Building2,
  },
  faction: {
    color: "#a05a2c",
    soft: "rgba(160,90,44,0.10)",
    halo: "rgba(160,90,44,0.20)",
    ink: "#7d4520",
    label: "势力",
    icon: Flag,
  },
  location: {
    color: "#2f7a63",
    soft: "rgba(47,122,99,0.08)",
    halo: "rgba(47,122,99,0.18)",
    ink: "#266352",
    label: "地点",
    icon: MapPin,
  },
  artifact: {
    color: "#2f5d8a",
    soft: "rgba(47,93,138,0.08)",
    halo: "rgba(47,93,138,0.18)",
    ink: "#264c70",
    label: "信物",
    icon: Gem,
  },
  plot_event: {
    color: "#5d4e9e",
    soft: "rgba(93,78,158,0.08)",
    halo: "rgba(93,78,158,0.18)",
    ink: "#4c4082",
    label: "事件",
    icon: Zap,
  },
  plot_thread: {
    color: "#a03a6b",
    soft: "rgba(160,58,107,0.08)",
    halo: "rgba(160,58,107,0.18)",
    ink: "#823058",
    label: "剧情线",
    icon: GitBranch,
  },
  world_rule: {
    color: "#2f6f8a",
    soft: "rgba(47,111,138,0.08)",
    halo: "rgba(47,111,138,0.18)",
    ink: "#265a70",
    label: "世界规则",
    icon: ScrollText,
  },
  concept: {
    color: "#6b675c",
    soft: "rgba(107,103,92,0.06)",
    halo: "rgba(107,103,92,0.14)",
    ink: "#6b675c",
    label: "概念",
    icon: Boxes,
  },
  // Concept subtypes (frontend refinement of the flattened "concept" bucket).
  // Keys match graph-concept.ts layer keys; the rail + nodes resolve these
  // through layerVisual() so 分析·事件 and 世界观·设定 read as distinct layers.
  "concept:event": {
    color: "#5d4e9e",
    soft: "rgba(93,78,158,0.08)",
    halo: "rgba(93,78,158,0.18)",
    ink: "#4c4082",
    label: "分析·事件",
    icon: Zap,
  },
  "concept:world": {
    color: "#2f6f8a",
    soft: "rgba(47,111,138,0.08)",
    halo: "rgba(47,111,138,0.18)",
    ink: "#265a70",
    label: "世界观·设定",
    icon: ScrollText,
  },
  "concept:concept": {
    color: "#6b675c",
    soft: "rgba(107,103,92,0.06)",
    halo: "rgba(107,103,92,0.14)",
    ink: "#6b675c",
    label: "概念",
    icon: Boxes,
  },
  manuscript_scene: {
    color: "#8a5a52",
    soft: "rgba(138,90,82,0.08)",
    halo: "rgba(138,90,82,0.16)",
    ink: "#6f483f",
    label: "场景",
    icon: BookOpen,
  },
};

export function nodeVisual(nodeType: string): NodeVisual {
  return NODE_VISUALS[nodeType] ?? DEFAULT_NODE;
}

/**
 * Visual for a filter-rail layer key. Concept layer keys ("concept:event" …)
 * have their own entry; anything else falls back to the node_type visual.
 */
export function layerVisual(layerKey: string): NodeVisual {
  return NODE_VISUALS[layerKey] ?? nodeVisual(layerKey);
}

export function nodeTypeLabel(nodeType: string): string {
  return (NODE_VISUALS[nodeType] ?? DEFAULT_NODE).label;
}

/** Ordered list of the node types the layer rail offers (most story-first). */
export const KNOWN_NODE_TYPES: string[] = [
  "character",
  "organization",
  "faction",
  "location",
  "artifact",
  "plot_thread",
  "plot_event",
  "world_rule",
  "concept",
  "manuscript_scene",
];

// ── Edges ────────────────────────────────────────────────────────────────────

export type EdgeVisual = {
  label: string;
  tint: "warm" | "cool" | "neutral";
};

const DEFAULT_EDGE: EdgeVisual = { label: "关联", tint: "neutral" };

const EDGE_VISUALS: Record<string, EdgeVisual> = {
  relationship: { label: "关系", tint: "warm" },
  participates_in: { label: "参与", tint: "cool" },
  belongs_to: { label: "隶属", tint: "cool" },
  opposes: { label: "对立", tint: "warm" },
  constrained_by: { label: "受制", tint: "cool" },
  causes: { label: "引发", tint: "cool" },
  reveals: { label: "揭示", tint: "cool" },
  foreshadows: { label: "伏笔", tint: "warm" },
  located_in: { label: "所在", tint: "neutral" },
  mentions: { label: "提及", tint: "neutral" },
};

export function edgeVisual(edgeType: string): EdgeVisual {
  return EDGE_VISUALS[edgeType] ?? DEFAULT_EDGE;
}

export function edgeTypeLabel(edgeType: string): string {
  return (EDGE_VISUALS[edgeType] ?? DEFAULT_EDGE).label;
}

/** Lifecycle → Chinese label (canon reads as established, candidate as pending). */
export function lifecycleLabel(lifecycle: string): string {
  switch (lifecycle) {
    case "canon":
      return "正典";
    case "candidate":
      return "候选";
    case "seed":
      return "种子";
    case "simulation":
      return "推演";
    case "manuscript":
      return "稿件";
    case "archived":
      return "归档";
    default:
      return lifecycle || "—";
  }
}

/** Extra icons re-exported so the rails stay lean. */
export { Landmark };
