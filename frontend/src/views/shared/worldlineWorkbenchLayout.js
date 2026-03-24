export const WORLDLINE_LEFT_PANE_STORAGE_KEY = "mirofish.worldline.leftPaneWidth";
export const WORLDLINE_WORKBENCH_DESKTOP_BREAKPOINT = 1360;
export const WORLDLINE_LEFT_PANE_DEFAULT_WIDTH = 980;
export const WORLDLINE_LEFT_PANE_MIN_WIDTH = 900;
export const WORLDLINE_LEFT_PANE_MAX_WIDTH = 1120;
export const WORLDLINE_WORKBENCH_MODE_DESKTOP = "desktop";
export const WORLDLINE_WORKBENCH_MODE_STACKED = "stacked";
const VIEWPORT_WIDTH_FALLBACK = 1440;
const LEFT_PANE_MAX_RATIO = 0.72;

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

export function resolveWorldlineWorkbenchMode(viewportWidth) {
  const resolvedViewportWidth = Number.isFinite(viewportWidth) && viewportWidth > 0
    ? viewportWidth
    : VIEWPORT_WIDTH_FALLBACK;
  return resolvedViewportWidth >= WORLDLINE_WORKBENCH_DESKTOP_BREAKPOINT
    ? WORLDLINE_WORKBENCH_MODE_DESKTOP
    : WORLDLINE_WORKBENCH_MODE_STACKED;
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
  return resolveWorldlineWorkbenchMode(viewportWidth) === WORLDLINE_WORKBENCH_MODE_DESKTOP
    ? WORLDLINE_LEFT_PANE_MIN_WIDTH
    : 0;
}
