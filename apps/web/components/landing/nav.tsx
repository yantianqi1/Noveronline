"use client";

/**
 * Fixed landing chrome.
 *
 * `mix-blend-difference` with white foregrounds lets one header travel across
 * the ink hero and the paper sections without theme switching — white text
 * differences to near-black over paper and stays white over ink. Everything
 * inside must therefore stay grayscale; the vermilion CtaLink variants would
 * blend unpredictably, so the nav restyles ghost-light to plain white.
 *
 * NOTE: this component intentionally does NOT import ./landing.css — Next
 * only accepts first-party global CSS from layout files. Import it once from
 * the landing route's layout.
 */

import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

import { landingContent } from "./content";
import { CtaLink } from "./primitives";

export default function LandingNav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  const { nav } = landingContent;

  return (
    <header
      className={cn(
        "fixed inset-x-0 top-0 z-50 mix-blend-difference",
        "border-b border-transparent transition-colors duration-300",
        scrolled && "border-white/25",
      )}
    >
      <div className="mx-auto flex h-16 max-w-[1200px] items-center justify-between px-5 md:px-8">
        <a href="#top" className="flex items-baseline gap-3 text-white">
          <span className="font-serif text-lg leading-none">{nav.brand}</span>
          <span className="hidden font-mono text-micro uppercase tracking-label text-white/55 md:inline">
            {nav.brandSub}
          </span>
        </a>

        <nav aria-label="Landing sections" className="hidden items-center gap-7 md:flex">
          {nav.links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-sm text-white/70 transition-colors hover:text-white"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <CtaLink
          href={nav.cta.href}
          size="sm"
          variant="ghost-light"
          className="border-white/35 text-white hover:border-white hover:text-white"
        >
          {nav.cta.label}
        </CtaLink>
      </div>
    </header>
  );
}
