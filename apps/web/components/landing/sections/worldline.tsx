"use client";

/**
 * WorldlineSection — the dark single-world immersion block ("夜空中的单行道").
 *
 * A self-drawn 2D canvas renders one gold hairline timeline crossing the
 * viewport. A bright pulse travels it on a slow loop; passing the midpoint
 * variable-injection node it briefly blooms 4 translucent bezier possibility
 * paths, which then all converge back onto the single main line — the product
 * truth is one world (diverge → converge), never parallel branches.
 *
 * Plain canvas on purpose (no dependencies), mirroring HanziField: DPR ≤ 2,
 * paused offscreen via IntersectionObserver, one static frame under
 * `prefers-reduced-motion`, full cleanup on unmount.
 */

import { useEffect, useRef } from "react";

import { landingContent } from "@/components/landing/content";
import { Eyebrow, Reveal, SplitReveal } from "@/components/landing/primitives";

const { worldline } = landingContent;

const GOLD_RGB = "181, 133, 74"; // --color-gold
const INK_TEXT_RGB = "247, 236, 210"; // --color-ink-text (hot pulse core)
const TAU = Math.PI * 2;

/** One full pulse journey along the line, in ms. Slow and stately. */
const LOOP_MS = 12000;
/** Timeline vertical position as a fraction of section height. Keep in sync
 *  with the variable card's `top-[68%]` below. */
const LINE_Y_FRAC = 0.68;
/** Injection node horizontal position (fraction of canvas width). */
const INJECTION_X_FRAC = 0.5;
/** Line insets so the hairline never touches the viewport edge. */
const LINE_PAD_X_FRAC = 0.06;
/** Possibility-path vertical offsets, as multiples of max spread. */
const BRANCH_OFFSETS = [-1, -0.42, 0.42, 1] as const;

function smoothstep(edge0: number, edge1: number, x: number): number {
  const t = Math.min(1, Math.max(0, (x - edge0) / (edge1 - edge0)));
  return t * t * (3 - 2 * t);
}

/** Ambient timeline canvas. Renders `<canvas aria-hidden>`; position it with
 *  `absolute inset-0 h-full w-full` from the caller. */
function WorldlineCanvas({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let raf = 0;
    let width = 0;
    let height = 0;
    let visible = true;

    const draw = (time: number) => {
      ctx.clearRect(0, 0, width, height);

      const y = height * LINE_Y_FRAC;
      const x0 = width * LINE_PAD_X_FRAC;
      const x1 = width * (1 - LINE_PAD_X_FRAC);
      const cx = width * INJECTION_X_FRAC;
      const fan = Math.min(width * 0.24, 300); // divergence region length
      const spread = Math.min(height * 0.085, 72); // max branch amplitude

      // Under reduced motion the pulse rests at the injection node: the static
      // frame is exactly "main line + injection point".
      const restProgress = (cx - x0) / (x1 - x0);
      const progress = reduce ? restProgress : (time % LOOP_MS) / LOOP_MS;
      const px = x0 + (x1 - x0) * progress;

      // Bloom envelope: paths fade in as the pulse enters the injection
      // region and fade out as it leaves the convergence point.
      const bloom = reduce
        ? 0
        : smoothstep(cx - 24, cx + fan * 0.3, px) *
          (1 - smoothstep(cx + fan * 0.6, cx + fan + 48, px));

      // ── Main line: one gold hairline, fading out at both extremes. ──
      const lineGradient = ctx.createLinearGradient(x0, 0, x1, 0);
      lineGradient.addColorStop(0, `rgba(${GOLD_RGB}, 0)`);
      lineGradient.addColorStop(0.08, `rgba(${GOLD_RGB}, 0.4)`);
      lineGradient.addColorStop(0.92, `rgba(${GOLD_RGB}, 0.4)`);
      lineGradient.addColorStop(1, `rgba(${GOLD_RGB}, 0)`);
      ctx.strokeStyle = lineGradient;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x0, y);
      ctx.lineTo(x1, y);
      ctx.stroke();

      // ── Possibility paths: diverge at the node, converge back to the
      //    single line — never parallel branches. ──
      if (bloom > 0.01) {
        ctx.lineWidth = 1;
        ctx.strokeStyle = `rgba(${GOLD_RGB}, ${0.26 * bloom})`;
        for (const factor of BRANCH_OFFSETS) {
          const lift = factor * spread * (0.35 + 0.65 * bloom);
          ctx.beginPath();
          ctx.moveTo(cx, y);
          ctx.bezierCurveTo(
            cx + fan * 0.28,
            y + lift,
            cx + fan * 0.72,
            y + lift,
            cx + fan,
            y,
          );
          ctx.stroke();
        }
        // Convergence point marker.
        ctx.fillStyle = `rgba(${GOLD_RGB}, ${0.5 * bloom})`;
        ctx.beginPath();
        ctx.arc(cx + fan, y, 1.5, 0, TAU);
        ctx.fill();
      }

      // ── Injection node: ring + core, brightening as the pulse passes. ──
      const nodeGlow = 0.55 + 0.45 * bloom;
      ctx.strokeStyle = `rgba(${GOLD_RGB}, ${0.6 * nodeGlow})`;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(cx, y, 6 + 2 * bloom, 0, TAU);
      ctx.stroke();
      ctx.fillStyle = `rgba(${GOLD_RGB}, ${0.9 * nodeGlow})`;
      ctx.beginPath();
      ctx.arc(cx, y, 2.2, 0, TAU);
      ctx.fill();

      // ── Pulse: hot core, breathing halo, short comet tail. ──
      const phase = reduce ? 0 : Math.sin(time / 420);
      const haloRadius = 7 + 1.5 * phase;
      ctx.fillStyle = `rgba(${GOLD_RGB}, 0.1)`;
      ctx.beginPath();
      ctx.arc(px, y, haloRadius * 1.9, 0, TAU);
      ctx.fill();
      ctx.fillStyle = `rgba(${GOLD_RGB}, 0.22)`;
      ctx.beginPath();
      ctx.arc(px, y, haloRadius, 0, TAU);
      ctx.fill();
      ctx.fillStyle = `rgba(${INK_TEXT_RGB}, 0.95)`;
      ctx.beginPath();
      ctx.arc(px, y, 2.4, 0, TAU);
      ctx.fill();
      if (!reduce) {
        const tail = ctx.createLinearGradient(px - 34, 0, px, 0);
        tail.addColorStop(0, `rgba(${GOLD_RGB}, 0)`);
        tail.addColorStop(1, `rgba(${GOLD_RGB}, 0.5)`);
        ctx.strokeStyle = tail;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(px - 34, y);
        ctx.lineTo(px, y);
        ctx.stroke();
      }
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      // Reduced motion renders exactly one static frame per layout change.
      if (reduce) draw(0);
    };

    const loop = (time: number) => {
      if (visible) draw(time);
      raf = requestAnimationFrame(loop);
    };

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(canvas);
    const intersectionObserver = new IntersectionObserver((entries) => {
      visible = entries[0]?.isIntersecting ?? true;
    });
    intersectionObserver.observe(canvas);

    resize();
    if (!reduce) {
      raf = requestAnimationFrame(loop);
    }

    return () => {
      cancelAnimationFrame(raf);
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
    };
  }, []);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
}

export function WorldlineSection() {
  return (
    <section
      id="worldline"
      className="relative flex min-h-[110svh] items-center overflow-hidden bg-ink-surface"
    >
      <WorldlineCanvas className="absolute inset-0 h-full w-full" />
      <div className="landing-grain" aria-hidden />

      {/* Copy layer, stacked above the canvas. */}
      <div className="relative z-10 mx-auto w-full max-w-6xl -translate-y-[9svh] px-6 md:px-10">
        <Reveal className="mb-8">
          <Eyebrow tone="dark">{worldline.eyebrow}</Eyebrow>
        </Reveal>
        <h2 className="font-serif text-[clamp(2.6rem,8vw,6rem)] text-ink-text">
          <SplitReveal text={worldline.display} delay={0.1} />
        </h2>
        <Reveal delay={0.5} className="mt-8 max-w-[48ch]">
          <p className="text-base leading-relaxed text-ink-text-muted md:text-md">
            {worldline.sub}
          </p>
        </Reveal>
      </div>

      {/* Variable-injection label card, floating over the canvas node. The
          68% top matches LINE_Y_FRAC in the canvas above. */}
      <Reveal
        delay={1}
        y={12}
        className="pointer-events-none absolute left-1/2 top-[68%] z-10 -translate-x-1/2 -translate-y-full"
      >
        <div className="flex flex-col items-center">
          <div className="whitespace-nowrap rounded-control border border-ink-line bg-ink-surface-raised px-3.5 py-2 font-mono text-micro uppercase tracking-label text-ink-text-muted">
            {worldline.variableExample}
          </div>
          <span aria-hidden className="h-8 w-px bg-ink-line" />
        </div>
      </Reveal>
    </section>
  );
}
