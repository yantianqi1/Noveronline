/**
 * Agent detail presentation helpers.
 * Ported from src-vue/views/character-console/agentDetailPresentation.js.
 */

/* ------------------------------------------------------------------ */
/*  Constants                                                          */
/* ------------------------------------------------------------------ */

const SUMMARY_FIELD_MAP: Record<string, Array<{ key: string; label: string }>> = {
  character: [
    { key: "personality", label: "性格" },
    { key: "loyalty", label: "忠诚" },
    { key: "short_term_goal", label: "短期目标" },
    { key: "skills", label: "关键能力" },
  ],
  organization: [
    { key: "public_stance", label: "公开立场" },
    { key: "strategic_goal", label: "战略目标" },
    { key: "resources", label: "核心资源" },
  ],
  relationship: [
    { key: "power_dynamic", label: "权力动态" },
    { key: "trust_level", label: "信任程度" },
    { key: "stability_forecast", label: "稳定预期" },
  ],
};

const DETAIL_SECTION_PATHS: Record<string, string[]> = {
  identity_hint: ["identity", "identity_hint"],
  organization_type: ["identity", "organization_type"],
  personality: ["behavior", "personality"],
  skills: ["behavior", "skills"],
  loyalty: ["behavior", "loyalty"],
  long_term_goal: ["behavior", "long_term_goal"],
  short_term_goal: ["behavior", "short_term_goal"],
  resources: ["behavior", "resources"],
  internal_factions: ["behavior", "internal_factions"],
  public_stance: ["behavior", "public_stance"],
  strategic_goal: ["behavior", "strategic_goal"],
  conflict_targets: ["behavior", "conflict_targets"],
  territorial_control: ["private", "territorial_control"],
  secrets: ["private", "secrets"],
  power_dynamic: ["relationship", "power_dynamic"],
  trust_level: ["relationship", "trust_level"],
  conflict_trigger: ["relationship", "conflict_trigger"],
  stability_forecast: ["relationship", "stability_forecast"],
  history: ["relationship", "history"],
  last_action: ["relationship", "last_action"],
};

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface AgentData {
  agent_id?: string;
  agent_kind?: string;
  display_name?: string;
  summary?: string;
  role?: string;
  drive?: string;
  tension?: string;
  status?: string;
  state_version?: number;
  state_source?: string;
  template_sections?: string[];
  template_payload?: Record<string, unknown>;
  state?: Record<string, unknown>;
  last_action_at?: string;
  last_dialogue_at?: string;
  [key: string]: unknown;
}

export interface DetailSection {
  key: string;
  label: string;
  variant: "text" | "entries" | "items";
  text?: string;
  entries?: Array<{ label: string; value: string }>;
  items?: string[];
}

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

function normalizeText(value: unknown): string {
  return value == null ? "" : String(value).trim();
}

function formatValue(value: unknown): string {
  if (Array.isArray(value)) {
    return value.map(normalizeText).filter(Boolean).join("、");
  }
  return normalizeText(value);
}

function readSectionValue(templatePayload: Record<string, unknown>, path: string[] = []): unknown {
  let current: unknown = templatePayload;
  for (const segment of path) {
    if (!current || typeof current !== "object") return "";
    current = (current as Record<string, unknown>)[segment];
  }
  return current;
}

function readAgentValue(agent: AgentData, key: string): unknown {
  const state = agent.state || {};
  if (key in state) return state[key];
  const templatePayload = (state.template_payload as Record<string, unknown>) || {};
  return readSectionValue(templatePayload, DETAIL_SECTION_PATHS[key] || []);
}

function buildSummaryEntries(agent: AgentData | null, limit = 3): string[] {
  if (!agent) return [];
  const fields = SUMMARY_FIELD_MAP[agent.agent_kind || ""] || [];
  const items: string[] = [];
  for (const field of fields) {
    const formatted = formatValue(readAgentValue(agent, field.key));
    if (!formatted) continue;
    items.push(`${field.label}：${formatted}`);
    if (items.length >= limit) break;
  }
  return items;
}

/* ------------------------------------------------------------------ */
/*  Section labels (for template sections)                             */
/* ------------------------------------------------------------------ */

const SECTION_LABELS: Record<string, string> = {
  identity: "身份信息",
  motivation: "动机驱力",
  tension: "内在张力",
  relationship: "关系网络",
  behavior: "行为模式",
  state: "当前状态",
  risk: "风险标记",
  private: "隐秘档案",
  summary: "摘要",
};

const FIELD_LABELS: Record<string, string> = {
  entity_name: "名称",
  entity_type: "类型",
  role: "叙事定位",
  identity_hint: "身份线索",
  core_drive: "核心驱力",
  hidden_tension: "隐藏张力",
  summary: "关系概览",
  personality: "性格特征",
  skills: "技能专长",
  status: "状态",
  surface_mask: "表面形象",
};

const HIDDEN_FIELDS = new Set(["entity_name", "entity_type"]);

/* ------------------------------------------------------------------ */
/*  Public API                                                         */
/* ------------------------------------------------------------------ */

export function buildAgentCardHighlights(agent: AgentData | null): string[] {
  return buildSummaryEntries(agent, 3);
}

export function buildSelectedAgentSummaryLines(agent: AgentData | null): string[] {
  const lines = buildSummaryEntries(agent, 3);
  if (lines.length) return lines;
  const fallback = normalizeText(agent?.summary);
  return fallback ? [fallback] : [];
}

export function buildSelectedAgentDetailSections(agent: AgentData | null): DetailSection[] {
  if (!agent) return [];
  const state = agent.state || {};
  const templateSections = (agent.template_sections || (state.template_sections as string[]) || []);
  const templatePayload = ((state.template_payload as Record<string, unknown>) || agent.template_payload || {});

  // Legacy fallback when no template sections
  if (!templateSections.length) {
    const result: DetailSection[] = [];
    const fallbacks = [
      { key: "entity_role", src: agent.role || (state.role as string) || "" },
      { key: "core_drive", src: agent.drive || (state.drive as string) || "" },
      { key: "surface_mask", src: (state.surface_mask as string) || "" },
      { key: "hidden_tension", src: agent.tension || (state.tension as string) || "" },
      { key: "relationship_summary", src: (state.relationship_summary as string) || agent.summary || "" },
    ];
    const labels: Record<string, string> = {
      entity_role: "故事定位",
      core_drive: "核心动机",
      surface_mask: "表层伪装",
      hidden_tension: "隐藏张力",
      relationship_summary: "关系摘要",
    };
    for (const f of fallbacks) {
      if (f.src) result.push({ key: f.key, label: labels[f.key] || f.key, variant: "text", text: f.src });
    }
    return result;
  }

  const sections: DetailSection[] = [];
  for (const section of templateSections) {
    const value = templatePayload[section];
    const label = SECTION_LABELS[section] || section;
    if (typeof value === "string") {
      sections.push({ key: section, label, variant: "text", text: value || "暂无" });
    } else if (Array.isArray(value)) {
      const items = value.map(normalizeText).filter(Boolean);
      if (items.length) sections.push({ key: section, label, variant: "items", items });
    } else if (value && typeof value === "object") {
      const entries = Object.entries(value as Record<string, unknown>)
        .filter(([k]) => !HIDDEN_FIELDS.has(k))
        .map(([k, v]) => ({ label: FIELD_LABELS[k] || k, value: formatValue(v) }))
        .filter((e) => e.value);
      if (entries.length) sections.push({ key: section, label, variant: "entries", entries });
    }
  }
  return sections;
}
