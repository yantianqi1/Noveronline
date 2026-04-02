import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import {
  clampWorldlineLeftPaneWidth,
  clampWorldlineMidPaneWidth,
  resolveWorldlineWorkbenchMode,
  restoreWorldlineLeftPaneWidth,
  restoreWorldlineMidPaneWidth,
  WORLDLINE_LEFT_PANE_DEFAULT_WIDTH,
  WORLDLINE_LEFT_PANE_STORAGE_KEY,
  WORLDLINE_MID_PANE_DEFAULT_WIDTH,
  WORLDLINE_MID_PANE_STORAGE_KEY,
} from "../views/shared/worldlineWorkbenchLayout.js";

const DRAG_CURSOR = "col-resize";
const DIVIDER_WIDTH = 16;

export function useWorldlineWorkbenchLayout() {
  const stageRef = ref(null);
  const leftPaneWidth = ref(WORLDLINE_LEFT_PANE_DEFAULT_WIDTH);
  const midPaneWidth = ref(WORLDLINE_MID_PANE_DEFAULT_WIDTH);
  const activeResizer = ref(null);
  const resizing = computed(() => activeResizer.value !== null);
  const workbenchMode = ref(resolveWorldlineWorkbenchMode(window.innerWidth));

  const stageStyle = computed(() => ({
    "--worldline-left-pane-width": `${leftPaneWidth.value}px`,
    "--worldline-mid-pane-width": `${midPaneWidth.value}px`,
  }));

  function syncLayoutState() {
    workbenchMode.value = resolveWorldlineWorkbenchMode(window.innerWidth);
    const rawLeft = window.localStorage.getItem(WORLDLINE_LEFT_PANE_STORAGE_KEY);
    const rawMid = window.localStorage.getItem(WORLDLINE_MID_PANE_STORAGE_KEY);
    leftPaneWidth.value = restoreWorldlineLeftPaneWidth(rawLeft, window.innerWidth);
    midPaneWidth.value = restoreWorldlineMidPaneWidth(rawMid, window.innerWidth);
  }

  function updateLeftPaneWidth(nextWidth) {
    const width = clampWorldlineLeftPaneWidth(nextWidth, window.innerWidth);
    leftPaneWidth.value = width;
    window.localStorage.setItem(WORLDLINE_LEFT_PANE_STORAGE_KEY, String(width));
  }

  function updateMidPaneWidth(nextWidth) {
    const width = clampWorldlineMidPaneWidth(nextWidth, window.innerWidth);
    midPaneWidth.value = width;
    window.localStorage.setItem(WORLDLINE_MID_PANE_STORAGE_KEY, String(width));
  }

  function beginLeftResize(event) {
    activeResizer.value = "left";
    setDragDocumentState(true);
    applyLeftResize(event);
  }

  function beginMidResize(event) {
    activeResizer.value = "mid";
    setDragDocumentState(true);
    applyMidResize(event);
  }

  function stopResize() {
    if (!activeResizer.value) {
      return;
    }
    activeResizer.value = null;
    setDragDocumentState(false);
  }

  function handlePointerMove(event) {
    if (activeResizer.value === "left") {
      applyLeftResize(event);
    } else if (activeResizer.value === "mid") {
      applyMidResize(event);
    }
  }

  function applyLeftResize(event) {
    const rect = stageRef.value?.getBoundingClientRect();
    if (!rect) {
      return;
    }
    updateLeftPaneWidth(event.clientX - rect.left);
  }

  function applyMidResize(event) {
    const rect = stageRef.value?.getBoundingClientRect();
    if (!rect) {
      return;
    }
    const rawMid = event.clientX - rect.left - leftPaneWidth.value - DIVIDER_WIDTH;
    updateMidPaneWidth(rawMid);
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
    midPaneWidth,
    resizing,
    workbenchMode,
    beginLeftResize,
    beginMidResize,
  };
}

function setDragDocumentState(active) {
  document.body.style.cursor = active ? DRAG_CURSOR : "";
  document.body.style.userSelect = active ? "none" : "";
}
