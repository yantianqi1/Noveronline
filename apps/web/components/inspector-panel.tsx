import type { ReactNode } from "react";

type InspectorPanelProps = {
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  collapsed?: boolean;
  status?: ReactNode;
  title: ReactNode;
};

/**
 * Progressive-disclosure inspector for detail, evidence, and secondary context.
 * On narrow viewports CSS turns this into a bottom sheet surface.
 */
export function InspectorPanel({
  actions,
  children,
  className = "",
  collapsed = false,
  status,
  title,
}: InspectorPanelProps) {
  return (
    <aside
      className={["inspector-panel", className].filter(Boolean).join(" ")}
      data-collapsed={collapsed ? "true" : "false"}
    >
      <header className="inspector-panel-header">
        <div>
          <h2>{title}</h2>
          {status ? <div className="inspector-panel-status">{status}</div> : null}
        </div>
        {actions ? <div className="inspector-panel-actions">{actions}</div> : null}
      </header>
      <div className="inspector-panel-body">{children}</div>
    </aside>
  );
}
