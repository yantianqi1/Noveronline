"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

export function WriterRunAutoRefresh({
  active,
  intervalMs = 1800,
}: {
  active: boolean;
  intervalMs?: number;
}) {
  const router = useRouter();

  useEffect(() => {
    if (!active) {
      return;
    }
    const refresh = () => {
      if (document.visibilityState === "visible") {
        router.refresh();
      }
    };
    const interval = window.setInterval(refresh, Math.max(1500, intervalMs));
    const first = window.setTimeout(refresh, 700);
    return () => {
      window.clearInterval(interval);
      window.clearTimeout(first);
    };
  }, [active, intervalMs, router]);

  return null;
}
