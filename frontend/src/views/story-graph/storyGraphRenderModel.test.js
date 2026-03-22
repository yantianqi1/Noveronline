import test from "node:test";
import assert from "node:assert/strict";

import {
  buildLegendItems,
  buildRenderableGraphData,
  getTypeColor,
} from "./storyGraphRenderModel.js";

const nodes = [
  { id: "n1", name: "沈星", entity_type: "Character" },
  { id: "n2", name: "青岚会", entity_type: "organization" },
  { id: "n3", name: "北境盟", entity_type: "Faction" },
  { id: "n4", name: "断剑", entity_type: "artifact" },
  { id: "n5", name: "未知物", entity_type: "" },
];

test("同一对节点的多条边会生成不同曲率索引", () => {
  const { edges } = buildRenderableGraphData({
    nodes,
    edges: [
      { id: "e1", source_id: "n1", target_id: "n2", name: "加入" },
      { id: "e2", source_id: "n2", target_id: "n1", name: "吸纳" },
      { id: "e3", source_id: "n1", target_id: "n2", name: "背叛" },
    ],
  });

  const pairEdges = edges.filter((edge) => edge.pairKey === "n1::n2");

  assert.equal(pairEdges.length, 3);
  assert.deepEqual(
    pairEdges.map((edge) => edge.curvatureIndex),
    [-1, 0, 1],
  );
  assert.equal(pairEdges.every((edge) => edge.curvature !== 0), true);
});

test("自环边会被标记为自环并生成圆弧元数据", () => {
  const { edges } = buildRenderableGraphData({
    nodes,
    edges: [{ id: "loop-1", source_id: "n3", target_id: "n3", name: "牵制自身" }],
  });

  assert.equal(edges.length, 1);
  assert.equal(edges[0].isSelfLoop, true);
  assert.equal(edges[0].loopRadius, 30);
  assert.equal(edges[0].arcSweepFlag, 1);
});

test("实体类型会稳定映射到固定颜色", () => {
  assert.equal(getTypeColor("character"), "#FF6B35");
  assert.equal(getTypeColor("organization"), "#004E89");
  assert.equal(getTypeColor("faction"), "#7B2D8E");
  assert.equal(getTypeColor("artifact"), "#C5283D");
  assert.equal(getTypeColor("unknown"), "#f39c12");
  assert.equal(getTypeColor("Character"), "#FF6B35");
});

test("图例顺序优先跟随过滤顺序，未出现在过滤清单中的类型排在后面", () => {
  const items = buildLegendItems({
    nodes,
    typeOptions: [
      { key: "character", label: "角色" },
      { key: "organization", label: "组织" },
      { key: "faction", label: "势力" },
      { key: "artifact", label: "物件" },
    ],
  });

  assert.deepEqual(
    items.map((item) => item.key),
    ["character", "organization", "faction", "artifact", "unknown"],
  );
  assert.equal(items[0].label, "角色");
  assert.equal(items.at(-1)?.count, 1);
});
