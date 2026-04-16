import { describe, expect, it } from "vitest";

import type { GraphNodeVM } from "./graph-view-model";
import { describeStage, formatCounts } from "./build-stage-meta";
import { buildWorldOverview } from "./world-overview-model";

describe("story graph display text", () => {
  it("decodes escaped unicode entity text before building user-facing overview", () => {
    const nodes: GraphNodeVM[] = [
      {
        id: "char-1",
        name: "\\u53F6\\u5B50",
        entity_type: "Character",
        summary: "\\u4E3B\\u89D2",
        attributes: { importance_tier: "protagonist" },
      },
    ];

    const overview = buildWorldOverview({ nodes, edges: [], projectName: "\\u6211\\u7684\\u5C0F\\u8BF4" });

    expect(overview.hero.projectName).toBe("我的小说");
    expect(overview.hero.protagonistNames).toEqual(["叶子"]);
    expect(overview.hero.headline).toContain("叶子");
    expect(overview.cast.protagonist[0]?.summary).toBe("主角");
  });

  it("keeps build progress labels free of engineering storage names", () => {
    const persistMeta = describeStage("persist");
    const loadMeta = describeStage("load_artifacts");
    const counts = formatCounts({
      artifacts_loaded: 4,
      source_artifacts: { story_memory: 1 },
      storage_path: "/tmp/project/story_graph.sqlite3",
    });

    expect(`${persistMeta.title} ${persistMeta.description}`).not.toMatch(/JSON|SQLite|sqlite|\.json/i);
    expect(`${loadMeta.title} ${loadMeta.description}`).not.toMatch(/artifact|local_block|story_memory/i);
    expect(counts).not.toMatch(/source_artifacts|storage_path|story_graph|sqlite|\/tmp/i);
  });

  it("compacts sentence-like entity names before composing overview hooks", () => {
    const longName = "云在天空中飘荡着，云上淡淡的月光；夜已经深了，平原上浩浩荡荡的动静还未有停歇下来";
    const nodes: GraphNodeVM[] = [
      {
        id: "char-1",
        name: "莱茵帝国",
        entity_type: "Character",
        summary: "边境势力",
        attributes: { importance_tier: "major" },
      },
      {
        id: "char-2",
        name: longName,
        entity_type: "Character",
        summary: longName,
        attributes: { importance_tier: "major" },
      },
    ];
    const overview = buildWorldOverview({
      nodes,
      edges: [{
        id: "edge-1",
        source_id: "char-1",
        target_id: "char-2",
        source_name: "莱茵帝国",
        target_name: longName,
        name: "冲突",
        fact: longName,
        weight: 1,
      }],
      projectName: "我的小说",
    });

    const hook = overview.hooks.find((item) => item.kind === "conflict_peak");

    expect(hook?.title).not.toContain("浩浩荡荡");
    expect(hook?.body).not.toContain("停歇下来");
    expect(hook?.title.length).toBeLessThanOrEqual(72);
    expect(hook?.body.length).toBeLessThanOrEqual(140);
  });

  it("translates machine relationship labels into Chinese overview copy", () => {
    const nodes: GraphNodeVM[] = [
      { id: "a", name: "乌家", entity_type: "Character", summary: "", attributes: { importance_tier: "major" } },
      { id: "b", name: "苏家", entity_type: "Character", summary: "", attributes: { importance_tier: "major" } },
    ];
    const overview = buildWorldOverview({
      nodes,
      edges: [{
        id: "edge-1",
        source_id: "a",
        target_id: "b",
        source_name: "乌家",
        target_name: "苏家",
        name: "CO_APPEARS_WITH",
        fact: "conflict",
        weight: 1,
      }],
      projectName: "我的小说",
    });

    const topBond = overview.highlights.topBonds[0];
    const hook = overview.hooks.find((item) => item.kind === "conflict_peak");

    expect(topBond?.label).toBe("共同出现");
    expect(hook?.body).toContain("冲突");
    expect(hook?.body).not.toContain("conflict");
    expect(hook?.body).not.toContain("CO_APPEARS_WITH");
  });
});
