"use client";

import { Check, CircleAlert, X } from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { type Locale, tx } from "../lib/locale";
import { humanizeFailure } from "../lib/user-facing-copy";

const HOLD_MS = 3200;
const STATUS_KEYS = ["writerRunStatus", "writerRunCode", "writerRunMessage"] as const;

type ToastTone = "success" | "error";

type WriterTransientToastProps = {
  locale: Locale;
  /** Server-passed status from the last form redirect (optional; URL is also read). */
  status?: { status: string; code: string; message: string } | null;
};

/**
 * Light auto-dismiss toast for writer admission feedback.
 * Replaces the permanent "操作已提交" strip above the composer.
 * Strips writerRunStatus* query params via history.replaceState so we never
 * trigger a second RSC navigation (the double flash after server redirect).
 */
export function WriterTransientToast({ locale, status }: WriterTransientToastProps) {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [toast, setToast] = useState<{ tone: ToastTone; text: string } | null>(null);
  const shownKeyRef = useRef<string>("");

  const clearStatusQuery = useCallback(() => {
    if (typeof window === "undefined") {
      return;
    }
    const next = new URLSearchParams(window.location.search);
    let changed = false;
    for (const key of STATUS_KEYS) {
      if (next.has(key)) {
        next.delete(key);
        changed = true;
      }
    }
    if (!changed) {
      return;
    }
    const qs = next.toString();
    const href = qs ? `${pathname}?${qs}` : pathname;
    // Soft URL clean only — avoid a second Next.js navigation flash.
    window.history.replaceState(window.history.state, "", href);
  }, [pathname]);

  const queryStatus = searchParams.get("writerRunStatus");
  const queryMessage = searchParams.get("writerRunMessage");
  const queryCode = searchParams.get("writerRunCode");

  useEffect(() => {
    // Prefer URL (fresh redirect). Fall back to server prop once per code+status.
    const toneRaw = queryStatus || status?.status || "";
    if (toneRaw !== "success" && toneRaw !== "error") {
      return;
    }
    const code = queryCode || status?.code || "";
    const rawMessage = queryMessage || status?.message || "";
    const message =
      toneRaw === "success"
        ? rawMessage || tx(locale, "已开始处理", "Started")
        : humanizeFailure(locale, code, rawMessage || undefined);
    const key = `${toneRaw}:${code}:${message}`;
    if (shownKeyRef.current === key) {
      return;
    }
    shownKeyRef.current = key;
    setToast({
      tone: toneRaw === "error" ? "error" : "success",
      text: message,
    });
    const clearTimer = window.setTimeout(() => {
      clearStatusQuery();
    }, 80);
    const hideTimer = window.setTimeout(() => {
      setToast(null);
    }, HOLD_MS);
    return () => {
      window.clearTimeout(clearTimer);
      window.clearTimeout(hideTimer);
    };
  }, [queryStatus, queryMessage, queryCode, status?.status, status?.message, status?.code, locale, clearStatusQuery]);

  if (!toast) {
    return null;
  }

  return (
    <div
      className="writer-transient-toast"
      data-tone={toast.tone}
      role={toast.tone === "error" ? "alert" : "status"}
      aria-live="polite"
    >
      <span className="writer-transient-toast-icon" aria-hidden="true">
        {toast.tone === "error" ? <CircleAlert size={16} /> : <Check size={16} />}
      </span>
      <p>{toast.text}</p>
      <button
        type="button"
        className="writer-transient-toast-dismiss"
        aria-label={tx(locale, "关闭", "Dismiss")}
        onClick={() => setToast(null)}
      >
        <X size={14} />
      </button>
    </div>
  );
}
