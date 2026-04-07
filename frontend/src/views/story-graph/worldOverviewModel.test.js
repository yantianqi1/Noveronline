import test from "node:test";
import assert from "node:assert/strict";

import {
  buildHeroSummary,
  buildCastRadar,
  buildRelationshipHighlights,
  buildEventTimeline,
  buildStoryHooks,
  buildHealthCheck,
  buildWorldOverview,
} from "./worldOverviewModel.js";

// Fixture: tiny novel world
const nodes = [
  { id: "c1", name: "林惊羽", entity_type: "character", summary: "主角少年", attributes: { importance_tier: "protagonist", aliases: ["阿羽"] } },
  { id: "c2", name: "苏璃", entity_type: "character", summary: "师姐", attributes: { importance_tier: "major" } },
  { id: "c3", name: "暗夜使", entity_type: "character", summary: "反派", attributes: { importance_tier: "major" } },
  { id: "c4", name: "孤儿少年", entity_type: "character", summary: "", attributes: { importance_tier: "supporting" } },
  { id: "c5", name: "未登场主角", entity_type: "character", summary: "", attributes: { importance_tier: "protagonist" } },
  { id: "o1", name: "北冥宗", entity_type: "organization", attributes: { importance_tier: "major" } },
  { id: "o2", name: "黑魔教", entity_type: "faction", attributes: { importance_tier: "major" } },
  { id: "e1", name: "山门初遇", entity_type: "plotevent", summary: "林惊羽踏入北冥宗", attributes: { chapter_id: "ch1" } },
  { id: "e2", name: "盗诀风波", entity_type: "plotevent", summary: "秘籍被盗", attributes: { chapter_id: "ch7" } },
  { id: "r1", name: "宗门戒律", entity_type: "rulesystem", summary: "门下不得私斗", attributes: {} },
  { id: "r2", name: "未触发规则", entity_type: "rulesystem", summary: "", attributes: {} },
  { id: "u1", name: "未知物", entity_type: "unknown", attributes: {} },
];

const edges = [
  { id: "e_lc_su", source_id: "c1", target_id: "c2", source_name: "林惊羽", target_name: "苏璃", name: "ALLIED_WITH", fact: "并肩作战", weight: 4 },
  { id: "e_lc_an", source_id: "c1", target_id: "c3", source_name: "林惊羽", target_name: "暗夜使", name: "CONFLICTS_WITH", fact: "敌对仇杀", weight: 6 },
  { id: "e_su_lc", source_id: "c2", target_id: "c1", source_name: "苏璃", target_name: "林惊羽", name: "情感羁绊", fact: "暗生情愫", weight: 2 },
  { id: "e_lc_o1", source_id: "c1", target_id: "o1", source_name: "林惊羽", target_name: "北冥宗", name: "BELONGS_TO", fact: "弟子", weight: 3 },
  { id: "e_lc_o2", source_id: "c1", target_id: "o2", source_name: "林惊羽", target_name: "黑魔教", name: "INFILTRATES", fact: "卧底", weight: 1 },
  { id: "e_lc_e1", source_id: "c1", target_id: "e1", source_name: "林惊羽", target_name: "山门初遇", name: "PARTICIPATES_IN", fact: "", weight: 1 },
  { id: "e_su_e2", source_id: "c2", target_id: "e2", source_name: "苏璃", target_name: "盗诀风波", name: "PARTICIPATES_IN", fact: "", weight: 1 },
  { id: "e_lc_r1", source_id: "c1", target_id: "r1", source_name: "林惊羽", target_name: "宗门戒律", name: "OBEYS_RULE", fact: "", weight: 1 },
];

test("buildHeroSummary 给出总览数字与一句话", () => {
  const hero = buildHeroSummary({ nodes, edges, projectName: "长生剑诀" });
  assert.equal(hero.projectName, "长生剑诀");
  assert.equal(hero.totalNodes, nodes.length);
  assert.equal(hero.totalEdges, edges.length);
  assert.ok(hero.protagonistNames.includes("林惊羽"));
  assert.equal(hero.eventCount, 2);
  assert.match(hero.headline, /林惊羽|主线/);
});

test("buildCastRadar 按 tier 分组并按 degree 排序", () => {
  const cast = buildCastRadar({ nodes, edges });
  assert.equal(cast.protagonist[0].name, "林惊羽");
  assert.ok(cast.protagonist.find((c) => c.name === "未登场主角"));
  assert.ok(cast.major.length >= 2);
  assert.equal(cast.organizations[0].name, "北冥宗");
});

test("buildRelationshipHighlights 抽出核心羁绊与冲突", () => {
  const h = buildRelationshipHighlights({ nodes, edges });
  assert.ok(h.topBonds.length > 0);
  assert.ok(h.conflicts.some((c) => c.sourceName === "林惊羽" && c.targetName === "暗夜使"));
  // 孤儿警示：c4 孤儿少年 应被识别
  assert.ok(h.orphans.some((o) => o.name === "孤儿少年"));
});

test("buildEventTimeline 按 chapter 顺序排列", () => {
  const tl = buildEventTimeline({ nodes, edges });
  assert.equal(tl.length, 2);
  assert.equal(tl[0].chapterId, "ch1");
  assert.equal(tl[1].chapterId, "ch7");
  assert.ok(tl[0].participants.some((p) => p.name === "林惊羽"));
});

test("buildStoryHooks 至少给出一个跨阵营桥梁锚点和一个空闲规则锚点", () => {
  const hooks = buildStoryHooks({ nodes, edges });
  assert.ok(hooks.length > 0);
  const kinds = new Set(hooks.map((h) => h.kind));
  // 林惊羽同时连两个组织 → bridge
  assert.ok(kinds.has("bridge"));
  // 未触发规则
  assert.ok(kinds.has("idle_rule"));
  // 未登场主角
  assert.ok(kinds.has("idle_character"));
  // 高权重冲突
  assert.ok(kinds.has("conflict_peak"));
});

test("buildHealthCheck 报告 unknown 类型与孤立节点", () => {
  const issues = buildHealthCheck({ nodes, edges });
  const kinds = new Set(issues.map((i) => i.kind));
  assert.ok(kinds.has("unknown_type"));
  assert.ok(kinds.has("zero_degree")); // r2 未触发规则、c5 未登场主角、u1 等
});

test("buildWorldOverview 顶层聚合包含所有 7 个 section", () => {
  const ov = buildWorldOverview({ nodes, edges, projectName: "长生剑诀" });
  assert.ok(ov.hero);
  assert.ok(ov.cast);
  assert.ok(ov.highlights);
  assert.ok(ov.timeline);
  assert.ok(ov.rules);
  assert.ok(ov.hooks);
  assert.ok(ov.health);
});

test("空图谱不会崩", () => {
  const ov = buildWorldOverview({ nodes: [], edges: [] });
  assert.equal(ov.hero.totalNodes, 0);
  assert.deepEqual(ov.cast.protagonist, []);
  assert.deepEqual(ov.timeline, []);
});
