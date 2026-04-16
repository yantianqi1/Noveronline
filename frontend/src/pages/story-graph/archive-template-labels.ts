/**
 * Archive template tier / section / kind labels.
 * Ported from src-vue/views/story-graph/archiveTemplateLabels.js.
 */

const TIER_LABELS: Record<string, string> = {
  protagonist: "\u4E3B\u89D2",
  major: "\u91CD\u8981",
  supporting: "\u914D\u89D2",
  minor: "\u6B21\u8981",
};

const SECTION_LABELS: Record<string, string> = {
  identity: "\u8EAB\u4EFD",
  motivation: "\u52A8\u673A",
  tension: "\u5F20\u529B",
  relationship: "\u5173\u7CFB",
  behavior: "\u884C\u4E3A",
  state: "\u72B6\u6001",
  risk: "\u98CE\u9669",
  private: "\u9690\u79D8",
  summary: "\u6458\u8981",
};

const KIND_LABELS: Record<string, string> = {
  character: "\u89D2\u8272",
  organization: "\u7EC4\u7EC7",
  relationship: "\u5173\u7CFB",
  generic: "\u5176\u4ED6\u5BF9\u8C61",
};

function normalizeLabelKey(value: string): string {
  return String(value || "").trim().toLowerCase();
}

export const sectionKeysByTier: Record<string, string[]> = {
  protagonist: ["identity", "motivation", "tension", "relationship", "behavior", "state", "risk", "private"],
  major: ["identity", "motivation", "tension", "relationship", "behavior", "state", "risk"],
  supporting: ["identity", "motivation", "tension", "relationship", "state"],
  minor: ["identity", "state", "summary"],
};

export const tierSelectOptions = Object.keys(TIER_LABELS).map((value) => ({
  value,
  label: TIER_LABELS[value]!,
}));

export function formatArchiveTierLabel(tier: string): string {
  const normalized = normalizeLabelKey(tier);
  return TIER_LABELS[normalized] || String(tier || "");
}

export function formatArchiveSectionLabel(section: string): string {
  const normalized = normalizeLabelKey(section);
  return SECTION_LABELS[normalized] || String(section || "");
}

export function formatArchiveKindLabel(kind: string): string {
  const normalized = normalizeLabelKey(kind);
  return KIND_LABELS[normalized] || String(kind || "");
}
