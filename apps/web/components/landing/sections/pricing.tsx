"use client";

/**
 * Pricing section ("方案") — three tiers on manuscript paper.
 *
 * The recommended plan is raised off the row as an ink slab (lg:-translate-y-4)
 * and stamped with a vermilion seal ("荐"); the other two stay quiet panel
 * cards. Cards cascade in with a staggered Reveal and lift 2px on hover —
 * the hover shift is CSS-only and gated behind `motion-safe`, and every
 * entrance primitive collapses to a plain fade under reduced motion.
 */

import { Check } from "lucide-react";

import { landingContent } from "@/components/landing/content";
import {
  CtaLink,
  Eyebrow,
  Reveal,
  SplitReveal,
} from "@/components/landing/primitives";
import { cn } from "@/lib/utils";

export function PricingSection() {
  const { pricing } = landingContent;

  return (
    <section
      id="pricing"
      className="relative scroll-mt-16 overflow-hidden bg-paper"
    >
      <div aria-hidden className="landing-grain" />

      <div className="relative mx-auto max-w-[1200px] px-5 py-24 md:px-8 md:py-32">
        <Reveal>
          <Eyebrow tone="light">{pricing.eyebrow}</Eyebrow>
        </Reveal>

        <h2 className="mt-6 font-serif text-[clamp(2.2rem,5vw,3.75rem)] leading-tight text-ink">
          <SplitReveal text={pricing.display} delay={0.05} />
        </h2>

        <div className="mt-14 grid grid-cols-1 gap-5 md:mt-20 lg:grid-cols-3 lg:gap-6">
          {pricing.tiers.map((tier, index) => (
            <Reveal
              key={tier.name}
              delay={0.1 + index * 0.12}
              className={cn(tier.featured && "lg:-translate-y-4")}
            >
              <article
                className={cn(
                  "relative flex h-full flex-col rounded-panel p-7 transition-transform duration-300 ease-paper motion-safe:hover:-translate-y-0.5 md:p-8",
                  tier.featured
                    ? "bg-ink-surface text-ink-text shadow-ink"
                    : "border border-line bg-panel shadow-hairline",
                )}
              >
                {tier.featured ? (
                  <span
                    aria-hidden
                    className="absolute -top-3 right-6 flex size-10 rotate-3 items-center justify-center bg-accent font-serif text-lg leading-none text-paper shadow-accent"
                  >
                    荐
                  </span>
                ) : null}

                <p
                  className={cn(
                    "font-mono text-micro uppercase tracking-label",
                    tier.featured ? "text-ink-text-muted" : "text-muted",
                  )}
                >
                  {tier.name}
                  {tier.featured ? (
                    <span className="sr-only">（推荐）</span>
                  ) : null}
                </p>

                <p className="mt-6 flex items-baseline gap-2">
                  <span className="font-serif text-display leading-none">
                    {tier.price}
                  </span>
                  {tier.period ? (
                    <span
                      className={cn(
                        "font-mono text-caption",
                        tier.featured ? "text-ink-text-muted" : "text-muted-soft",
                      )}
                    >
                      {tier.period}
                    </span>
                  ) : null}
                </p>

                <div
                  aria-hidden
                  className={cn(
                    "my-7 h-px w-full",
                    tier.featured ? "bg-ink-line" : "bg-line",
                  )}
                />

                <ul
                  className={cn(
                    "flex flex-col gap-3 text-sm",
                    tier.featured ? "text-ink-text-muted" : "text-ink-soft",
                  )}
                >
                  {tier.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-3">
                      <Check
                        aria-hidden
                        className="mt-0.5 size-4 shrink-0 text-accent"
                      />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>

                <div className="mt-auto pt-8">
                  <CtaLink
                    href={tier.cta.href}
                    variant={tier.featured ? "primary" : "ghost-dark"}
                    className="w-full"
                  >
                    {tier.cta.label}
                  </CtaLink>
                </div>
              </article>
            </Reveal>
          ))}
        </div>

        <Reveal delay={0.1}>
          <p className="mt-14 text-center font-mono text-sm text-muted md:mt-16">
            {pricing.footnote}
          </p>
        </Reveal>
      </div>
    </section>
  );
}
