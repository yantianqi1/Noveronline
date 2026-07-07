import { describe, expect, it } from "vitest";

import { buildSaasWriterRunPayload } from "./writer-workbench-state";

describe("buildSaasWriterRunPayload", () => {
  it("carries explicit writer reference selections into v1 run options", () => {
    const payload = buildSaasWriterRunPayload({
      taskType: "continue",
      chapterId: "chapter-1",
      selectedSceneId: "scene-2",
      authorInstruction: "续写塔下重逢",
      sceneFocus: "塔下",
      moduleKey: "writer_composer",
      selectedAssetIds: ["asset-1", "asset-2"],
      worldlinePathIds: ["path-main"],
      characterNames: ["顾行舟", "沈照"],
      graphNodeNames: ["废塔"],
      assetQuery: "机关线索",
      worldRuleQuery: "禁术代价",
    });

    expect(payload).toEqual({
      mode: "continue",
      chapter_id: "chapter-1",
      scene_id: "scene-2",
      instruction: "续写塔下重逢",
      options: {
        module_key: "writer_composer",
        selected_asset_ids: ["asset-1", "asset-2"],
        worldline_path_ids: ["path-main"],
        character_names: ["顾行舟", "沈照"],
        graph_node_names: ["废塔"],
        asset_query: "机关线索",
        world_rule_query: "禁术代价",
      },
    });
  });

  it("omits empty references and falls back to scene focus for instruction", () => {
    const payload = buildSaasWriterRunPayload({
      taskType: "write_scene",
      chapterId: "",
      selectedSceneId: "",
      authorInstruction: "   ",
      sceneFocus: "破门",
      moduleKey: "writer_composer",
      selectedAssetIds: [],
      worldlinePathIds: [""],
      characterNames: ["", "沈照"],
      graphNodeNames: [],
      assetQuery: "",
      worldRuleQuery: "   ",
    });

    expect(payload).toEqual({
      mode: "draft",
      instruction: "破门",
      options: {
        module_key: "writer_composer",
        character_names: ["沈照"],
      },
    });
  });
});
