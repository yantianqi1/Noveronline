"use client";

import { useReducedMotion } from "motion/react";

/**
 * Shared motion language for the Asset Library workbench.
 *
 * One place for the timing/easing tokens and the reduced-motion-safe entrance
 * variants, so every surface (list rows, inspector, empty states, popovers)
 * moves the same way and degrades to opacity-only when the user prefers
 * reduced motion. Reuses the timing already established across the app
 * (user-menu popover, upload-panel stagger): 160/220/280ms, expo-out ease.
 */

export const EASE = [0.22, 1, 0.36, 1] as const;

export const DUR = {
  fast: 0.16,
  med: 0.22,
  slow: 0.28,
} as const;

/**
 * Reduced-motion-safe fade-up entrance variants. When the user prefers reduced
 * motion the vertical travel collapses away, leaving a plain opacity fade —
 * same information, no vestibular trigger.
 */
export function useFadeUp() {
  const reduce = useReducedMotion();
  return {
    initial: reduce ? { opacity: 0 } : { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    exit: reduce ? { opacity: 0 } : { opacity: 0, y: 6 },
  };
}

/**
 * Reduced-motion-safe horizontal slide (inspector / overlay panels). Collapses
 * the x-travel under reduced motion.
 */
export function useSlideIn() {
  const reduce = useReducedMotion();
  return {
    initial: reduce ? { opacity: 0 } : { opacity: 0, x: 12 },
    animate: { opacity: 1, x: 0 },
    exit: reduce ? { opacity: 0 } : { opacity: 0, x: 8 },
  };
}
