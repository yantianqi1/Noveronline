"use client";

import { useEffect } from "react";

const SESSION_REFRESH_STORAGE_KEY = "mf_auto_refresh_at";
const SESSION_REFRESH_STATUS_KEY = "mf_auto_refresh_status";
const SESSION_REFRESH_COOLDOWN_MS = 25 * 60 * 1000;

export function SessionAutoRefresh(input: { enabled: boolean }) {
  useEffect(() => {
    if (!input.enabled) {
      return;
    }

    const now = Date.now();
    if (!claimRefreshWindow(now)) {
      return;
    }

    const controller = new AbortController();
    void refreshSession(controller.signal);
    return () => {
      controller.abort();
    };
  }, [input.enabled]);

  return null;
}

function claimRefreshWindow(now: number) {
  try {
    const previous = Number(window.sessionStorage.getItem(SESSION_REFRESH_STORAGE_KEY) ?? "0");
    if (Number.isFinite(previous) && now - previous < SESSION_REFRESH_COOLDOWN_MS) {
      return false;
    }
    window.sessionStorage.setItem(SESSION_REFRESH_STORAGE_KEY, String(now));
  } catch {
    return true;
  }
  return true;
}

async function refreshSession(signal: AbortSignal) {
  try {
    const response = await fetch("/api/auth/session/refresh", {
      method: "POST",
      credentials: "same-origin",
      cache: "no-store",
      signal,
    });
    rememberRefreshStatus(response.ok ? "ok" : "failed");
  } catch {
    if (!signal.aborted) {
      rememberRefreshStatus("failed");
    }
  }
}

function rememberRefreshStatus(status: "ok" | "failed") {
  try {
    window.sessionStorage.setItem(SESSION_REFRESH_STATUS_KEY, status);
  } catch {
    return;
  }
}
