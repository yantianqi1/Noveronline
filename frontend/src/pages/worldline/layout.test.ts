import { describe, expect, it } from "vitest";

import { WORLDLINE_PANEL_LAYOUT } from "./layout";

const PERCENT_SIZE_PATTERN = /^\d+%$/;

describe("worldline panel layout", () => {
  it("uses explicit percentage strings for resizable panel size props", () => {
    for (const mode of Object.values(WORLDLINE_PANEL_LAYOUT)) {
      for (const panel of Object.values(mode.panels)) {
        expect(panel.defaultSize).toMatch(PERCENT_SIZE_PATTERN);
        expect(panel.minSize).toMatch(PERCENT_SIZE_PATTERN);
        if (panel.maxSize) {
          expect(panel.maxSize).toMatch(PERCENT_SIZE_PATTERN);
        }
      }
    }
  });

  it("keeps every default layout mode normalized to 100 percent", () => {
    for (const mode of Object.values(WORLDLINE_PANEL_LAYOUT)) {
      const total = Object.values(mode.panels).reduce(
        (sum, panel) => sum + Number.parseInt(panel.defaultSize, 10),
        0,
      );

      expect(total).toBe(100);
    }
  });
});
