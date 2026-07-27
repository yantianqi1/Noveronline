import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Paper surfaces.
 *
 * `border border-line bg-panel` plus a hairline shadow was hand-written in 35
 * files, drifting a little each time. One definition keeps every card, panel,
 * and popover on the same paper stock and the same light source.
 */
const cardVariants = cva("border border-line bg-panel", {
  variants: {
    elevation: {
      flat: "shadow-none",
      hairline: "shadow-hairline",
      lift: "shadow-lift",
      panel: "shadow-panel",
    },
    radius: {
      control: "rounded-control",
      panel: "rounded-panel",
      modal: "rounded-modal",
    },
    padding: {
      none: "",
      sm: "p-3",
      md: "p-4",
      lg: "p-5",
    },
  },
  defaultVariants: { elevation: "hairline", radius: "panel", padding: "none" },
});

export interface CardProps
  extends HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof cardVariants> {}

export function Card({ className, elevation, radius, padding, ...props }: CardProps) {
  return <div className={cn(cardVariants({ elevation, radius, padding }), className)} {...props} />;
}

/**
 * A titled block inside a rail or panel. Replaces the per-rail section headers
 * that each picked their own size, tracking, and spacing.
 */
export function RailSection({
  title,
  action,
  className,
  children,
}: {
  title: string;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn("px-4 py-4", className)}>
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <h3 className="text-caption font-medium tracking-label text-muted">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

/**
 * Empty state: one icon, one sentence, at most one action. The spec requires
 * every empty state to name the next step rather than just report absence.
 */
export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-8 py-12 text-center", className)}>
      {icon ? (
        <div className="mb-4 grid size-12 place-items-center rounded-full border border-line bg-panel text-muted">
          {icon}
        </div>
      ) : null}
      <p className="font-serif text-lg font-semibold text-ink">{title}</p>
      {description ? (
        <p className="mt-2 max-w-[42ch] text-base text-muted">{description}</p>
      ) : null}
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
