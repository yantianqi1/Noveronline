"use client";

import { memo } from "react";
import { Handle, Position, type NodeProps, type Node } from "@xyflow/react";

import { layerVisual } from "./graph-visual";

/**
 * The constellation node, light "paper & ink" edition.
 *
 * Two shapes keep the sky readable:
 *  - Characters (and other named entities) render as round vermilion seals —
 *    a glowing icon orb with the name underneath, like a stamp on manuscript.
 *  - Concepts render as quiet rectangular paper slips, so the dozens of
 *    background notions recede instead of competing with the cast.
 *
 * Each node carries a `layerKey` (node_type for entities, "concept:<subtype>"
 * for concepts) so slips pick up their subtype's palette — 分析·事件 violet,
 * 世界观·设定 slate — instead of one flat grey. Concept slips show the cleaned
 * Chinese-first `displayTitle`; machine-placeholder titles get a dashed 待命名
 * treatment so they read as unresolved, not as content.
 *
 * Only the focused node and its neighbours lift (vermilion ring + halo);
 * everything else merely softens, it never gets buried in darkness.
 */

export type ConstellationNodeData = {
  title: string;
  /** Filter layer key — node_type for entities, "concept:<subtype>" for concepts. */
  layerKey: string;
  importance: number;
  dimmed: boolean;
  focused: boolean;
  /** True when the title is a machine placeholder we replaced (待命名). */
  isUntitled: boolean;
};

export type ConstellationNodeType = Node<ConstellationNodeData, "constellation">;

const HANDLES = (
  <>
    <Handle type="target" position={Position.Top} className="!opacity-0" />
    <Handle type="source" position={Position.Bottom} className="!opacity-0" />
    <Handle type="target" position={Position.Left} id="l" className="!opacity-0" />
    <Handle type="source" position={Position.Right} id="r" className="!opacity-0" />
  </>
);

function ConstellationNodeComponent({ data, selected }: NodeProps<ConstellationNodeType>) {
  const visual = layerVisual(data.layerKey);
  const Icon = visual.icon;
  const importance = Math.max(0, Math.min(1, data.importance || 0));
  const lit = selected || data.focused;
  const isConcept = data.layerKey.startsWith("concept:");

  if (isConcept) {
    // ── Quiet paper slip for background notions ──
    return (
      <div
        className={`relative flex max-w-[190px] items-center gap-1.5 rounded-control border px-2.5 py-1.5 transition-all duration-300 ${
 data.isUntitled ? "border-dashed" : ""
        }`}
        style={{
          borderColor: lit ? visual.color : "rgba(86,69,45,0.18)",
          background: lit ? "#fffdf8" : "rgba(255,253,248,0.72)",
          boxShadow: lit ? `0 0 0 1px ${visual.color}44, 0 4px 14px -6px rgba(23,26,27,0.25)` : "0 1px 3px rgba(23,26,27,0.08)",
          opacity: data.dimmed ? 0.38 : 1,
        }}
      >
        {HANDLES}
        <Icon className="size-3 shrink-0" style={{ color: lit ? visual.color : visual.ink }} aria-hidden />
        <span
          className={`truncate text-caption leading-snug `}
          style={{ color: lit ? "#2a2620" : visual.ink }}
        >
          {data.title}
        </span>
      </div>
    );
  }

  // ── Round seal for characters / named entities ──
  const orb = 40 + importance * 18;
  return (
    <div
      className="relative flex flex-col items-center transition-all duration-300"
      style={{ opacity: data.dimmed ? 0.4 : 1, transform: lit ? "scale(1.08)" : "scale(1)" }}
    >
      {HANDLES}
      {/* Halo */}
      <span
        aria-hidden
        className="absolute rounded-full transition-opacity duration-300"
        style={{
          width: orb * 2.1,
          height: orb * 2.1,
          top: orb * 0.5 - orb * 1.05,
          background: `radial-gradient(circle, ${visual.halo}, transparent 65%)`,
          opacity: lit ? 1 : 0,
        }}
      />
      {/* Orb */}
      <span
        className="relative grid place-items-center rounded-full transition-all duration-300"
        style={{
          width: orb,
          height: orb,
          background: `radial-gradient(circle at 32% 28%, ${visual.color}, ${visual.color}dd 70%)`,
          boxShadow: lit
            ? `0 0 0 2px #f2d8b4, 0 0 0 5px ${visual.color}55, 0 10px 26px -8px ${visual.color}88`
            : `0 0 0 1.5px rgba(255,253,248,0.9), 0 6px 18px -6px ${visual.color}66`,
          color: "#fdf3e3",
        }}
      >
        <Icon style={{ width: 16 + importance * 6, height: 16 + importance * 6 }} aria-hidden />
      </span>
      {/* Name plate */}
      <span
        className="relative mt-1.5 max-w-[150px] rounded-control px-1.5 text-center leading-tight transition-all duration-300"
        style={{
          background: lit ? "rgba(255,253,248,0.95)" : "transparent",
          boxShadow: lit ? "0 1px 4px rgba(23,26,27,0.12)" : "none",
        }}
      >
        <span className="block truncate text-caption font-semibold" style={{ color: lit ? "#201a14" : "#3c3a36" }}>
          {data.title}
        </span>
        <span className="block text-micro font-medium tracking-label" style={{ color: lit ? visual.color : "#a89f88" }}>
          {visual.label}
        </span>
      </span>
    </div>
  );
}

export const ConstellationNode = memo(ConstellationNodeComponent);
