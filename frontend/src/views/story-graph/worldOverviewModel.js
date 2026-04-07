// 世界速览 Dashboard 的所有派生算法。
// 纯函数，输入 { nodes, edges, projectName? }，输出可直接喂给卡片组件的结构。
// 所有算法都是启发式（无需 LLM），离线即可跑。

// ---- 通用工具 ---------------------------------------------------------------

const TIER_RANK = { protagonist: 0, major: 1, supporting: 2, minor: 3 };

function nodeTier(node) {
  return (node?.attributes?.importance_tier || "supporting").toLowerCase();
}

function nodeType(node) {
  return String(node?.entity_type || "unknown").toLowerCase();
}

function buildDegreeMap(nodes, edges) {
  const map = Object.fromEntries(nodes.map((n) => [n.id, 0]));
  for (const edge of edges) {
    if (edge.source_id in map) map[edge.source_id] += 1;
    if (edge.target_id in map) map[edge.target_id] += 1;
  }
  return map;
}

function buildNodeIndex(nodes) {
  return Object.fromEntries(nodes.map((n) => [n.id, n]));
}

function tierWeight(tier) {
  return ({ protagonist: 4, major: 3, supporting: 2, minor: 1 })[tier] || 1;
}

// ---- Hero 卡片 --------------------------------------------------------------

export function buildHeroSummary({ nodes = [], edges = [], projectName = "" } = {}) {
  const totalNodes = nodes.length;
  const totalEdges = edges.length;
  const typeSet = new Set(nodes.map(nodeType).filter((t) => t && t !== "unknown"));
  const protagonists = nodes.filter((n) => nodeTier(n) === "protagonist");
  const majorOrgs = nodes.filter(
    (n) => ["organization", "faction", "group"].includes(nodeType(n)) && nodeTier(n) !== "minor"
  );
  const eventNodes = nodes.filter((n) => nodeType(n) === "plotevent");

  return {
    projectName: projectName || "未命名小说",
    totalNodes,
    totalEdges,
    typeCount: typeSet.size,
    protagonistNames: protagonists.slice(0, 3).map((n) => n.name),
    majorOrgNames: majorOrgs.slice(0, 3).map((n) => n.name),
    eventCount: eventNodes.length,
    headline: buildHeadline({ protagonists, majorOrgs, eventNodes }),
  };
}

function buildHeadline({ protagonists, majorOrgs, eventNodes }) {
  if (!protagonists.length && !majorOrgs.length) {
    return "尚未识别出主角与主要势力，可在阅读笔记中补充关键人物。";
  }
  const lead = protagonists[0]?.name || majorOrgs[0]?.name || "主线";
  const opp = majorOrgs[0]?.name || protagonists[1]?.name || "未知阵营";
  const events = eventNodes.length;
  return `主线：${lead} ⚔ ${opp}　·　${events} 个剧情事件`;
}

// ---- Cast Radar 卡片 --------------------------------------------------------

export function buildCastRadar({ nodes = [], edges = [] } = {}) {
  const degrees = buildDegreeMap(nodes, edges);
  const characters = nodes.filter((n) => nodeType(n) === "character");
  const orgs = nodes.filter((n) =>
    ["organization", "faction", "group"].includes(nodeType(n))
  );

  const grouped = { protagonist: [], major: [], supporting: [], minor: [] };
  for (const c of characters) {
    const t = nodeTier(c);
    (grouped[t] || grouped.supporting).push({
      id: c.id,
      name: c.name,
      summary: c.summary || "",
      tier: t,
      degree: degrees[c.id] || 0,
      aliases: c.attributes?.aliases || [],
    });
  }

  for (const tier of Object.keys(grouped)) {
    grouped[tier].sort((a, b) => b.degree - a.degree);
  }

  const orgList = orgs
    .map((o) => ({
      id: o.id,
      name: o.name,
      summary: o.summary || "",
      type: nodeType(o),
      degree: degrees[o.id] || 0,
    }))
    .sort((a, b) => b.degree - a.degree);

  return {
    protagonist: grouped.protagonist,
    major: grouped.major,
    supporting: grouped.supporting,
    minor: grouped.minor,
    organizations: orgList,
    totalCharacters: characters.length,
  };
}

// ---- Relationship Highlights 卡片 ------------------------------------------

const CONFLICT_KEYWORDS = ["敌", "反目", "背叛", "冲突", "仇", "杀", "对立", "hostile", "conflict", "betray"];
const ROMANCE_KEYWORDS = ["爱", "情", "恋", "夫妻", "romance", "love"];

function isConflictEdge(edge) {
  const text = `${edge.name || ""} ${edge.fact || ""}`.toLowerCase();
  return CONFLICT_KEYWORDS.some((k) => text.includes(k.toLowerCase()));
}

function isRomanceEdge(edge) {
  const text = `${edge.name || ""} ${edge.fact || ""}`.toLowerCase();
  return ROMANCE_KEYWORDS.some((k) => text.includes(k.toLowerCase()));
}

export function buildRelationshipHighlights({ nodes = [], edges = [] } = {}) {
  const nodeIndex = buildNodeIndex(nodes);
  const degrees = buildDegreeMap(nodes, edges);

  const enriched = edges
    .map((e) => {
      const src = nodeIndex[e.source_id];
      const tgt = nodeIndex[e.target_id];
      if (!src || !tgt) return null;
      const tierBoost = tierWeight(nodeTier(src)) + tierWeight(nodeTier(tgt));
      return {
        ...e,
        score: (e.weight || 1) * tierBoost,
        src,
        tgt,
      };
    })
    .filter(Boolean);

  const topBonds = enriched
    .slice()
    .sort((a, b) => b.score - a.score)
    .slice(0, 5)
    .map(formatHighlightEdge);

  const conflicts = enriched
    .filter(isConflictEdge)
    .sort((a, b) => b.score - a.score)
    .slice(0, 5)
    .map(formatHighlightEdge);

  const triangles = findTriangles(nodes, enriched).slice(0, 3);

  const orphans = nodes
    .filter((n) => nodeType(n) === "character" && (degrees[n.id] || 0) <= 1)
    .map((n) => ({
      id: n.id,
      name: n.name,
      tier: nodeTier(n),
      degree: degrees[n.id] || 0,
    }))
    .slice(0, 6);

  return {
    topBonds,
    conflicts,
    triangles,
    orphans,
  };
}

function formatHighlightEdge(edge) {
  return {
    id: edge.id,
    source_id: edge.source_id,
    target_id: edge.target_id,
    sourceName: edge.src.name,
    targetName: edge.tgt.name,
    label: edge.name || "关联",
    fact: edge.fact || "",
    weight: edge.weight || 1,
  };
}

function findTriangles(nodes, edges) {
  const adj = new Map();
  for (const e of edges) {
    if (!adj.has(e.source_id)) adj.set(e.source_id, new Set());
    if (!adj.has(e.target_id)) adj.set(e.target_id, new Set());
    adj.get(e.source_id).add(e.target_id);
    adj.get(e.target_id).add(e.source_id);
  }
  const ids = nodes
    .filter((n) => nodeType(n) === "character")
    .map((n) => n.id)
    .slice(0, 80); // 上限 80 防止 O(n^3) 爆炸
  const triangles = [];
  const seen = new Set();
  for (let i = 0; i < ids.length; i++) {
    for (let j = i + 1; j < ids.length; j++) {
      if (!adj.get(ids[i])?.has(ids[j])) continue;
      for (let k = j + 1; k < ids.length; k++) {
        if (adj.get(ids[i])?.has(ids[k]) && adj.get(ids[j])?.has(ids[k])) {
          const key = [ids[i], ids[j], ids[k]].sort().join("|");
          if (seen.has(key)) continue;
          seen.add(key);
          const involved = [ids[i], ids[j], ids[k]];
          // 检查是否至少一条边是情感类
          const hasRomance = edges.some(
            (e) =>
              involved.includes(e.source_id) &&
              involved.includes(e.target_id) &&
              isRomanceEdge(e)
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

// ---- Event Timeline 卡片 ----------------------------------------------------

export function buildEventTimeline({ nodes = [], edges = [] } = {}) {
  const events = nodes.filter((n) => nodeType(n) === "plotevent");
  const nodeIndex = buildNodeIndex(nodes);
  const items = events.map((e) => {
    const chapterId = String(e.attributes?.chapter_id || "");
    const order = parseChapterOrder(chapterId);
    const incoming = edges.filter((edge) => edge.target_id === e.id);
    const participants = incoming
      .map((edge) => nodeIndex[edge.source_id])
      .filter(Boolean)
      .map((n) => ({ id: n.id, name: n.name, type: nodeType(n) }));
    return {
      id: e.id,
      name: e.name,
      summary: e.summary || "",
      chapterId,
      order,
      participants,
    };
  });
  items.sort((a, b) => a.order - b.order);
  return items;
}

function parseChapterOrder(chapterId) {
  const m = String(chapterId || "").match(/(\d+)/);
  return m ? parseInt(m[1], 10) : Number.MAX_SAFE_INTEGER;
}

// ---- World Rules 卡片 -------------------------------------------------------

export function buildWorldRules({ nodes = [], edges = [] } = {}) {
  const rules = nodes.filter((n) => nodeType(n) === "rulesystem");
  const nodeIndex = buildNodeIndex(nodes);
  return rules.map((r) => {
    const incoming = edges.filter((e) => e.target_id === r.id);
    const linked = incoming
      .map((e) => nodeIndex[e.source_id])
      .filter(Boolean)
      .slice(0, 6)
      .map((n) => ({ id: n.id, name: n.name, type: nodeType(n) }));
    return {
      id: r.id,
      name: r.name,
      summary: r.summary || r.attributes?.rule_text || "",
      linked,
    };
  });
}

// ---- Story Hooks 卡片（最高价值）-------------------------------------------

export function buildStoryHooks({ nodes = [], edges = [] } = {}) {
  const nodeIndex = buildNodeIndex(nodes);
  const degrees = buildDegreeMap(nodes, edges);
  const hooks = [];

  // Hook A: 高 tier 角色但出现极少 → "尚未登场"
  const idleHighTier = nodes
    .filter(
      (n) =>
        nodeType(n) === "character" &&
        ["protagonist", "major"].includes(nodeTier(n)) &&
        (degrees[n.id] || 0) <= 1
    )
    .slice(0, 3);
  for (const c of idleHighTier) {
    hooks.push({
      kind: "idle_character",
      title: `「${c.name}」尚未真正登场`,
      body: `${c.name} 被标记为${nodeTier(c) === "protagonist" ? "主角" : "主要角色"}，但目前几乎没有关联事件。可写一场让 TA 正式入场的戏。`,
      involvedIds: [c.id],
      involvedNames: [c.name],
    });
  }

  // Hook B: 高权重 + 冲突关系 → 矛盾爆点
  const conflictEdges = edges
    .filter(isConflictEdge)
    .map((e) => ({
      ...e,
      src: nodeIndex[e.source_id],
      tgt: nodeIndex[e.target_id],
    }))
    .filter((e) => e.src && e.tgt)
    .sort((a, b) => (b.weight || 1) - (a.weight || 1))
    .slice(0, 3);
  for (const e of conflictEdges) {
    hooks.push({
      kind: "conflict_peak",
      title: `${e.src.name} 与 ${e.tgt.name} 的冲突已到爆点`,
      body: `${e.fact || e.name || "矛盾"}（关联强度 ${e.weight || 1}）。可写 TA 们的正面对决或一次决定性的背叛。`,
      involvedIds: [e.src.id, e.tgt.id],
      involvedNames: [e.src.name, e.tgt.name],
    });
  }

  // Hook C: 跨组织桥梁角色 → 卧底/双面人
  const orgs = nodes.filter((n) =>
    ["organization", "faction", "group"].includes(nodeType(n))
  );
  if (orgs.length >= 2) {
    const orgIds = new Set(orgs.map((o) => o.id));
    const charOrgLinks = new Map(); // charId -> Set<orgId>
    for (const e of edges) {
      const sIsChar = nodeIndex[e.source_id] && nodeType(nodeIndex[e.source_id]) === "character";
      const tIsOrg = orgIds.has(e.target_id);
      if (sIsChar && tIsOrg) {
        if (!charOrgLinks.has(e.source_id)) charOrgLinks.set(e.source_id, new Set());
        charOrgLinks.get(e.source_id).add(e.target_id);
      }
    }
    let count = 0;
    for (const [charId, orgSet] of charOrgLinks) {
      if (orgSet.size >= 2 && count < 2) {
        const char = nodeIndex[charId];
        const orgNames = [...orgSet].map((id) => nodeIndex[id]?.name).filter(Boolean);
        hooks.push({
          kind: "bridge",
          title: `${char.name} 同时关联 ${orgNames.length} 个阵营`,
          body: `${char.name} 与 ${orgNames.join("、")} 都有归属关联，可作为卧底、双面人或调停者写一段忠诚危机。`,
          involvedIds: [charId, ...orgSet],
          involvedNames: [char.name, ...orgNames],
        });
        count++;
      }
    }
  }

  // Hook D: 未触发的世界规则
  const ruleNodes = nodes.filter((n) => nodeType(n) === "rulesystem");
  const usedRuleIds = new Set(edges.map((e) => e.target_id));
  const idleRules = ruleNodes.filter((r) => !usedRuleIds.has(r.id)).slice(0, 2);
  for (const r of idleRules) {
    hooks.push({
      kind: "idle_rule",
      title: `世界规则「${r.name}」尚未发挥作用`,
      body: `这条设定还没有任何角色或事件触发它。可写一场让 TA 第一次显灵或被打破的戏。`,
      involvedIds: [r.id],
      involvedNames: [r.name],
    });
  }

  return hooks.slice(0, 10);
}

// ---- Health Check 卡片 ------------------------------------------------------

export function buildHealthCheck({ nodes = [], edges = [] } = {}) {
  const degrees = buildDegreeMap(nodes, edges);
  const issues = [];

  // 0 度节点
  const zeroDegree = nodes.filter((n) => (degrees[n.id] || 0) === 0);
  if (zeroDegree.length) {
    issues.push({
      kind: "zero_degree",
      label: "孤立节点",
      severity: "warn",
      items: zeroDegree.slice(0, 8).map((n) => ({ id: n.id, name: n.name, type: nodeType(n) })),
      total: zeroDegree.length,
    });
  }

  // 单方面关系
  const edgePairs = new Set();
  const oneWay = [];
  for (const e of edges) {
    edgePairs.add(`${e.source_id}|${e.target_id}`);
  }
  for (const e of edges) {
    if (!edgePairs.has(`${e.target_id}|${e.source_id}`)) {
      oneWay.push(e);
    }
  }
  if (oneWay.length) {
    issues.push({
      kind: "one_way",
      label: "单方面关系",
      severity: "info",
      items: oneWay.slice(0, 6).map((e) => ({
        id: e.id,
        name: `${e.source_name} → ${e.target_name}（${e.name || "关联"}）`,
      })),
      total: oneWay.length,
    });
  }

  // unknown 类型
  const unknowns = nodes.filter((n) => nodeType(n) === "unknown");
  if (unknowns.length) {
    issues.push({
      kind: "unknown_type",
      label: "未分类节点",
      severity: "warn",
      items: unknowns.slice(0, 6).map((n) => ({ id: n.id, name: n.name })),
      total: unknowns.length,
    });
  }

  return issues;
}

// ---- 顶层聚合 ---------------------------------------------------------------

export function buildWorldOverview({ nodes = [], edges = [], projectName = "" } = {}) {
  return {
    hero: buildHeroSummary({ nodes, edges, projectName }),
    cast: buildCastRadar({ nodes, edges }),
    highlights: buildRelationshipHighlights({ nodes, edges }),
    timeline: buildEventTimeline({ nodes, edges }),
    rules: buildWorldRules({ nodes, edges }),
    hooks: buildStoryHooks({ nodes, edges }),
    health: buildHealthCheck({ nodes, edges }),
  };
}
