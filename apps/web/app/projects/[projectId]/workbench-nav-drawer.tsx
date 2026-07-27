"use client";

import { Menu, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { IconButton } from "@/components/ui/icon-button";

import { WorkbenchNav } from "./workbench-nav-rail";
import { sectionBySlug, WORKBENCH_SECTIONS } from "./workbench-nav";

/**
 * Workbench navigation for the phone band.
 *
 * The nav rail is inline from `stack` (861px) up and hidden below it, so on a
 * phone there was previously no way to reach another workbench at all — the
 * rail simply disappeared. This is the drawer the spec calls for, plus the
 * current section's name in the header so the user still knows where they are.
 */
export function WorkbenchNavDrawer({ projectId }: { projectId: string }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  // Close on route change — the drawer's whole job is to navigate away.
  useEffect(() => setOpen(false), [pathname]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const slug = pathname.split("/")[3] ?? "";
  const current = sectionBySlug(slug) ?? WORKBENCH_SECTIONS[0];

  return (
    <div className="flex min-w-0 items-center gap-2 stack:hidden">
      <IconButton
        label="工作台导航"
        size="sm"
        onClick={() => setOpen(true)}
        aria-expanded={open}
      >
        <Menu className="size-4" aria-hidden />
      </IconButton>
      <span className="truncate text-sm font-medium text-ink">{current.label}</span>

      {open ? (
        <>
          <div
            aria-hidden
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-40 bg-ink/45"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-label="工作台导航"
            className="fixed inset-y-0 left-0 z-50 flex w-[min(280px,85vw)] flex-col overflow-y-auto border-r border-line bg-panel py-4 shadow-panel"
          >
            <div className="mb-3 flex items-center justify-between px-4">
              <span className="text-caption font-medium tracking-label text-muted">工作台</span>
              <IconButton label="关闭导航" size="sm" onClick={() => setOpen(false)}>
                <X className="size-4" aria-hidden />
              </IconButton>
            </div>
            <WorkbenchNav projectId={projectId} />
          </div>
        </>
      ) : null}
    </div>
  );
}
