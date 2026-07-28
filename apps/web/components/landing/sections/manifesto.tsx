"use client";

/**
 * Manifesto — the paper declaration section ("故事越大，记忆越脆弱。").
 *
 * Editorial-magazine composition on `bg-paper`: a hairline-ruled eyebrow row,
 * the giant SplitReveal display line with 「脆弱」 in vermilion, three
 * struck-through margin notes scattered like killed drafts, the body column
 * offset right for asymmetry, and a slightly tilted marquee strip of story
 * nouns at the foot. A ghost "01" serial overprints the display's top-right
 * corner — decoration only, hidden from assistive tech.
 *
 * All entrances go through Reveal/SplitReveal, so reduced motion collapses
 * them to plain fades; the marquee freezes itself under reduced motion. The
 * note tilts and the marquee's -2deg lean are static styling, not animation.
 */

import { cn } from "@/lib/utils";

import { landingContent } from "../content";
import { Eyebrow, Marquee, Reveal, SplitReveal } from "../primitives";

/** Substring of `manifesto.display` rendered in vermilion. */
const ACCENT_WORD = "脆弱";

/** Seconds between characters of the display line. */
const CHAR_STAGGER = 0.04;

/**
 * Per-note static tilt plus its scattered `lg` placement (notes stay in flow,
 * stacked, below `lg`). Positions assume the display's natural wrap: the
 * accent word plus its closing punctuation are kept on one nowrap cluster, so
 * line two is always just 「脆弱。」 and the space right of it is free.
 */
const NOTE_LAYOUTS = [
  { rotate: "-rotate-2", placement: "lg:-top-12 lg:right-[6%]" },
  { rotate: "rotate-[1.5deg]", placement: "lg:bottom-6 lg:left-[34%]" },
  { rotate: "-rotate-1", placement: "lg:-bottom-16 lg:right-[14%]" },
] as const;

export function ManifestoSection() {
  const { manifesto } = landingContent;

  // Split the display line around the accent word so 「脆弱」 can take the
  // vermilion ink while the per-character stagger continues seamlessly. The
  // accent and the trailing punctuation share one nowrap cluster: CJK may
  // break anywhere, and a lone "。" — or the accent word split across lines —
  // would read as a typesetting bug.
  const accentAt = manifesto.display.indexOf(ACCENT_WORD);
  const head = accentAt >= 0 ? manifesto.display.slice(0, accentAt) : manifesto.display;
  const tail = accentAt >= 0 ? manifesto.display.slice(accentAt + ACCENT_WORD.length) : "";
  const headLen = Array.from(head).length;
  const accentLen = Array.from(ACCENT_WORD).length;

  // One marquee cycle is ~25 hanzi — too narrow to cover wide viewports with
  // the primitive's two copies, so the loop repeats the cycle twice per copy.
  const marqueeItems = [...manifesto.marquee, ...manifesto.marquee];

  return (
    <section className="relative overflow-hidden bg-paper pb-24 pt-20 md:pb-36 md:pt-28 lg:pb-44 lg:pt-40">
      <div aria-hidden className="landing-grain" />

      <div className="relative mx-auto max-w-[1200px] px-5 md:px-8">
        <Reveal y={12}>
          <div className="flex items-baseline justify-between gap-6 border-t border-line pt-5">
            <Eyebrow tone="light">{manifesto.eyebrow}</Eyebrow>
            <span
              aria-hidden
              className="font-mono text-micro uppercase tracking-label text-muted-soft"
            >
              Manifesto
            </span>
          </div>
        </Reveal>

        <div className="relative mt-12 md:mt-16 lg:mt-24">
          <span
            aria-hidden
            className="pointer-events-none absolute -top-16 right-0 hidden select-none font-serif text-[14vw] leading-none text-ink/5 lg:block"
          >
            01
          </span>

          <h2 className="font-serif leading-tight text-ink text-[clamp(2.25rem,9vw,7rem)]">
            <SplitReveal text={head} stagger={CHAR_STAGGER} />
            {accentAt >= 0 ? (
              <span className="whitespace-nowrap">
                <span className="text-accent">
                  <SplitReveal
                    text={ACCENT_WORD}
                    delay={headLen * CHAR_STAGGER}
                    stagger={CHAR_STAGGER}
                  />
                </span>
                <SplitReveal
                  text={tail}
                  delay={(headLen + accentLen) * CHAR_STAGGER}
                  stagger={CHAR_STAGGER}
                />
              </span>
            ) : null}
          </h2>

          <div className="mt-10 flex flex-col items-start gap-3 lg:mt-0">
            {manifesto.marginNotes.map((note, i) => {
              const layout = NOTE_LAYOUTS[i % NOTE_LAYOUTS.length];
              return (
                <Reveal
                  key={note}
                  delay={0.45 + i * 0.14}
                  y={14}
                  className={cn("lg:absolute", layout.placement)}
                >
                  <span
                    className={cn(
                      "inline-block max-w-[15rem] border border-line-soft bg-paper-deep px-4 py-2.5 shadow-hairline",
                      "font-serif text-sm leading-relaxed text-muted line-through decoration-ink/40",
                      layout.rotate,
                    )}
                  >
                    {note}
                  </span>
                </Reveal>
              );
            })}
          </div>
        </div>

        <Reveal delay={0.15} className="mt-14 lg:ml-[26%] lg:mt-28">
          <p className="max-w-[62ch] text-md text-ink-soft">{manifesto.body}</p>
        </Reveal>
      </div>

      <div className="mt-20 md:mt-28 lg:mt-36">
        <Reveal y={20}>
          <div className="-rotate-2">
            <div className="mx-[-4%] w-[108%] border-y border-line py-4 md:py-5">
              <Marquee
                items={marqueeItems}
                separator="·"
                speed={40}
                className="font-mono text-sm tracking-[0.3em] text-muted"
              />
            </div>
          </div>
        </Reveal>
      </div>
    </section>
  );
}
