import type { ReactNode } from "react";

type WorkspaceHeaderProps = {
  actions?: ReactNode;
  className?: string;
  description?: ReactNode;
  /** Optional kicker; omit when it only repeats the title. */
  eyebrow?: ReactNode;
  icon?: ReactNode;
  meta?: ReactNode;
  title: ReactNode;
};

/**
 * Compact paper-style page header for creative workbenches.
 * Prefer one primary action; keep secondary stats as small meta chips.
 * Keep height tight (~72–96px content) — no marketing heroes.
 * Description should be one short line; meta should stay to ~2 pills.
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
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
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
