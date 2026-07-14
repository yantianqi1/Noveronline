import assert from "node:assert/strict";
import test from "node:test";

import { formatBeijingTime, formatBeijingTimeLabel } from "../lib/beijing-time.ts";

test("formatBeijingTime converts Postgres UTC timestamps to Asia/Shanghai", () => {
  const value = "2026-07-14 04:56:36.19514+00";
  const zh = formatBeijingTime("zh-CN", value);
  const en = formatBeijingTime("en", value);

  assert.match(zh, /2026/);
  assert.match(zh, /12:56:36|12:56/);
  assert.doesNotMatch(zh, /\+00/);
  assert.match(en, /2026/);
  assert.match(en, /12:56/);
});

test("formatBeijingTimeLabel appends Beijing zone marker", () => {
  const value = "2026-07-14T04:56:36.000Z";
  assert.match(formatBeijingTimeLabel("zh-CN", value), /北京时间/);
  assert.match(formatBeijingTimeLabel("en", value), /Beijing/);
});

test("formatBeijingTime returns empty for missing values", () => {
  assert.equal(formatBeijingTime("zh-CN", ""), "");
  assert.equal(formatBeijingTime("zh-CN", null), "");
});
