"use client";

import { createPortal } from "react-dom";
import { useEffect, useState, type ReactNode } from "react";

/**
 * A single shared top bar for the whole project workspace.
 *
 * Every workbench used to stack its own header row under the project bar,
 * which read as a grid of small boxes. Instead the project header (in the
 * server layout) exposes one content slot — a plain <div id="project-topbar-slot">
 * sitting in the bar — and the active workbench portals its contextual controls
 * (the writer's chapter switcher / word count / save state) into that same row.
 * Non-writer sections leave the slot empty, so the bar stays a single calm
 * header everywhere.
 *
 * The writer is a client island inside a server layout, so the bridge is a DOM
 * portal into that fixed id rather than React context (which can't cross the
 * server/client boundary from the layout down).
 */
export function ProjectTopbarSlot({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<HTMLElement | null>(null);

  useEffect(() => {
    setTarget(document.getElementById("project-topbar-slot"));
  }, []);

  if (!target) return null;
  return createPortal(children, target);
}
