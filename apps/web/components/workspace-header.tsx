import type { ReactNode } from "react";

type WorkspaceHeaderProps = {
  actions?: ReactNode;
  className?: string;
  description?: ReactNode;
  eyebrow: ReactNode;
  icon?: ReactNode;
  meta?: ReactNode;
  title: ReactNode;
};

/**
 * Compact paper-style page header for creative workbenches.
 * Prefer one primary action; keep secondary stats as small meta chips.
 * Keep height tight (~72–96px content) — no marketing heroes.
 */
export function WorkspaceHeader({
  actions,
  className = "",
  description,
  eyebrow,
  icon,
  meta,
  title,
}: WorkspaceHeaderProps) {
  return (
    <header className={["workspace-header", "workspace-header-compact", className].filter(Boolean).join(" ")}>
      <div className="workspace-header-copy">
        <p className="eyebrow">{eyebrow}</p>
        <h1>
          {icon ? (
            <span className="page-title-icon" aria-hidden="true">
              {icon}
            </span>
          ) : null}
          {title}
        </h1>
        {description ? <p className="workspace-header-description overview-intro">{description}</p> : null}
        {meta ? <div className="status-row workspace-header-meta">{meta}</div> : null}
      </div>
      {actions ? <div className="workspace-header-actions">{actions}</div> : null}
    </header>
  );
}
