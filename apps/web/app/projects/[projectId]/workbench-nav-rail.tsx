"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

import { WORKBENCH_SECTIONS } from "./workbench-nav";

/**
 * The project workspace's fixed primary nav rail.
 *
 * Renders the seven mandated workbench entries in order and highlights the one
 * matching the current path. Pure navigation chrome — no data fetching.
 */
export function WorkbenchNav({ projectId }: { projectId: string }) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;

  return (
    <nav aria-label="工作台导航" className="flex flex-col gap-1 px-3">
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
            className={cn(
              "group relative flex items-center gap-3 rounded-[10px] px-3.5 py-2.5 text-[13.5px] transition-colors duration-200",
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
            <span className="truncate">{section.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
