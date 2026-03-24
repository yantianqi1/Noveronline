export const ARCHIVE_LIBRARY_LAYOUT_STORAGE_KEY = "mirofish.archiveLibrary.splitRatio";
export const ARCHIVE_LIBRARY_DESKTOP_BREAKPOINT = 1200;
export const ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP = "desktop";
export const ARCHIVE_LIBRARY_LAYOUT_MODE_STACKED = "stacked";
export const ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO = 0.5;
export const ARCHIVE_LIBRARY_SPLIT_MIN_RATIO = 0.42;
export const ARCHIVE_LIBRARY_SPLIT_MAX_RATIO = 0.58;
export const ARCHIVE_LIBRARY_DIVIDER_SIZE_PX = 18;
const CONTAINER_WIDTH_FALLBACK = 1440;

export function resolveArchiveLibraryLayoutMode(containerWidth) {
  const resolvedWidth = normalizeContainerWidth(containerWidth);
  return resolvedWidth >= ARCHIVE_LIBRARY_DESKTOP_BREAKPOINT
    ? ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP
    : ARCHIVE_LIBRARY_LAYOUT_MODE_STACKED;
}

export function clampArchiveLibrarySplitRatio(ratio, containerWidth) {
  const nextRatio = Number(ratio);
  if (resolveArchiveLibraryLayoutMode(containerWidth) !== ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP) {
    return ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO;
  }
  if (!Number.isFinite(nextRatio)) {
    return ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO;
  }
  return Math.min(
    Math.max(nextRatio, ARCHIVE_LIBRARY_SPLIT_MIN_RATIO),
    ARCHIVE_LIBRARY_SPLIT_MAX_RATIO,
  );
}

export function restoreArchiveLibrarySplitRatio(rawValue, containerWidth) {
  const parsedRatio = Number.parseFloat(rawValue ?? "");
  if (!Number.isFinite(parsedRatio)) {
    return clampArchiveLibrarySplitRatio(ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO, containerWidth);
  }
  return clampArchiveLibrarySplitRatio(parsedRatio, containerWidth);
}

function normalizeContainerWidth(containerWidth) {
  return Number.isFinite(containerWidth) && containerWidth > 0
    ? containerWidth
    : CONTAINER_WIDTH_FALLBACK;
}
