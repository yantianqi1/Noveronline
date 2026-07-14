"use client";

import { Check, CircleAlert, X } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { type Locale, tx } from "../lib/locale";
import { humanizeFailure } from "../lib/user-facing-copy";
import { Bi } from "./bilingual-text";

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
 * Strips writerRunStatus* query params after show so refresh stays clean.
 */
export function WriterTransientToast({ locale, status }: WriterTransientToastProps) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const [toast, setToast] = useState<{ tone: ToastTone; text: string } | null>(null);
  const shownKeyRef = useRef<string>("");

  const clearStatusQuery = useCallback(() => {
    const next = new URLSearchParams(searchParams.toString());
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
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }, [pathname, router, searchParams]);

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
        ? rawMessage || tx(locale, "写作任务已加入队列，等待 Pi Writer 执行", "Writer run queued for Pi Writer")
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

/** Fallback copy helper for non-client call sites. */
export function writerAdmissionSuccessCopy(locale: Locale) {
  return tx(locale, "写作任务已加入队列", "Writer run queued");
}

export function WriterTransientToastFallback() {
  return (
    <p className="sr-only">
      <Bi zh="状态提示" en="Status notice" />
    </p>
  );
}
