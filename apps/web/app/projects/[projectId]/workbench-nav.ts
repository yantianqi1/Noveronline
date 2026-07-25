import {
  Boxes,
  Feather,
  LayoutDashboard,
  Network,
  Settings,
  Users,
  Waypoints,
  type LucideIcon,
} from "lucide-react";

/**
 * The project workspace's fixed primary navigation.
 *
 * This set is mandated by docs/refactor-saas/37-frontend-module-inventory.md:
 * every project exposes exactly these seven workbench entries, in this order.
 * "总览" folds import+analysis into the overview surface (no separate nav item).
 */

export type WorkbenchSection = {
  slug: string;
  label: string;
  icon: LucideIcon;
  /** One-line description used on the section's landing surface. */
  tagline: string;
};

export const WORKBENCH_SECTIONS: WorkbenchSection[] = [
  {
    slug: "overview",
    label: "总览",
    icon: LayoutDashboard,
    tagline: "项目阶段、就绪度与原文导入分析，都在这里完成。",
  },
  {
    slug: "graph",
    label: "故事图谱",
    icon: Network,
    tagline: "故事世界地图：构建、浏览、筛选与候选采用。",
  },
  {
    slug: "assets",
    label: "资产库",
    icon: Boxes,
    tagline: "角色、设定、关系、伏笔、规则与档案的统一入口。",
  },
  {
    slug: "worldline",
    label: "世界线",
    icon: Waypoints,
    tagline: "单世界剧情推演：启动、变量注入与事件流。",
  },
  {
    slug: "characters",
    label: "角色控制",
    icon: Users,
    tagline: "以第一人称进入角色，在当前世界节点互动写作。",
  },
  {
    slug: "writer",
    label: "写作台",
    icon: Feather,
    tagline: "主写作界面：连续稿件画布与常驻 Writer 协作。",
  },
  {
    slug: "settings",
    label: "设置",
    icon: Settings,
    tagline: "项目配置、LLM 模块绑定、成员与用量。",
  },
];

export const DEFAULT_SECTION = "overview";

export function isValidSection(slug: string): boolean {
  return WORKBENCH_SECTIONS.some((section) => section.slug === slug);
}

export function sectionBySlug(slug: string): WorkbenchSection | undefined {
  return WORKBENCH_SECTIONS.find((section) => section.slug === slug);
}
