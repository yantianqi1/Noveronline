"use client";

import { useEffect } from "react";

import type { CurrentUserSessionsSummary } from "../lib/api";

const SESSION_REFRESH_STORAGE_KEY = "mf_auto_refresh_at";
const SESSION_REFRESH_STATUS_KEY = "mf_auto_refresh_status";
const SESSION_REFRESH_COOLDOWN_MS = 25 * 60 * 1000;
const SESSION_REFRESH_THRESHOLD_MS = 15 * 60 * 1000;

export function SessionAutoRefresh(input: { enabled: boolean }) {
  useEffect(() => {
    if (!input.enabled) {
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      void refreshSessionWhenNeeded(controller.signal);
    }, 1000);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [input.enabled]);

  return null;
}

async function refreshSessionWhenNeeded(signal: AbortSignal) {
  try {
    const response = await fetch("/api/auth/sessions", {
      credentials: "same-origin",
      cache: "no-store",
      signal,
    });
    if (!response.ok) {
      return;
    }
    const summary = await response.json() as CurrentUserSessionsSummary;
    const currentSession = summary.ok
      ? summary.sessions.find((session) => session.current)
      : undefined;
    const now = Date.now();
    const expiresAt = Date.parse(currentSession?.expires_at ?? "");
    if (!Number.isFinite(expiresAt) || expiresAt - now > SESSION_REFRESH_THRESHOLD_MS) {
      return;
    }
    if (claimRefreshWindow(now)) {
      await refreshSession(signal);
    }
  } catch {
    return;
  }
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
