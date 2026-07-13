"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

export const WORKSPACE_NAVIGATION_START_EVENT = "mirofish:workspace-navigation-start";
export const WORKSPACE_NAVIGATION_COMPLETE_EVENT = "mirofish:workspace-navigation-complete";

const navigationFallbackTimeoutMs = 10_000;

export function signalWorkspaceNavigationStart() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(WORKSPACE_NAVIGATION_START_EVENT));
  }
}

export function signalWorkspaceNavigationComplete() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(WORKSPACE_NAVIGATION_COMPLETE_EVENT));
  }
}

export function WorkspaceRouteTransition({ children }: Readonly<{ children: React.ReactNode }>) {
  const pathname = usePathname();
  const [pending, setPending] = useState(false);
  const fallbackTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    function clearPending() {
      setPending(false);
      if (fallbackTimer.current !== undefined) {
        window.clearTimeout(fallbackTimer.current);
        fallbackTimer.current = undefined;
      }
      document.getElementById("workspace-main")?.focus({ preventScroll: true });
    }

    function beginNavigation() {
      if (fallbackTimer.current !== undefined) {
        window.clearTimeout(fallbackTimer.current);
      }
      setPending(true);
      fallbackTimer.current = window.setTimeout(clearPending, navigationFallbackTimeoutMs);
    }

    window.addEventListener(WORKSPACE_NAVIGATION_START_EVENT, beginNavigation);
    window.addEventListener(WORKSPACE_NAVIGATION_COMPLETE_EVENT, clearPending);
    return () => {
      window.removeEventListener(WORKSPACE_NAVIGATION_START_EVENT, beginNavigation);
      window.removeEventListener(WORKSPACE_NAVIGATION_COMPLETE_EVENT, clearPending);
      if (fallbackTimer.current !== undefined) {
        window.clearTimeout(fallbackTimer.current);
      }
    };
  }, []);

  return (
    <div className="workspace-route-stage" data-pending={pending ? "true" : "false"}>
      <div
        aria-hidden="true"
        className="workspace-route-progress"
        data-visible={pending ? "true" : "false"}
      >
        <span />
      </div>
      <div className="workspace-route-content" key={pathname}>
        {children}
      </div>
    </div>
  );
}
