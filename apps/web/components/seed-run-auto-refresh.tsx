"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

/**
 * While a Seed run is active, periodically refresh the Overview RSC tree so
 * workflow status/progress/events appear without a manual reload.
 * This is not token streaming; it is status/event polling against the read API.
 */
export function SeedRunAutoRefresh({
  active,
  intervalMs = 3000,
}: {
  active: boolean;
  intervalMs?: number;
}) {
  const router = useRouter();

  useEffect(() => {
    if (!active) {
      return;
    }
    const id = window.setInterval(() => {
      router.refresh();
    }, Math.max(1500, intervalMs));
    // Immediate refresh shortly after mount so a just-started run does not sit on the first queued snapshot.
    const first = window.setTimeout(() => router.refresh(), 800);
    return () => {
      window.clearInterval(id);
      window.clearTimeout(first);
    };
  }, [active, intervalMs, router]);

  return null;
}
