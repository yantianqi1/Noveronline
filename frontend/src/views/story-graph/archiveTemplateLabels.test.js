import test from "node:test";
import assert from "node:assert/strict";

import {
  formatArchiveSectionLabel,
  formatArchiveTierLabel,
  tierSelectOptions,
} from "./archiveTemplateLabels.js";

test("档位和模板字段显示中文标签", () => {
  assert.equal(formatArchiveTierLabel("protagonist"), "主角");
  assert.equal(formatArchiveTierLabel("major"), "重要");
  assert.equal(formatArchiveTierLabel("supporting"), "配角");
  assert.equal(formatArchiveTierLabel("minor"), "次要");
  assert.equal(formatArchiveSectionLabel("identity"), "身份");
  assert.equal(formatArchiveSectionLabel("motivation"), "动机");
  assert.equal(formatArchiveSectionLabel("relationship"), "关系");
  assert.equal(formatArchiveSectionLabel("private"), "隐秘");
});

test("档位下拉选项保留内部值，但向界面暴露中文标签", () => {
  assert.deepEqual(tierSelectOptions.map((item) => item.value), [
    "protagonist",
    "major",
    "supporting",
    "minor",
  ]);
  assert.deepEqual(tierSelectOptions.map((item) => item.label), [
    "主角",
    "重要",
    "配角",
    "次要",
  ]);
});
