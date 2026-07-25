import { cn } from "@/lib/utils";

/**
 * WorkbenchMasthead — the one compact栏目条 every workbench uses.
 *
 * Replaces the old three-tier stacked masthead (eyebrow / big title / tagline
 * paragraph) that pushed real content to the middle of the screen. Everything
 * collapses into a single row: a vermilion eyebrow chip, the serif title, the
 * tagline as a quiet inline aside, and any status/count/actions pinned right.
 * The full tagline survives as a tooltip, so no information is lost — it's just
 * no longer paying for a full-width row of vertical space.
 *
 * Height target: one ~52px row instead of ~120px of stack.
 */
export function WorkbenchMasthead({
  eyebrow,
  title,
  tagline,
  aside,
  className,
}: {
  /** The small-caps vermilion label, e.g. "资 产 库". */
  eyebrow: string;
  /** The serif workbench title, e.g. "故事资产". */
  title: string;
  /** One-line description; rendered inline, truncated, with full text on hover. */
  tagline?: string;
  /** Right-aligned status / counts / actions. */
  aside?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex h-[52px] shrink-0 items-center gap-3 border-b border-line-soft px-6",
        className,
      )}
    >
      <span className="shrink-0 rounded-[6px] border border-accent/30 bg-accent-wash px-2 py-1 text-[10.5px] font-medium tracking-[0.22em] text-accent">
        {eyebrow}
      </span>
      <h1 className="shrink-0 font-serif text-[18px] font-semibold leading-none text-ink">{title}</h1>
      {tagline ? (
        <>
          <span aria-hidden className="h-4 w-px shrink-0 bg-line" />
          <p
            title={tagline}
            className="min-w-0 flex-1 truncate text-[12.5px] leading-none text-muted"
          >
            {tagline}
          </p>
        </>
      ) : (
        <span className="flex-1" />
      )}
      {aside ? <div className="flex shrink-0 items-center gap-3">{aside}</div> : null}
    </div>
  );
}
