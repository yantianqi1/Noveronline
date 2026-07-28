"use client";

/**
 * Pipeline ("主链 / THE PIPELINE") — ink-surface, scroll-driven journey.
 *
 * On lg+ viewports the section is a 400vh scroll track: a sticky h-svh stage
 * holds six nodes on one horizontal hairline, and useScroll/useTransform
 * translate the row left as the page scrolls while a gold overlay draws the
 * path with scaleX (origin-left). A mono counter and a short progress
 * hairline sit bottom-right. Below lg — and always under
 * prefers-reduced-motion — the same stages render as a static vertical stack
 * on a left spine; no sticky, no translation, and Reveal collapses to a plain
 * fade through the shared primitives.
 */

import {
  BookOpenText,
  LibraryBig,
  Network,
  Orbit,
  PenLine,
  ScrollText,
  type LucideIcon,
} from "lucide-react";
import {
  motion,
  useReducedMotion,
  useScroll,
  useTransform,
} from "motion/react";
import { useEffect, useRef, useState } from "react";

import { landingContent } from "@/components/landing/content";
import {
  Eyebrow,
  Reveal,
  SplitReveal,
} from "@/components/landing/primitives";

const { pipeline } = landingContent;

type StageIconName = (typeof pipeline.stages)[number]["icon"];

const STAGE_ICONS: Record<StageIconName, LucideIcon> = {
  BookOpenText,
  Network,
  LibraryBig,
  Orbit,
  PenLine,
  ScrollText,
};

const stageNumber = (index: number) => String(index + 1).padStart(2, "0");

/** Hairline-ringed glyph puck. `relative` so it paints over the spine/line. */
function StageMarker({ icon: Icon }: { icon: LucideIcon }) {
  return (
    <span className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-ink-line bg-ink-surface-raised">
      <Icon aria-hidden strokeWidth={1.5} className="size-5 text-ink-text" />
    </span>
  );
}

function SectionHeading() {
  return (
    <div>
      <Eyebrow tone="dark">{pipeline.eyebrow}</Eyebrow>
      <h2 className="mt-7 font-serif leading-none">
        <SplitReveal
          text={pipeline.display}
          className="text-[clamp(2.25rem,4.5vw,3.5rem)]"
        />
      </h2>
    </div>
  );
}

/** Static vertical stack: mobile default and the reduced-motion fallback. */
function PipelineStack() {
  return (
    <div className="relative overflow-hidden">
      <div aria-hidden className="landing-grain" />

      <div className="relative mx-auto max-w-[1200px] px-5 py-24 md:px-8 lg:py-32">
        <SectionHeading />

        <ol className="relative mt-14 flex flex-col gap-12 md:mt-16">
          <span
            aria-hidden
            className="absolute bottom-4 left-6 top-4 w-px -translate-x-1/2 bg-ink-line"
          />
          {pipeline.stages.map((stage, index) => (
            <li key={stage.title}>
              <Reveal delay={0.05 + index * 0.06}>
                <div className="flex items-start gap-5">
                  <StageMarker icon={STAGE_ICONS[stage.icon]} />
                  <div>
                    <span className="font-mono text-micro tracking-label text-gold">
                      {stageNumber(index)}
                    </span>
                    <h3 className="mt-2 font-serif text-xl text-ink-text">
                      {stage.title}
                    </h3>
                    <p className="mt-2.5 max-w-[30ch] text-sm text-ink-text-muted">
                      {stage.description}
                    </p>
                  </div>
                </div>
              </Reveal>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

/** Desktop journey: sticky viewport, horizontally scrubbed node track. */
function PipelineJourney() {
  const targetRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const trackRef = useRef<HTMLDivElement>(null);
  // How far the track must travel: its width beyond the sticky viewport.
  const [range, setRange] = useState(0);

  useEffect(() => {
    const track = trackRef.current;
    const viewport = viewportRef.current;
    if (!track || !viewport) return;
    const measure = () =>
      setRange(Math.max(0, track.scrollWidth - viewport.clientWidth));
    measure();
    // Covers viewport resizes and late webfont metric changes alike.
    const observer = new ResizeObserver(measure);
    observer.observe(track);
    observer.observe(viewport);
    return () => observer.disconnect();
  }, []);

  const { scrollYProgress } = useScroll({
    target: targetRef,
    offset: ["start start", "end end"],
  });
  const x = useTransform(scrollYProgress, (v) => -range * v);
  const total = pipeline.stages.length;
  const current = useTransform(scrollYProgress, (v) =>
    String(Math.min(total, Math.max(1, Math.floor(v * total) + 1))).padStart(
      2,
      "0",
    ),
  );

  return (
    <div ref={targetRef} className="relative h-[400vh]">
      <div ref={viewportRef} className="sticky top-0 h-svh overflow-hidden">
        <div aria-hidden className="landing-grain" />

        <div className="absolute inset-x-0 top-0">
          <div className="mx-auto max-w-[1200px] px-8 pt-24">
            <SectionHeading />
          </div>
        </div>

        <div className="flex h-full items-center">
          <motion.div
            ref={trackRef}
            style={{ x }}
            className="relative flex items-start gap-24 pl-[8vw] pr-[18vw] will-change-transform"
          >
            {/* The path: ink hairline base, gold overlay drawn by scroll. */}
            <span
              aria-hidden
              className="absolute inset-x-0 top-6 h-px bg-ink-line"
            />
            <motion.span
              aria-hidden
              style={{ scaleX: scrollYProgress }}
              className="absolute inset-x-0 top-6 h-px origin-left bg-gold"
            />

            {pipeline.stages.map((stage, index) => (
              <article key={stage.title} className="w-72 shrink-0">
                <div className="flex h-12 items-center gap-4">
                  <StageMarker icon={STAGE_ICONS[stage.icon]} />
                  <span className="font-mono text-micro tracking-label text-gold">
                    {stageNumber(index)}
                  </span>
                </div>
                <h3 className="mt-7 font-serif text-xl text-ink-text">
                  {stage.title}
                </h3>
                <p className="mt-3 max-w-[30ch] text-sm text-ink-text-muted">
                  {stage.description}
                </p>
              </article>
            ))}
          </motion.div>
        </div>

        <div className="absolute inset-x-0 bottom-0 pb-10">
          <div className="mx-auto flex max-w-[1200px] items-center justify-end gap-4 px-8">
            <span className="font-mono text-micro tracking-label text-ink-text-muted">
              <motion.span className="text-ink-text">{current}</motion.span>
              {" / "}
              {String(total).padStart(2, "0")}
            </span>
            <span aria-hidden className="relative h-px w-28 bg-ink-line">
              <motion.span
                style={{ scaleX: scrollYProgress }}
                className="absolute inset-0 origin-left bg-gold"
              />
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function PipelineSection() {
  const reduce = useReducedMotion();

  return (
    <section id="pipeline" className="relative bg-ink-surface text-ink-text">
      {reduce ? (
        <PipelineStack />
      ) : (
        <>
          <div className="lg:hidden">
            <PipelineStack />
          </div>
          <div className="hidden lg:block">
            <PipelineJourney />
          </div>
        </>
      )}
    </section>
  );
}
