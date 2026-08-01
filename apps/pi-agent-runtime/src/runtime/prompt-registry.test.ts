import { describe, expect, it } from "vitest";

import { versionWriterPrompt, WRITER_PROMPT_VERSIONS } from "./prompt-registry.js";

describe("Writer prompt registry", () => {
  it("gives every core prompt a stable traceable version", () => {
    for (const key of ["retrieval_planner", "rerank", "consistency", "orchestrator", "composer"] as const) {
      expect(versionWriterPrompt(key, "prompt")).toContain(`Prompt contract: ${key}@${WRITER_PROMPT_VERSIONS[key]}`);
    }
  });
});
