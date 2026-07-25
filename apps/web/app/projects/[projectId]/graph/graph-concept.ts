import type { GraphNode } from "@/lib/api/graph-types";

/**
 * Concept refinement for the Story Graph — pure presentation logic.
 *
 * The backend currently flattens every analysis/world asset into a single
 * `concept` node_type, so the constellation shows 78 indistinguishable slips
 * with machine or English-sentence titles. The signal to tell them apart is
 * already on the node, passed through the Go read side untouched:
 *   attributes.category           "analysis" (timeline events) | "world" (settings)
 *   attributes.tags               "note_summary" | "world_rule" | ...
 *   attributes.payload.world      "ancient" | "modern"
 *   attributes.payload.timeframe  "Day 1 (Ancient) - Night"
 *   attributes.payload.id         "event_010"
 *
 * `resolveConcept` turns that into a display subtype, a world grouping, and a
 * cleaned Chinese-first title — all derived, never fabricated, and only used
 * for rendering (the raw title/summary stay intact in the inspector).
 */

export type ConceptSubtype = "event" | "world" | "concept";

export type ConceptInfo = {
  subtype: ConceptSubtype;
  /** 分析·事件 / 世界观·设定 / 概念 */
  subtypeLabel: string;
  /** 现代 / 古代 / 设定 */
  world: string;
  /** Cleaned, Chinese-first display title. */
  displayTitle: string;
  /** True when the source title was a machine placeholder we had to replace. */
  isUntitled: boolean;
  /** Raw timeframe from the payload, when present. */
  timeframe: string;
};

const SUBTYPE_LABEL: Record<ConceptSubtype, string> = {
  event: "分析·事件",
  world: "世界观·设定",
  concept: "概念",
};

/** Machine placeholder titles that must never be shown as-is. */
const PLACEHOLDER_TITLES = new Set([
  "note_summary",
  "concept",
  "note",
  "analysis",
  "world_rule",
  "plot_event",
  "summary",
  "untitled",
]);

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}

function tagsOf(attributes: Record<string, unknown>): string[] {
  const raw = attributes.tags;
  if (!Array.isArray(raw)) return [];
  return raw.filter((t): t is string => typeof t === "string").map((t) => t.toLowerCase());
}

function isPlaceholderTitle(title: string): boolean {
  const t = title.trim().toLowerCase();
  return t === "" || PLACEHOLDER_TITLES.has(t);
}

/** True when the title reads as an English sentence, even if it embeds a CJK
 * entity (e.g. "Shen Cuihua returns to 青山医院 at dawn"). Heuristic: it starts
 * with a latin letter and latin letters outnumber CJK characters — a Chinese-
 * first title (青山医院 Qingshan) keeps a CJK majority and is left intact. */
function isEnglishSentence(title: string): boolean {
  const t = title.trim();
  if (!t) return false;
  if (!/^[A-Za-z]/.test(t)) return false;
  const latin = (t.match(/[A-Za-z]/g) ?? []).length;
  const cjk = (t.match(/[一-鿿]/g) ?? []).length;
  return latin > cjk;
}

/**
 * Pull the most salient run of Chinese out of a mixed-language sentence. The
 * lead is the first CJK run (optionally with internal ·「」『』（） and one
 * immediately-following single latin proper noun, like 青山医院 Qingshan). It
 * stops before any space-separated English clause ("青山医院 at dawn" → "青山医院").
 * Returns "" when there is no Chinese to anchor on.
 */
function extractChineseLead(title: string): string {
  const match = title.match(/[一-鿿][一-鿿·「」『』（）()]*/);
  if (!match) return "";
  const lead = match[0];
  const rest = title.slice((match.index ?? 0) + lead.length);
  // Append one adjacent latin proper noun (no internal spaces), e.g. " Qingshan".
  const suffix = rest.match(/^\s?([A-Za-z0-9/-]+)(?![A-Za-z0-9/-]*\s+[A-Za-z])/);
  return suffix ? `${lead} ${suffix[1]}` : lead;
}

const WORLD_LABEL: Record<string, string> = {
  modern: "现代",
  ancient: "古代",
};

/** Translate a raw payload.world into a Chinese grouping label. */
export function worldGroupLabel(world: string): string {
  const w = world.trim().toLowerCase();
  if (!w) return "设定";
  return WORLD_LABEL[w] ?? "设定";
}

/** Turn a timeframe like "Day 1 (Ancient) - Night" into a short Chinese tag. */
function timeframeTag(timeframe: string): string {
  const t = timeframe.trim();
  if (!t) return "";
  const day = t.match(/day\s*(\d+(?:\s*[-–]\s*\d+)?)/i);
  const phase = /night/i.test(t)
    ? "夜"
    : /late night/i.test(t)
      ? "深夜"
      : /dawn/i.test(t)
        ? "清晨"
        : /morning/i.test(t)
          ? "晨"
          : /evening/i.test(t)
            ? "暮"
            : "";
  if (day) return `第${day[1].replace(/\s+/g, "")}天${phase ? `·${phase}` : ""}`;
  return phase || t.slice(0, 10);
}

/**
 * Resolve one node's concept subtype + world + cleaned title. Returns null for
 * non-concept node types so callers can branch cheaply.
 */
export function resolveConcept(node: Pick<GraphNode, "node_type" | "title" | "attributes">): ConceptInfo | null {
  if (node.node_type !== "concept") return null;
  const attributes = asRecord(node.attributes);
  const payload = asRecord(attributes.payload);
  const category = asString(attributes.category).toLowerCase();
  const tags = tagsOf(attributes);

  const subtype: ConceptSubtype =
    category === "analysis" || tags.includes("note_summary")
      ? "event"
      : category === "world" || tags.includes("world_rule")
        ? "world"
        : "concept";

  const world = asString(payload.world).toLowerCase();
  const timeframe = asString(payload.timeframe);
  const id = asString(payload.id);
  const rawTitle = (node.title ?? "").trim();

  // World/setting entries already carry good bilingual titles — keep them.
  if (subtype !== "event") {
    return {
      subtype,
      subtypeLabel: SUBTYPE_LABEL[subtype],
      world: worldGroupLabel(world),
      displayTitle: isPlaceholderTitle(rawTitle) ? "未命名设定" : rawTitle,
      isUntitled: isPlaceholderTitle(rawTitle),
      timeframe,
    };
  }

  // Timeline events: replace placeholder / English-sentence titles.
  let displayTitle = rawTitle;
  let isUntitled = false;
  if (isPlaceholderTitle(rawTitle)) {
    isUntitled = true;
    const where = worldGroupLabel(world);
    const when = timeframeTag(timeframe);
    displayTitle = [where !== "设定" ? where : "", when].filter(Boolean).join(" · ") || "未命名事件";
  } else if (isEnglishSentence(rawTitle)) {
    const lead = extractChineseLead(rawTitle);
    if (lead) {
      displayTitle = lead;
    } else {
      isUntitled = true;
      const where = worldGroupLabel(world);
      const when = timeframeTag(timeframe);
      displayTitle = [where !== "设定" ? where : "", when].filter(Boolean).join(" · ") || "未命名事件";
    }
  }
  // Disambiguate exact-duplicate titles with the event id (e.g. two event_012).
  if (id && !displayTitle.includes(id)) {
    // keep title clean; id only appended when needed by caller grouping
  }
  return {
    subtype,
    subtypeLabel: SUBTYPE_LABEL[subtype],
    world: worldGroupLabel(world),
    displayTitle,
    isUntitled,
    timeframe,
  };
}

/**
 * The layer key a node files under in the filter rail. Non-concepts use their
 * own node_type; concepts fan out by subtype so the rail can toggle
 * 分析·事件 / 世界观·设定 / 概念 independently.
 */
export function layerKeyOf(node: Pick<GraphNode, "node_type" | "title" | "attributes">): string {
  if (node.node_type !== "concept") return node.node_type;
  return `concept:${resolveConcept(node)?.subtype ?? "concept"}`;
}

/** Layer keys for the three concept subtypes, in stable order. */
export const CONCEPT_LAYER_KEYS = ["concept:event", "concept:world", "concept:concept"] as const;

/** True for layer keys that represent background concepts (default-hidden). */
export function isConceptLayerKey(layerKey: string): boolean {
  return layerKey.startsWith("concept:");
}
