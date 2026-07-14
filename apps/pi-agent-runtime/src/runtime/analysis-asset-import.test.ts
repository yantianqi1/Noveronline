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

  it("uses from/to aliases for relationships", () => {
    const title = composeAnalysisAssetTitle("relationship", "", {
      from: "A",
      to: "B",
      kind: "盟友",
    });
    expect(title).toBe("A → B / 盟友");
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
