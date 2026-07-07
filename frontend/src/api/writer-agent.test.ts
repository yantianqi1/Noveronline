import { describe, expect, it } from "vitest";

import { normalizeWriterRunEvent } from "./writer-agent";

describe("normalizeWriterRunEvent", () => {
  it("keeps completed writer tool results inspectable for the trace panel", () => {
    const event = normalizeWriterRunEvent({
      type: "writer.tool.completed",
      payload: {
        tool_name: "query_assets",
        is_error: false,
        result: {
          items: [{ asset_id: "asset-1", title: "密室规则" }],
          count: 1,
        },
      },
    });

    expect(event).toEqual({
      type: "tool_result",
      name: "query_assets",
      status: "done",
      full_result: JSON.stringify(
        {
          items: [{ asset_id: "asset-1", title: "密室规则" }],
          count: 1,
        },
        null,
        2,
      ),
    });
  });
});
