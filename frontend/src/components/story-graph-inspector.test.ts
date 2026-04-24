import { describe, expect, it } from "vitest";

import type { GraphNodeVM } from "@/pages/story-graph/graph-view-model";
import {
  EVENT_KIND_EMPTY_HINTS,
  EVENT_KIND_LABELS,
  normalizeEvidenceRefs,
  pickEventPrimaryText,
  resolveCardKind,
} from "./story-graph-inspector";

function makeNode(overrides: Partial<GraphNodeVM> = {}): GraphNodeVM {
  return {
    id: "n1",
    name: "节点",
    entity_type: "Character",
    summary: "",
    attributes: {},
    ...overrides,
  };
}

describe("resolveCardKind", () => {
  it("maps character-family types to character card", () => {
    expect(resolveCardKind("Character")).toBe("character");
    expect(resolveCardKind("organization")).toBe("character");
    expect(resolveCardKind("Faction")).toBe("character");
    expect(resolveCardKind("group")).toBe("character");
  });

  it("maps event-family types to event card", () => {
    expect(resolveCardKind("PlotEvent")).toBe("event");
    expect(resolveCardKind("plotevent")).toBe("event");
    expect(resolveCardKind("Conflict")).toBe("event");
    expect(resolveCardKind("event")).toBe("event");
  });

  it("maps location/artifact/rule to their dedicated cards", () => {
    expect(resolveCardKind("Location")).toBe("location");
    expect(resolveCardKind("Artifact")).toBe("artifact");
    expect(resolveCardKind("KnowledgeItem")).toBe("artifact");
    expect(resolveCardKind("RuleSystem")).toBe("rule");
  });

  it("falls through to generic for unknown / missing types", () => {
    expect(resolveCardKind(undefined)).toBe("generic");
    expect(resolveCardKind("")).toBe("generic");
    expect(resolveCardKind("Unknown")).toBe("generic");
  });
});

describe("normalizeEvidenceRefs", () => {
  it("reads evidence from the canonical top-level node field", () => {
    const node = makeNode({
      evidence_refs: [
        { snippet: "林动挥手告别家人" },
        { snippet: "远方传来雷鸣" },
      ],
    });
    expect(normalizeEvidenceRefs(node.attributes, node)).toEqual([
      "林动挥手告别家人",
      "远方传来雷鸣",
    ]);
  });

  it("falls back to attributes.evidence_refs for legacy snapshots", () => {
    const node = makeNode({
      attributes: {
        evidence_refs: ["单条文本佐证", { snippet: "对象型佐证" }],
      },
    });
    expect(normalizeEvidenceRefs(node.attributes, node)).toEqual([
      "单条文本佐证",
      "对象型佐证",
    ]);
  });

  it("returns empty array when no evidence is available", () => {
    const node = makeNode();
    expect(normalizeEvidenceRefs(node.attributes, node)).toEqual([]);
  });
});

describe("pickEventPrimaryText", () => {
  it("prefers node.summary when it differs from the node name", () => {
    const node = makeNode({
      name: "京城潜伏线",
      summary: "细作在京城安插眼线，监视朝局动向。",
      attributes: { kind: "key_event", description: "忽略该字段" },
    });
    const result = pickEventPrimaryText(node);
    expect(result.primary).toContain("细作");
    expect(result.kindLabel).toBe(EVENT_KIND_LABELS.key_event);
  });

  it("falls back to attributes.description when summary equals name", () => {
    const node = makeNode({
      name: "京城潜伏线",
      summary: "京城潜伏线",
      attributes: { kind: "key_event", description: "细作在京城安插眼线。" },
    });
    const result = pickEventPrimaryText(node);
    expect(result.primary).toBe("细作在京城安插眼线。");
  });

  it("returns the kind-specific empty hint when no description is available", () => {
    const arcNode = makeNode({
      name: "启程弧线",
      summary: "启程弧线",
      attributes: { kind: "arc" },
    });
    const threadNode = makeNode({
      name: "神秘石符来历",
      summary: "神秘石符来历",
      attributes: { kind: "thread" },
    });
    const keyEventNode = makeNode({
      name: "符纹塔斗法",
      summary: "符纹塔斗法",
      attributes: { kind: "key_event" },
    });
    expect(pickEventPrimaryText(arcNode).emptyHint).toBe(EVENT_KIND_EMPTY_HINTS.arc);
    expect(pickEventPrimaryText(threadNode).emptyHint).toBe(
      EVENT_KIND_EMPTY_HINTS.thread,
    );
    expect(pickEventPrimaryText(keyEventNode).emptyHint).toBe(
      EVENT_KIND_EMPTY_HINTS.key_event,
    );
  });

  it("uses the default empty hint when kind is missing or unknown", () => {
    const node = makeNode({ name: "无类型事件", summary: "无类型事件" });
    expect(pickEventPrimaryText(node).emptyHint).toBe("暂无事件描述。");
    expect(pickEventPrimaryText(node).kindLabel).toBe("");
  });
});
