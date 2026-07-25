import assert from "node:assert/strict";
import test from "node:test";

// graph-concept.ts is pure presentation logic with only a type-only import, so
// Node's native TS support can import and exercise the real functions (no mocks).
const {
  resolveConcept,
  layerKeyOf,
  worldGroupLabel,
  isConceptLayerKey,
  CONCEPT_LAYER_KEYS,
} = await import("../app/projects/[projectId]/graph/graph-concept.ts");

function conceptNode({ title, category, tags = [], payload = {} }) {
  return {
    node_type: "concept",
    title,
    attributes: { category, tags, payload },
  };
}

test("resolveConcept returns null for non-concept nodes", () => {
  assert.equal(resolveConcept({ node_type: "character", title: "沈翠花", attributes: {} }), null);
});

test("timeline events (category=analysis / note_summary) resolve to the event subtype", () => {
  const byCategory = resolveConcept(conceptNode({ title: "x", category: "analysis" }));
  assert.equal(byCategory.subtype, "event");
  assert.equal(byCategory.subtypeLabel, "分析·事件");

  const byTag = resolveConcept(conceptNode({ title: "x", category: "", tags: ["note_summary"] }));
  assert.equal(byTag.subtype, "event");
});

test("world rules (category=world / world_rule) resolve to the world subtype and keep good titles", () => {
  const info = resolveConcept(
    conceptNode({ title: "青山医院", category: "world", tags: ["world_rule"], payload: { world: "modern" } }),
  );
  assert.equal(info.subtype, "world");
  assert.equal(info.subtypeLabel, "世界观·设定");
  assert.equal(info.displayTitle, "青山医院");
  assert.equal(info.isUntitled, false);
  assert.equal(info.world, "现代");
});

test("placeholder event titles are replaced with a readable 世界·时间 tag and flagged 待命名", () => {
  const info = resolveConcept(
    conceptNode({
      title: "note_summary",
      category: "analysis",
      payload: { world: "ancient", timeframe: "Day 1 (Ancient) - Night" },
    }),
  );
  assert.equal(info.subtype, "event");
  assert.equal(info.isUntitled, true);
  assert.equal(info.displayTitle, "古代 · 第1天·夜");
});

test("empty timeframe still yields a stable untitled label", () => {
  const info = resolveConcept(conceptNode({ title: "note_summary", category: "analysis", payload: {} }));
  assert.equal(info.isUntitled, true);
  assert.equal(info.displayTitle, "未命名事件");
});

test("English-sentence event titles surface their Chinese lead when present", () => {
  const info = resolveConcept(
    conceptNode({ title: "Shen Cuihua returns to 青山医院 at dawn", category: "analysis", payload: {} }),
  );
  assert.equal(info.displayTitle, "青山医院");
  assert.equal(info.isUntitled, false);
});

test("layerKeyOf fans concepts out by subtype and keeps entities on their node_type", () => {
  assert.equal(layerKeyOf({ node_type: "character", title: "x", attributes: {} }), "character");
  assert.equal(
    layerKeyOf(conceptNode({ title: "x", category: "analysis" })),
    "concept:event",
  );
  assert.equal(
    layerKeyOf(conceptNode({ title: "x", category: "world" })),
    "concept:world",
  );
  assert.equal(layerKeyOf(conceptNode({ title: "x", category: "" })), "concept:concept");
});

test("worldGroupLabel translates payload worlds and defaults to 设定", () => {
  assert.equal(worldGroupLabel("modern"), "现代");
  assert.equal(worldGroupLabel("ancient"), "古代");
  assert.equal(worldGroupLabel(""), "设定");
  assert.equal(worldGroupLabel("other"), "设定");
});

test("concept layer keys are recognised and ordered", () => {
  assert.deepEqual([...CONCEPT_LAYER_KEYS], ["concept:event", "concept:world", "concept:concept"]);
  for (const key of CONCEPT_LAYER_KEYS) assert.equal(isConceptLayerKey(key), true);
  assert.equal(isConceptLayerKey("character"), false);
});
