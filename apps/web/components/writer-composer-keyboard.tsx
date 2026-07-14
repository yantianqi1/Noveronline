"use client";

import { useEffect } from "react";

/**
 * Lifts the writer composer above the soft keyboard on mobile browsers by
 * tracking visualViewport and setting a CSS variable on the dock.
 */
export function WriterComposerKeyboard() {
  useEffect(() => {
    const viewport = window.visualViewport;
    if (!viewport) {
      return;
    }

    const apply = () => {
      const dock = document.querySelector<HTMLElement>(".writer-composer-dock");
      if (!dock) {
        return;
      }
      const inset = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
      dock.style.setProperty("--writer-keyboard-inset", `${inset}px`);
      if (inset > 0) {
        dock.dataset.keyboardOpen = "true";
      } else {
        delete dock.dataset.keyboardOpen;
      }
    };

    apply();
    viewport.addEventListener("resize", apply);
    viewport.addEventListener("scroll", apply);
    return () => {
      viewport.removeEventListener("resize", apply);
      viewport.removeEventListener("scroll", apply);
      const dock = document.querySelector<HTMLElement>(".writer-composer-dock");
      dock?.style.removeProperty("--writer-keyboard-inset");
      delete dock?.dataset.keyboardOpen;
    };
  }, []);

  return null;
}
