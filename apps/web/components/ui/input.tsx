import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, invalid = false, ...props }, ref) => {
    return (
      <input
        ref={ref}
        aria-invalid={invalid || undefined}
        className={cn(
          "flex h-11 w-full rounded-control border bg-panel px-3.5 text-md text-ink shadow-hairline transition-colors placeholder:text-muted-soft",
          "outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/25",
          "disabled:cursor-not-allowed disabled:opacity-55",
          // Error state reads as danger, not brand. Both used to be vermilion
          // rings, so "I'm editing this" and "this is wrong" looked identical.
          invalid ? "border-danger ring-1 ring-danger/25" : "border-line",
          className,
        )}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";
