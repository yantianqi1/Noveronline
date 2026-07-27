import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Heights follow the spec's control sizing: 40px on desktop, 44px+ where a
 * touch target is the primary affordance. `primary` is the only filled
 * vermilion variant — a screen should carry exactly one of it, with every
 * other action stepping down to outline / subtle / ghost.
 */
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-control font-medium transition-all outline-none focus-visible:ring-2 focus-visible:ring-accent/40 focus-visible:ring-offset-2 focus-visible:ring-offset-paper disabled:pointer-events-none disabled:opacity-55 active:translate-y-px",
  {
    variants: {
      variant: {
        primary: "bg-accent text-panel shadow-accent hover:bg-accent-strong",
        outline:
          "border border-line bg-panel text-ink shadow-hairline hover:border-accent/50 hover:text-accent",
        subtle: "bg-paper-deep text-ink hover:bg-line-soft",
        ghost: "text-muted hover:bg-accent-wash hover:text-accent",
        danger:
          "border border-danger/40 bg-danger-wash text-danger hover:bg-danger hover:text-panel",
      },
      size: {
        lg: "h-12 px-6 text-md",
        md: "h-10 px-5 text-base",
        sm: "h-9 px-3.5 text-sm",
        xs: "h-8 px-3 text-caption",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "md",
    },
  },
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
  loading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, loading = false, disabled, children, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        ref={ref}
        className={cn(buttonVariants({ variant, size }), className)}
        disabled={disabled || loading}
        aria-busy={loading || undefined}
        {...props}
      >
        {loading ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
        {children}
      </Comp>
    );
  },
);
Button.displayName = "Button";

export { buttonVariants };
