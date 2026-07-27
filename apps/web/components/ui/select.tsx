"use client";

import { ChevronDown } from "lucide-react";
import { forwardRef, type SelectHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Native select with the paper chrome applied.
 *
 * Native rather than custom on purpose: the spec prefers system controls, and
 * the settings surface has dozens of these — a bespoke listbox would cost
 * keyboard and mobile behaviour for nothing. The default arrow is suppressed
 * so the chevron matches the rest of the lucide icon set.
 */
export const Select = forwardRef<HTMLSelectElement, SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <div className="relative inline-flex min-w-0 items-center">
      <select
        ref={ref}
        className={cn(
          "h-9 w-full min-w-0 appearance-none rounded-control border border-line bg-panel py-0 pl-3 pr-8 text-sm text-ink shadow-hairline transition-colors outline-none",
          "hover:border-accent/50 focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/25",
          "disabled:cursor-not-allowed disabled:opacity-55",
          className,
        )}
        {...props}
      >
        {children}
      </select>
      <ChevronDown
        aria-hidden
        className="pointer-events-none absolute right-2.5 size-3.5 text-muted"
      />
    </div>
  ),
);
Select.displayName = "Select";
