"use client";

import { useReducedMotion } from "motion/react";

/**
 * The app's single motion language.
 *
 * Consolidates what were three byte-identical copies (asset-motion.ts,
 * worldline-motion.ts, character-motion.ts). The timings are the three tiers
 * the design spec mandates — 160 / 220 / 280ms with 220ms for ordinary state
 * changes — and the easing matches `--ease-paper` in globals.css, so a panel
 * animated with `motion/react` and one animated with a Tailwind `transition-*`
 * utility move on the same curve.
 */

export const EASE = [0.22, 1, 0.36, 1] as const;

export const DUR = {
  fast: 0.16,
  med: 0.22,
  slow: 0.28,
} as const;

/**
 * Reduced-motion-safe fade-up entrance. When the user prefers reduced motion
 * the vertical travel collapses away, leaving a plain opacity fade — same
 * information, no vestibular trigger.
 */
export function useFadeUp() {
  const reduce = useReducedMotion();
  return {
    initial: reduce ? { opacity: 0 } : { opacity: 0, y: 8 },
    animate: { opacity: 1, y: 0 },
    exit: reduce ? { opacity: 0 } : { opacity: 0, y: 6 },
  };
}

/** Reduced-motion-safe horizontal slide, for inspectors and overlay panels. */
export function useSlideIn() {
  const reduce = useReducedMotion();
  return {
    initial: reduce ? { opacity: 0 } : { opacity: 0, x: 12 },
    animate: { opacity: 1, x: 0 },
    exit: reduce ? { opacity: 0 } : { opacity: 0, x: 8 },
  };
}
