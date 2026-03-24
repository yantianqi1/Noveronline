import { buildArchiveDetailSections } from "../../components/archiveDetailSections.js";

const SUMMARY_FIELD_MAP = Object.freeze({
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
});

const DETAIL_SECTION_PATHS = Object.freeze({
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
});

function normalizeText(value) {
  return value == null ? "" : String(value).trim();
}

function formatValue(value) {
  if (Array.isArray(value)) {
    return value.map(normalizeText).filter(Boolean).join("、");
  }
  return normalizeText(value);
}

function readSectionValue(templatePayload, path = []) {
  let current = templatePayload;
  for (const segment of path) {
    if (!current || typeof current !== "object") {
      return "";
    }
    current = current[segment];
  }
  return current;
}

function readAgentValue(agent, key) {
  const state = agent?.state || {};
  if (key in state) {
    return state[key];
  }
  const templatePayload = state.template_payload || {};
  return readSectionValue(templatePayload, DETAIL_SECTION_PATHS[key] || []);
}

function buildSummaryEntries(agent, limit = 3) {
  const fields = SUMMARY_FIELD_MAP[agent?.agent_kind] || [];
  const items = [];
  for (const field of fields) {
    const formatted = formatValue(readAgentValue(agent, field.key));
    if (!formatted) {
      continue;
    }
    items.push(`${field.label}：${formatted}`);
    if (items.length >= limit) {
      break;
    }
  }
  return items;
}

export function buildAgentCardHighlights(agent) {
  return buildSummaryEntries(agent, 3);
}

export function buildSelectedAgentSummaryLines(agent) {
  const lines = buildSummaryEntries(agent, 3);
  if (lines.length) {
    return lines;
  }
  const fallback = normalizeText(agent?.summary);
  return fallback ? [fallback] : [];
}

export function buildSelectedAgentDetailSections(agent) {
  if (!agent) {
    return [];
  }
  const state = agent.state || {};
  return buildArchiveDetailSections({
    entity_role: agent.role || state.role || "",
    core_drive: agent.drive || state.drive || "",
    surface_mask: state.surface_mask || "",
    hidden_tension: agent.tension || state.tension || "",
    relationship_summary: state.relationship_summary || agent.summary || "",
    template_sections: agent.template_sections || state.template_sections || [],
    template_payload: state.template_payload || agent.template_payload || {},
  });
}
