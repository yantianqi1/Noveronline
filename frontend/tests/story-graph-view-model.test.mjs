import test from "node:test";
import assert from "node:assert/strict";

import {
  buildGraphDisplayState,
  shouldRenderNodeLabels,
} from "../src/views/story-graph/storyGraphViewModel.js";

test("buildGraphDisplayState hides noisy types by default and keeps core relations", () => {
  const nodes = [
    { id: "char_1", name: "陈迹", entity_type: "Character" },
    { id: "org_1", name: "密谍司", entity_type: "Organization" },
    { id: "faction_1", name: "景朝", entity_type: "Faction" },
    { id: "loc_1", name: "出门", entity_type: "Location" },
    { id: "event_1", name: "审讯周成义", entity_type: "PlotEvent" },
  ];
  const edges = [
    { id: "edge_1", source_id: "char_1", target_id: "org_1", name: "效忠" },
    { id: "edge_2", source_id: "char_1", target_id: "loc_1", name: "位于" },
    { id: "edge_3", source_id: "org_1", target_id: "faction_1", name: "隶属" },
    { id: "edge_4", source_id: "event_1", target_id: "char_1", name: "参与" },
  ];

  const state = buildGraphDisplayState({ nodes, edges });

  assert.deepEqual(
    state.visibleNodes.map((node) => node.id),
    ["char_1", "org_1", "faction_1"],
  );
  assert.deepEqual(
    state.visibleEdges.map((edge) => edge.id),
    ["edge_1", "edge_3"],
  );
});

test("shouldRenderNodeLabels hides labels when the graph is dense", () => {
  assert.equal(shouldRenderNodeLabels(12), true);
  assert.equal(shouldRenderNodeLabels(48), false);
});
