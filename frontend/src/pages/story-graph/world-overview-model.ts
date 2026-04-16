/**
 * World overview dashboard computation model.
 * Ported from src-vue/views/story-graph/worldOverviewModel.js.
 *
 * Pure functions: input { nodes, edges, projectName }, output dashboard structure.
 */

import type { GraphNodeVM, GraphEdgeVM } from "./graph-view-model";
import {
  compactDisplayText,
  sanitizeDisplayText,
  sanitizeGraphEdges,
  sanitizeGraphNodes,
} from "./display-text";

/* ---- Common helpers ---- */

const TIER_RANK: Record<string, number> = { protagonist: 0, major: 1, supporting: 2, minor: 3 };
const OVERVIEW_NAME_LIMIT = 24;
const OVERVIEW_SUMMARY_LIMIT = 72;
const OVERVIEW_EDGE_LABEL_LIMIT = 18;
const OVERVIEW_FACT_LIMIT = 34;

function nodeTier(node: GraphNodeVM): string {
  return (String((node.attributes?.importance_tier as string) || "supporting")).toLowerCase();
}

function nodeType(node: GraphNodeVM): string {
  return String(node.entity_type || "unknown").toLowerCase();
}

function buildDegreeMap(nodes: GraphNodeVM[], edges: GraphEdgeVM[]): Record<string, number> {
  const map: Record<string, number> = {};
  for (const n of nodes) map[n.id] = 0;
  for (const edge of edges) {
    if (edge.source_id in map) map[edge.source_id]! += 1;
    if (edge.target_id in map) map[edge.target_id]! += 1;
  }
  return map;
}

function buildNodeIndex(nodes: GraphNodeVM[]): Record<string, GraphNodeVM> {
  return Object.fromEntries(nodes.map((n) => [n.id, n]));
}

function tierWeight(tier: string): number {
  return ({ protagonist: 4, major: 3, supporting: 2, minor: 1 } as Record<string, number>)[tier] || 1;
}

function compactOverviewNodes(nodes: GraphNodeVM[]): GraphNodeVM[] {
  return sanitizeGraphNodes(nodes).map((node) => ({
    ...node,
    name: compactDisplayText(node.name, OVERVIEW_NAME_LIMIT),
    summary: compactDisplayText(node.summary, OVERVIEW_SUMMARY_LIMIT),
  }));
}

function compactOverviewEdges(edges: GraphEdgeVM[]): GraphEdgeVM[] {
  return sanitizeGraphEdges(edges).map((edge) => ({
    ...edge,
    source_name: compactDisplayText(edge.source_name, OVERVIEW_NAME_LIMIT),
    target_name: compactDisplayText(edge.target_name, OVERVIEW_NAME_LIMIT),
    name: compactDisplayText(edge.name, OVERVIEW_EDGE_LABEL_LIMIT),
    fact: compactDisplayText(edge.fact, OVERVIEW_FACT_LIMIT),
  }));
}

/* ---- Interfaces ---- */

export interface HeroSummary {
  projectName: string;
  totalNodes: number;
  totalEdges: number;
  typeCount: number;
  protagonistNames: string[];
  majorOrgNames: string[];
  eventCount: number;
  headline: string;
}

export interface CastItem {
  id: string;
  name: string;
  summary: string;
  tier?: string;
  type?: string;
  degree: number;
  aliases?: string[];
}

export interface CastRadar {
  protagonist: CastItem[];
  major: CastItem[];
  supporting: CastItem[];
  minor: CastItem[];
  organizations: CastItem[];
  totalCharacters: number;
}

export interface HighlightEdge {
  id: string;
  source_id: string;
  target_id: string;
  sourceName: string;
  targetName: string;
  label: string;
  fact: string;
  weight: number;
}

export interface Triangle {
  members: Array<{ id: string; name: string }>;
}

export interface OrphanItem {
  id: string;
  name: string;
  tier: string;
  degree: number;
}

export interface RelationshipHighlights {
  topBonds: HighlightEdge[];
  conflicts: HighlightEdge[];
  triangles: Triangle[];
  orphans: OrphanItem[];
}

export interface TimelineItem {
  id: string;
  name: string;
  summary: string;
  chapterId: string;
  order: number;
  participants: Array<{ id: string; name: string; type: string }>;
}

export interface WorldRule {
  id: string;
  name: string;
  summary: string;
  linked: Array<{ id: string; name: string; type: string }>;
}

export interface StoryHook {
  kind: string;
  title: string;
  body: string;
  involvedIds: string[];
  involvedNames: string[];
}

export interface HealthIssue {
  kind: string;
  label: string;
  severity: string;
  items: Array<{ id: string; name: string; type?: string }>;
  total: number;
}

export interface WorldOverview {
  hero: HeroSummary;
  cast: CastRadar;
  highlights: RelationshipHighlights;
  timeline: TimelineItem[];
  rules: WorldRule[];
  hooks: StoryHook[];
  health: HealthIssue[];
}

/* ---- Hero ---- */

function buildHeadline({
  protagonists,
  majorOrgs,
  eventNodes,
}: {
  protagonists: GraphNodeVM[];
  majorOrgs: GraphNodeVM[];
  eventNodes: GraphNodeVM[];
}): string {
  if (!protagonists.length && !majorOrgs.length) {
    return "\u5C1A\u672A\u8BC6\u522B\u51FA\u4E3B\u89D2\u4E0E\u4E3B\u8981\u52BF\u529B\uFF0C\u53EF\u5728\u9605\u8BFB\u7B14\u8BB0\u4E2D\u8865\u5145\u5173\u952E\u4EBA\u7269\u3002";
  }
  const lead = protagonists[0]?.name || majorOrgs[0]?.name || "\u4E3B\u7EBF";
  const opp = majorOrgs[0]?.name || protagonists[1]?.name || "\u672A\u77E5\u9635\u8425";
  const events = eventNodes.length;
  return `\u4E3B\u7EBF\uFF1A${lead} \u2694 ${opp}\u3000\u00B7\u3000${events} \u4E2A\u5267\u60C5\u4E8B\u4EF6`;
}

export function buildHeroSummary({
  nodes = [],
  edges = [],
  projectName = "",
}: {
  nodes?: GraphNodeVM[];
  edges?: GraphEdgeVM[];
  projectName?: string;
} = {}): HeroSummary {
  const totalNodes = nodes.length;
  const totalEdges = edges.length;
  const typeSet = new Set(nodes.map(nodeType).filter((t) => t && t !== "unknown"));
  const protagonists = nodes.filter((n) => nodeTier(n) === "protagonist");
  const majorOrgs = nodes.filter(
    (n) => ["organization", "faction", "group"].includes(nodeType(n)) && nodeTier(n) !== "minor",
  );
  const eventNodes = nodes.filter((n) => nodeType(n) === "plotevent");

  return {
    projectName: projectName || "\u672A\u547D\u540D\u5C0F\u8BF4",
    totalNodes,
    totalEdges,
    typeCount: typeSet.size,
    protagonistNames: protagonists.slice(0, 3).map((n) => n.name),
    majorOrgNames: majorOrgs.slice(0, 3).map((n) => n.name),
    eventCount: eventNodes.length,
    headline: buildHeadline({ protagonists, majorOrgs, eventNodes }),
  };
}

/* ---- Cast Radar ---- */

export function buildCastRadar({
  nodes = [],
  edges = [],
}: {
  nodes?: GraphNodeVM[];
  edges?: GraphEdgeVM[];
} = {}): CastRadar {
  const degrees = buildDegreeMap(nodes, edges);
  const characters = nodes.filter((n) => nodeType(n) === "character");
  const orgs = nodes.filter((n) => ["organization", "faction", "group"].includes(nodeType(n)));

  const grouped: Record<string, CastItem[]> = { protagonist: [], major: [], supporting: [], minor: [] };
  for (const c of characters) {
    const t = nodeTier(c);
    (grouped[t] || grouped.supporting!).push({
      id: c.id,
      name: c.name,
      summary: c.summary || "",
      tier: t,
      degree: degrees[c.id] || 0,
      aliases: (c.attributes?.aliases as string[]) || [],
    });
  }
  for (const tier of Object.keys(grouped)) {
    grouped[tier]!.sort((a, b) => b.degree - a.degree);
  }

  const organizations = orgs
    .map((o) => ({
      id: o.id,
      name: o.name,
      summary: o.summary || "",
      type: nodeType(o),
      degree: degrees[o.id] || 0,
    }))
    .sort((a, b) => b.degree - a.degree);

  return {
    protagonist: grouped.protagonist!,
    major: grouped.major!,
    supporting: grouped.supporting!,
    minor: grouped.minor!,
    organizations,
    totalCharacters: characters.length,
  };
}

/* ---- Relationship Highlights ---- */

const CONFLICT_KEYWORDS = ["\u654C", "\u53CD\u76EE", "\u80CC\u53DB", "\u51B2\u7A81", "\u4EC7", "\u6740", "\u5BF9\u7ACB", "hostile", "conflict", "betray"];
const ROMANCE_KEYWORDS = ["\u7231", "\u60C5", "\u604B", "\u592B\u59BB", "romance", "love"];

function isConflictEdge(edge: GraphEdgeVM): boolean {
  const text = `${edge.name || ""} ${edge.fact || ""}`.toLowerCase();
  return CONFLICT_KEYWORDS.some((k) => text.includes(k.toLowerCase()));
}

function isRomanceEdge(edge: GraphEdgeVM): boolean {
  const text = `${edge.name || ""} ${edge.fact || ""}`.toLowerCase();
  return ROMANCE_KEYWORDS.some((k) => text.includes(k.toLowerCase()));
}

interface EnrichedEdge extends GraphEdgeVM {
  score: number;
  src: GraphNodeVM;
  tgt: GraphNodeVM;
}

function formatHighlightEdge(edge: EnrichedEdge): HighlightEdge {
  return {
    id: edge.id,
    source_id: edge.source_id,
    target_id: edge.target_id,
    sourceName: edge.src.name,
    targetName: edge.tgt.name,
    label: edge.name || "\u5173\u8054",
    fact: edge.fact || "",
    weight: edge.weight || 1,
  };
}

function findTriangles(nodes: GraphNodeVM[], edges: EnrichedEdge[]): Triangle[] {
  const adj = new Map<string, Set<string>>();
  for (const e of edges) {
    if (!adj.has(e.source_id)) adj.set(e.source_id, new Set());
    if (!adj.has(e.target_id)) adj.set(e.target_id, new Set());
    adj.get(e.source_id)!.add(e.target_id);
    adj.get(e.target_id)!.add(e.source_id);
  }
  const ids = nodes
    .filter((n) => nodeType(n) === "character")
    .map((n) => n.id)
    .slice(0, 80);
  const triangles: Triangle[] = [];
  const seen = new Set<string>();
  for (let i = 0; i < ids.length; i++) {
    for (let j = i + 1; j < ids.length; j++) {
      if (!adj.get(ids[i]!)?.has(ids[j]!)) continue;
      for (let k = j + 1; k < ids.length; k++) {
        if (adj.get(ids[i]!)?.has(ids[k]!) && adj.get(ids[j]!)?.has(ids[k]!)) {
          const key = [ids[i], ids[j], ids[k]].sort().join("|");
          if (seen.has(key)) continue;
          seen.add(key);
          const involved = [ids[i]!, ids[j]!, ids[k]!];
          const hasRomance = edges.some(
            (e) =>
              involved.includes(e.source_id) &&
              involved.includes(e.target_id) &&
              isRomanceEdge(e),
          );
          if (hasRomance) {
            triangles.push({
              members: involved.map((id) => ({
                id,
                name: nodes.find((n) => n.id === id)?.name || "",
              })),
            });
          }
        }
      }
    }
  }
  return triangles;
}

export function buildRelationshipHighlights({
  nodes = [],
  edges = [],
}: {
  nodes?: GraphNodeVM[];
  edges?: GraphEdgeVM[];
} = {}): RelationshipHighlights {
  const nodeIndex = buildNodeIndex(nodes);
  const degrees = buildDegreeMap(nodes, edges);

  const enriched: EnrichedEdge[] = edges
    .map((e) => {
      const src = nodeIndex[e.source_id];
      const tgt = nodeIndex[e.target_id];
      if (!src || !tgt) return null;
      const tierBoost = tierWeight(nodeTier(src)) + tierWeight(nodeTier(tgt));
      return { ...e, score: (e.weight || 1) * tierBoost, src, tgt };
    })
    .filter((e): e is EnrichedEdge => e !== null);

  const topBonds = [...enriched]
    .sort((a, b) => b.score - a.score)
    .slice(0, 5)
    .map(formatHighlightEdge);

  const conflicts = enriched
    .filter(isConflictEdge)
    .sort((a, b) => b.score - a.score)
    .slice(0, 5)
    .map(formatHighlightEdge);

  const triangles = findTriangles(nodes, enriched).slice(0, 3);

  const orphans: OrphanItem[] = nodes
    .filter((n) => nodeType(n) === "character" && (degrees[n.id] || 0) <= 1)
    .map((n) => ({ id: n.id, name: n.name, tier: nodeTier(n), degree: degrees[n.id] || 0 }))
    .slice(0, 6);

  return { topBonds, conflicts, triangles, orphans };
}

/* ---- Event Timeline ---- */

function parseChapterOrder(chapterId: string): number {
  const m = String(chapterId || "").match(/(\d+)/);
  return m ? parseInt(m[1]!, 10) : Number.MAX_SAFE_INTEGER;
}

export function buildEventTimeline({
  nodes = [],
  edges = [],
}: {
  nodes?: GraphNodeVM[];
  edges?: GraphEdgeVM[];
} = {}): TimelineItem[] {
  const events = nodes.filter((n) => nodeType(n) === "plotevent");
  const nodeIndex = buildNodeIndex(nodes);
  const items = events.map((e) => {
    const chapterId = String((e.attributes?.chapter_id as string) || "");
    const order = parseChapterOrder(chapterId);
    const incoming = edges.filter((edge) => edge.target_id === e.id);
    const participants = incoming
      .map((edge) => nodeIndex[edge.source_id])
      .filter((n): n is GraphNodeVM => !!n)
      .map((n) => ({ id: n.id, name: n.name, type: nodeType(n) }));
    return { id: e.id, name: e.name, summary: e.summary || "", chapterId, order, participants };
  });
  items.sort((a, b) => a.order - b.order);
  return items;
}

/* ---- World Rules ---- */

export function buildWorldRules({
  nodes = [],
  edges = [],
}: {
  nodes?: GraphNodeVM[];
  edges?: GraphEdgeVM[];
} = {}): WorldRule[] {
  const rules = nodes.filter((n) => nodeType(n) === "rulesystem");
  const nodeIndex = buildNodeIndex(nodes);
  return rules.map((r) => {
    const incoming = edges.filter((e) => e.target_id === r.id);
    const linked = incoming
      .map((e) => nodeIndex[e.source_id])
      .filter((n): n is GraphNodeVM => !!n)
      .slice(0, 6)
      .map((n) => ({ id: n.id, name: n.name, type: nodeType(n) }));
    return { id: r.id, name: r.name, summary: r.summary || (r.attributes?.rule_text as string) || "", linked };
  });
}

/* ---- Story Hooks ---- */

export function buildStoryHooks({
  nodes = [],
  edges = [],
}: {
  nodes?: GraphNodeVM[];
  edges?: GraphEdgeVM[];
} = {}): StoryHook[] {
  const nodeIndex = buildNodeIndex(nodes);
  const degrees = buildDegreeMap(nodes, edges);
  const hooks: StoryHook[] = [];

  // Hook A: idle high-tier characters
  const idleHighTier = nodes
    .filter(
      (n) =>
        nodeType(n) === "character" &&
        ["protagonist", "major"].includes(nodeTier(n)) &&
        (degrees[n.id] || 0) <= 1,
    )
    .slice(0, 3);
  for (const c of idleHighTier) {
    hooks.push({
      kind: "idle_character",
      title: `\u300C${c.name}\u300D\u5C1A\u672A\u771F\u6B63\u767B\u573A`,
      body: `${c.name} \u88AB\u6807\u8BB0\u4E3A${nodeTier(c) === "protagonist" ? "\u4E3B\u89D2" : "\u4E3B\u8981\u89D2\u8272"}\uFF0C\u4F46\u76EE\u524D\u51E0\u4E4E\u6CA1\u6709\u5173\u8054\u4E8B\u4EF6\u3002\u53EF\u5199\u4E00\u573A\u8BA9 TA \u6B63\u5F0F\u5165\u573A\u7684\u620F\u3002`,
      involvedIds: [c.id],
      involvedNames: [c.name],
    });
  }

  // Hook B: conflict peak
  const conflictEdges = edges
    .filter(isConflictEdge)
    .map((e) => ({ ...e, src: nodeIndex[e.source_id], tgt: nodeIndex[e.target_id] }))
    .filter((e): e is typeof e & { src: GraphNodeVM; tgt: GraphNodeVM } => !!e.src && !!e.tgt)
    .sort((a, b) => (b.weight || 1) - (a.weight || 1))
    .slice(0, 3);
  for (const e of conflictEdges) {
    hooks.push({
      kind: "conflict_peak",
      title: `${e.src.name} \u4E0E ${e.tgt.name} \u7684\u51B2\u7A81\u5DF2\u5230\u7206\u70B9`,
      body: `${e.fact || e.name || "\u77DB\u76FE"}\uFF08\u5173\u8054\u5F3A\u5EA6 ${e.weight || 1}\uFF09\u3002\u53EF\u5199 TA \u4EEC\u7684\u6B63\u9762\u5BF9\u51B3\u6216\u4E00\u6B21\u51B3\u5B9A\u6027\u7684\u80CC\u53DB\u3002`,
      involvedIds: [e.src.id, e.tgt.id],
      involvedNames: [e.src.name, e.tgt.name],
    });
  }

  // Hook C: bridge characters
  const orgs = nodes.filter((n) => ["organization", "faction", "group"].includes(nodeType(n)));
  if (orgs.length >= 2) {
    const orgIds = new Set(orgs.map((o) => o.id));
    const charOrgLinks = new Map<string, Set<string>>();
    for (const e of edges) {
      const sIsChar = nodeIndex[e.source_id] && nodeType(nodeIndex[e.source_id]!) === "character";
      const tIsOrg = orgIds.has(e.target_id);
      if (sIsChar && tIsOrg) {
        if (!charOrgLinks.has(e.source_id)) charOrgLinks.set(e.source_id, new Set());
        charOrgLinks.get(e.source_id)!.add(e.target_id);
      }
    }
    let count = 0;
    for (const [charId, orgSet] of charOrgLinks) {
      if (orgSet.size >= 2 && count < 2) {
        const char = nodeIndex[charId];
        if (!char) continue;
        const orgNames = [...orgSet].map((id) => nodeIndex[id]?.name).filter(Boolean) as string[];
        hooks.push({
          kind: "bridge",
          title: `${char.name} \u540C\u65F6\u5173\u8054 ${orgNames.length} \u4E2A\u9635\u8425`,
          body: `${char.name} \u4E0E ${orgNames.join("\u3001")} \u90FD\u6709\u5F52\u5C5E\u5173\u8054\uFF0C\u53EF\u4F5C\u4E3A\u5367\u5E95\u3001\u53CC\u9762\u4EBA\u6216\u8C03\u505C\u8005\u5199\u4E00\u6BB5\u5FE0\u8BDA\u5371\u673A\u3002`,
          involvedIds: [charId, ...orgSet],
          involvedNames: [char.name, ...orgNames],
        });
        count++;
      }
    }
  }

  // Hook D: idle rules
  const ruleNodes = nodes.filter((n) => nodeType(n) === "rulesystem");
  const usedRuleIds = new Set(edges.map((e) => e.target_id));
  const idleRules = ruleNodes.filter((r) => !usedRuleIds.has(r.id)).slice(0, 2);
  for (const r of idleRules) {
    hooks.push({
      kind: "idle_rule",
      title: `\u4E16\u754C\u89C4\u5219\u300C${r.name}\u300D\u5C1A\u672A\u53D1\u6325\u4F5C\u7528`,
      body: "\u8FD9\u6761\u8BBE\u5B9A\u8FD8\u6CA1\u6709\u4EFB\u4F55\u89D2\u8272\u6216\u4E8B\u4EF6\u89E6\u53D1\u5B83\u3002\u53EF\u5199\u4E00\u573A\u8BA9 TA \u7B2C\u4E00\u6B21\u663E\u7075\u6216\u88AB\u6253\u7834\u7684\u620F\u3002",
      involvedIds: [r.id],
      involvedNames: [r.name],
    });
  }

  return hooks.slice(0, 10);
}

/* ---- Health Check ---- */

export function buildHealthCheck({
  nodes = [],
  edges = [],
}: {
  nodes?: GraphNodeVM[];
  edges?: GraphEdgeVM[];
} = {}): HealthIssue[] {
  const degrees = buildDegreeMap(nodes, edges);
  const issues: HealthIssue[] = [];

  const zeroDegree = nodes.filter((n) => (degrees[n.id] || 0) === 0);
  if (zeroDegree.length) {
    issues.push({
      kind: "zero_degree",
      label: "\u5B64\u7ACB\u8282\u70B9",
      severity: "warn",
      items: zeroDegree.slice(0, 8).map((n) => ({ id: n.id, name: n.name, type: nodeType(n) })),
      total: zeroDegree.length,
    });
  }

  const edgePairs = new Set<string>();
  const oneWay: GraphEdgeVM[] = [];
  for (const e of edges) edgePairs.add(`${e.source_id}|${e.target_id}`);
  for (const e of edges) {
    if (!edgePairs.has(`${e.target_id}|${e.source_id}`)) oneWay.push(e);
  }
  if (oneWay.length) {
    issues.push({
      kind: "one_way",
      label: "\u5355\u65B9\u9762\u5173\u7CFB",
      severity: "info",
      items: oneWay.slice(0, 6).map((e) => ({
        id: e.id,
        name: `${e.source_name} \u2192 ${e.target_name}\uFF08${e.name || "\u5173\u8054"}\uFF09`,
      })),
      total: oneWay.length,
    });
  }

  const unknowns = nodes.filter((n) => nodeType(n) === "unknown");
  if (unknowns.length) {
    issues.push({
      kind: "unknown_type",
      label: "\u672A\u5206\u7C7B\u8282\u70B9",
      severity: "warn",
      items: unknowns.slice(0, 6).map((n) => ({ id: n.id, name: n.name })),
      total: unknowns.length,
    });
  }

  return issues;
}

/* ---- Top-level aggregator ---- */

export function buildWorldOverview({
  nodes = [],
  edges = [],
  projectName = "",
}: {
  nodes?: GraphNodeVM[];
  edges?: GraphEdgeVM[];
  projectName?: string;
} = {}): WorldOverview {
  const displayNodes = compactOverviewNodes(nodes);
  const displayEdges = compactOverviewEdges(edges);
  const displayProjectName = sanitizeDisplayText(projectName, { emptyLabel: "" });

  return {
    hero: buildHeroSummary({ nodes: displayNodes, edges: displayEdges, projectName: displayProjectName }),
    cast: buildCastRadar({ nodes: displayNodes, edges: displayEdges }),
    highlights: buildRelationshipHighlights({ nodes: displayNodes, edges: displayEdges }),
    timeline: buildEventTimeline({ nodes: displayNodes, edges: displayEdges }),
    rules: buildWorldRules({ nodes: displayNodes, edges: displayEdges }),
    hooks: buildStoryHooks({ nodes: displayNodes, edges: displayEdges }),
    health: buildHealthCheck({ nodes: displayNodes, edges: displayEdges }),
  };
}
