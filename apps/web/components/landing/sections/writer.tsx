"use client";

/**
 * Writer 写作台 — the agent-thread console loops the tool-activity demo from
 * `landingContent.writer.thread` (spinner → check → typed candidate prose,
 * then fade and replay) beside an annotated manuscript card. The three writer
 * bullets close the section on hairlines. Reduced motion renders the console
 * in its final state with no loop and freezes the caret.
 */

import {
  CheckCircle2,
  Circle,
  Loader2,
  MousePointerClick,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

import { landingContent } from "@/components/landing/content";
import {
  EASE_OUT,
  Eyebrow,
  Reveal,
  SplitReveal,
} from "@/components/landing/primitives";
import { cn } from "@/lib/utils";

const THREAD = landingContent.writer.thread;

/** Candidate prose typed once the tool calls resolve (demo-only copy). */
const CANDIDATE = "沈知微攥紧船票，江风把旧誓言送回耳边。";
const CANDIDATE_CHARS = Array.from(CANDIDATE);

const SPIN_MS = 700;
const STEP_GAP_MS = 240;
const TYPE_MS = 60;
const HOLD_MS = 2400;
const FADE_MS = 500;

const BULLET_ICONS = [MousePointerClick, ShieldCheck, RefreshCw] as const;

/* ── Agent thread console ───────────────────────────────────────────────── */

function AgentThreadConsole() {
  const reduce = useReducedMotion();
  const [doneCount, setDoneCount] = useState(0);
  const [runningIndex, setRunningIndex] = useState(-1);
  const [typedChars, setTypedChars] = useState(0);
  const [fading, setFading] = useState(false);
  const [cycle, setCycle] = useState(0);

  useEffect(() => {
    if (reduce) return;

    const timers: ReturnType<typeof setTimeout>[] = [];
    const later = (fn: () => void, ms: number) => {
      timers.push(setTimeout(fn, ms));
    };

    let t = 500;
    THREAD.forEach((_, index) => {
      later(() => setRunningIndex(index), t);
      later(() => {
        setDoneCount(index + 1);
        setRunningIndex((current) => (current === index ? -1 : current));
      }, t + SPIN_MS);
      t += SPIN_MS + STEP_GAP_MS;
    });

    const typeStart = t + 300;
    CANDIDATE_CHARS.forEach((_, k) => {
      later(() => setTypedChars(k + 1), typeStart + k * TYPE_MS);
    });

    const holdEnd = typeStart + CANDIDATE_CHARS.length * TYPE_MS + HOLD_MS;
    later(() => setFading(true), holdEnd);
    later(() => {
      setDoneCount(0);
      setRunningIndex(-1);
      setTypedChars(0);
      setFading(false);
      setCycle((current) => current + 1);
    }, holdEnd + FADE_MS + 100);

    return () => {
      timers.forEach((timer) => clearTimeout(timer));
    };
  }, [reduce, cycle]);

  // Reduced motion pins every stage to its resolved state, no loop.
  const effDone = reduce ? THREAD.length : doneCount;
  const effRunning = reduce ? -1 : runningIndex;
  const effTyped = reduce ? CANDIDATE_CHARS.length : typedChars;
  const typingPhase = effDone === THREAD.length;

  return (
    <div className="rounded-panel border border-ink-line bg-ink-surface p-6 shadow-ink">
      <div className="flex items-center justify-between border-b border-ink-line pb-4">
        <span className="font-mono text-micro uppercase tracking-label text-ink-text-muted">
          Agent Thread
        </span>
        <span className="flex items-center gap-2 font-mono text-micro uppercase tracking-label text-ink-text-muted">
          <span
            aria-hidden
            className={cn(
              "size-1.5 rounded-full bg-gold",
              !reduce && "animate-pulse",
            )}
          />
          Live Demo
        </span>
      </div>

      <p className="sr-only">
        Writer Agent 演示：依次检索伏笔库、读取角色档案并生成候选正文，随后逐字打出一段正文。
      </p>

      <div
        aria-hidden
        className={cn(
          "transition-opacity duration-500",
          fading && "opacity-0",
        )}
      >
        <ol className="mt-5 space-y-3">
          {THREAD.map((entry, index) => {
            const isDone = index < effDone;
            const isRunning = index === effRunning;
            return (
              <li
                key={entry.action}
                className={cn(
                  "flex h-7 items-center gap-3 font-mono text-sm transition-opacity duration-300",
                  isDone || isRunning ? "opacity-100" : "opacity-35",
                )}
              >
                <span className="w-4 shrink-0 text-micro text-ink-text-muted">
                  0{index + 1}
                </span>
                {isDone ? (
                  <CheckCircle2
                    aria-hidden
                    className="size-4 shrink-0 text-gold"
                  />
                ) : isRunning ? (
                  <Loader2
                    aria-hidden
                    className="size-4 shrink-0 animate-spin text-gold"
                  />
                ) : (
                  <Circle
                    aria-hidden
                    className="size-3 shrink-0 text-ink-text-muted opacity-50"
                  />
                )}
                <span className="text-ink-text">{entry.action}</span>
                {isDone ? (
                  <motion.span
                    initial={reduce ? false : { opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ duration: 0.3, ease: EASE_OUT }}
                    className="truncate text-ink-text-muted"
                  >
                    · {entry.detail}
                  </motion.span>
                ) : null}
              </li>
            );
          })}
        </ol>

        <div className="mt-5 border-t border-ink-line pt-4">
          <span className="font-mono text-micro uppercase tracking-label text-ink-text-muted">
            候选正文 · {THREAD[THREAD.length - 1]?.detail}
          </span>
          <p className="mt-2 min-h-7 font-serif text-sm text-ink-text">
            {CANDIDATE_CHARS.slice(0, effTyped).join("")}
            {typingPhase ? (
              <span
                aria-hidden
                className={cn(
                  "ml-0.5 inline-block h-4 w-px translate-y-0.5 bg-gold",
                  !reduce && "animate-[caret-blink_1s_steps(1)_infinite]",
                )}
              />
            ) : null}
          </p>
        </div>
      </div>
    </div>
  );
}

/* ── Manuscript card ────────────────────────────────────────────────────── */

function ManuscriptCard() {
  return (
    <figure className="flex h-full flex-col rounded-panel border border-line bg-panel p-7 shadow-panel lg:p-8">
      <div className="flex items-baseline justify-between border-b border-line-soft pb-4">
        <span className="font-mono text-micro uppercase tracking-label text-muted">
          Manuscript
        </span>
        <span className="font-mono text-micro text-muted-soft">第 214 章</span>
      </div>

      <blockquote className="mb-8 mt-6 font-serif text-reading text-ink">
        江面起了雾，渡船未至第三个渡口便
        <del className="text-accent/70 decoration-accent/60 decoration-1">
          停了又走
        </del>
        <span className="relative mx-0.5 text-accent underline decoration-accent/60 underline-offset-4">
          泊了片刻
          <span
            aria-hidden
            className="absolute -top-2 left-1/2 -translate-x-1/2 font-mono text-micro"
          >
            ˄
          </span>
        </span>
        。沈知微立在船尾，攥着那张被水浸软的船票。她忽然想起临行那晚，母亲把灯芯挑得很低：走可以，别忘了回来。
      </blockquote>

      <figcaption className="mt-auto flex items-baseline justify-between border-t border-line-soft pt-4 font-mono text-micro text-muted">
        <span>批注 2 处</span>
        <span>v214</span>
      </figcaption>
    </figure>
  );
}

/* ── Section ────────────────────────────────────────────────────────────── */

export function WriterSection() {
  return (
    <section id="writer" className="relative overflow-hidden bg-paper-deep">
      <div aria-hidden className="landing-grain" />

      <div className="relative mx-auto max-w-6xl px-6 py-24 md:px-10 lg:py-32">
        <header className="max-w-3xl">
          <Eyebrow>{landingContent.writer.eyebrow}</Eyebrow>
          <h2 className="mt-6 font-serif text-xl text-ink md:text-display">
            <SplitReveal text={landingContent.writer.display} />
          </h2>
        </header>

        <div className="mt-14 grid grid-cols-1 gap-8 lg:mt-16 lg:grid-cols-12 lg:gap-10">
          <Reveal className="lg:col-span-7">
            <AgentThreadConsole />
          </Reveal>
          <Reveal className="lg:col-span-5" delay={0.12}>
            <ManuscriptCard />
          </Reveal>
        </div>

        <Reveal delay={0.2}>
          <div className="mt-14 flex flex-col divide-y divide-line border-y border-line md:flex-row md:divide-x md:divide-y-0 lg:mt-16">
            {landingContent.writer.bullets.map((bullet, index) => {
              const Icon = BULLET_ICONS[index] ?? MousePointerClick;
              return (
                <div
                  key={bullet}
                  className="flex min-h-14 flex-1 items-center gap-3 py-4 md:justify-center"
                >
                  <Icon aria-hidden className="size-4 shrink-0 text-accent" />
                  <span className="text-sm text-ink-soft">{bullet}</span>
                </div>
              );
            })}
          </div>
        </Reveal>
      </div>
    </section>
  );
}
