"use client";

/**
 * HanziField — a 2D canvas field of drifting hanzi glyphs for the landing
 * page's dark surfaces (ink hero, worldline immersion).
 *
 * Plain canvas 2D on purpose: the effect is ambient texture, not a WebGL
 * showcase, and skipping a renderer keeps the landing bundle lean. Motion is
 * paused offscreen (IntersectionObserver) and reduced to a single static
 * frame under `prefers-reduced-motion`.
 */

import { useEffect, useRef } from "react";

import { landingContent } from "./content";

export interface HanziFieldProps {
  className?: string;
  /** Particle count scale; 1 ≈ one glyph per 18,000px² of canvas area. */
  density?: number;
  /** Glyph pool. Defaults to the hero's 梦海墨舟夜航灯书忆 set. */
  characters?: string;
  /** Base color for glyphs and hairline links (any CSS color). */
  tint?: string;
  /** Pointer repulsion; ignored under reduced motion. */
  interactive?: boolean;
}

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  glyph: string;
  size: number;
  alpha: number;
  /** Twinkle phase offset so glyphs never pulse in lockstep. */
  phase: number;
}

/** Max center distance at which two particles get a hairline link. */
const LINK_DISTANCE = 120;
/** Pointer influence radius for the repulsion force. */
const POINTER_RADIUS = 140;
/** Canvas can't resolve the var() chain in --font-serif, so its fallback
 *  stack is duplicated here. */
const GLYPH_FONT_STACK = '"Songti SC", "SimSun", Georgia, serif';

export function HanziField({
  className,
  density = 1,
  characters,
  tint = "#f1e6cf",
  interactive = true,
}: HanziFieldProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const glyphPool = characters ?? landingContent.hero.canvasCharacters;

  useEffect(() => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const glyphs = Array.from(glyphPool);
    const pointer = { x: 0, y: 0, inside: false };

    let particles: Particle[] = [];
    let raf = 0;
    let width = 0;
    let height = 0;
    let visible = true;

    const spawn = () => {
      const count = Math.max(12, Math.round(((width * height) / 18000) * density));
      particles = Array.from({ length: count }, (_, index) => ({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.24,
        vy: (Math.random() - 0.5) * 0.24,
        glyph: glyphs[index % glyphs.length] ?? "墨",
        size: 13 + Math.random() * 17,
        alpha: 0.14 + Math.random() * 0.3,
        phase: Math.random() * Math.PI * 2,
      }));
    };

    const draw = (time: number) => {
      ctx.clearRect(0, 0, width, height);

      ctx.strokeStyle = tint;
      ctx.lineWidth = 0.5;
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const a = particles[i];
          const b = particles[j];
          const dx = a.x - b.x;
          const dy = a.y - b.y;
          const distSq = dx * dx + dy * dy;
          if (distSq > LINK_DISTANCE * LINK_DISTANCE) continue;
          ctx.globalAlpha = (1 - Math.sqrt(distSq) / LINK_DISTANCE) * 0.12;
          ctx.beginPath();
          ctx.moveTo(a.x, a.y);
          ctx.lineTo(b.x, b.y);
          ctx.stroke();
        }
      }

      ctx.fillStyle = tint;
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      for (const p of particles) {
        const twinkle = reduce ? 1 : 0.75 + 0.25 * Math.sin(time / 1400 + p.phase);
        ctx.globalAlpha = p.alpha * twinkle;
        ctx.font = `${p.size}px ${GLYPH_FONT_STACK}`;
        ctx.fillText(p.glyph, p.x, p.y);
      }
      ctx.globalAlpha = 1;
    };

    const step = (time: number) => {
      for (const p of particles) {
        if (interactive && pointer.inside) {
          const dx = p.x - pointer.x;
          const dy = p.y - pointer.y;
          const dist = Math.hypot(dx, dy);
          if (dist < POINTER_RADIUS && dist > 0.01) {
            const force = ((POINTER_RADIUS - dist) / POINTER_RADIUS) * 0.35;
            p.vx += (dx / dist) * force;
            p.vy += (dy / dist) * force;
          }
        }
        // Damping + clamp lets repulsion energy settle back into a slow drift.
        p.vx = Math.max(-0.9, Math.min(0.9, p.vx * 0.985));
        p.vy = Math.max(-0.9, Math.min(0.9, p.vy * 0.985));
        p.x += p.vx;
        p.y += p.vy;
        const margin = 40;
        if (p.x < -margin) p.x = width + margin;
        else if (p.x > width + margin) p.x = -margin;
        if (p.y < -margin) p.y = height + margin;
        else if (p.y > height + margin) p.y = -margin;
      }
      draw(time);
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      width = canvas.clientWidth;
      height = canvas.clientHeight;
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      spawn();
      // Reduced motion renders exactly one static frame per layout change.
      if (reduce) draw(0);
    };

    const loop = (time: number) => {
      if (visible) step(time);
      raf = requestAnimationFrame(loop);
    };

    // The canvas usually sits under content, so the pointer is tracked on
    // window and mapped into canvas space instead of relying on hit-testing.
    const onPointerMove = (event: PointerEvent) => {
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const y = event.clientY - rect.top;
      pointer.x = x;
      pointer.y = y;
      pointer.inside = x >= 0 && y >= 0 && x <= rect.width && y <= rect.height;
    };

    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(canvas);
    const intersectionObserver = new IntersectionObserver((entries) => {
      visible = entries[0]?.isIntersecting ?? true;
    });
    intersectionObserver.observe(canvas);
    if (interactive && !reduce) {
      window.addEventListener("pointermove", onPointerMove, { passive: true });
    }

    resize();
    if (!reduce) {
      raf = requestAnimationFrame(loop);
    }

    return () => {
      cancelAnimationFrame(raf);
      resizeObserver.disconnect();
      intersectionObserver.disconnect();
      if (interactive && !reduce) {
        window.removeEventListener("pointermove", onPointerMove);
      }
    };
  }, [glyphPool, density, tint, interactive]);

  return <canvas ref={canvasRef} className={className} aria-hidden="true" />;
}
