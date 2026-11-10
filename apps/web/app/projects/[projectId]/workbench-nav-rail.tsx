"use client";

import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";

import { WORKBENCH_SECTIONS } from "./workbench-nav";

const STORAGE_KEY = "mirofish.nav-rail.collapsed";

/**
 * The project workspace's fixed primary nav rail.
 *
 * Renders the seven mandated workbench entries in order and highlights the one
 * matching the current path. The rail collapses to a slim icon strip (labels
 * hidden, icons carry tooltips) so the workbench content gets the width back;
 * the choice persists in localStorage. Pure navigation chrome — no data fetching.
 */
export function WorkbenchNav({ projectId, collapsible = true }: { projectId: string; collapsible?: boolean }) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;
  // Start expanded to match the server render, then reconcile with the saved
  // preference after mount so hydration never mismatches.
  const [collapsed, setCollapsed] = useState(false);
  const navRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!collapsible) return;
    try {
      setCollapsed(window.localStorage.getItem(STORAGE_KEY) === "1");
    } catch {
      // storage unavailable — stay expanded
    }
  }, [collapsible]);

  // Keep the wrapping <aside>'s width in sync with the collapsed state. The
  // aside lives in the server layout (so the rail stays the only client
  // island); we reach it through the nav's closest ancestor and flip a data
  // attribute the layout's CSS hooks on, with a smooth width transition.
  useEffect(() => {
    const aside = navRef.current?.closest("aside");
    if (!aside) return;
    aside.setAttribute("data-collapsed", collapsed ? "true" : "false");
  }, [collapsed]);

  function toggle() {
    setCollapsed((prev) => {
      const next = !prev;
      try {
        window.localStorage.setItem(STORAGE_KEY, next ? "1" : "0");
      } catch {
        // storage unavailable — the visual toggle still works for this session
      }
      return next;
    });
  }

  return (
    <nav
      ref={navRef}
      aria-label="工作台导航"
      className={cn("flex flex-col gap-1", collapsible && "h-full", collapsed ? "px-2" : "px-3")}
    >
      <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
        {WORKBENCH_SECTIONS.map((section) => {
          const href = `${base}/${section.slug}`;
          // A section is active on its exact path or any nested path beneath it.
          const active = pathname === href || pathname.startsWith(`${href}/`);
          const Icon = section.icon;
          return (
            <Link
              key={section.slug}
              href={href}
              aria-current={active ? "page" : undefined}
              title={collapsed ? section.label : undefined}
              aria-label={collapsed ? section.label : undefined}
              className={cn(
                "group relative flex min-h-11 items-center rounded-panel py-2.5 text-sm transition-colors duration-200",
                collapsed ? "justify-center px-0" : "gap-3 px-3.5",
                active
                  ? "bg-accent-wash font-medium text-accent-strong"
                  : "text-ink-soft hover:bg-paper-deep hover:text-ink",
              )}
            >
              {/* active indicator bar */}
              <span
                aria-hidden
                className={cn(
                  "absolute left-0 top-1/2 h-[18px] w-[3px] -translate-y-1/2 rounded-full bg-accent transition-opacity duration-200",
                  active ? "opacity-100" : "opacity-0",
                )}
              />
              <Icon
                className={cn(
                  "size-[17px] shrink-0 transition-colors",
                  active ? "text-accent" : "text-muted group-hover:text-ink",
                )}
                aria-hidden
              />
              {!collapsed && <span className="truncate">{section.label}</span>}
            </Link>
          );
        })}
      </div>

      {/* Collapse toggle — pinned to the rail's foot. */}
      {collapsible ? <button
        type="button"
        onClick={toggle}
        aria-expanded={!collapsed}
        aria-label={collapsed ? "展开导航" : "收起导航"}
        title={collapsed ? "展开导航" : "收起导航"}
        className={cn(
          "mt-2 flex shrink-0 items-center rounded-panel border-t border-line-soft py-2.5 pt-3 text-muted transition-colors hover:bg-paper-deep hover:text-ink",
          collapsed ? "justify-center px-0" : "gap-3 px-3.5",
        )}
      >
        {collapsed ? (
          <PanelLeftOpen className="size-[17px] shrink-0" aria-hidden />
        ) : (
          <>
            <PanelLeftClose className="size-[17px] shrink-0" aria-hidden />
            <span className="text-sm">收起</span>
          </>
        )}
      </button> : null}
    </nav>
  );
}
