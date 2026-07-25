"use client";

import { memo } from "react";
import { BaseEdge, getBezierPath, type EdgeProps, type Edge } from "@xyflow/react";

import { edgeVisual } from "./graph-visual";

/**
 * A relation thread between two constellation cards, light edition.
 *
 * Threads are soft ink lines on paper; focused relations warm to vermilion and
 * carry a slow stream of gold motes, so the "who-loves-whom" of the story
 * literally flows. Everything outside the current focus fades to a faint
 * pencil line instead of vanishing.
 */

export type FlowEdgeData = {
  edgeType: string;
  weight: number;
  focused: boolean;
  dimmed: boolean;
};

export type FlowEdgeType = Edge<FlowEdgeData, "flow">;

function FlowEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
}: EdgeProps<FlowEdgeType>) {
  const weight = Math.max(0.15, Math.min(1, data?.weight ?? 0.4));
  const visual = edgeVisual(data?.edgeType ?? "relationship");
  const focused = Boolean(selected || data?.focused);
  const dimmed = Boolean(data?.dimmed);

  const [path] = getBezierPath({ sourceX, sourceY, sourcePosition, targetX, targetY, targetPosition });

  // Ink on paper: neutral threads are warm-grey; focus warms to vermilion,
  // cool relations (events, rules) lean to a slate blue.
  const stroke = focused
    ? "143,33,27"
    : visual.tint === "warm"
      ? "160,90,44"
      : visual.tint === "cool"
        ? "90,110,140"
        : "120,112,96";

  const baseOpacity = dimmed ? 0.08 : focused ? 0.8 : 0.3;
  const strokeWidth = (0.7 + weight * 1.6) * (focused ? 1.4 : 1);

  const duration = 5 - weight * 2.2;
  const motes = focused ? 3 : weight > 0.6 ? 2 : 0;

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{
          stroke: `rgba(${stroke},${0.55 + weight * 0.35})`,
          strokeWidth,
          opacity: baseOpacity,
          transition: "opacity 300ms ease, stroke-width 300ms ease, stroke 300ms ease",
        }}
      />
      {!dimmed &&
        Array.from({ length: motes }).map((_, i) => (
          <circle key={i} r={focused ? 2.6 : 2} fill={focused ? "#b5854a" : `rgba(${stroke},0.85)`} opacity={baseOpacity + 0.2}>
            <animateMotion dur={`${duration}s`} begin={`${(duration / motes) * i}s`} repeatCount="indefinite" path={path} />
          </circle>
        ))}
    </>
  );
}

export const FlowEdge = memo(FlowEdgeComponent);
