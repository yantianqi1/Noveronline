"use client";

/**
 * Motion primitives for the landing page ("墨·纸·印").
 *
 * Every entrance respects `prefers-reduced-motion` by collapsing travel/blur
 * down to a plain opacity fade — same information, no vestibular trigger.
 * Easing mirrors `--ease-paper` so JS-driven and CSS-driven motion agree.
 */

import { ArrowUpRight } from "lucide-react";
import {
  motion,
  useMotionValue,
  useReducedMotion,
  useSpring,
} from "motion/react";
import Link from "next/link";
import {
  useCallback,
  useRef,
  type CSSProperties,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";

import { EASE } from "@/lib/motion";
import { cn } from "@/lib/utils";

/** The paper easing, re-exported so sections import from one place. */
export const EASE_OUT = EASE;

/** Soft settle — entrances, drawers, large surfaces. */
export const SPRING_SOFT = {
  type: "spring",
  stiffness: 120,
  damping: 26,
  mass: 0.9,
} as const;

/** Snappy settle — small controls, hover responses. */
export const SPRING_SNAP = {
  type: "spring",
  stiffness: 300,
  damping: 30,
} as const;

/* ── Reveal ─────────────────────────────────────────────────────────────── */

export interface RevealProps {
  children: ReactNode;
  /** Seconds before the entrance starts. */
  delay?: number;
  /** Vertical travel in px; collapses to 0 under reduced motion. */
  y?: number;
  /** Also resolve an 8px blur during the entrance. */
  blur?: boolean;
  className?: string;
  /** Animate only on the first viewport entry. */
  once?: boolean;
}

export function Reveal({
  children,
  delay = 0,
  y = 28,
  blur = false,
  className,
  once = true,
}: RevealProps) {
  const reduce = useReducedMotion();
  const hidden = reduce
    ? { opacity: 0 }
    : { opacity: 0, y, ...(blur ? { filter: "blur(8px)" } : {}) };
  const shown = reduce
    ? { opacity: 1 }
    : { opacity: 1, y: 0, ...(blur ? { filter: "blur(0px)" } : {}) };

  return (
    <motion.div
      className={className}
      initial={hidden}
      whileInView={shown}
      viewport={{ once, margin: "-15% 0px" }}
      transition={{ duration: 0.9, delay, ease: EASE_OUT }}
    >
      {children}
    </motion.div>
  );
}

/* ── SplitReveal ────────────────────────────────────────────────────────── */

export interface SplitRevealProps {
  /** Text split per character; CJK-safe. */
  text: string;
  className?: string;
  /** Extra classes on each animated character. */
  charClassName?: string;
  /** Seconds before the first character rises. */
  delay?: number;
  /** Seconds between characters. */
  stagger?: number;
}

/**
 * Per-character masked rise for display headings. Reduced motion renders the
 * plain string so screen readers and vestibular-sensitive users get the same
 * content without the choreography.
 */
export function SplitReveal({
  text,
  className,
  charClassName,
  delay = 0,
  stagger = 0.035,
}: SplitRevealProps) {
  const reduce = useReducedMotion();
  if (reduce) {
    return <span className={className}>{text}</span>;
  }

  return (
    <span className={className} aria-label={text}>
      {Array.from(text).map((char, index) => (
        <span
          key={`${char}-${index}`}
          aria-hidden
          className="inline-block overflow-hidden align-bottom"
        >
          <motion.span
            className={cn("inline-block will-change-transform", charClassName)}
            initial={{ y: "110%" }}
            whileInView={{ y: "0%" }}
            viewport={{ once: true, margin: "-10% 0px" }}
            transition={{
              duration: 0.7,
              delay: delay + index * stagger,
              ease: EASE_OUT,
            }}
          >
            {char === " " ? " " : char}
          </motion.span>
        </span>
      ))}
    </span>
  );
}

/* ── Magnetic ───────────────────────────────────────────────────────────── */

export interface MagneticProps {
  children: ReactNode;
  /** Pull factor: offset = pointer delta × strength. */
  strength?: number;
  className?: string;
}

/**
 * Pointer magnetism for CTAs and seal motifs. Only mouse pointers engage it —
 * touch would drag content out from under the finger — and reduced motion
 * leaves the element static.
 */
export function Magnetic({ children, strength = 0.35, className }: MagneticProps) {
  const reduce = useReducedMotion();
  const ref = useRef<HTMLDivElement>(null);
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  // Responsive but damped: the element should feel pulled, not dragged.
  const springX = useSpring(x, { stiffness: 180, damping: 15, mass: 0.1 });
  const springY = useSpring(y, { stiffness: 180, damping: 15, mass: 0.1 });

  const onPointerMove = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      if (reduce || event.pointerType !== "mouse" || !ref.current) return;
      const rect = ref.current.getBoundingClientRect();
      x.set((event.clientX - (rect.left + rect.width / 2)) * strength);
      y.set((event.clientY - (rect.top + rect.height / 2)) * strength);
    },
    [reduce, strength, x, y],
  );

  const onPointerLeave = useCallback(() => {
    x.set(0);
    y.set(0);
  }, [x, y]);

  return (
    <motion.div
      ref={ref}
      className={className}
      style={{ x: springX, y: springY }}
      onPointerMove={onPointerMove}
      onPointerLeave={onPointerLeave}
    >
      {children}
    </motion.div>
  );
}

/* ── Marquee ────────────────────────────────────────────────────────────── */

export interface MarqueeProps {
  items: string[];
  /** Glyph rendered between items. */
  separator?: string;
  /** Seconds per full loop. */
  speed?: number;
  reverse?: boolean;
  className?: string;
}

/**
 * Infinite loop: the track holds two identical copies and the `marquee`
 * keyframes (defined in landing.css) translate it -50%. Reduced motion leaves
 * the track static.
 */
export function Marquee({
  items,
  separator = "·",
  speed = 32,
  reverse = false,
  className,
}: MarqueeProps) {
  const reduce = useReducedMotion();
  const trackStyle: CSSProperties | undefined = reduce
    ? undefined
    : {
        animation: `marquee ${speed}s linear infinite`,
        animationDirection: reverse ? "reverse" : "normal",
      };

  return (
    <div className={cn("overflow-hidden", className)}>
      <div className="flex w-max" style={trackStyle}>
        {[0, 1].map((copy) => (
          <div
            key={copy}
            aria-hidden={copy === 1}
            className="flex shrink-0 items-baseline"
          >
            {items.map((item, index) => (
              <span key={index} className="flex items-baseline whitespace-nowrap">
                <span>{item}</span>
                <span aria-hidden className="mx-[0.6em] opacity-40">
                  {separator}
                </span>
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Eyebrow ────────────────────────────────────────────────────────────── */

export interface EyebrowProps {
  children: ReactNode;
  /** Surface the label sits on: "light" paper or "dark" ink. */
  tone?: "dark" | "light";
  className?: string;
}

export function Eyebrow({ children, tone = "light", className }: EyebrowProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-3 font-mono text-micro uppercase tracking-label",
        tone === "light" ? "text-muted" : "text-ink-text-muted",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn("h-px w-7", tone === "light" ? "bg-line" : "bg-ink-line")}
      />
      {children}
    </span>
  );
}

/* ── CtaLink ────────────────────────────────────────────────────────────── */

export interface CtaLinkProps {
  href: string;
  children: ReactNode;
  /**
   * `primary` is the single vermilion action; `ghost-dark` is a hairline
   * outline for paper surfaces, `ghost-light` for ink surfaces.
   */
  variant?: "primary" | "ghost-dark" | "ghost-light";
  size?: "sm" | "md" | "lg";
  className?: string;
}

const CTA_SIZES: Record<NonNullable<CtaLinkProps["size"]>, string> = {
  sm: "h-9 px-4 text-sm",
  md: "h-11 px-6 text-base",
  lg: "h-13 px-7 text-md",
};

export function CtaLink({
  href,
  children,
  variant = "primary",
  size = "md",
  className,
}: CtaLinkProps) {
  return (
    <Link
      href={href}
      className={cn(
        "group relative inline-flex items-center justify-center gap-2 overflow-hidden whitespace-nowrap rounded-control font-medium transition-colors",
        CTA_SIZES[size],
        variant === "primary" && "bg-accent text-panel shadow-accent",
        variant === "ghost-dark" &&
          "border border-line text-ink hover:border-accent/60 hover:text-accent",
        variant === "ghost-light" &&
          "border border-ink-line text-ink-text hover:border-ink-text/40",
        className,
      )}
    >
      {/* Vermilion-deep sweep, drawn under the label. */}
      {variant === "primary" ? (
        <span
          aria-hidden
          className="absolute inset-0 -translate-x-full bg-accent-strong transition-transform duration-[var(--duration-slow)] ease-paper group-hover:translate-x-0"
        />
      ) : null}
      <span className="relative">{children}</span>
      <ArrowUpRight
        aria-hidden
        className="relative size-4 transition-transform ease-paper group-hover:translate-x-0.5 group-hover:-translate-y-0.5"
      />
    </Link>
  );
}
