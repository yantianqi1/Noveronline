import type { GraphEdgeVM, GraphNodeVM } from "./graph-view-model";

const HEX_RADIX = 16;
const HIGH_SURROGATE_START = 0xd800;
const LOW_SURROGATE_START = 0xdc00;
const SURROGATE_BLOCK_SIZE = 0x400;
const NON_BMP_OFFSET = 0x10000;

const SURROGATE_ESCAPE_RE = /\\u(d[89ab][0-9a-f]{2})\\u(d[cdef][0-9a-f]{2})/gi;
const UNICODE_ESCAPE_RE = /\\u([0-9a-f]{4})/gi;
const SIMPLE_ESCAPE_RE = /\\([nrt])/g;
const PROJECT_ID_RE = /^proj_[a-z0-9]{8,}$/i;
const PATH_LIKE_RE = /(?:[A-Za-z]:)?[\\/][^\s，。；、]+/g;
const FILE_TOKEN_RE = /\b[\w.-]+\.(json|sqlite3|sqlite|db|py|ts|tsx|vue|js|tmp)\b/gi;
const INTERNAL_TOKEN_RE = /\b[a-z][a-z0-9]+(?:_[a-z0-9]+)+\b/gi;

const EMPTY_DISPLAY = "系统数据";
const UNTITLED_PROJECT = "未命名卷宗";
const DEFAULT_COMPACT_LENGTH = 28;

const SIMPLE_ESCAPES: Record<string, string> = {
  n: "\n",
  r: "\r",
  t: "\t",
};

const INTERNAL_LABELS: Record<string, string> = {
  local_block_facts: "章节事实线索",
  block_analyses: "章节结构分析",
  story_memory: "故事记忆",
  chapter_continuity: "章节连续性",
  reading_notes: "阅读笔记",
  seed_analysis: "种子分析",
  narrative_archives: "角色档案",
  agent_profiles: "角色代理档案",
  story_graph: "故事关系数据",
  source_artifacts: "来源线索",
  storage_path: "保存位置",
};

const FILE_LABELS: Record<string, string> = {
  "local_block_facts.json": "章节事实线索",
  "block_analyses.json": "章节结构分析",
  "story_memory.json": "故事记忆",
  "chapter_continuity.json": "章节连续性",
  "reading_notes.json": "阅读笔记",
  "seed_analysis.json": "种子分析",
  "narrative_archives.json": "角色档案",
  "agent_profiles.json": "角色代理档案",
  "story_graph.json": "故事关系数据",
  "story_graph.sqlite3": "故事关系索引",
};

const RELATION_LABELS: Record<string, string> = {
  ALLY: "同盟",
  BELONGS_TO: "归属",
  CO_APPEARS_WITH: "共同出现",
  CONFLICT: "冲突",
  ENEMY: "敌对",
  FRIEND: "友好",
  HOSTILE: "敌对",
  INVOLVED_IN: "参与",
  LOCATED_IN: "位于",
  LOVE: "情感关联",
  MEMBER_OF: "成员",
  OBEYS_RULE: "遵循规则",
  PARTICIPATES_IN: "参与",
  POSSESSES: "持有",
  PRACTICES: "实践",
  RELATES_TO: "相关",
  ROMANCE: "情感关联",
  SEEKS: "追寻",
  TAKES_PLACE_IN: "发生于",
  UTILIZES_KNOWLEDGE: "使用知识",
};

interface DisplayTextOptions {
  emptyLabel?: string;
  allowInternalTokens?: boolean;
}

function decodeSurrogatePair(highHex: string, lowHex: string): string {
  const high = Number.parseInt(highHex, HEX_RADIX);
  const low = Number.parseInt(lowHex, HEX_RADIX);
  const codePoint = (
    (high - HIGH_SURROGATE_START) * SURROGATE_BLOCK_SIZE
    + (low - LOW_SURROGATE_START)
    + NON_BMP_OFFSET
  );
  return String.fromCodePoint(codePoint);
}

export function decodeEscapedUnicode(value: string): string {
  return String(value || "")
    .replace(SURROGATE_ESCAPE_RE, (_match, high, low) => decodeSurrogatePair(high, low))
    .replace(UNICODE_ESCAPE_RE, (_match, hex) => String.fromCharCode(Number.parseInt(hex, HEX_RADIX)))
    .replace(SIMPLE_ESCAPE_RE, (_match, key) => SIMPLE_ESCAPES[key] ?? key);
}

function basename(value: string): string {
  const normalized = value.replace(/\\/g, "/");
  const parts = normalized.split("/");
  return parts[parts.length - 1] || value;
}

function labelForStorageToken(token: string): string {
  const name = basename(token);
  const lower = name.toLowerCase();
  if (FILE_LABELS[lower]) return FILE_LABELS[lower];
  const withoutExt = lower.replace(/\.(json|sqlite3|sqlite|db|py|ts|tsx|vue|js|tmp)$/i, "");
  return INTERNAL_LABELS[withoutExt] || EMPTY_DISPLAY;
}

function normalizeWhitespace(value: string): string {
  return value.replace(/\s+/g, " ").trim();
}

function replaceStorageTokens(value: string): string {
  return value
    .replace(PATH_LIKE_RE, (match) => labelForStorageToken(match))
    .replace(FILE_TOKEN_RE, (match) => labelForStorageToken(match));
}

function replaceInternalTokens(value: string): string {
  return value.replace(INTERNAL_TOKEN_RE, (match) => INTERNAL_LABELS[match] || match);
}

function isInternalDisplayValue(value: string): boolean {
  if (!value) return true;
  if (PROJECT_ID_RE.test(value)) return true;
  return value === EMPTY_DISPLAY;
}

function relationKey(value: string): string {
  return value.trim().replace(/\s+/g, "_").toUpperCase();
}

function isMachineRelationLabel(value: string): boolean {
  return /^[A-Z0-9_]+$/.test(value) || /^[a-z]+(?:_[a-z]+)*$/.test(value);
}

function formatRelationLabel(value: unknown, emptyLabel: string): string {
  const text = sanitizeDisplayText(value, { emptyLabel: "" });
  const key = relationKey(text);
  if (RELATION_LABELS[key]) return RELATION_LABELS[key];
  return isMachineRelationLabel(text) ? emptyLabel : text;
}

export function sanitizeDisplayText(input: unknown, options: DisplayTextOptions = {}): string {
  const emptyLabel = options.emptyLabel ?? EMPTY_DISPLAY;
  const decoded = decodeEscapedUnicode(String(input ?? ""));
  const storageCleaned = replaceStorageTokens(decoded);
  const tokenCleaned = options.allowInternalTokens
    ? storageCleaned
    : replaceInternalTokens(storageCleaned);
  const normalized = normalizeWhitespace(tokenCleaned);
  return isInternalDisplayValue(normalized) ? emptyLabel : normalized;
}

export function compactDisplayText(input: unknown, maxLength = DEFAULT_COMPACT_LENGTH): string {
  const text = sanitizeDisplayText(input, { emptyLabel: "" });
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}…`;
}

export function sanitizeDisplayValue(value: unknown): unknown {
  if (typeof value === "string") return sanitizeDisplayText(value);
  if (Array.isArray(value)) return value.map(sanitizeDisplayValue);
  if (!value || typeof value !== "object") return value;
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>).map(([key, item]) => [
      key,
      sanitizeDisplayValue(item),
    ]),
  );
}

export function sanitizeGraphNode(node: GraphNodeVM): GraphNodeVM {
  return {
    ...node,
    name: sanitizeDisplayText(node.name, { emptyLabel: "未命名实体" }),
    summary: sanitizeDisplayText(node.summary, { emptyLabel: "" }),
    attributes: sanitizeDisplayValue(node.attributes) as Record<string, unknown>,
  };
}

export function sanitizeGraphEdge(edge: GraphEdgeVM): GraphEdgeVM {
  const fact = formatRelationLabel(edge.fact, "");
  return {
    ...edge,
    source_name: sanitizeDisplayText(edge.source_name, { emptyLabel: "未知来源" }),
    target_name: sanitizeDisplayText(edge.target_name, { emptyLabel: "未知目标" }),
    name: formatRelationLabel(edge.name, "关联"),
    fact: fact || sanitizeDisplayText(edge.fact, { emptyLabel: "" }),
  };
}

export function sanitizeGraphNodes(nodes: GraphNodeVM[] = []): GraphNodeVM[] {
  return nodes.map(sanitizeGraphNode);
}

export function sanitizeGraphEdges(edges: GraphEdgeVM[] = []): GraphEdgeVM[] {
  return edges.map(sanitizeGraphEdge);
}

export function formatProjectDisplayName(project: Record<string, unknown> | undefined): string {
  const rawName = project?.name || project?.project_name || project?.title || "";
  const displayName = sanitizeDisplayText(rawName, { emptyLabel: "" });
  return displayName || UNTITLED_PROJECT;
}

export function formatStageSampleLabel(item: unknown): string {
  if (item == null) return "";
  if (typeof item === "string") {
    return sanitizeDisplayText(item, { emptyLabel: EMPTY_DISPLAY });
  }
  if (typeof item !== "object") {
    return sanitizeDisplayText(item, { emptyLabel: "" });
  }
  const obj = item as Record<string, unknown>;
  const name = sanitizeDisplayText(obj.name, { emptyLabel: "" });
  const fact = sanitizeDisplayText(obj.fact, { emptyLabel: "" });
  const summary = sanitizeDisplayText(obj.summary, { emptyLabel: "" });
  return name || fact || summary || "";
}
