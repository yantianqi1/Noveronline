const TIER_LABELS = Object.freeze({
  protagonist: "主角",
  major: "重要",
  supporting: "配角",
  minor: "次要",
});

const SECTION_LABELS = Object.freeze({
  identity: "身份",
  motivation: "动机",
  tension: "张力",
  relationship: "关系",
  behavior: "行为",
  state: "状态",
  risk: "风险",
  private: "隐秘",
  summary: "摘要",
});

const KIND_LABELS = Object.freeze({
  character: "角色",
  organization: "组织",
  relationship: "关系",
  generic: "其他对象",
});

function normalizeLabelKey(value) {
  return String(value || "").trim().toLowerCase();
}

export const sectionKeysByTier = Object.freeze({
  protagonist: ["identity", "motivation", "tension", "relationship", "behavior", "state", "risk", "private"],
  major: ["identity", "motivation", "tension", "relationship", "behavior", "state", "risk"],
  supporting: ["identity", "motivation", "tension", "relationship", "state"],
  minor: ["identity", "state", "summary"],
});

export const tierSelectOptions = Object.freeze(
  Object.keys(TIER_LABELS).map((value) => ({ value, label: TIER_LABELS[value] })),
);

export function formatArchiveTierLabel(tier) {
  const normalized = normalizeLabelKey(tier);
  return TIER_LABELS[normalized] || String(tier || "");
}

export function formatArchiveSectionLabel(section) {
  const normalized = normalizeLabelKey(section);
  return SECTION_LABELS[normalized] || String(section || "");
}

export function formatArchiveKindLabel(kind) {
  const normalized = normalizeLabelKey(kind);
  return KIND_LABELS[normalized] || String(kind || "");
}
