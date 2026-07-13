import type { ReactNode } from "react";

type WorkspaceDisclosureProps = {
  children: ReactNode;
  className?: string;
  description?: ReactNode;
  label: ReactNode;
  open?: boolean;
  tone?: "default" | "ink" | "technical";
};

export function WorkspaceDisclosure({
  children,
  className = "",
  description,
  label,
  open = false,
  tone = "default",
}: WorkspaceDisclosureProps) {
  return (
    <details
      className={["workspace-disclosure", className].filter(Boolean).join(" ")}
      data-tone={tone}
      open={open}
    >
      <summary>
        <span>{label}</span>
        {description ? <small>{description}</small> : null}
      </summary>
      <div className="workspace-disclosure-content">{children}</div>
    </details>
  );
}
