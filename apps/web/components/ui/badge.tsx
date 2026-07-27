import { cva, type VariantProps } from "class-variance-authority";
import type { HTMLAttributes } from "react";

import { cn } from "@/lib/utils";

/**
 * Status pills and lifecycle marks.
 *
 * The tone names are the semantic contract, not colour names: `success`
 * completes, `candidate` awaits review, `danger` failed. Vermilion (`accent`)
 * is reserved for the brand and for selection — before this existed, "已完成"
 * and "失败" were both solid red, so the colour carried no information at all.
 *
 * Colour is never the only signal: pair a badge with an icon or explicit text.
 */
const badgeVariants = cva(
  "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5 text-caption font-medium",
  {
    variants: {
      tone: {
        neutral: "border border-line bg-paper text-muted",
        accent: "border border-accent/30 bg-accent-wash text-accent",
        success: "border border-success/30 bg-success-wash text-success",
        warning: "border border-warning/30 bg-warning-wash text-warning",
        danger: "border border-danger/30 bg-danger-wash text-danger",
        candidate: "border border-candidate/30 bg-candidate-wash text-candidate",
      },
      solid: {
        true: "border-transparent",
        false: "",
      },
    },
    compoundVariants: [
      { tone: "accent", solid: true, class: "bg-accent text-panel" },
      { tone: "success", solid: true, class: "bg-success text-panel" },
      { tone: "warning", solid: true, class: "bg-warning text-panel" },
      { tone: "danger", solid: true, class: "bg-danger text-panel" },
      { tone: "candidate", solid: true, class: "bg-candidate text-panel" },
    ],
    defaultVariants: { tone: "neutral", solid: false },
  },
);

export interface BadgeProps
  extends HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, tone, solid, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ tone, solid }), className)} {...props} />;
}

/**
 * The workbench eyebrow label.
 *
 * Deliberately not vermilion. Ten copies of this chip were painted in accent,
 * which meant every screen carried three or four permanent red marks and the
 * one action that mattered no longer stood out. Hanzi labels also must not
 * carry hand-typed spaces — the tracking token does that work.
 */
export function Eyebrow({ className, ...props }: HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "shrink-0 rounded-control border border-line-soft bg-paper-deep px-2 py-1 text-caption font-medium tracking-label text-muted",
        className,
      )}
      {...props}
    />
  );
}
