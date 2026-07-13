import type { ReactNode } from "react";

type MetaChipProps = {
  children: ReactNode;
  className?: string;
};

/** Compact secondary status chip for headers and list meta. */
export function MetaChip({ children, className = "" }: MetaChipProps) {
  return <span className={["status-pill", "meta-chip", className].filter(Boolean).join(" ")}>{children}</span>;
}
