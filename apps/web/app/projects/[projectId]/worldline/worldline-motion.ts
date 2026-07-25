"use client";

import { useReducedMotion } from "motion/react";

/**
 * Shared motion language for the Worldline workbench. Mirrors the Asset
 * Library's timing/easing so every surface (timeline cards, inspector, overlay)
 * moves the same way and degrades to opacity-only under reduced motion.
 */

export const EASE = [0.22, 1, 0.36, 1] as const;

export const DUR = {
  fast: 0.16,
  med: 0.22,
  slow: 0.28,
} as const;

/** Reduced-motion-safe fade-up entrance (timeline events, panels). */
export function useFadeUp() {
  const reduce = useReducedMotion();
  return {
    initial: reduce ? { opacity: 0 } : { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    exit: reduce ? { opacity: 0 } : { opacity: 0, y: 6 },
  };
}

/** Reduced-motion-safe horizontal slide (inspector / overlay panels). */
export function useSlideIn() {
  const reduce = useReducedMotion();
  return {
    initial: reduce ? { opacity: 0 } : { opacity: 0, x: 12 },
    animate: { opacity: 1, x: 0 },
    exit: reduce ? { opacity: 0 } : { opacity: 0, x: 8 },
  };
}
