"use client";

import { useEffect } from "react";

/**
 * After channel create/update/sync/disable, the page remounts via server-action
 * redirect. Restore the operator to the edited channel card without the browser
 * smooth-scrolling from the document top (which feels like chaotic jumping).
 */
export function LLMChannelFocus({
  focusChannelId,
  focusChannelKey,
}: {
  focusChannelId?: string;
  focusChannelKey?: string;
}) {
  useEffect(() => {
    const fromHash = typeof window !== "undefined" ? window.location.hash.replace(/^#/, "").trim() : "";
    const targetId =
      (focusChannelId && focusChannelId.trim()) ||
      (fromHash.startsWith("channel-") ? fromHash : "") ||
      (focusChannelKey ? `channel-${focusChannelKey.trim()}` : "");
    if (!targetId) {
      return;
    }

    const card = document.getElementById(targetId);
    if (!(card instanceof HTMLDetailsElement)) {
      return;
    }

    const adminGroup = card.closest("details.llm-module-group");
    if (adminGroup instanceof HTMLDetailsElement) {
      adminGroup.open = true;
    }
    card.open = true;

    // Instant restore: html has data-scroll-behavior="smooth", which otherwise
    // animates from y=0 after the redirect remount and looks like thrashing.
    const previous = document.documentElement.style.scrollBehavior;
    document.documentElement.style.scrollBehavior = "auto";
    card.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "auto" });
    window.requestAnimationFrame(() => {
      document.documentElement.style.scrollBehavior = previous;
    });
  }, [focusChannelId, focusChannelKey]);

  return null;
}
