import { describe, expect, it } from "vitest";

import {
  extractAnalysisCandidatesFromWorkspaceFiles,
  extractItemsFromCandidateDocument,
} from "./analysis-candidate-extract.js";

describe("analysis candidate extract", () => {
  it("accepts canonical {items:[...]} documents", () => {
    const items = extractItemsFromCandidateDocument(
      "30-candidates/characters.json",
      JSON.stringify({
        items: [{ name: "林深", summary: "主角" }, { name: "静妃", summary: "贵妃" }],
      }),
    );
    expect(items).toHaveLength(2);
    expect(items[0]?.name).toBe("林深");
  });

  it("accepts type-keyed arrays agents commonly emit", () => {
    const characters = extractItemsFromCandidateDocument(
      "30-candidates/characters.json",
      JSON.stringify({ characters: [{ name: "陈迹", description: "主角" }] }),
    );
    const relationships = extractItemsFromCandidateDocument(
      "30-candidates/relationships.json",
      JSON.stringify({
        relationships: [{ subject: "陈迹", object: "乌云", type: "契约", description: "共生" }],
      }),
    );
    expect(characters).toHaveLength(1);
    expect(relationships).toHaveLength(1);
    expect(relationships[0]?.subject).toBe("陈迹");
  });

  it("flattens world_rules encyclopedia objects into rule candidates", () => {
    const items = extractItemsFromCandidateDocument(
      "30-candidates/world_rules.json",
      JSON.stringify({
        world_name: "大宁朝",
        world_type: "架空古代",
        cultivation_system: {
          name: "山君门径",
          description: "官员血脉可吸引冰流",
        },
        geography: {
          洛城: { summary: "主角出身地" },
        },
      }),
    );
    expect(items.length).toBeGreaterThanOrEqual(3);
    expect(items.some((item) => item.name === "大宁朝")).toBe(true);
    expect(items.some((item) => String(item.name).includes("山君") || item.section === "cultivation_system")).toBe(true);
  });

  it("maps workspace files into typed candidate rows for auto-import", () => {
    const rows = extractAnalysisCandidatesFromWorkspaceFiles([
      {
        path: "30-candidates/characters.json",
        content_text: JSON.stringify({ characters: [{ name: "陈迹", summary: "主角" }] }),
      },
      {
        path: "30-candidates/relationships.json",
        content_text: JSON.stringify({
          relationships: [{ subject: "陈迹", object: "乌云", type: "契约" }],
        }),
      },
      {
        path: "20-notes/sequential/01.md",
        content_text: "ignore me",
      },
    ]);
    expect(rows).toHaveLength(2);
    expect(rows[0]?.candidate_type).toBe("character");
    expect(rows[1]?.candidate_type).toBe("relationship");
    // No name/title/summary on the item → no fabricated schema-key literal; the
    // relationship title is composed downstream from subject/object.
    expect(rows[1]?.name).toBe("");
  });

  it("extracts timeline.json items as plot_event candidates with Chinese titles", () => {
    const rows = extractAnalysisCandidatesFromWorkspaceFiles([
      {
        path: "30-candidates/timeline.json",
        content_text: JSON.stringify({
          items: [
            {
              title: "沈翠花夜探青山医院",
              summary: "沈翠花夜探青山医院，发现冰流异动。",
              timeframe: "第1天·夜",
              world: "modern",
              participants: ["沈翠花", "青山医院"],
            },
            {
              summary: "顾晏在现代线醒来，发现自己失去记忆。",
              timeframe: "第2天·晨",
              world: "modern",
            },
          ],
        }),
      },
    ]);
    expect(rows).toHaveLength(2);
    expect(rows[0]?.candidate_type).toBe("plot_event");
    expect(rows[0]?.name).toBe("沈翠花夜探青山医院");
    // Second item has no title → falls back to a truncated Chinese summary,
    // never the bare "plot_event" key.
    expect(rows[1]?.candidate_type).toBe("plot_event");
    expect(rows[1]?.name).toContain("顾晏");
    expect(rows[1]?.name).not.toBe("plot_event");
  });

  it("gives untitled events a readable timeframe tag instead of a placeholder", () => {
    const rows = extractAnalysisCandidatesFromWorkspaceFiles([
      {
        path: "30-candidates/timeline.json",
        content_text: JSON.stringify({ items: [{ timeframe: "第3天·暮", world: "ancient" }] }),
      },
    ]);
    expect(rows[0]?.candidate_type).toBe("plot_event");
    expect(rows[0]?.name).toBe("未命名事件 · 第3天·暮");
  });

  it("returns empty for invalid JSON instead of throwing", () => {
    expect(extractItemsFromCandidateDocument("30-candidates/characters.json", "{not-json")).toEqual([]);
  });
});
