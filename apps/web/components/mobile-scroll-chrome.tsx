"use client";

import { useEffect } from "react";

const PHONE_MQ = "(max-width: 860px)";
const IDLE_FOLD_MS = 1500;
const SCROLL_DELTA_PX = 4;
const THREAD_SCROLL_SEL = ".writer-thread-scroll, .app-main";

/**
 * Phone chrome: elevate styling after scroll, and auto-fold top/bottom bars
 * when idle. Any scroll motion (window or writer thread) re-shows chrome.
 *
 * data-mobile-scroll: rest | elevated  (visual weight of top bar)
 * data-mobile-chrome: shown | folded   (translate chrome off-screen when idle)
 */
export function MobileScrollChrome() {
  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const media = window.matchMedia(PHONE_MQ);
    let raf = 0;
    let lastElevated = false;
    let lastChrome: "shown" | "folded" = "shown";
    let lastY = window.scrollY || 0;
    let idleTimer: ReturnType<typeof setTimeout> | null = null;
    const boundScrollers = new WeakSet<EventTarget>();
    const observed: Element[] = [];
    let observer: MutationObserver | null = null;

    function frameEl() {
      return document.querySelector(".app-frame.app-frame-unified");
    }

    function setScrollElevated(elevated: boolean) {
      if (elevated === lastElevated) {
        return;
      }
      lastElevated = elevated;
      const value = elevated ? "elevated" : "rest";
      document.documentElement.dataset.mobileScroll = value;
      const frame = frameEl();
      if (frame instanceof HTMLElement) {
        frame.dataset.mobileScroll = value;
      }
    }

    function setChrome(state: "shown" | "folded") {
      if (state === lastChrome) {
        return;
      }
      lastChrome = state;
      document.documentElement.dataset.mobileChrome = state;
      const frame = frameEl();
      if (frame instanceof HTMLElement) {
        frame.dataset.mobileChrome = state;
      }
    }

    function clearIdle() {
      if (idleTimer) {
        clearTimeout(idleTimer);
        idleTimer = null;
      }
    }

    function scheduleFold() {
      clearIdle();
      if (!media.matches) {
        return;
      }
      idleTimer = setTimeout(() => {
        setChrome("folded");
      }, IDLE_FOLD_MS);
    }

    function onActivity(sourceY: number) {
      if (!media.matches) {
        setScrollElevated(false);
        setChrome("shown");
        clearIdle();
        return;
      }
      const delta = Math.abs(sourceY - lastY);
      lastY = sourceY;
      if (delta >= SCROLL_DELTA_PX || sourceY > 8) {
        setScrollElevated(sourceY > 8);
        setChrome("shown");
        scheduleFold();
      }
    }

    function measureWindow() {
      raf = 0;
      if (!media.matches) {
        setScrollElevated(false);
        setChrome("shown");
        clearIdle();
        return;
      }
      onActivity(window.scrollY || 0);
    }

    function onWindowScroll() {
      if (raf) {
        return;
      }
      raf = window.requestAnimationFrame(measureWindow);
    }

    function onElementScroll(event: Event) {
      const target = event.currentTarget;
      if (!(target instanceof HTMLElement)) {
        return;
      }
      if (raf) {
        return;
      }
      raf = window.requestAnimationFrame(() => {
        raf = 0;
        if (!media.matches) {
          return;
        }
        // Nested scrollers still re-show chrome; elevate when either window or
        // the scroller has moved past the threshold.
        const y = Math.max(window.scrollY || 0, target.scrollTop || 0);
        onActivity(y);
      });
    }

    function bindScroller(el: Element) {
      if (!(el instanceof HTMLElement) || boundScrollers.has(el)) {
        return;
      }
      boundScrollers.add(el);
      el.addEventListener("scroll", onElementScroll, { passive: true });
      observed.push(el);
    }

    function scanScrollers() {
      document.querySelectorAll(THREAD_SCROLL_SEL).forEach(bindScroller);
    }

    function onMediaChange() {
      if (!media.matches) {
        setScrollElevated(false);
        setChrome("shown");
        clearIdle();
        return;
      }
      setChrome("shown");
      scheduleFold();
      measureWindow();
    }

    setScrollElevated(false);
    setChrome("shown");
    measureWindow();
    scheduleFold();
    scanScrollers();

    window.addEventListener("scroll", onWindowScroll, { passive: true });
    window.addEventListener("touchstart", () => {
      if (media.matches) {
        setChrome("shown");
        scheduleFold();
      }
    }, { passive: true });
    media.addEventListener("change", onMediaChange);

    observer = new MutationObserver(() => scanScrollers());
    observer.observe(document.body, { childList: true, subtree: true });

    return () => {
      window.removeEventListener("scroll", onWindowScroll);
      media.removeEventListener("change", onMediaChange);
      clearIdle();
      if (raf) {
        window.cancelAnimationFrame(raf);
      }
      observer?.disconnect();
      for (const el of observed) {
        el.removeEventListener("scroll", onElementScroll);
      }
      delete document.documentElement.dataset.mobileScroll;
      delete document.documentElement.dataset.mobileChrome;
      const frame = frameEl();
      if (frame instanceof HTMLElement) {
        delete frame.dataset.mobileScroll;
        delete frame.dataset.mobileChrome;
      }
    };
  }, []);

  return null;
}
