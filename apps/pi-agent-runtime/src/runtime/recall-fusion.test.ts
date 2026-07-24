import { describe, expect, it } from "vitest";

import { reciprocalRankFusion, RRF_K, type FusionItem } from "./recall-fusion.js";

function item(id: string, channel: string, title?: string): FusionItem {
  return { id, channel, title };
}

describe("reciprocalRankFusion", () => {
  it("floats items that multiple channels agree on above single-channel items", () => {
    const keyed = [item("a", "keyed"), item("b", "keyed"), item("c", "keyed")];
    const hybrid = [item("b", "hybrid"), item("d", "hybrid"), item("e", "hybrid")];
    const manuscript = [item("b", "manuscript", "Master")];

    const fused = reciprocalRankFusion([keyed, hybrid, manuscript]);

    // "b" is rank 2 in keyed, rank 1 in hybrid, rank 1 in manuscript -> top.
    expect(fused[0]?.id).toBe("b");
    expect(fused[0]?.channels).toEqual(["keyed", "hybrid", "manuscript"]);
    expect(fused[0]?.best_rank).toBe(1);
    // Its score is the sum of its three channel contributions.
    const expected = 1 / (RRF_K + 2) + 1 / (RRF_K + 1) + 1 / (RRF_K + 1);
    expect(fused[0]?.rrf_score).toBeCloseTo(expected, 6);
  });

  it("orders by score, then best rank, then id for determinism", () => {
    const list1 = [item("x", "hybrid"), item("y", "hybrid")];
    const list2 = [item("y", "keyed"), item("x", "keyed")];
    const fused = reciprocalRankFusion([list1, list2]);
    // Both appear in both channels with mirrored ranks -> equal score; best_rank tie -> id order.
    expect(fused.map((f) => f.id)).toEqual(["x", "y"]);
    expect(fused[0]?.rrf_score).toBeCloseTo(fused[1]?.rrf_score ?? 0, 6);
  });

  it("handles empty channels and empty input", () => {
    expect(reciprocalRankFusion([])).toEqual([]);
    expect(reciprocalRankFusion([[], []])).toEqual([]);
    const fused = reciprocalRankFusion([[item("solo", "keyed")], []]);
    expect(fused).toHaveLength(1);
    expect(fused[0]?.rrf_score).toBeCloseTo(1 / (RRF_K + 1), 6);
  });

  it("dedupes the same id within a single channel by accumulating ranks", () => {
    const fused = reciprocalRankFusion([[item("a", "hybrid"), item("a", "hybrid")]]);
    expect(fused).toHaveLength(1);
    expect(fused[0]?.channels).toEqual(["hybrid"]);
    expect(fused[0]?.best_rank).toBe(1);
    expect(fused[0]?.rrf_score).toBeCloseTo(1 / (RRF_K + 1) + 1 / (RRF_K + 2), 6);
  });
});
