/**
 * Read-side helpers: human titles and structured body from asset payload
 * when stored title is a machine type key (legacy pi_analysis imports).
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

const META_PAYLOAD_KEYS = new Set([
  "analysis_candidate_type",
  "workspace_path",
  "auto_imported",
  "asset_id",
  "lifecycle",
  "category",
]);

export type StructuredField = {
  key: string;
  labelZh: string;
  labelEn: string;
  value: string;
};

export type StructuredAssetBody = {
  fields: StructuredField[];
  prose: string;
  /** Non-empty only when summary is not a duplicate of prose. */
  summaryDistinct: string;
  rawPayload: Record<string, unknown> | null;
};

function firstString(payload: Record<string, unknown> | undefined, keys: string[]): string {
  if (!payload) return "";
  for (const key of keys) {
    const value = payload[key];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
  }
  return "";
}

export function isTypeKeyTitle(value: string | undefined | null): boolean {
  return TYPE_KEY_TITLES.has(String(value ?? "").trim().toLowerCase());
}

function composeRelationshipTitle(payload: Record<string, unknown> | undefined): string {
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
  if (!source && !target) return "";
  const left = source || "?";
  const right = target || "?";
  return relType ? `${left} → ${right} / ${relType}` : `${left} → ${right}`;
}

function truncateText(value: string, max: number): string {
  const trimmed = value.trim();
  if (max <= 0 || trimmed.length <= max) return trimmed;
  return `${trimmed.slice(0, max)}…`;
}

/**
 * Prefer stored title when human; otherwise compose from payload (list + preview).
 */
export function displayAssetTitle(input: {
  title?: string | null;
  asset_type?: string | null;
  summary?: string | null;
  payload?: Record<string, unknown> | null;
}): string {
  const title = String(input.title ?? "").trim();
  const payload = input.payload ?? undefined;
  const assetType = String(input.asset_type ?? "").trim().toLowerCase();
  const candidateType = firstString(payload, ["analysis_candidate_type"]).toLowerCase()
    || (assetType === "note" ? "note_summary" : assetType === "story_ontology" ? "ontology" : assetType);

  if (title && !isTypeKeyTitle(title)) {
    return title;
  }

  const fromPayload = firstString(payload, ["name", "title", "canonical_name", "label"]);
  if (fromPayload && !isTypeKeyTitle(fromPayload)) {
    return fromPayload;
  }

  switch (candidateType) {
    case "relationship": {
      const composed = composeRelationshipTitle(payload);
      if (composed) return composed;
      break;
    }
    case "character": {
      const name = firstString(payload, ["character_name", "full_name"]);
      if (name) return name;
      break;
    }
    case "world_rule": {
      const rule = firstString(payload, ["rule_text", "rule", "statement", "summary", "description"]);
      if (rule) return truncateText(rule, 80);
      break;
    }
    case "plot_thread": {
      const thread = firstString(payload, ["thread_title", "hook", "summary", "description"]);
      if (thread) return truncateText(thread, 80);
      break;
    }
    case "note_summary":
    case "note": {
      const note = firstString(payload, ["summary", "description", "content", "text", "body", "excerpt"]);
      if (note) return truncateText(note, 80);
      break;
    }
    case "ontology":
    case "story_ontology": {
      const onto = firstString(payload, ["summary", "description"]);
      if (onto) return truncateText(onto, 80);
      break;
    }
  }

  const summary = String(input.summary ?? "").trim();
  if (summary && !isTypeKeyTitle(summary)) {
    return truncateText(summary, 80);
  }
  return title || assetType || "—";
}

function field(
  key: string,
  labelZh: string,
  labelEn: string,
  value: string,
): StructuredField | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  return { key, labelZh, labelEn, value: trimmed };
}

/**
 * Type-aware structured body for preview; raw JSON is optional, not primary.
 */
export function structureAssetBody(input: {
  title?: string | null;
  summary?: string | null;
  asset_type?: string | null;
  content_text?: string | null;
  payload?: Record<string, unknown> | null;
}): StructuredAssetBody {
  const payload = (input.payload && typeof input.payload === "object")
    ? input.payload
    : null;
  const assetType = String(input.asset_type ?? "").trim().toLowerCase();
  const candidateType = firstString(payload ?? undefined, ["analysis_candidate_type"]).toLowerCase()
    || (assetType === "note" ? "note_summary" : assetType === "story_ontology" ? "ontology" : assetType);

  const fields: StructuredField[] = [];
  let prose = "";

  const contentText = String(input.content_text ?? "").trim();
  const summary = String(input.summary ?? "").trim();

  if (candidateType === "relationship" && payload) {
    const source = firstString(payload, [
      "source", "source_name", "source_entity", "source_entity_name", "from", "from_name", "a", "character_a",
    ]);
    const target = firstString(payload, [
      "target", "target_name", "target_entity", "target_entity_name", "to", "to_name", "b", "character_b",
    ]);
    const relType = firstString(payload, [
      "relationship_type", "relation_type", "type", "kind", "relation", "bond_type",
    ]);
    const desc = firstString(payload, ["summary", "description", "blurb", "content", "text", "body"]);
    const f1 = field("source", "一方", "Source", source);
    const f2 = field("target", "另一方", "Target", target);
    const f3 = field("relation", "关系类型", "Relation", relType);
    if (f1) fields.push(f1);
    if (f2) fields.push(f2);
    if (f3) fields.push(f3);
    prose = desc || contentText || summary;
  } else if (candidateType === "character" && payload) {
    const identity = firstString(payload, ["identity", "role", "archetype", "occupation"]);
    const personality = firstString(payload, ["personality", "traits", "temperament"]);
    const appearance = firstString(payload, ["appearance", "looks"]);
    const f1 = field("identity", "身份", "Identity", identity);
    const f2 = field("personality", "性格", "Personality", personality);
    const f3 = field("appearance", "外貌", "Appearance", appearance);
    if (f1) fields.push(f1);
    if (f2) fields.push(f2);
    if (f3) fields.push(f3);
    prose = firstString(payload, ["content", "text", "body", "description", "summary", "blurb"])
      || contentText
      || summary;
  } else if ((candidateType === "world_rule" || candidateType === "plot_thread") && payload) {
    const rule = firstString(payload, ["rule_text", "rule", "statement", "hook", "thread_title"]);
    if (rule) {
      fields.push({
        key: "rule",
        labelZh: candidateType === "plot_thread" ? "线索" : "规则",
        labelEn: candidateType === "plot_thread" ? "Thread" : "Rule",
        value: rule,
      });
    }
    prose = firstString(payload, ["content", "text", "body", "description", "summary", "blurb"])
      || contentText
      || summary;
  } else {
    prose = contentText
      || firstString(payload ?? undefined, ["content", "text", "body", "content_text", "note", "excerpt", "description", "summary", "blurb", "rule_text"])
      || summary;
  }

  // Avoid repeating the display title as the only "prose" when it's just a type key.
  if (prose && isTypeKeyTitle(prose)) {
    prose = "";
  }

  // Drop structured field rows that merely echo the prose (e.g. world_rule rule_text).
  if (prose) {
    const proseNorm = normalizeDisplayText(prose);
    for (let i = fields.length - 1; i >= 0; i -= 1) {
      if (normalizeDisplayText(fields[i].value) === proseNorm) {
        fields.splice(i, 1);
      }
    }
  }

  return {
    fields,
    prose: prose.length > 4000 ? `${prose.slice(0, 4000)}…` : prose,
    /** Distinct short summary for the preview header; empty when it equals body. */
    summaryDistinct: distinctSummary(summary, prose),
    rawPayload: payload && Object.keys(payload).length > 0 ? payload : null,
  };
}

function normalizeDisplayText(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

/**
 * Keep a summary only when it adds information beyond the body prose.
 * Analysis imports often copy the same English/Chinese paragraph into both fields.
 */
export function distinctSummary(summary: string, prose: string): string {
  const s = String(summary ?? "").trim();
  if (!s || isTypeKeyTitle(s)) return "";
  const p = String(prose ?? "").trim();
  if (!p) return s;
  if (normalizeDisplayText(s) === normalizeDisplayText(p)) return "";
  // Summary that is only a truncated prefix of the body is still redundant.
  if (p.startsWith(s) && p.length > s.length) return "";
  if (s.startsWith(p) && s.length <= p.length + 8) return "";
  return s;
}

export function formatRawPayloadJson(payload: Record<string, unknown> | null | undefined): string {
  if (!payload || Object.keys(payload).length === 0) return "";
  try {
    const filtered: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(payload)) {
      if (META_PAYLOAD_KEYS.has(key)) continue;
      filtered[key] = value;
    }
    const source = Object.keys(filtered).length > 0 ? filtered : payload;
    const json = JSON.stringify(source, null, 2);
    return json.length > 2400 ? `${json.slice(0, 2400)}…` : json;
  } catch {
    return "";
  }
}
