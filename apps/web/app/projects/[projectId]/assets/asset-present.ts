import {
  Archive,
  Ban,
  BookMarked,
  BookOpen,
  Boxes,
  Dna,
  Feather,
  FileCode2,
  FileText,
  Gem,
  Globe,
  Link2,
  ListTree,
  MapPin,
  NotebookText,
  PenLine,
  ScrollText,
  Sparkles,
  Swords,
  UserRound,
  Users,
  Waypoints,
  type LucideIcon,
} from "lucide-react";

/**
 * Domain presentation for the Asset Library: friendly Chinese labels + icons
 * for asset types, sources, and lifecycles. The editorial system gives each
 * lifecycle one honest treatment — vermilion for canon, old gold for candidate
 * (the only place gold appears, per the paper-ink-vermilion contract).
 */

export type TypePresentation = { label: string; icon: LucideIcon };

const TYPE_PRESENTATION: Record<string, TypePresentation> = {
  character: { label: "角色", icon: Users },
  relationship: { label: "关系", icon: Link2 },
  world_rule: { label: "世界规则", icon: ScrollText },
  plot_thread: { label: "剧情线", icon: Waypoints },
  foreshadowing: { label: "伏笔", icon: Sparkles },
  scene: { label: "场景", icon: MapPin },
  location: { label: "地点", icon: MapPin },
  item: { label: "器物", icon: Gem },
  event: { label: "事件", icon: Swords },
  archive: { label: "档案", icon: BookOpen },
  chapter: { label: "章节", icon: FileText },
  // Types the seed / analysis / archive pipelines actually produce (no enum on
  // the backend column, so the list must label them rather than fall through).
  note: { label: "笔记", icon: NotebookText },
  story_ontology: { label: "故事本体", icon: Dna },
  archive_entity: { label: "档案实体", icon: Archive },
  writing_style: { label: "文风", icon: Feather },
  author_style: { label: "作者风格", icon: PenLine },
  character_archetype: { label: "角色原型", icon: UserRound },
  worldview: { label: "世界观", icon: Globe },
  plot_template: { label: "剧情模板", icon: ListTree },
  prompt_template: { label: "提示模板", icon: FileCode2 },
  manuscript_block: { label: "手稿块", icon: BookMarked },
  forbidden_lexicon: { label: "违禁词表", icon: Ban },
  terminology: { label: "术语", icon: BookOpen },
};

export function presentType(assetType: string): TypePresentation {
  return TYPE_PRESENTATION[assetType] ?? { label: assetType || "资产", icon: Boxes };
}

const SOURCE_LABELS: Record<string, string> = {
  seed: "Seed 分析",
  seed_analysis: "Seed 分析",
  seed_pipeline: "Seed 流水线",
  pi_analysis: "智能解析",
  narrative_archives: "叙事档案",
  manual: "手动创建",
  author: "作者",
  writer: "写作台",
  distillation: "手稿蒸馏",
  manuscript: "手稿蒸馏",
  manuscript_distillation: "手稿蒸馏",
  graph: "故事图谱",
  worldline: "世界线",
  character: "角色控制",
  import: "导入",
  legacy: "旧版导入",
};

export function presentSource(sourceKind: string): string {
  return SOURCE_LABELS[sourceKind] ?? sourceKind ?? "其他来源";
}

// The canonical lifecycle set, mirrored from the backend `assets.lifecycle`
// CHECK constraint. `enabled`/`disabled` is a separate boolean column, never a
// lifecycle, so it does not appear here.
export type Lifecycle =
  | "seed"
  | "candidate"
  | "canon"
  | "material"
  | "simulation"
  | "draft"
  | "manuscript"
  | "archived"
  | string;

export function isCandidate(lifecycle: string): boolean {
  return lifecycle === "candidate" || lifecycle === "draft";
}

/**
 * One honest status chip per lifecycle. Vermilion marks canon (the adopted,
 * authoritative state); old gold is reserved strictly for candidate/draft (the
 * only place gold appears). Every other lifecycle is a neutral paper chip — a
 * state, not a status that needs hue.
 */
export function lifecycleChip(lifecycle: string): { label: string; className: string } {
  switch (lifecycle) {
    case "canon":
      return {
        label: "正典",
        className: "border-accent/35 bg-accent-wash text-accent-strong",
      };
    case "candidate":
      return {
        label: "候选",
        className: "border-gold/50 bg-gold/10 text-[#8a6a33]",
      };
    case "draft":
      return {
        label: "草稿",
        className: "border-gold/40 bg-gold/5 text-[#8a6a33]",
      };
    case "seed":
      return { label: "种子", className: "border-line bg-paper-deep/60 text-muted" };
    case "material":
      return { label: "素材", className: "border-line bg-paper-deep/60 text-muted" };
    case "simulation":
      return { label: "模拟", className: "border-line bg-paper-deep/60 text-muted" };
    case "manuscript":
      return { label: "手稿", className: "border-line bg-paper-deep/60 text-muted" };
    case "archived":
      return {
        label: "已归档",
        className: "border-line bg-paper-deep/60 text-muted",
      };
    default:
      return {
        label: lifecycle || "未标注",
        className: "border-line bg-paper-deep/60 text-muted",
      };
  }
}

/** A short, readable timestamp for list/detail rows (zh-CN). */
export function formatAssetTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" });
}

export function formatAssetDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleString("zh-CN", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
