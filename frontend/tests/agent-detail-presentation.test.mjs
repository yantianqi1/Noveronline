import test from "node:test";
import assert from "node:assert/strict";

import {
  buildAgentCardHighlights,
  buildSelectedAgentDetailSections,
  buildSelectedAgentSummaryLines,
} from "../src/views/character-console/agentDetailPresentation.js";

test("character card highlights prioritize personality loyalty and short term goal", () => {
  const highlights = buildAgentCardHighlights({
    agent_kind: "character",
    state: {
      personality: "多疑克制",
      loyalty: "优先真相",
      short_term_goal: "验证密信",
      skills: ["潜入", "取证"],
    },
  });

  assert.deepEqual(highlights, ["性格：多疑克制", "忠诚：优先真相", "短期目标：验证密信"]);
});

test("organization summary lines read from selectedAgent state", () => {
  const lines = buildSelectedAgentSummaryLines({
    agent_kind: "organization",
    state: {
      public_stance: "维护宗门秩序",
      strategic_goal: "保持镜湖控制权",
      resources: ["刑堂", "镜湖密库"],
    },
  });

  assert.deepEqual(lines, [
    "公开立场：维护宗门秩序",
    "战略目标：保持镜湖控制权",
    "核心资源：刑堂、镜湖密库",
  ]);
});

test("detail sections are built from selectedAgent.state.template_payload", () => {
  const sections = buildSelectedAgentDetailSections({
    template_sections: ["identity", "behavior", "private"],
    state: {
      template_payload: {
        identity: { entity_name: "沈夜", role: "主角", identity_hint: "外门弟子" },
        behavior: {
          agent_behavior_hint: "先搜证再摊牌",
          skills: ["潜入", "取证"],
        },
        private: {
          secrets: ["掌握镜湖铜片"],
        },
      },
    },
  });

  assert.deepEqual(
    sections.map((item) => item.label),
    ["身份信息", "行动倾向", "隐秘信息"],
  );
  assert.equal(sections[0].entries[2].value, "外门弟子");
  assert.equal(sections[1].entries[1].value, "潜入、取证");
  assert.equal(sections[2].entries[0].value, "掌握镜湖铜片");
});

test("relationship card highlights expose power trust and stability", () => {
  const highlights = buildAgentCardHighlights({
    agent_kind: "relationship",
    state: {
      power_dynamic: "宗门占上风",
      trust_level: "接近崩溃",
      stability_forecast: "短期内继续恶化",
    },
  });

  assert.deepEqual(highlights, ["权力动态：宗门占上风", "信任程度：接近崩溃", "稳定预期：短期内继续恶化"]);
});
