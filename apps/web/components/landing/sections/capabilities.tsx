"use client";

/**
 * Capabilities ("能力") — paper-surface bento grid.
 *
 * Six hairline panels on an asymmetric 12-column rhythm (7/5 · 5/7 · 4/8)
 * rather than an even grid. Each panel carries a thin-stroke lucide glyph, a
 * mono index, a serif title and a muted description; the lead panel adds a
 * restrained static SVG sketch of the story graph (hairlines + nodes, labels
 * sourced from the manifesto marquee terms). Entrance stagger comes from
 * Reveal; hover lift is SPRING_SOFT and collapses under reduced motion.
 */

import {
  BookUser,
  Boxes,
  Cable,
  Network,
  Orbit,
  SpellCheck,
  type LucideIcon,
} from "lucide-react";
import { motion, useReducedMotion } from "motion/react";

import { landingContent } from "@/components/landing/content";
import {
  Eyebrow,
  Reveal,
  SplitReveal,
  SPRING_SOFT,
} from "@/components/landing/primitives";
import { cn } from "@/lib/utils";

const { capabilities, manifesto } = landingContent;

type CapabilityIconName = (typeof capabilities.items)[number]["icon"];

const CAPABILITY_ICONS: Record<CapabilityIconName, LucideIcon> = {
  Network,
  BookUser,
  Boxes,
  Orbit,
  SpellCheck,
  Cable,
};

/** Row rhythm across the 12-column lg grid: 7/5, then 5/7, then 4/8. */
const SPANS = [
  "lg:col-span-7",
  "lg:col-span-5",
  "lg:col-span-5",
  "lg:col-span-7",
  "lg:col-span-4",
  "lg:col-span-8",
] as const;

/**
 * Static sketch of the story graph for the lead panel: one accent hub, a few
 * ink nodes and hairline edges. Pure presentational SVG — no animation, so
 * reduced motion needs no special-casing here.
 */
function GraphSketch() {
  const hub = { x: 84, y: 104 };
  const nodes = [
    { x: 212, y: 38, label: manifesto.marquee[4] }, // 伏笔
    { x: 300, y: 104, label: manifesto.marquee[5] }, // 世界规则
    { x: 224, y: 168, label: manifesto.marquee[3] }, // 事件
    { x: 44, y: 26, label: manifesto.marquee[0] }, // 角色
  ];

  return (
    <svg
      aria-hidden
      viewBox="0 0 360 200"
      className="h-auto w-full max-w-md"
      fill="none"
    >
      {nodes.map((node) => (
        <line
          key={`edge-${node.x}-${node.y}`}
          x1={hub.x}
          y1={hub.y}
          x2={node.x}
          y2={node.y}
          stroke="var(--color-line)"
          strokeWidth="1"
        />
      ))}
      <line
        x1={nodes[0].x}
        y1={nodes[0].y}
        x2={nodes[1].x}
        y2={nodes[1].y}
        stroke="var(--color-line-soft)"
        strokeWidth="1"
      />
      {nodes.map((node) => (
        <g key={`node-${node.x}-${node.y}`}>
          <circle cx={node.x} cy={node.y} r="3" fill="var(--color-ink-soft)" />
          <text
            x={node.x + 10}
            y={node.y + 4}
            fontSize="11"
            fill="var(--color-muted)"
            className="font-serif"
          >
            {node.label}
          </text>
        </g>
      ))}
      <circle cx={hub.x} cy={hub.y} r="4.5" fill="var(--color-accent)" />
      <circle
        cx={hub.x}
        cy={hub.y}
        r="9"
        stroke="var(--color-accent)"
        strokeWidth="1"
        opacity="0.35"
      />
    </svg>
  );
}

export function CapabilitiesSection() {
  const reduce = useReducedMotion();

  return (
    <section
      id="capabilities"
      className="relative overflow-hidden bg-paper text-ink"
    >
      <div aria-hidden className="landing-grain" />

      <div className="relative mx-auto max-w-[1200px] px-5 py-24 md:px-8 lg:py-32">
        <Eyebrow>{capabilities.eyebrow}</Eyebrow>
        <h2 className="mt-7 max-w-4xl font-serif leading-none">
          <SplitReveal
            text={capabilities.display}
            className="text-[clamp(2.5rem,7vw,4.5rem)]"
          />
        </h2>

        <div className="mt-14 grid grid-cols-1 gap-4 lg:mt-20 lg:grid-cols-12 lg:gap-5">
          {capabilities.items.map((item, index) => {
            const Icon = CAPABILITY_ICONS[item.icon];
            return (
              <Reveal
                key={item.title}
                delay={0.05 + index * 0.07}
                className={cn("h-full", SPANS[index % SPANS.length])}
              >
                <motion.article
                  whileHover={reduce ? undefined : { y: -4 }}
                  transition={SPRING_SOFT}
                  className="group flex h-full flex-col rounded-panel border border-line bg-panel p-6 transition-colors duration-300 hover:border-ink/35 md:p-7"
                >
                  <div className="flex items-start justify-between">
                    <Icon
                      aria-hidden
                      strokeWidth={1.5}
                      className="size-7 text-ink-soft transition-colors duration-300 group-hover:text-accent"
                    />
                    <span className="font-mono text-micro tracking-label text-muted-soft">
                      {String(index + 1).padStart(2, "0")}
                    </span>
                  </div>

                  <h3 className="mt-7 font-serif text-lg">{item.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted">
                    {item.description}
                  </p>

                  {index === 0 ? (
                    <div className="mt-auto pt-9">
                      <GraphSketch />
                    </div>
                  ) : null}
                </motion.article>
              </Reveal>
            );
          })}
        </div>
      </div>
    </section>
  );
}
