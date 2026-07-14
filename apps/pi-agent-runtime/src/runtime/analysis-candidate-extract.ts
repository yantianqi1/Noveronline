/**
 * Normalize 30-candidates/*.json shapes into flat candidate rows for auto-import.
 * Agents are instructed to write {"items":[...]}, but commonly emit type-keyed
 * arrays ({"characters":[...]}, {"relationships":[...]}) or encyclopedia objects
 * for world_rules — accept those so finalize does not silently import zero assets.
 */

export type ExtractedAnalysisCandidate = {
  candidate_type: string;
  name: string;
  payload: Record<string, unknown>;
  workspace_path: string;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function humanizeKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\s+/g, " ")
    .trim() || key;
}

function candidateTypeForPath(path: string): string {
  if (path.includes("characters")) return "character";
  if (path.includes("relationships")) return "relationship";
  if (path.includes("world_rules")) return "world_rule";
  if (path.includes("plot_threads")) return "plot_thread";
  if (path.includes("ontology")) return "ontology";
  return "note_summary";
}

function arrayFromKnownKeys(parsed: Record<string, unknown>, type: string): Record<string, unknown>[] | null {
  const preferredKeys =
    type === "character"
      ? ["items", "characters", "entities", "people"]
      : type === "relationship"
        ? ["items", "relationships", "relations", "edges"]
        : type === "world_rule"
          ? ["items", "world_rules", "rules", "settings"]
          : type === "plot_thread"
            ? ["items", "plot_threads", "threads", "foreshadowing"]
            : type === "ontology"
              ? ["items", "ontology", "types", "classes"]
              : ["items", "notes", "summaries"];

  for (const key of preferredKeys) {
    const value = parsed[key];
    if (Array.isArray(value)) {
      return value.filter(isRecord);
    }
  }
  return null;
}

function flattenWorldRuleEncyclopedia(parsed: Record<string, unknown>): Record<string, unknown>[] {
  const items: Record<string, unknown>[] = [];
  const worldName = typeof parsed.world_name === "string" ? parsed.world_name.trim() : "";
  const worldType = typeof parsed.world_type === "string" ? parsed.world_type.trim() : "";
  if (worldName || worldType) {
    items.push({
      name: worldName || "世界设定",
      title: worldName || "世界设定",
      summary: worldType || worldName || "世界设定总览",
      rule_text: [worldName && `世界：${worldName}`, worldType && `类型：${worldType}`]
        .filter(Boolean)
        .join("\n"),
      section: "overview",
      world_name: worldName || undefined,
      world_type: worldType || undefined,
    });
  }

  for (const [key, value] of Object.entries(parsed)) {
    if (key === "world_name" || key === "world_type" || key === "items") continue;
    if (Array.isArray(value)) {
      for (const entry of value) {
        if (isRecord(entry)) {
          const name = String(entry.name ?? entry.title ?? humanizeKey(key));
          items.push({ ...entry, name, title: entry.title ?? name, section: key });
          continue;
        }
        if (typeof entry === "string" && entry.trim()) {
          items.push({
            name: humanizeKey(key),
            title: humanizeKey(key),
            rule_text: entry.trim(),
            section: key,
          });
        }
      }
      continue;
    }
    if (isRecord(value)) {
      const nestedName = typeof value.name === "string" && value.name.trim()
        ? value.name.trim()
        : typeof value.title === "string" && value.title.trim()
          ? value.title.trim()
          : humanizeKey(key);
      const summary = typeof value.summary === "string" && value.summary.trim()
        ? value.summary.trim()
        : typeof value.description === "string" && value.description.trim()
          ? value.description.trim()
          : nestedName;
      const ruleText = typeof value.rule_text === "string" && value.rule_text.trim()
        ? value.rule_text.trim()
        : typeof value.description === "string" && value.description.trim()
          ? value.description.trim()
          : JSON.stringify(value, null, 2).slice(0, 8_000);
      items.push({
        ...value,
        name: nestedName,
        title: nestedName,
        summary,
        rule_text: ruleText,
        section: key,
      });
      continue;
    }
    if (typeof value === "string" && value.trim()) {
      items.push({
        name: humanizeKey(key),
        title: humanizeKey(key),
        rule_text: value.trim(),
        section: key,
      });
    }
  }
  return items;
}

/** Extract item records from one candidate JSON document. */
export function extractItemsFromCandidateDocument(
  path: string,
  contentText: string,
): Record<string, unknown>[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(contentText);
  } catch {
    return [];
  }
  if (Array.isArray(parsed)) {
    return parsed.filter(isRecord);
  }
  if (!isRecord(parsed)) {
    return [];
  }
  const type = candidateTypeForPath(path);
  const fromKeys = arrayFromKnownKeys(parsed, type);
  if (fromKeys) {
    return fromKeys;
  }
  if (type === "world_rule") {
    return flattenWorldRuleEncyclopedia(parsed);
  }
  return [];
}

export function extractAnalysisCandidatesFromWorkspaceFiles(
  files: ReadonlyArray<{ path: string; content_text?: string | null }>,
): ExtractedAnalysisCandidate[] {
  const candidates: ExtractedAnalysisCandidate[] = [];
  for (const file of files) {
    if (!file.path.startsWith("30-candidates/") || !file.content_text) continue;
    const type = candidateTypeForPath(file.path);
    const items = extractItemsFromCandidateDocument(file.path, file.content_text);
    for (const item of items) {
      candidates.push({
        candidate_type: type,
        name: String(item.name ?? item.title ?? type),
        payload: item,
        workspace_path: file.path,
      });
    }
  }
  return candidates;
}
