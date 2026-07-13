import type { ReactNode } from "react";

type PublicErrorNoticeProps = {
  action?: ReactNode;
  message: ReactNode;
  recovery?: ReactNode;
  title: ReactNode;
};

/**
 * Author-safe failure surface: what happened, impact, and how to recover.
 * Do not pass internal codes, UUIDs, stack traces, or provider bodies.
 */
export function PublicErrorNotice({ action, message, recovery, title }: PublicErrorNoticeProps) {
  return (
    <div className="public-error-notice" role="alert">
      <strong>{title}</strong>
      <p>{message}</p>
      {recovery ? <p className="public-error-recovery">{recovery}</p> : null}
      {action ? <div className="public-error-action">{action}</div> : null}
    </div>
  );
}
