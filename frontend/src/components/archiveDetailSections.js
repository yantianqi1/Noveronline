const EMPTY_TEXT = "暂无";

const SECTION_LABELS = Object.freeze({
  identity: "身份信息",
  motivation: "动机段",
  tension: "张力段",
  relationship: "关系段",
  behavior: "行动倾向",
  state: "当前状态",
  risk: "风险段",
  private: "隐秘信息",
  summary: "摘要",
});

function buildTextSection(text) {
  return { variant: "text", text };
}

function normalizeScalar(value) {
  if (value === undefined || value === null) {
    return "";
  }
  return String(value).trim();
}

function formatEntryValue(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeScalar).filter(Boolean).join("、");
  }
  if (value && typeof value === "object") {
    return Object.entries(value)
      .map(([key, item]) => `${key}: ${formatEntryValue(item)}`)
      .filter((item) => item !== ": ")
      .join("；");
  }
  return normalizeScalar(value);
}

function buildEntriesSection(payload) {
  const entries = Object.entries(payload)
    .map(([label, value]) => ({ label, value: formatEntryValue(value) }))
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
  if (Array.isArray(value)) {
    return buildItemsSection(value);
  }
  if (value && typeof value === "object") {
    return buildEntriesSection(value);
  }
  return buildTextSection(normalizeScalar(value) || EMPTY_TEXT);
}

function buildSection(key, label, value) {
  return {
    key,
    label,
    ...buildSectionPayload(value),
  };
}

function buildLegacySections(archive) {
  return [
    buildSection("entity_role", "故事定位", archive.entity_role || "暂无定位"),
    buildSection("core_drive", "核心动机", archive.core_drive || "暂无动机"),
    buildSection("surface_mask", "表层伪装", archive.surface_mask || "暂无表层描述"),
    buildSection("hidden_tension", "隐藏张力", archive.hidden_tension || "暂无隐藏张力"),
    buildSection("relationship_summary", "关系摘要", archive.relationship_summary || "暂无关系摘要"),
  ];
}

export function buildArchiveDetailSections(archive) {
  if (!archive) {
    return [];
  }
  const templateSections = archive.template_sections || [];
  const templatePayload = archive.template_payload || {};
  if (templateSections.length) {
    return templateSections.map((section) => (
      buildSection(section, SECTION_LABELS[section] || section, templatePayload[section])
    ));
  }
  return buildLegacySections(archive);
}
