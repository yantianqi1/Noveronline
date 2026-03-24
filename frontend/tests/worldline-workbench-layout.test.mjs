import test from "node:test";
import assert from "node:assert/strict";

import {
  clampWorldlineLeftPaneWidth,
  resolveWorldlineWorkbenchMode,
  restoreWorldlineLeftPaneWidth,
  WORLDLINE_WORKBENCH_DESKTOP_BREAKPOINT,
  WORLDLINE_LEFT_PANE_DEFAULT_WIDTH,
  WORLDLINE_LEFT_PANE_MAX_WIDTH,
  WORLDLINE_LEFT_PANE_MIN_WIDTH,
} from "../src/views/shared/worldlineWorkbenchLayout.js";

test("restoreWorldlineLeftPaneWidth returns the default width when storage is empty", () => {
  assert.equal(restoreWorldlineLeftPaneWidth(null, 1600), WORLDLINE_LEFT_PANE_DEFAULT_WIDTH);
});

test("desktop breakpoint keeps wide screens in fixed three-column mode", () => {
  assert.equal(resolveWorldlineWorkbenchMode(WORLDLINE_WORKBENCH_DESKTOP_BREAKPOINT), "desktop");
  assert.equal(resolveWorldlineWorkbenchMode(1200), "stacked");
});

test("clampWorldlineLeftPaneWidth enforces the desktop minimum width", () => {
  assert.equal(clampWorldlineLeftPaneWidth(120, 1600), WORLDLINE_LEFT_PANE_MIN_WIDTH);
});

test("clampWorldlineLeftPaneWidth enforces the viewport-derived maximum width", () => {
  assert.equal(clampWorldlineLeftPaneWidth(1400, 1600), WORLDLINE_LEFT_PANE_MAX_WIDTH);
  assert.equal(clampWorldlineLeftPaneWidth(1200, 2000), WORLDLINE_LEFT_PANE_MAX_WIDTH);
});

test("restoreWorldlineLeftPaneWidth clamps valid persisted values", () => {
  assert.equal(restoreWorldlineLeftPaneWidth("980", 1600), 980);
  assert.equal(restoreWorldlineLeftPaneWidth("900", 1600), WORLDLINE_LEFT_PANE_MIN_WIDTH);
});

test("restoreWorldlineLeftPaneWidth falls back to the default width for invalid values", () => {
  assert.equal(restoreWorldlineLeftPaneWidth("not-a-number", 1600), WORLDLINE_LEFT_PANE_DEFAULT_WIDTH);
});
