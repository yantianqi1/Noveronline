import test from "node:test";
import assert from "node:assert/strict";

import { buildArchiveDetailSections } from "../src/components/archiveDetailSections.js";

test("buildArchiveDetailSections prefers template sections when present", () => {
  const sections = buildArchiveDetailSections({
    template_sections: ["identity", "relationship", "state"],
    template_payload: {
      identity: { entity_name: "沈夜", role: "主角" },
      relationship: ["沈夜", "玄霄宗", "存在对抗关系"],
      state: "表面立场仍待进一步观察",
    },
  });

  assert.deepEqual(
    sections.map((item) => item.label),
    ["身份信息", "关系段", "当前状态"],
  );
  assert.equal(sections[0].variant, "entries");
  assert.deepEqual(sections[0].entries, [
    { label: "entity_name", value: "沈夜" },
    { label: "role", value: "主角" },
  ]);
  assert.equal(sections[1].variant, "items");
  assert.deepEqual(sections[1].items, ["沈夜", "玄霄宗", "存在对抗关系"]);
  assert.equal(sections[2].variant, "text");
  assert.equal(sections[2].text, "表面立场仍待进一步观察");
});

test("buildArchiveDetailSections falls back to legacy archive fields", () => {
  const sections = buildArchiveDetailSections({
    entity_role: "主角",
    core_drive: "查清真相",
    surface_mask: "冷静克制",
    hidden_tension: "身份暴露",
    relationship_summary: "与玄霄宗对立",
  });

  assert.deepEqual(
    sections.map((item) => item.label),
    ["故事定位", "核心动机", "表层伪装", "隐藏张力", "关系摘要"],
  );
  assert.ok(sections.every((item) => item.variant === "text"));
  assert.equal(sections[0].text, "主角");
});

test("buildArchiveDetailSections returns placeholder text for empty values", () => {
  const sections = buildArchiveDetailSections({
    template_sections: ["risk", "private"],
    template_payload: {
      risk: [],
      private: {},
    },
  });

  assert.deepEqual(
    sections.map((item) => item.text),
    ["暂无", "暂无"],
  );
});
