"use client";

import { motion, type Variants } from "motion/react";
import { Feather } from "lucide-react";

/**
 * Animated masthead for the vermilion cover.
 *
 * The whole plate is choreographed like a book being opened and stamped:
 * the brand row fades in, each hanzi of the vertical title rises into place
 * with a slight settle (as if brushed), the hairline rule draws itself, and
 * finally the white seal drops in with a soft press. All animation is pure
 * opacity/transform, respects the parent's layout, and adds no repaints of
 * the form column.
 */

const easeOut = [0.22, 1, 0.36, 1] as const;

const brandRow: Variants = {
  hidden: { opacity: 0, y: -8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: easeOut } },
};

const masthead: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.14, delayChildren: 0.25 } },
};

// Each hanzi: rises from below, soft blur resolving to sharp — like ink settling.
const hanzi: Variants = {
  hidden: { opacity: 0, y: 26, filter: "blur(6px)" },
  show: {
    opacity: 1,
    y: 0,
    filter: "blur(0px)",
    transition: { duration: 0.6, ease: easeOut },
  },
};

const rule: Variants = {
  hidden: { scaleY: 0, opacity: 0 },
  show: {
    scaleY: 1,
    opacity: 1,
    transition: { duration: 0.7, ease: easeOut, delay: 0.15 },
  },
};

const subtitle: Variants = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: easeOut, delay: 0.35 } },
};

// The seal stamps down: overshoot scale + a quick settle, like a chop hitting paper.
const seal: Variants = {
  hidden: { opacity: 0, scale: 1.4, rotate: -6, y: -10 },
  show: {
    opacity: 1,
    scale: 1,
    rotate: 0,
    y: 0,
    transition: { type: "spring", stiffness: 320, damping: 20, delay: 1.05 },
  },
};

const colophon: Variants = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: easeOut, delay: 1.2 } },
};

const TITLE = "墨鱼小说";

export function CoverMasthead() {
  return (
    <>
      {/* top brand row */}
      <motion.div
        variants={brandRow}
        initial="hidden"
        animate="show"
        className="relative z-10 flex items-center gap-3 px-12 pt-12"
      >
        <span className="grid size-10 place-items-center rounded-[10px] bg-white/12 text-white ring-1 ring-white/25 backdrop-blur-sm">
          <Feather className="size-4.5" aria-hidden />
        </span>
        <span className="text-[13px] font-medium tracking-[0.28em] text-white/85">
          MIROFISH NOVEL
        </span>
      </motion.div>

      {/* vertical masthead */}
      <div className="relative z-10 flex flex-1 items-center justify-center overflow-hidden px-8 py-6">
        <motion.div
          variants={masthead}
          initial="hidden"
          animate="show"
          className="relative flex h-full max-h-[600px] items-center justify-center gap-10"
        >
          {/* vertical title — one motion.span per hanzi, staggered */}
          <h1
            aria-label={TITLE}
            className="select-none font-brush font-semibold text-white"
            style={{
              writingMode: "vertical-rl",
              textOrientation: "upright",
              fontSize: "clamp(72px, 6.8vw, 112px)",
              letterSpacing: "0.18em",
              lineHeight: 1,
              textShadow: "0 2px 28px rgba(60,8,6,0.5)",
            }}
          >
            {TITLE.split("").map((char, index) => (
              <motion.span
                key={`${char}-${index}`}
                variants={hanzi}
                className="inline-block"
                aria-hidden
              >
                {char}
              </motion.span>
            ))}
          </h1>

          {/* hairline rule draws itself between title and subtitle */}
          <motion.span
            aria-hidden
            variants={rule}
            style={{ transformOrigin: "top" }}
            className="w-px self-stretch bg-gradient-to-b from-transparent via-white/30 to-transparent"
          />

          {/* vertical subtitle */}
          <motion.p
            variants={subtitle}
            className="select-none font-serif text-white/70"
            style={{
              writingMode: "vertical-rl",
              textOrientation: "upright",
              fontSize: "15px",
              letterSpacing: "0.52em",
              paddingTop: "10px",
            }}
          >
            长篇小说工作台
          </motion.p>

          {/* seal — stamps in at the foot of the masthead */}
          <motion.div
            variants={seal}
            className="absolute -bottom-2 right-0 grid size-14 place-items-center rounded-[6px] bg-white text-accent shadow-[0_6px_18px_-4px_rgba(60,8,6,0.5)] ring-1 ring-black/5"
          >
            <span className="font-brush text-[26px] leading-none">著</span>
          </motion.div>
        </motion.div>
      </div>

      {/* bottom colophon */}
      <motion.div
        variants={colophon}
        initial="hidden"
        animate="show"
        className="relative z-10 flex items-end justify-between gap-6 px-12 pb-12"
      >
        <p className="max-w-[250px] font-serif text-[14px] leading-[1.9] text-white/75">
          把故事世界、人物与章节，
          <br />
          收进一处安静的地方。
        </p>
        <p className="shrink-0 text-[11px] tracking-[0.3em] text-white/45">NO.01 — 卷首</p>
      </motion.div>
    </>
  );
}
