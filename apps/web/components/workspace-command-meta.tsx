"use client";

import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

/**
 * Renders page-specific stats into the sticky workspace command bar slot.
 * Used when a workbench drops its local WorkspaceHeader and keeps only two
 * high-signal facts in the top chrome.
 */
export function WorkspaceCommandMeta({ children }: { children: ReactNode }) {
  const [slot, setSlot] = useState<HTMLElement | null>(null);

  useEffect(() => {
    setSlot(document.querySelector<HTMLElement>("[data-workspace-command-meta]"));
  }, []);

  if (!slot) {
    return null;
  }
  return createPortal(children, slot);
}
