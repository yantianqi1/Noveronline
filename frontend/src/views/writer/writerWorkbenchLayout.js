export const WRITER_WORKBENCH_DESKTOP_BREAKPOINT = 1440;
export const WRITER_WORKBENCH_MODE_DESKTOP = "desktop";
export const WRITER_WORKBENCH_MODE_STACKED = "stacked";
const VIEWPORT_FALLBACK = 1440;

export function resolveWriterWorkbenchMode(viewportWidth) {
  const width = Number.isFinite(viewportWidth) && viewportWidth > 0 ? viewportWidth : VIEWPORT_FALLBACK;
  return width >= WRITER_WORKBENCH_DESKTOP_BREAKPOINT
    ? WRITER_WORKBENCH_MODE_DESKTOP
    : WRITER_WORKBENCH_MODE_STACKED;
}

export function buildWriterWorkbenchColumns(mode) {
  return mode === WRITER_WORKBENCH_MODE_DESKTOP
    ? "minmax(280px, 340px) minmax(0, 1fr) minmax(280px, 360px)"
    : "1fr";
}
