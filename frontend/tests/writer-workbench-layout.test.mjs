import test from "node:test";
import assert from "node:assert/strict";

import {
  WRITER_WORKBENCH_DESKTOP_BREAKPOINT,
  WRITER_WORKBENCH_MODE_DESKTOP,
  WRITER_WORKBENCH_MODE_STACKED,
  buildWriterWorkbenchColumns,
  resolveWriterWorkbenchMode,
} from "../src/views/writer/writerWorkbenchLayout.js";

test("writer workbench uses desktop mode above the breakpoint", () => {
  assert.equal(resolveWriterWorkbenchMode(WRITER_WORKBENCH_DESKTOP_BREAKPOINT), WRITER_WORKBENCH_MODE_DESKTOP);
  assert.equal(resolveWriterWorkbenchMode(1200), WRITER_WORKBENCH_MODE_STACKED);
});

test("writer workbench columns reflect the current mode", () => {
  assert.equal(
    buildWriterWorkbenchColumns(WRITER_WORKBENCH_MODE_DESKTOP),
    "minmax(280px, 340px) minmax(0, 1fr) minmax(280px, 360px)",
  );
  assert.equal(buildWriterWorkbenchColumns(WRITER_WORKBENCH_MODE_STACKED), "1fr");
});
