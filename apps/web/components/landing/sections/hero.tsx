"use client";

/**
 * Hero — the dark ink opening of the landing page ("墨·纸·印").
 *
 * A drifting HanziField canvas and film grain sit under a left-bottom
 * editorial composition: mono eyebrow, two giant serif display lines rising
 * per character (the accent word in vermilion), one muted sub line, the
 * magnetic primary CTA beside a ghost-light secondary, and a hairline-ruled
 * stat row. A vertical marginal note rides the right edge; a breathing
 * scroll cue anchors the bottom centre.
 *
 * All choreography degrades under prefers-reduced-motion: the primitives
 * collapse to opacity fades, HanziField renders a single static frame, and
 * the scroll cue stays still.
 */

import { ArrowDown } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";

import { HanziField } from "@/components/landing/canvas-field";
import { landingContent } from "@/components/landing/content";
import {
  CtaLink,
  Eyebrow,
  Magnetic,
  Reveal,
  SplitReveal,
} from "@/components/landing/primitives";
import { cn } from "@/lib/utils";

/** Per-character cadence of the two display lines. */
const CHAR_STAGGER = 0.04;
/** Seconds before the first display character rises. */
const LINE_ONE_DELAY = 0.15;

export function HeroSection() {
  const reduce = useReducedMotion();
  const { hero, manifesto } = landingContent;

  const [lineOne, lineTwo] = hero.displayLines;

  // Split the second display line around the accent word so it alone renders
  // in vermilion while the per-character rise continues seamlessly across the
  // boundary. `className` (not `charClassName`) carries the colour so it also
  // survives the reduced-motion plain-text path.
  const accentAt = lineTwo.indexOf(hero.displayAccent);
  const hasAccent = accentAt >= 0;
  const beforeAccent = hasAccent ? lineTwo.slice(0, accentAt) : lineTwo;
  const afterAccent = hasAccent
    ? lineTwo.slice(accentAt + hero.displayAccent.length)
    : "";

  const lineTwoDelay =
    LINE_ONE_DELAY + Array.from(lineOne).length * CHAR_STAGGER + 0.12;
  const accentDelay =
    lineTwoDelay + Array.from(beforeAccent).length * CHAR_STAGGER;
  const afterDelay =
    accentDelay + Array.from(hero.displayAccent).length * CHAR_STAGGER;

  // Vertical marginal note: the marquee vocabulary's first four entries.
  const verticalNote = manifesto.marquee.slice(0, 4).join("·");

  return (
    <section className="relative flex min-h-svh flex-col overflow-hidden bg-ink-surface text-ink-text">
      {/* Ambient layers: drifting hanzi field under film grain. */}
      <div className="absolute inset-0 h-full w-full">
        <HanziField
          characters={hero.canvasCharacters}
          className="block h-full w-full"
        />
      </div>
      <div aria-hidden className="landing-grain" />

      {/* Vertical marginal note on the right edge. */}
      <span
        aria-hidden
        className="writing-vertical absolute right-6 top-1/2 hidden -translate-y-1/2 select-none font-serif text-base tracking-[0.3em] text-ink-text-muted opacity-40 lg:block"
      >
        {verticalNote}
      </span>

      {/* Left-bottom editorial composition. */}
      <div className="relative mx-auto flex w-full max-w-[1200px] flex-1 flex-col justify-end px-5 pb-28 pt-32 md:px-8 md:pb-32">
        <Reveal delay={0.05} y={16}>
          <Eyebrow tone="dark">{hero.eyebrow}</Eyebrow>
        </Reveal>

        <h1 className="mt-7 font-serif text-[clamp(3rem,13vw,9rem)] leading-none">
          <SplitReveal
            className="block"
            text={lineOne}
            delay={LINE_ONE_DELAY}
            stagger={CHAR_STAGGER}
          />
          <span className="block">
            {beforeAccent ? (
              <SplitReveal
                text={beforeAccent}
                delay={lineTwoDelay}
                stagger={CHAR_STAGGER}
              />
            ) : null}
            {hasAccent ? (
              <SplitReveal
                className="text-accent"
                text={hero.displayAccent}
                delay={accentDelay}
                stagger={CHAR_STAGGER}
              />
            ) : null}
            {afterAccent ? (
              <SplitReveal
                text={afterAccent}
                delay={afterDelay}
                stagger={CHAR_STAGGER}
              />
            ) : null}
          </span>
        </h1>

        <Reveal delay={0.9} y={20} className="mt-8 max-w-[44ch]">
          <p className="text-base leading-relaxed text-ink-text-muted md:text-lg">
            {hero.sub}
          </p>
        </Reveal>

        <Reveal delay={1.05} y={20} className="mt-10">
          <div className="flex flex-wrap items-center gap-4">
            <Magnetic strength={0.3}>
              <CtaLink href={hero.primaryCta.href} size="lg">
                {hero.primaryCta.label}
              </CtaLink>
            </Magnetic>
            <CtaLink
              href={hero.secondaryCta.href}
              variant="ghost-light"
              size="lg"
            >
              {hero.secondaryCta.label}
            </CtaLink>
          </div>
        </Reveal>

        <Reveal delay={1.2} y={16} className="mt-14 md:mt-16">
          <ul className="flex flex-col gap-3 border-t border-ink-line pt-5 md:flex-row md:items-center md:gap-0">
            {hero.stats.map((stat, index) => (
              <li
                key={stat}
                className={cn(
                  "font-mono text-micro uppercase tracking-label text-ink-text-muted",
                  index > 0 && "md:border-l md:border-ink-line md:pl-6",
                  index < hero.stats.length - 1 && "md:pr-6",
                )}
              >
                {stat}
              </li>
            ))}
          </ul>
        </Reveal>
      </div>

      {/* Breathing scroll cue, bottom centre; static under reduced motion. */}
      <Reveal
        delay={1.5}
        y={10}
        className="pointer-events-none absolute inset-x-0 bottom-6 hidden md:block"
      >
        <motion.div
          className="mx-auto flex w-fit flex-col items-center gap-2 text-ink-text-muted"
          animate={reduce ? undefined : { y: [0, 6, 0] }}
          transition={{
            duration: 2.6,
            repeat: Number.POSITIVE_INFINITY,
            ease: "easeInOut",
          }}
        >
          <ArrowDown aria-hidden className="size-4" strokeWidth={1.25} />
          <span className="font-mono text-micro uppercase tracking-label">
            Scroll
          </span>
        </motion.div>
      </Reveal>
    </section>
  );
}
