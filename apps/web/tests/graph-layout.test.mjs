import assert from "node:assert/strict";
import test from "node:test";

// graph-layout.ts imports d3-force (a real dependency) — exercising the true
// layout confirms banded concepts leave the force cast and file into tidy,
// non-overlapping shelves while characters stay in the constellation.
const { computeForceLayout } = await import("../app/projects/[projectId]/graph/graph-layout.ts");

let seq = 0;
function node(node_type, title, attributes = {}) {
  seq += 1;
  return {
    node_id: `n${seq}`,
    node_type,
    title,
    importance: 0.5,
    cluster_id: "",
    attributes,
  };
}

function character(id, title) {
  return { node_id: id, node_type: "character", title, importance: 0.8, cluster_id: "c1", attributes: {} };
}

const characters = [character("a", "沈翠花"), character("b", "顾晏"), character("c", "陆时衍")];
const charEdges = [
  { source_node_id: "a", target_node_id: "b", edge_type: "relationship", weight: 0.9 },
  { source_node_id: "b", target_node_id: "c", edge_type: "relationship", weight: 0.7 },
];

function eventNode(id, world) {
  return {
    node_id: id,
    node_type: "concept",
    title: "note_summary",
    importance: 0.4,
    cluster_id: "",
    attributes: { category: "analysis", tags: ["note_summary"], payload: { world, timeframe: "Day 1 - Night" } },
  };
}

test("banded concepts leave the force cast and land on shelves below it", () => {
  const events = [eventNode("e1", "modern"), eventNode("e2", "modern"), eventNode("e3", "ancient")];
  const nodes = [...characters, ...events];
  const bands = new Map([
    ["e1", { band: "event:现代", order: 1 }],
    ["e2", { band: "event:现代", order: 2 }],
    ["e3", { band: "event:古代", order: 1 }],
  ]);
  const layout = computeForceLayout(nodes, charEdges, 1100, { bands });

  // Every node is placed.
  for (const n of nodes) assert.ok(layout.has(n.node_id), `${n.node_id} placed`);

  // Banded events sit strictly below the lowest character (the constellation).
  const charMaxY = Math.max(...characters.map((c) => layout.get(c.node_id).y));
  for (const e of events) {
    assert.ok(layout.get(e.node_id).y > charMaxY, `${e.node_id} banded below constellation`);
  }
});

test("band members never overlap and deterministic order holds", () => {
  const events = Array.from({ length: 12 }, (_, i) => eventNode(`ev${i}`, "modern"));
  const bands = new Map(events.map((e, i) => [e.node_id, { band: "event:现代", order: i }]));
  const layout = computeForceLayout(events, [], 1100, { bands });

  const points = events.map((e) => layout.get(e.node_id));
  const keys = new Set(points.map((p) => `${Math.round(p.x)}:${Math.round(p.y)}`));
  assert.equal(keys.size, events.length, "each event occupies a distinct cell");

  // Same input → identical layout (deterministic).
  const again = computeForceLayout(events, [], 1100, { bands });
  for (const e of events) {
    assert.deepEqual(again.get(e.node_id), layout.get(e.node_id));
  }
});

test("nodes without a band entry stay in the force cast", () => {
  const layout = computeForceLayout(characters, charEdges, 1100, { bands: new Map() });
  // Linked characters pull together: the pair a–b is closer than the band gap.
  const a = layout.get("a");
  const b = layout.get("b");
  const dist = Math.hypot(a.x - b.x, a.y - b.y);
  assert.ok(dist > 0 && dist < 1100, "linked characters gather, not flung apart");
});
