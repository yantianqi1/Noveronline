import type { ReactNode } from "react";

type EmptyStateProps = {
  action?: ReactNode;
  className?: string;
  description?: ReactNode;
  title: ReactNode;
};

/** Quiet empty surface for browse/search zero results. */
export function EmptyState({ action, className = "", description, title }: EmptyStateProps) {
  return (
    <div className={["empty-state", className].filter(Boolean).join(" ")} role="status">
      <strong className="empty-state-title">{title}</strong>
      {description ? <p className="empty-state-description">{description}</p> : null}
      {action ? <div className="empty-state-action">{action}</div> : null}
    </div>
  );
}
