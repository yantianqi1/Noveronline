import type { ReactNode } from "react";

type PublicErrorNoticeProps = {
  action?: ReactNode;
  /** Optional machine diagnostics; never shown as primary copy. */
  diagnostics?: ReactNode;
  message: ReactNode;
  recovery?: ReactNode;
  title: ReactNode;
};

/**
 * Author-safe failure surface: what happened, impact, and how to recover.
 * Do not pass internal codes, UUIDs, stack traces, or provider bodies as title/message.
 * Put codes only in `diagnostics` (collapsed by default).
 */
export function PublicErrorNotice({
  action,
  diagnostics,
  message,
  recovery,
  title,
}: PublicErrorNoticeProps) {
  return (
    <div className="public-error-notice" role="alert">
      <strong>{title}</strong>
      <p>{message}</p>
      {recovery ? <p className="public-error-recovery">{recovery}</p> : null}
      {action ? <div className="public-error-action">{action}</div> : null}
      {diagnostics ? (
        <details className="public-error-diagnostics">
          <summary>诊断信息</summary>
          <div className="public-error-diagnostics-body">{diagnostics}</div>
        </details>
      ) : null}
    </div>
  );
}
