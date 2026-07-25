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
          "flex h-11 w-full rounded-[10px] border bg-panel px-3.5 text-[15px] text-ink shadow-[0_1px_2px_rgba(23,26,27,0.04)] transition-colors duration-200 placeholder:text-muted/60",
          "outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/25",
          "disabled:cursor-not-allowed disabled:opacity-55",
          invalid ? "border-accent/70 ring-1 ring-accent/20" : "border-line",
          className,
        )}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";
