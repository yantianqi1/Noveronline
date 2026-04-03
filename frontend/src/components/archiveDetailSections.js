const EMPTY_TEXT = "暂无";
const PLACEHOLDER = "暂无记录";

const SECTION_LABELS = Object.freeze({
  identity: "身份信息",
  motivation: "动机驱力",
  tension: "内在张力",
  relationship: "关系网络",
  behavior: "行为模式",
  state: "当前状态",
  risk: "风险标记",
  private: "隐秘档案",
  summary: "摘要",
  agent_profile: "角色画像",
});

const FIELD_LABELS = Object.freeze({
  entity_name: "名称",
  entity_type: "类型",
  role: "叙事定位",
  identity_hint: "身份线索",
  organization_type: "组织类型",
  source: "来源",
  target: "目标",
  core_drive: "核心驱力",
  hidden_tension: "隐藏张力",
  summary: "关系概览",
  change: "关系变化",
  history: "关系历程",
  power_dynamic: "权力结构",
  trust_level: "信任程度",
  conflict_trigger: "冲突触发",
  stability_forecast: "稳定性预测",
  last_action: "最近行为",
  agent_behavior_hint: "行为倾向",
  personality: "性格特征",
  skills: "技能专长",
  loyalty: "忠诚归属",
  long_term_goal: "长期目标",
  short_term_goal: "短期目标",
  resources: "组织资源",
  internal_factions: "内部派系",
  public_stance: "公开立场",
  strategic_goal: "战略目标",
  conflict_targets: "冲突对象",
  status: "状态",
  surface_mask: "表面形象",
  can_act_as_agent: "可作为 Agent",
  notable_risks: "风险项",
  human_ai_relation_tag: "人机关系标记",
  secrets: "秘密",
  territorial_control: "势力范围",
});

const BOOLEAN_LABELS = Object.freeze({ true: "是", false: "否" });

const HIDDEN_FIELDS = new Set(["entity_name", "entity_type"]);

// ── Agent profile group config ──

const PROFILE_GROUP_CONFIG = [
  { key: "basic_info", label: "基本信息", defaultExpanded: true, fields: {
    name: "名称", aliases: "别名", identity: "身份", status: "状态",
  }},
  { key: "personality", label: "性格画像", defaultExpanded: true, fields: {
    core_traits: "核心特质", values: "价值观", fears: "恐惧与弱点", decision_pattern: "决策模式",
  }},
  { key: "motivation", label: "动机目标", defaultExpanded: true, fields: {
    ultimate_goal: "终极目标", current_objective: "当前目标", internal_conflict: "内心矛盾",
  }},
  { key: "speech", label: "语言风格", defaultExpanded: false, fields: {
    style: "表达风格", verbal_habits: "口头禅", tone_range: "语气特征", example_quotes: "经典语录",
  }},
  { key: "capabilities", label: "能力特长", defaultExpanded: false, fields: {
    skills: "技能", limitations: "局限性", resources: "掌握资源",
  }},
  { key: "knowledge_boundary", label: "知识边界", defaultExpanded: false, fields: {
    knows: "已知信息", does_not_know: "未知信息", believes_wrongly: "错误认知",
  }},
  { key: "relationships", label: "人际关系", defaultExpanded: false, fields: {} },
];

// ── Helpers ──

function buildTextSection(text) {
  return { variant: "text", text };
}

function normalizeScalar(value) {
  if (value === undefined || value === null) return "";
  if (typeof value === "boolean") return BOOLEAN_LABELS[String(value)] || String(value);
  return String(value).trim();
}

function isPlaceholder(value) {
  if (!value) return true;
  if (value === PLACEHOLDER) return true;
  if (Array.isArray(value) && value.length === 1 && value[0] === PLACEHOLDER) return true;
  return false;
}

function formatEntryValue(value) {
  if (Array.isArray(value)) return value.map(normalizeScalar).filter(Boolean).join("、");
  if (value && typeof value === "object") {
    return Object.entries(value)
      .map(([key, item]) => `${FIELD_LABELS[key] || key}: ${formatEntryValue(item)}`)
      .filter((item) => !item.endsWith(": "))
      .join("；");
  }
  return normalizeScalar(value);
}

function resolveLabel(key) {
  return FIELD_LABELS[key] || key;
}

function buildEntriesSection(payload) {
  const entries = Object.entries(payload)
    .filter(([key]) => !HIDDEN_FIELDS.has(key))
    .map(([key, value]) => ({ label: resolveLabel(key), value: formatEntryValue(value) }))
    .filter((item) => item.value);
  return entries.length ? { variant: "entries", entries } : buildTextSection(EMPTY_TEXT);
}

function buildItemsSection(items) {
  const normalizedItems = items.map(normalizeScalar).filter(Boolean);
  return normalizedItems.length
    ? { variant: "items", items: normalizedItems }
    : buildTextSection(EMPTY_TEXT);
}

function buildSectionPayload(value) {
  if (Array.isArray(value)) return buildItemsSection(value);
  if (value && typeof value === "object") return buildEntriesSection(value);
  return buildTextSection(normalizeScalar(value) || EMPTY_TEXT);
}

function buildSection(key, label, value) {
  return { key, label, ...buildSectionPayload(value) };
}

// ── Agent profile section builder ──

function formatProfileFieldValue(value) {
  if (Array.isArray(value)) return value.map(normalizeScalar).filter(Boolean);
  return normalizeScalar(value);
}

function buildProfileGroups(profileData) {
  const groups = [];
  for (const config of PROFILE_GROUP_CONFIG) {
    const groupData = profileData[config.key];
    if (!groupData) continue;

    // relationships is an array, handle specially
    if (config.key === "relationships") {
      if (!Array.isArray(groupData) || groupData.length === 0) continue;
      const items = groupData.map((rel) => {
        if (typeof rel === "string") return { label: "关系", value: rel };
        const target = rel.target || rel.name || "";
        const desc = rel.description || rel.relation || rel.type || "";
        return { label: target, value: desc };
      }).filter((item) => item.value);
      if (!items.length) continue;
      groups.push({
        key: `profile_${config.key}`,
        label: config.label,
        variant: "collapsible",
        defaultExpanded: config.defaultExpanded,
        items,
      });
      continue;
    }

    if (typeof groupData !== "object") continue;

    const items = [];
    for (const [fieldKey, fieldLabel] of Object.entries(config.fields)) {
      const rawValue = groupData[fieldKey];
      if (isPlaceholder(rawValue)) continue;
      const formatted = formatProfileFieldValue(rawValue);
      if (!formatted || (Array.isArray(formatted) && formatted.length === 0)) continue;
      items.push({ label: fieldLabel, value: formatted });
    }
    if (!items.length) continue;

    groups.push({
      key: `profile_${config.key}`,
      label: config.label,
      variant: "collapsible",
      defaultExpanded: config.defaultExpanded,
      items,
    });
  }
  return groups;
}

// ── Legacy fallback ──

function buildLegacySections(archive) {
  return [
    buildSection("entity_role", "故事定位", archive.entity_role || "暂无定位"),
    buildSection("core_drive", "核心动机", archive.core_drive || "暂无动机"),
    buildSection("surface_mask", "表层伪装", archive.surface_mask || "暂无表层描述"),
    buildSection("hidden_tension", "隐藏张力", archive.hidden_tension || "暂无隐藏张力"),
    buildSection("relationship_summary", "关系摘要", archive.relationship_summary || "暂无关系摘要"),
  ];
}

// ── Main export ──

export function buildArchiveDetailSections(archive) {
  if (!archive) return [];
  const templateSections = archive.template_sections || [];
  const templatePayload = archive.template_payload || {};
  if (!templateSections.length) return buildLegacySections(archive);

  const sections = [];
  for (const section of templateSections) {
    if (section === "agent_profile") {
      const profileData = templatePayload[section];
      if (profileData) {
        sections.push(...buildProfileGroups(profileData));
      }
      continue;
    }
    sections.push(
      buildSection(section, SECTION_LABELS[section] || section, templatePayload[section])
    );
  }
  return sections;
}
