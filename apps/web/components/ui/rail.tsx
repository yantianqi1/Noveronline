"use client";

import { X } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

import { IconButton } from "./icon-button";

/**
 * Workbench side rails, with the responsive collapse the spec requires.
 *
 * Three-column workbenches previously pinned both rails with `shrink-0` while
 * the centre column carried `min-w-0` (which it needs, for truncation). Below
 * roughly 820px of usable width that arithmetic squeezed the centre toward
 * zero — the worldline timeline measured 65px at an 883px viewport, with the
 * primary button's label wrapping one character per line.
 *
 * The fix is not a minimum width on the centre but making the rails obey the
 * layout bands: an inspector rail is inline only at `wide` (≥1200px) and
 * becomes an overlay drawer below that; a filter rail is inline from `stack`
 * (≥861px). Same pattern the asset workspace already used, now shared.
 */
export function InspectorRail({
  side = "right",
  open,
  onClose,
  label,
  className,
  children,
}: {
  side?: "left" | "right";
  /** Drawer visibility below the `wide` band. Inline above it regardless. */
  open: boolean;
  onClose: () => void;
  /** Accessible name for the drawer landmark. */
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <>
      {/* Scrim, drawer mode only. Strong enough to isolate the foreground. */}
      {open ? (
        <div
          aria-hidden
          onClick={onClose}
          className="fixed inset-0 z-30 bg-ink/45 wide:hidden"
        />
      ) : null}

      <aside
        aria-label={label}
        className={cn(
          "flex h-full w-rail-inspector shrink-0 flex-col overflow-hidden border-line bg-panel",
          side === "right" ? "border-l" : "border-r",
          // Drawer below `wide`: fixed overlay, only when opened.
          "max-wide:fixed max-wide:inset-y-0 max-wide:z-40 max-wide:w-full max-wide:max-w-[420px] max-wide:shadow-panel",
          side === "right" ? "max-wide:right-0" : "max-wide:left-0",
          open ? "max-wide:flex" : "max-wide:hidden",
          className,
        )}
      >
        <div className="flex items-center justify-between gap-2 border-b border-line-soft px-4 py-2 wide:hidden">
          <span className="truncate text-sm font-medium text-ink">{label}</span>
          <IconButton label="关闭" size="sm" onClick={onClose}>
            <X className="size-4" aria-hidden />
          </IconButton>
        </div>
        {children}
      </aside>
    </>
  );
}

/**
 * Secondary filter / navigation rail. Inline on the desktop shell, hidden on
 * phones where the workbench collapses to a single column.
 */
export function FilterRail({
  side = "left",
  label,
  className,
  children,
}: {
  side?: "left" | "right";
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <aside
      aria-label={label}
      className={cn(
        "hidden h-full w-rail-filter shrink-0 flex-col overflow-y-auto border-line-soft bg-paper/40 stack:flex",
        side === "left" ? "border-r" : "border-l",
        className,
      )}
    >
      {children}
    </aside>
  );
}
