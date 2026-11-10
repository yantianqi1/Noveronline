"use client";

import { Menu, X } from "lucide-react";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { IconButton } from "@/components/ui/icon-button";
import { Modal } from "@/components/ui/modal";

import { WorkbenchNav } from "./workbench-nav-rail";
import { sectionBySlug, WORKBENCH_SECTIONS } from "./workbench-nav";

/** Mobile navigation uses the native top layer, keeping keyboard focus inside. */
export function WorkbenchNavDrawer({ projectId }: { projectId: string }) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();

  useEffect(() => setOpen(false), [pathname]);
  useEffect(() => {
    const desktop = window.matchMedia("(min-width: 861px)");
    const closeOnDesktop = () => { if (desktop.matches) setOpen(false); };
    desktop.addEventListener("change", closeOnDesktop);
    return () => desktop.removeEventListener("change", closeOnDesktop);
  }, []);

  const current = sectionBySlug(pathname.split("/")[3] ?? "") ?? WORKBENCH_SECTIONS[0];

  return (
    <div className="flex min-w-0 items-center gap-2 stack:hidden">
      <IconButton label="工作台导航" className="size-11 shrink-0" onClick={() => setOpen(true)}
        aria-expanded={open} aria-haspopup="dialog">
        <Menu className="size-4" aria-hidden />
      </IconButton>
      <span className="truncate text-sm font-medium text-ink">{current.label}</span>
      {open ? (
        <Modal label="工作台导航" onClose={() => setOpen(false)}
          className="m-0 h-dvh max-h-dvh w-[min(280px,85vw)] max-w-none rounded-none border-y-0 border-l-0 py-4">
          <div className="mb-3 flex items-center justify-between px-4">
            <h2 className="font-serif text-lg font-semibold text-ink">工作台</h2>
            <IconButton label="关闭导航" className="size-11" onClick={() => setOpen(false)}>
              <X className="size-4" aria-hidden />
            </IconButton>
          </div>
          <WorkbenchNav projectId={projectId} collapsible={false} />
        </Modal>
      ) : null}
    </div>
  );
}
