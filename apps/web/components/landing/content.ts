/**
 * Landing page copy — the single source of truth for the marketing home
 * ("墨·纸·印": ink hero → paper manifesto/capabilities → dark writer/worldline
 * immersion → paper pricing → vermilion-seal finale).
 *
 * Pure data only: no React, no runtime code. Icons travel as `lucide-react`
 * export names so each section imports (and tree-shakes) only the glyphs it
 * actually renders.
 */

/** A `lucide-react` export name referenced from the copy data below. */
export type LandingIconName =
  | "BookOpenText"
  | "Network"
  | "LibraryBig"
  | "Orbit"
  | "PenLine"
  | "ScrollText"
  | "BookUser"
  | "Boxes"
  | "SpellCheck"
  | "Cable"
  | "GitBranch"
  | "Mail";

export interface LandingLink {
  label: string;
  href: string;
}

export interface PipelineStage {
  title: string;
  description: string;
  icon: LandingIconName;
}

export interface CapabilityItem {
  title: string;
  description: string;
  icon: LandingIconName;
}

export interface WriterThreadEntry {
  /** Tool activity, e.g. "检索伏笔库". */
  action: string;
  /** Outcome fragment, e.g. "命中 3 条". */
  detail: string;
}

export interface PricingTier {
  name: string;
  price: string;
  /** Billing cadence suffix ("每月"); empty for the free tier. */
  period: string;
  features: string[];
  cta: LandingLink;
  /** Marks the recommended tier ("推荐" badge + raised treatment). */
  featured: boolean;
}

export interface FooterLink extends LandingLink {
  icon?: LandingIconName;
}

export interface FooterColumn {
  title: string;
  links: FooterLink[];
}

/**
 * Section anchor ids, in page order. The hero deliberately carries no id —
 * the page root owns `id="top"` and the wordmark links there.
 */
export const LANDING_SECTION_IDS = [
  "pipeline",
  "capabilities",
  "writer",
  "worldline",
  "pricing",
  "finale",
] as const;

export type LandingSectionId = (typeof LANDING_SECTION_IDS)[number];

export const landingContent = {
  nav: {
    brand: "MiroFish",
    brandSub: "长篇小说创作引擎",
    links: [
      { label: "主链", href: "#pipeline" },
      { label: "能力", href: "#capabilities" },
      { label: "写作台", href: "#writer" },
      { label: "推演", href: "#worldline" },
      { label: "方案", href: "#pricing" },
    ] satisfies LandingLink[],
    cta: { label: "进入工作台", href: "/workspace" } satisfies LandingLink,
  },

  hero: {
    eyebrow: "MIROFISH NOVEL · MULTI-AGENT WRITING ENGINE",
    /** Two display lines; `displayAccent` marks the substring in vermilion. */
    displayLines: ["为长篇小说", "造第二记忆"],
    displayAccent: "第二记忆",
    sub: "上传手稿与设定，MiroFish 读出角色、关系、伏笔与世界规则，在唯一的世界线里推演剧情，再陪你把每一章写成。",
    primaryCta: { label: "开始创作", href: "/workspace" } satisfies LandingLink,
    secondaryCta: { label: "看主链", href: "#pipeline" } satisfies LandingLink,
    stats: ["6 领域智能体", "百万字级故事记忆", "单世界推演引擎"],
    /** Default glyph pool for the HanziField canvas behind the hero. */
    canvasCharacters: "梦海墨舟夜航灯书忆",
  },

  manifesto: {
    eyebrow: "为什么需要它",
    display: "故事越大，记忆越脆弱。",
    /** Struck-through sticky-note asides beside the display line. */
    marginNotes: [
      "设定散落在九个文档里",
      "角色在三百章后忘了自己的誓言",
      "伏笔埋下，再没人想起",
    ],
    body: "MiroFish 不替你写作。它先读懂你的世界——每一个人物、每一条暗线、每一条规则——再把这份记忆交给会写作的 Agent。",
    marquee: ["角色", "组织", "关系", "事件", "伏笔", "世界规则", "叙事阶段", "手稿块", "自由素材"],
  },

  pipeline: {
    eyebrow: "主链 / THE PIPELINE",
    display: "从手稿到世界，一条链路。",
    stages: [
      {
        title: "上传·精读",
        description: "Seed Pipeline 分段精读 TXT / MD / PDF，顺序聚合全书结构。",
        icon: "BookOpenText",
      },
      {
        title: "生成图谱",
        description: "本体与角色档案写入统一故事图谱。",
        icon: "Network",
      },
      {
        title: "档案与资产",
        description: "角色、伏笔、世界规则成为可检索的活资产。",
        icon: "LibraryBig",
      },
      {
        title: "世界线推演",
        description: "在唯一的 current world 注入变量，预演剧情走向。",
        icon: "Orbit",
      },
      {
        title: "写作智能体",
        description: "Writer Agent 带着完整故事记忆流式成稿。",
        icon: "PenLine",
      },
      {
        title: "成稿·审校",
        description: "编译手稿，独立 Reviewer 逐章审校。",
        icon: "ScrollText",
      },
    ] satisfies PipelineStage[],
  },

  capabilities: {
    eyebrow: "能力",
    display: "一个记得住世界的系统。",
    items: [
      {
        title: "故事图谱",
        description: "角色、组织、关系、事件、伏笔、世界规则，统一存储、随时检索。",
        icon: "Network",
      },
      {
        title: "角色档案",
        description: "每个角色一份活的档案，随剧情推进持续更新。",
        icon: "BookUser",
      },
      {
        title: "资产库",
        description: "手稿块、自由素材与设定统一进入资产视图。",
        icon: "Boxes",
      },
      {
        title: "单世界推演",
        description: "不做多分支幻觉——在唯一世界线里注入变量、观察后果。",
        icon: "Orbit",
      },
      {
        title: "独立审校",
        description: "writer_reviewer 是独立 LLM 审校模块，不是规则打分。",
        icon: "SpellCheck",
      },
      {
        title: "LLM Facility",
        description: "渠道、模型、配额与隐私边界统一治理。",
        icon: "Cable",
      },
    ] satisfies CapabilityItem[],
  },

  writer: {
    eyebrow: "WRITER AGENT",
    display: "你写，它记得；它写，你定夺。",
    /** Tool-activity stream demo entries. */
    thread: [
      { action: "检索伏笔库", detail: "命中 3 条" },
      { action: "读取角色档案", detail: "沈知微" },
      { action: "生成候选正文", detail: "第 214 章" },
    ] satisfies WriterThreadEntry[],
    bullets: [
      "选区驱动调用，对话即指挥",
      "候选正文先审校、再落纸",
      "世界数据随正文同步更新",
    ],
  },

  worldline: {
    eyebrow: "WORLDLINE",
    display: "注入一个变量，预演整个故事。",
    sub: "如果她在那一夜离开？单世界推演引擎沿唯一时间线走出后果，角色按自己的档案做出反应。",
    variableExample: "VAR · 她错过了那班船",
  },

  pricing: {
    eyebrow: "方案",
    display: "从第一行字开始。",
    tiers: [
      {
        name: "体验",
        price: "¥0",
        period: "",
        features: ["1 个创作项目", "Seed 精读 20 万字", "社区模型配额"],
        cta: { label: "免费开始", href: "/workspace" },
        featured: false,
      },
      {
        name: "创作者",
        price: "¥68",
        period: "每月",
        features: ["不限项目", "全量图谱与档案", "Worldline 推演引擎", "优先任务队列"],
        cta: { label: "开始创作", href: "/workspace" },
        featured: true,
      },
      {
        name: "工作室",
        price: "¥268",
        period: "每月",
        features: ["5 个协作席位", "私有模型渠道", "用量与成本报表", "专属支持"],
        cta: { label: "联系我们", href: "#" },
        featured: false,
      },
    ] satisfies PricingTier[],
    footnote: "按量计费 · 随时取消 · 支持开票",
  },

  finale: {
    display: "现在，让世界记住你。",
    cta: { label: "进入工作台", href: "/workspace" } satisfies LandingLink,
  },

  footer: {
    columns: [
      {
        title: "产品",
        links: [
          { label: "主链", href: "#pipeline" },
          { label: "写作台", href: "#writer" },
          { label: "推演", href: "#worldline" },
          { label: "方案", href: "#pricing" },
        ],
      },
      {
        title: "资源",
        links: [
          { label: "文档", href: "#" },
          { label: "更新日志", href: "#" },
          { label: "开源协议", href: "#" },
        ],
      },
      {
        title: "联系",
        links: [
          // lucide-react v1 removed brand glyphs, so GitBranch stands in for
          // the Github link; keep the label as the accessible name.
          { label: "Github", href: "#", icon: "GitBranch" },
          { label: "Mail", href: "#", icon: "Mail" },
        ],
      },
    ] satisfies FooterColumn[],
    bottom: "© 2026 MiroFish Novel · 长篇小说创作引擎",
  },
};

export type LandingContent = typeof landingContent;
