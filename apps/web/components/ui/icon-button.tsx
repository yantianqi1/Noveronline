import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Icon-only control.
 *
 * `label` is required, not optional: an icon button with no accessible name is
 * invisible to a screen reader, and the spec requires every icon-only button to
 * carry one. The visual box stays small while `before:` widens the hit area to
 * the 44px touch minimum without disturbing layout.
 */
const iconButtonVariants = cva(
  "relative inline-grid place-items-center rounded-control text-muted transition-colors outline-none before:absolute before:left-1/2 before:top-1/2 before:size-11 before:-translate-x-1/2 before:-translate-y-1/2 before:content-[''] focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2 focus-visible:ring-offset-paper disabled:pointer-events-none disabled:opacity-55",
  {
    variants: {
      variant: {
        ghost: "hover:bg-paper-deep hover:text-ink",
        outline: "border border-line bg-panel hover:border-accent/50 hover:text-accent",
        danger: "hover:bg-danger-wash hover:text-danger",
      },
      size: {
        md: "size-9",
        sm: "size-8",
      },
    },
    defaultVariants: { variant: "ghost", size: "md" },
  },
);

export interface IconButtonProps
  extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label">,
    VariantProps<typeof iconButtonVariants> {
  /** Accessible name. Also used as the native tooltip. */
  label: string;
}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  ({ className, variant, size, label, type = "button", children, ...props }, ref) => (
    <button
      ref={ref}
      type={type}
      aria-label={label}
      title={label}
      className={cn(iconButtonVariants({ variant, size }), className)}
      {...props}
    >
      {children}
    </button>
  ),
);
IconButton.displayName = "IconButton";
