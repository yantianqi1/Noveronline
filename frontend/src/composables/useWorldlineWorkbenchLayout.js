import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import {
  clampWorldlineLeftPaneWidth,
  resolveWorldlineWorkbenchMode,
  restoreWorldlineLeftPaneWidth,
  WORLDLINE_LEFT_PANE_DEFAULT_WIDTH,
  WORLDLINE_LEFT_PANE_STORAGE_KEY,
} from "../views/shared/worldlineWorkbenchLayout.js";

const DRAG_CURSOR = "col-resize";

export function useWorldlineWorkbenchLayout() {
  const stageRef = ref(null);
  const leftPaneWidth = ref(WORLDLINE_LEFT_PANE_DEFAULT_WIDTH);
  const resizing = ref(false);
  const workbenchMode = ref(resolveWorldlineWorkbenchMode(window.innerWidth));

  const stageStyle = computed(() => ({
    "--worldline-left-pane-width": `${leftPaneWidth.value}px`,
  }));

  function syncLayoutState() {
    workbenchMode.value = resolveWorldlineWorkbenchMode(window.innerWidth);
    const storage = window.localStorage.getItem(WORLDLINE_LEFT_PANE_STORAGE_KEY);
    leftPaneWidth.value = restoreWorldlineLeftPaneWidth(storage, window.innerWidth);
  }

  function updatePaneWidth(nextWidth) {
    const width = clampWorldlineLeftPaneWidth(nextWidth, window.innerWidth);
    leftPaneWidth.value = width;
    window.localStorage.setItem(WORLDLINE_LEFT_PANE_STORAGE_KEY, String(width));
  }

  function beginResize(event) {
    resizing.value = true;
    setDragDocumentState(true);
    updateFromPointer(event);
  }

  function stopResize() {
    if (!resizing.value) {
      return;
    }
    resizing.value = false;
    setDragDocumentState(false);
  }

  function handlePointerMove(event) {
    if (!resizing.value) {
      return;
    }
    updateFromPointer(event);
  }

  function updateFromPointer(event) {
    const rect = stageRef.value?.getBoundingClientRect();
    if (!rect) {
      return;
    }
    updatePaneWidth(event.clientX - rect.left);
  }

  onMounted(() => {
    syncLayoutState();
    window.addEventListener("resize", syncLayoutState);
    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", stopResize);
  });

  onBeforeUnmount(() => {
    stopResize();
    window.removeEventListener("resize", syncLayoutState);
    window.removeEventListener("pointermove", handlePointerMove);
    window.removeEventListener("pointerup", stopResize);
  });

  return {
    stageRef,
    stageStyle,
    leftPaneWidth,
    resizing,
    workbenchMode,
    beginResize,
  };
}

function setDragDocumentState(active) {
  document.body.style.cursor = active ? DRAG_CURSOR : "";
  document.body.style.userSelect = active ? "none" : "";
}
