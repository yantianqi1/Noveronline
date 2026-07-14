/**
 * Shared analysis-candidate → asset mapping (mirrors Go mapAnalysisCandidateToAsset).
 * Keep in sync with apps/api/internal/workflows/analysis_asset_import.go.
 */

const TYPE_KEY_TITLES = new Set([
  "character",
  "relationship",
  "world_rule",
  "plot_thread",
  "ontology",
  "note_summary",
  "note",
  "story_ontology",
]);

export function normalizeAnalysisCandidateType(value: string): string {
  const normalized = String(value ?? "").trim().toLowerCase();
  switch (normalized) {
    case "character":
    case "relationship":
    case "world_rule":
    case "plot_thread":
    case "ontology":
    case "note_summary":
      return normalized;
    default:
      return "note_summary";
  }
}

export function isTypeKeyTitle(value: string): boolean {
  return TYPE_KEY_TITLES.has(String(value ?? "").trim().toLowerCase());
}

export function firstString(payload: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

function truncateText(value: string, max: number): string {
  const trimmed = value.trim();
  if (max <= 0 || trimmed.length <= max) {
    return trimmed;
  }
  return `${trimmed.slice(0, max)}…`;
}

export function composeRelationshipTitle(payload: Record<string, unknown>): string {
  const source = firstString(payload, [
    "source", "source_name", "source_entity", "source_entity_name",
    "from", "from_name", "a", "character_a", "left", "subject",
  ]);
  const target = firstString(payload, [
    "target", "target_name", "target_entity", "target_entity_name",
    "to", "to_name", "b", "character_b", "right", "object",
  ]);
  const relType = firstString(payload, [
    "relationship_type", "relation_type", "type", "kind", "relation", "bond_type",
  ]);
  if (!source && !target) {
    return "";
  }
  const left = source || "?";
  const right = target || "?";
  return relType ? `${left} → ${right} / ${relType}` : `${left} → ${right}`;
}

export function composeAnalysisAssetTitle(
  candidateType: string,
  name: string,
  payload: Record<string, unknown>,
): string {
  const type = normalizeAnalysisCandidateType(candidateType);
  const explicit = String(name ?? "").trim();
  if (explicit && !isTypeKeyTitle(explicit)) {
    return explicit.slice(0, 240);
  }
  const fromPayload = firstString(payload, ["name", "title", "canonical_name", "label"]);
  if (fromPayload && !isTypeKeyTitle(fromPayload)) {
    return fromPayload.slice(0, 240);
  }

  switch (type) {
    case "relationship": {
      const composed = composeRelationshipTitle(payload);
      if (composed) return composed.slice(0, 240);
      break;
    }
    case "character": {
      const charName = firstString(payload, ["character_name", "full_name"]);
      if (charName) return charName.slice(0, 240);
      break;
    }
    case "world_rule": {
      const rule = firstString(payload, ["rule_text", "rule", "statement"]);
      if (rule) return truncateText(rule, 80);
      break;
    }
    case "plot_thread": {
      const thread = firstString(payload, ["thread_title", "hook"]);
      if (thread) return thread.slice(0, 240);
      break;
    }
    case "note_summary": {
      const note = firstString(payload, ["summary", "description", "content", "text", "body", "excerpt"]);
      if (note) return truncateText(note, 80);
      break;
    }
    case "ontology": {
      const onto = firstString(payload, ["summary", "description"]);
      if (onto) return truncateText(onto, 80);
      break;
    }
  }

  return (explicit || type).slice(0, 240);
}

export function composeAnalysisAssetContent(
  candidateType: string,
  title: string,
  summary: string,
  payload: Record<string, unknown>,
): string {
  const type = normalizeAnalysisCandidateType(candidateType);
  const content = firstString(payload, ["content", "text", "body", "content_text", "note", "excerpt"]);
  if (content) {
    return content.slice(0, 20_000);
  }
  if (type === "relationship") {
    const source = firstString(payload, [
      "source", "source_name", "source_entity", "source_entity_name", "from", "from_name", "a", "character_a",
    ]);
    const target = firstString(payload, [
      "target", "target_name", "target_entity", "target_entity_name", "to", "to_name", "b", "character_b",
    ]);
    const relType = firstString(payload, [
      "relationship_type", "relation_type", "type", "kind", "relation", "bond_type",
    ]);
    const desc = firstString(payload, ["summary", "description", "blurb"]);
    const parts: string[] = [];
    if (source || target) {
      let line = `${source} → ${target}`.trim();
      if (relType) line += `（${relType}）`;
      parts.push(line);
    }
    if (desc) parts.push(desc);
    if (parts.length > 0) {
      return parts.join("\n").slice(0, 20_000);
    }
  }
  const desc = firstString(payload, ["summary", "description", "blurb", "rule_text"]);
  if (desc) return desc.slice(0, 20_000);
  if (summary) return summary.slice(0, 20_000);
  return title.slice(0, 20_000);
}

export function mapAnalysisCandidateToAsset(
  candidateType: string,
  name: string,
  payload: Record<string, unknown>,
  workspacePath?: string,
): {
  asset_type: string;
  category: string;
  title: string;
  summary: string;
  content_text: string;
  payload: Record<string, unknown>;
  tags: string[];
} {
  const type = normalizeAnalysisCandidateType(candidateType);
  const assetType = type === "note_summary"
    ? "note"
    : type === "ontology"
      ? "story_ontology"
      : type;
  const category = type === "character"
    ? "characters"
    : type === "relationship"
      ? "relationships"
      : type === "world_rule"
        ? "world"
        : type === "plot_thread"
          ? "plot"
          : type === "ontology"
            ? "ontology"
            : "analysis";

  const title = composeAnalysisAssetTitle(type, name, payload);
  const summaryFromPayload = firstString(payload, ["summary", "description", "blurb", "rule_text", "excerpt"]);
  const summary = (summaryFromPayload || title).slice(0, 2000);
  const contentText = composeAnalysisAssetContent(type, title, summary, payload);
  const tags = Array.isArray(payload.tags)
    ? payload.tags.filter((item): item is string => typeof item === "string" && item.trim() !== "").slice(0, 24)
    : [];
  if (!tags.includes("pi_analysis")) tags.push("pi_analysis");
  if (!tags.includes(type)) tags.push(type);

  return {
    asset_type: assetType,
    category,
    title,
    summary,
    content_text: contentText,
    payload: {
      ...payload,
      analysis_candidate_type: type,
      workspace_path: workspacePath ?? null,
      auto_imported: true,
    },
    tags,
  };
}
