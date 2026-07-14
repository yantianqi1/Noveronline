"use client";

import { useEffect } from "react";

/**
 * Elevates the fixed mobile top bar as the user scrolls, and marks the
 * document for CSS-driven layered chrome (shadow, opacity, backdrop).
 */
export function MobileScrollChrome() {
  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const media = window.matchMedia("(max-width: 860px)");
    let frame = 0;
    let lastElevated = false;

    function apply(elevated: boolean) {
      if (elevated === lastElevated) {
        return;
      }
      lastElevated = elevated;
      document.documentElement.dataset.mobileScroll = elevated ? "elevated" : "rest";
      const frameEl = document.querySelector(".app-frame.app-frame-unified");
      if (frameEl instanceof HTMLElement) {
        frameEl.dataset.mobileScroll = elevated ? "elevated" : "rest";
      }
    }

    function measure() {
      frame = 0;
      if (!media.matches) {
        apply(false);
        return;
      }
      apply(window.scrollY > 8);
    }

    function onScroll() {
      if (frame) {
        return;
      }
      frame = window.requestAnimationFrame(measure);
    }

    apply(false);
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    media.addEventListener("change", measure);
    return () => {
      window.removeEventListener("scroll", onScroll);
      media.removeEventListener("change", measure);
      if (frame) {
        window.cancelAnimationFrame(frame);
      }
      delete document.documentElement.dataset.mobileScroll;
      const frameEl = document.querySelector(".app-frame.app-frame-unified");
      if (frameEl instanceof HTMLElement) {
        delete frameEl.dataset.mobileScroll;
      }
    };
  }, []);

  return null;
}
