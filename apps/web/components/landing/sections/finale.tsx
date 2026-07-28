"use client";

/**
 * Finale + footer — the landing page's dark closing movement ("印").
 *
 * A gold-tinted HanziField drifts behind the whole section: the giant
 * SplitReveal display line with its vermilion 「记住你」, the magnetic
 * primary CTA, and finally the footer behind a hairline top border. All
 * choreography comes from the shared primitives, so reduced motion collapses
 * to static text plus a single canvas frame without extra handling here.
 */

import { ArrowUp, GitBranch, Mail, type LucideIcon } from "lucide-react";

import { HanziField } from "@/components/landing/canvas-field";
import {
  landingContent,
  type FooterColumn,
  type LandingIconName,
} from "@/components/landing/content";
import {
  CtaLink,
  Magnetic,
  Reveal,
  SplitReveal,
} from "@/components/landing/primitives";

/** Substring of `finale.display` stamped in vermilion. */
const DISPLAY_ACCENT = "记住你";
/** Shared per-character cadence so the three SplitReveal runs stay in phase. */
const DISPLAY_STAGGER = 0.045;

/** Icons referenced by name from `footer.columns` (the contact column). */
const FOOTER_ICONS: Partial<Record<LandingIconName, LucideIcon>> = {
  GitBranch,
  Mail,
};

const charCount = (text: string) => Array.from(text).length;

/** Locate `accent` inside `text` so it can take its own char treatment. */
function splitAroundAccent(text: string, accent: string) {
  const start = text.indexOf(accent);
  if (start < 0) return null;
  return {
    before: text.slice(0, start),
    accent,
    after: text.slice(start + accent.length),
  };
}

export function FinaleSection() {
  const { finale, footer, nav, hero } = landingContent;
  const parts = splitAroundAccent(finale.display, DISPLAY_ACCENT);
  // `footer.columns` is a `satisfies` literal, so widen it to the exported
  // contract before reading the optional `icon` field.
  const columns: FooterColumn[] = footer.columns;

  return (
    <section
      id="finale"
      className="relative overflow-hidden bg-ink-surface text-ink-text"
    >
      <HanziField
        className="absolute inset-0 h-full w-full"
        density={0.6}
        tint="#b5854a"
      />
      <div aria-hidden className="landing-grain" />

      {/* Closing statement. */}
      <div className="relative mx-auto flex max-w-[1200px] flex-col items-center px-5 pb-24 pt-32 text-center md:px-8 md:pb-32 md:pt-44">
        <h2
          aria-label={finale.display}
          className="font-serif text-[clamp(2.25rem,9vw,7rem)] font-semibold leading-tight"
        >
          <span aria-hidden>
            {parts ? (
              <>
                <SplitReveal text={parts.before} stagger={DISPLAY_STAGGER} />
                <SplitReveal
                  text={parts.accent}
                  charClassName="text-accent"
                  delay={charCount(parts.before) * DISPLAY_STAGGER}
                  stagger={DISPLAY_STAGGER}
                />
                <SplitReveal
                  text={parts.after}
                  delay={
                    (charCount(parts.before) + charCount(parts.accent)) *
                    DISPLAY_STAGGER
                  }
                  stagger={DISPLAY_STAGGER}
                />
              </>
            ) : (
              <SplitReveal text={finale.display} stagger={DISPLAY_STAGGER} />
            )}
          </span>
        </h2>

        <Reveal delay={0.8} y={20} className="mt-12 md:mt-16">
          <Magnetic>
            <CtaLink href={finale.cta.href} variant="primary" size="lg">
              {finale.cta.label}
            </CtaLink>
          </Magnetic>
        </Reveal>
      </div>

      {/* Footer. */}
      <footer className="relative border-t border-ink-line">
        <Reveal y={24}>
          <div className="mx-auto max-w-[1200px] px-5 py-14 md:px-8 md:py-20">
            <div className="grid gap-12 sm:grid-cols-2 lg:grid-cols-[1.5fr_1fr_1fr_1fr] lg:gap-8">
              <div>
                <a
                  href="#top"
                  className="inline-flex min-h-10 items-center font-serif text-xl text-ink-text transition-colors hover:text-gold"
                >
                  {nav.brand}
                </a>
                <p className="mt-1 font-mono text-micro uppercase tracking-label text-ink-text-muted">
                  {nav.brandSub}
                </p>
                <p className="mt-5 max-w-[32ch] font-mono text-micro uppercase tracking-label text-ink-text-muted opacity-70">
                  {hero.eyebrow}
                </p>
              </div>

              {columns.map((column) => (
                <nav key={column.title} aria-label={column.title}>
                  <h3 className="font-mono text-micro uppercase tracking-label text-ink-text-muted">
                    {column.title}
                  </h3>
                  <ul className="mt-3">
                    {column.links.map((link) => {
                      const Icon = link.icon
                        ? FOOTER_ICONS[link.icon]
                        : undefined;
                      return (
                        <li key={link.label}>
                          <a
                            href={link.href}
                            className="group inline-flex min-h-10 items-center gap-2.5 text-sm text-ink-text-muted transition-colors hover:text-ink-text"
                          >
                            {Icon ? (
                              <Icon
                                aria-hidden
                                className="size-4 text-gold/70 transition-colors group-hover:text-gold"
                              />
                            ) : null}
                            {link.label}
                          </a>
                        </li>
                      );
                    })}
                  </ul>
                </nav>
              ))}
            </div>

            <div className="mt-14 flex flex-col border-t border-ink-line pt-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="flex min-h-10 items-center font-mono text-micro text-ink-text-muted opacity-80">
                {footer.bottom}
              </p>
              <a
                href="#top"
                className="group inline-flex min-h-10 items-center gap-2 self-start font-mono text-micro uppercase tracking-label text-ink-text-muted transition-colors hover:text-ink-text sm:self-auto"
              >
                回到顶部
                <ArrowUp
                  aria-hidden
                  className="size-3.5 motion-safe:transition-transform motion-safe:group-hover:-translate-y-0.5"
                />
              </a>
            </div>
          </div>
        </Reveal>
      </footer>
    </section>
  );
}
