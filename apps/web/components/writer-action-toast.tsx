"use client";

import { CheckCircle2, X, XCircle } from "lucide-react";
import { useEffect, useState } from "react";

import { type Locale, tx } from "../lib/locale";
import { humanizeFailure } from "../lib/user-facing-copy";
import { Bi } from "./bilingual-text";

const TOAST_AUTO_DISMISS_MS = 3000;

type ActionToastProps = {
  locale: Locale;
  status: string;
  code: string;
};

/**
 * Compact toast for workspace action feedback.
 * Success auto-dismisses after 3 s; errors stay until manually closed.
 * OPTIMISTIC_CONFLICT is suppressed here (handled inside the editor).
 */
export function ActionToast({ locale, status, code }: ActionToastProps) {
  const [visible, setVisible] = useState(true);

  const isError = status === "error";
  const isConflict = code === "OPTIMISTIC_CONFLICT";

  useEffect(() => {
    if (isError) return;
    const timer = setTimeout(() => setVisible(false), TOAST_AUTO_DISMISS_MS);
    return () => clearTimeout(timer);
  }, [isError]);

  if (!visible || isConflict) return null;

  const errorText = humanizeFailure(locale, code);

  return (
    <div
      className={`writer-action-toast ${isError ? "writer-action-toast--error" : "writer-action-toast--success"}`}
      role="status"
      data-workspace-code={code || undefined}
    >
      {isError ? (
        <XCircle aria-hidden="true" size={14} />
      ) : (
        <CheckCircle2 aria-hidden="true" size={14} />
      )}
      <span className="writer-action-toast-text">
        {isError ? errorText : <Bi zh="操作已提交" en="Action submitted" />}
      </span>
      <button
        aria-label={tx(locale, "关闭", "Dismiss")}
        className="writer-action-toast-close"
        onClick={() => setVisible(false)}
        type="button"
      >
        <X aria-hidden="true" size={12} />
      </button>
    </div>
  );
}
