// ── Left pane (selection column) ──
export const WORLDLINE_LEFT_PANE_STORAGE_KEY = "mirofish.worldline.leftPaneWidth";
export const WORLDLINE_LEFT_PANE_DEFAULT_WIDTH = 360;
export const WORLDLINE_LEFT_PANE_MIN_WIDTH = 280;
export const WORLDLINE_LEFT_PANE_MAX_WIDTH = 480;

// ── Mid pane (controls column) ──
export const WORLDLINE_MID_PANE_STORAGE_KEY = "mirofish.worldline.midPaneWidth";
export const WORLDLINE_MID_PANE_DEFAULT_WIDTH = 500;
export const WORLDLINE_MID_PANE_MIN_WIDTH = 420;
export const WORLDLINE_MID_PANE_MAX_WIDTH = 640;

// ── Breakpoints ──
export const WORLDLINE_WORKBENCH_THREE_COL_BREAKPOINT = 1440;
export const WORLDLINE_WORKBENCH_TWO_COL_BREAKPOINT = 1200;

// ── Mode constants ──
export const WORLDLINE_WORKBENCH_MODE_THREE_COL = "three-col";
export const WORLDLINE_WORKBENCH_MODE_TWO_COL = "two-col";
export const WORLDLINE_WORKBENCH_MODE_STACKED = "stacked";

const VIEWPORT_WIDTH_FALLBACK = 1440;
const LEFT_PANE_MAX_RATIO = 0.28;
const MID_PANE_MAX_RATIO = 0.38;

export function clampWorldlineLeftPaneWidth(width, viewportWidth) {
  const nextWidth = Number(width);
  if (!Number.isFinite(nextWidth)) {
    return WORLDLINE_LEFT_PANE_DEFAULT_WIDTH;
  }
  const minWidth = resolveWorldlineLeftPaneMinWidth(viewportWidth);
  const maxWidth = resolveWorldlineLeftPaneMaxWidth(viewportWidth);
  const lowerBound = Math.min(minWidth, maxWidth);
  return Math.min(Math.max(nextWidth, lowerBound), maxWidth);
}

export function restoreWorldlineLeftPaneWidth(rawValue, viewportWidth) {
  const parsedWidth = Number.parseFloat(rawValue ?? "");
  if (!Number.isFinite(parsedWidth)) {
    return clampWorldlineLeftPaneWidth(WORLDLINE_LEFT_PANE_DEFAULT_WIDTH, viewportWidth);
  }
  return clampWorldlineLeftPaneWidth(parsedWidth, viewportWidth);
}

export function clampWorldlineMidPaneWidth(width, viewportWidth) {
  const nextWidth = Number(width);
  if (!Number.isFinite(nextWidth)) {
    return WORLDLINE_MID_PANE_DEFAULT_WIDTH;
  }
  const minWidth = resolveWorldlineMidPaneMinWidth(viewportWidth);
  const maxWidth = resolveWorldlineMidPaneMaxWidth(viewportWidth);
  const lowerBound = Math.min(minWidth, maxWidth);
  return Math.min(Math.max(nextWidth, lowerBound), maxWidth);
}

export function restoreWorldlineMidPaneWidth(rawValue, viewportWidth) {
  const parsedWidth = Number.parseFloat(rawValue ?? "");
  if (!Number.isFinite(parsedWidth)) {
    return clampWorldlineMidPaneWidth(WORLDLINE_MID_PANE_DEFAULT_WIDTH, viewportWidth);
  }
  return clampWorldlineMidPaneWidth(parsedWidth, viewportWidth);
}

export function resolveWorldlineWorkbenchMode(viewportWidth) {
  const resolvedViewportWidth = Number.isFinite(viewportWidth) && viewportWidth > 0
    ? viewportWidth
    : VIEWPORT_WIDTH_FALLBACK;
  if (resolvedViewportWidth >= WORLDLINE_WORKBENCH_THREE_COL_BREAKPOINT) {
    return WORLDLINE_WORKBENCH_MODE_THREE_COL;
  }
  if (resolvedViewportWidth >= WORLDLINE_WORKBENCH_TWO_COL_BREAKPOINT) {
    return WORLDLINE_WORKBENCH_MODE_TWO_COL;
  }
  return WORLDLINE_WORKBENCH_MODE_STACKED;
}

export function resolveWorldlineLeftPaneMaxWidth(viewportWidth) {
  const resolvedViewportWidth = Number.isFinite(viewportWidth) && viewportWidth > 0
    ? viewportWidth
    : VIEWPORT_WIDTH_FALLBACK;
  return Math.min(
    WORLDLINE_LEFT_PANE_MAX_WIDTH,
    Math.floor(resolvedViewportWidth * LEFT_PANE_MAX_RATIO),
  );
}

function resolveWorldlineLeftPaneMinWidth(viewportWidth) {
  return resolveWorldlineWorkbenchMode(viewportWidth) === WORLDLINE_WORKBENCH_MODE_STACKED
    ? 0
    : WORLDLINE_LEFT_PANE_MIN_WIDTH;
}

function resolveWorldlineMidPaneMaxWidth(viewportWidth) {
  const resolvedViewportWidth = Number.isFinite(viewportWidth) && viewportWidth > 0
    ? viewportWidth
    : VIEWPORT_WIDTH_FALLBACK;
  return Math.min(
    WORLDLINE_MID_PANE_MAX_WIDTH,
    Math.floor(resolvedViewportWidth * MID_PANE_MAX_RATIO),
  );
}

function resolveWorldlineMidPaneMinWidth(viewportWidth) {
  return resolveWorldlineWorkbenchMode(viewportWidth) === WORLDLINE_WORKBENCH_MODE_STACKED
    ? 0
    : WORLDLINE_MID_PANE_MIN_WIDTH;
}
