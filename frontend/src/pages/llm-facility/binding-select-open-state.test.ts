import { describe, expect, it } from "vitest";

import {
  getLlmSettingsRefetchInterval,
  nextOpenBindingSelectKey,
} from "./binding-select-open-state";

describe("binding select open state", () => {
  it("tracks the currently opened binding select", () => {
    expect(nextOpenBindingSelectKey("", "writer:model", true)).toBe("writer:model");
    expect(
      nextOpenBindingSelectKey("writer:model", "writer:model", false),
    ).toBe("");
  });

  it("ignores close events from unrelated selects", () => {
    expect(
      nextOpenBindingSelectKey("writer:model", "writer:channel", false),
    ).toBe("writer:model");
  });

  it("pauses llm settings polling while a binding select is open", () => {
    expect(getLlmSettingsRefetchInterval("writer:model")).toBe(false);
    expect(getLlmSettingsRefetchInterval("")).toBe(2000);
  });
});
