import type { ButtonHTMLAttributes, ReactNode } from "react";

type UiButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  tone?: "primary" | "secondary" | "danger" | "ghost";
};

/**
 * Shared paper-ink control. Prefer data-tone="primary" only for the page's
 * single filled action.
 */
export function UiButton({
  children,
  className = "",
  tone = "secondary",
  type = "button",
  ...rest
}: UiButtonProps) {
  return (
    <button
      {...rest}
      className={["ui-button", className].filter(Boolean).join(" ")}
      data-tone={tone}
      type={type}
    >
      {children}
    </button>
  );
}
