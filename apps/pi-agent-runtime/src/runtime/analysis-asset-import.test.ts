import { describe, expect, it } from "vitest";
import { createHash } from "node:crypto";

import {
  composeAnalysisAssetTitle,
  mapAnalysisCandidateToAsset,
  normalizeAnalysisCandidateType,
} from "./analysis-asset-mapping.js";

describe("analysis auto-import mapping", () => {
  it("maps character candidates to library materials", () => {
    const mapped = mapAnalysisCandidateToAsset(
      normalizeAnalysisCandidateType("character"),
      "林深",
      { summary: "主角", tags: ["主线"] },
      "30-candidates/characters.json",
    );
    expect(mapped.asset_type).toBe("character");
    expect(mapped.category).toBe("characters");
    expect(mapped.title).toBe("林深");
    expect(mapped.summary).toBe("主角");
    expect(mapped.tags).toContain("pi_analysis");
    expect(mapped.payload.auto_imported).toBe(true);
  });

  it("maps note_summary and ontology to safe asset types", () => {
    expect(mapAnalysisCandidateToAsset("note_summary", "摘要", {}).asset_type).toBe("note");
    expect(mapAnalysisCandidateToAsset("ontology", "本体", {}).asset_type).toBe("story_ontology");
  });

  it("composes relationship title from source/target when name is a type key", () => {
    const mapped = mapAnalysisCandidateToAsset(
      "relationship",
      "relationship",
      {
        source: "林深",
        target: "静妃",
        relationship_type: "师徒",
        description: "静妃指点林深修炼",
      },
    );
    expect(mapped.title).toBe("林深 → 静妃 / 师徒");
    expect(mapped.summary).toBe("静妃指点林深修炼");
    expect(mapped.content_text).toContain("林深 → 静妃");
    expect(mapped.content_text).toContain("师徒");
  });

  it("composes note title from summary when name is type key", () => {
    const title = composeAnalysisAssetTitle("note_summary", "note_summary", {
      summary: "第一章揭示了林深身世与山海界入口",
    });
    expect(title).toContain("第一章揭示了林深身世");
    expect(title).not.toBe("note_summary");
  });

  it("maps plot_event to the plot category and keeps its asset type", () => {
    const mapped = mapAnalysisCandidateToAsset(
      "plot_event",
      "沈翠花夜探青山医院",
      { summary: "沈翠花夜探青山医院，发现冰流异动。", timeframe: "第1天·夜", world: "modern" },
      "30-candidates/timeline.json",
    );
    expect(mapped.asset_type).toBe("plot_event");
    expect(mapped.category).toBe("plot");
    expect(mapped.title).toBe("沈翠花夜探青山医院");
    expect(mapped.payload.analysis_candidate_type).toBe("plot_event");
  });

  it("never falls back to a bare type-key title for plot_event", () => {
    // Placeholder name + Chinese summary → summary composes the title.
    const fromSummary = composeAnalysisAssetTitle("plot_event", "plot_event", {
      summary: "沈翠花夜探青山医院，发现冰流异动。",
    });
    expect(fromSummary).toContain("沈翠花夜探青山医院");
    expect(fromSummary).not.toBe("plot_event");

    // No name/summary → readable untitled tag from timeframe, still not the key.
    const fromTimeframe = composeAnalysisAssetTitle("plot_event", "", { timeframe: "第2天·晨" });
    expect(fromTimeframe).toContain("未命名事件");
    expect(fromTimeframe).not.toBe("plot_event");

    // Nothing at all → readable untitled label, never the bare type key.
    expect(composeAnalysisAssetTitle("plot_event", "", {})).toBe("未命名事件");
  });

  it("never surfaces a bare type key as any asset title", () => {
    expect(composeAnalysisAssetTitle("note_summary", "", {})).not.toBe("note_summary");
    expect(composeAnalysisAssetTitle("note_summary", "", {})).toBe("未命名条目");
  });

  it("uses from/to aliases for relationships", () => {
    const title = composeAnalysisAssetTitle("relationship", "", {
      from: "A",
      to: "B",
      kind: "盟友",
    });
    expect(title).toBe("A → B / 盟友");
  });

  it("composes a rich character body from description", () => {
    const mapped = mapAnalysisCandidateToAsset("character", "陈迹", {
      summary: "军情司新人",
      description: "陈迹，舅舅陈守一培养的刀客，性格隐忍，为查父案潜入京城。",
    });
    expect(mapped.summary).toBe("军情司新人");
    expect(mapped.content_text).toContain("陈迹，舅舅陈守一培养的刀客");
    expect(mapped.content_text).toContain("军情司新人");
  });

  it("prefers an explicit body field for characters", () => {
    const mapped = mapAnalysisCandidateToAsset("character", "白鲤郡主", {
      summary: "短摘要",
      body: "一段完整的中文人物档案，覆盖身份、性格、动机与主线弧光。",
    });
    expect(mapped.content_text).toBe("一段完整的中文人物档案，覆盖身份、性格、动机与主线弧光。");
  });

  it("composes a rich world-rule body with evidence and meta", () => {
    const mapped = mapAnalysisCandidateToAsset("world_rule", "", {
      summary: "以太阳养剑可行",
      rule_text: "以太阳真火淬炼本命剑可成，但需每月朔日避雷劫，且耗寿三年。",
      evidence: "第二十一章：烈阳宗以日精养剑。",
      category: "world",
      confidence: "0.9",
    });
    expect(mapped.summary).toBe("以太阳养剑可行");
    expect(mapped.content_text).toContain("以太阳真火淬炼本命剑可成");
    expect(mapped.content_text).toContain("证据：第二十一章");
    expect(mapped.content_text).toContain("分类：world");
    expect(mapped.content_text).toContain("置信度：0.9");
  });

  it("composes a rich plot-event body with timeframe and participants", () => {
    const mapped = mapAnalysisCandidateToAsset("plot_event", "", {
      summary: "沈翠花夜探青山医院，发现冰流异动",
      timeframe: "第1天·夜",
      world: "modern",
      participants: ["沈翠花", "青山医院"],
    });
    expect(mapped.content_text).toContain("沈翠花夜探青山医院");
    expect(mapped.content_text).toContain("时间：第1天·夜");
    expect(mapped.content_text).toContain("世界：modern");
    expect(mapped.content_text).toContain("涉及：沈翠花、青山医院");
  });

  it("keeps summary on the short field, not the long description", () => {
    const mapped = mapAnalysisCandidateToAsset("character", "某人", {
      summary: "一句短摘要",
      description: "一段很长很长很长很長的描述，不应抢占摘要位置。",
    });
    expect(mapped.summary).toBe("一句短摘要");
  });

  it("builds stable source_ref for idempotent upserts", () => {
    const runId = "11111111-1111-4111-8111-111111111111";
    const candidateId = "22222222-2222-4222-8222-222222222222";
    const sourceRef = `${runId}:${candidateId}`;
    expect(sourceRef).toMatch(/^[0-9a-f-]+:[0-9a-f-]+$/);
    const digest = createHash("sha256").update(`pi_analysis\0${sourceRef}`).digest("hex");
    expect(digest).toHaveLength(64);
  });
});
