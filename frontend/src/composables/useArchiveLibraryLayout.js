import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import {
  ARCHIVE_LIBRARY_DIVIDER_SIZE_PX,
  ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP,
  ARCHIVE_LIBRARY_LAYOUT_STORAGE_KEY,
  ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO,
  clampArchiveLibrarySplitRatio,
  resolveArchiveLibraryLayoutMode,
  restoreArchiveLibrarySplitRatio,
} from "../views/shared/archiveLibraryLayout.js";

const DRAG_CURSOR = "col-resize";

export function useArchiveLibraryLayout() {
  const stageRef = ref(null);
  const splitRatio = ref(ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO);
  const layoutMode = ref(resolveArchiveLibraryLayoutMode(window.innerWidth));
  const resizing = ref(false);

  const stageStyle = computed(() => ({
    "--archive-library-divider-size": `${ARCHIVE_LIBRARY_DIVIDER_SIZE_PX}px`,
    "--archive-library-left-pane-ratio": String(splitRatio.value),
    "--archive-library-right-pane-ratio": String(1 - splitRatio.value),
  }));

  let resizeObserver = null;

  function syncLayoutFromElement() {
    applyContainerWidth(resolveContainerWidth(stageRef.value));
  }

  function applyContainerWidth(containerWidth) {
    const previousMode = layoutMode.value;
    const nextMode = resolveArchiveLibraryLayoutMode(containerWidth);
    layoutMode.value = nextMode;
    if (nextMode !== ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP) {
      splitRatio.value = ARCHIVE_LIBRARY_SPLIT_DEFAULT_RATIO;
      return;
    }
    if (previousMode !== ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP) {
      splitRatio.value = readStoredRatio(containerWidth);
      return;
    }
    splitRatio.value = clampArchiveLibrarySplitRatio(splitRatio.value, containerWidth);
  }

  function beginResize(event) {
    if (layoutMode.value !== ARCHIVE_LIBRARY_LAYOUT_MODE_DESKTOP) {
      return;
    }
    resizing.value = true;
    setDragDocumentState(true);
    updateFromPointer(event);
  }

  function updateFromPointer(event) {
    const nextRatio = resolvePointerRatio(event.clientX, stageRef.value);
    if (nextRatio === null) {
      return;
    }
    updateSplitRatio(nextRatio);
  }

  function handlePointerMove(event) {
    if (!resizing.value) {
      return;
    }
    updateFromPointer(event);
  }

  function stopResize() {
    if (!resizing.value) {
      return;
    }
    resizing.value = false;
    setDragDocumentState(false);
  }

  function updateSplitRatio(nextRatio) {
    const containerWidth = resolveContainerWidth(stageRef.value);
    const ratio = clampArchiveLibrarySplitRatio(nextRatio, containerWidth);
    splitRatio.value = ratio;
    window.localStorage.setItem(ARCHIVE_LIBRARY_LAYOUT_STORAGE_KEY, String(ratio));
  }

  onMounted(() => {
    splitRatio.value = readStoredRatio(resolveContainerWidth(stageRef.value));
    syncLayoutFromElement();
    resizeObserver = new ResizeObserver(syncLayoutFromElement);
    if (stageRef.value) {
      resizeObserver.observe(stageRef.value);
    }
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopResize);
  });

  onBeforeUnmount(() => {
    stopResize();
    resizeObserver?.disconnect();
    window.removeEventListener("pointermove", handlePointerMove);
    window.removeEventListener("pointerup", stopResize);
  });

  return {
    beginResize,
    layoutMode,
    resizing,
    stageRef,
    stageStyle,
  };
}

function readStoredRatio(containerWidth) {
  return restoreArchiveLibrarySplitRatio(
    window.localStorage.getItem(ARCHIVE_LIBRARY_LAYOUT_STORAGE_KEY),
    containerWidth,
  );
}

function resolveContainerWidth(element) {
  const width = element?.getBoundingClientRect?.().width;
  return Number.isFinite(width) && width > 0 ? width : window.innerWidth;
}

function resolvePointerRatio(clientX, element) {
  const rect = element?.getBoundingClientRect?.();
  if (!rect) {
    return null;
  }
  const availableWidth = rect.width - ARCHIVE_LIBRARY_DIVIDER_SIZE_PX;
  if (availableWidth <= 0) {
    return null;
  }
  const rawLeftWidth = clientX - rect.left - (ARCHIVE_LIBRARY_DIVIDER_SIZE_PX / 2);
  return rawLeftWidth / availableWidth;
}

function setDragDocumentState(active) {
  document.body.style.cursor = active ? DRAG_CURSOR : "";
  document.body.style.userSelect = active ? "none" : "";
}
