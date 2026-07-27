import { Eyebrow } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * WorkbenchMasthead — the one compact栏目条 every workbench uses.
 *
 * Replaces the old three-tier stacked masthead (eyebrow / big title / tagline
 * paragraph) that pushed real content to the middle of the screen. Everything
 * collapses into a single row: a quiet eyebrow chip, the serif title, the
 * tagline as an inline aside, and any status/count/actions pinned right.
 * The full tagline survives as a tooltip, so no information is lost — it's just
 * no longer paying for a full-width row of vertical space.
 *
 * The eyebrow used to be vermilion on every workbench, which meant each screen
 * opened with a permanent red mark competing with its actual primary action.
 * It is neutral now; red is reserved for the one thing worth doing.
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
  /** The quiet section label, e.g. "资产库". */
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
        "flex h-[52px] shrink-0 items-center gap-2 overflow-hidden border-b border-line-soft px-4 stack:gap-3 stack:px-6",
        className,
      )}
    >
      {/* On the phone band the header already names the section, so the chip
          and the tagline would only repeat it and crowd out the aside. */}
      <Eyebrow className="hidden stack:inline-flex">{eyebrow}</Eyebrow>
      <h1 className="min-w-0 shrink truncate font-serif text-lg font-semibold text-ink">{title}</h1>
      {tagline ? (
        <>
          <span aria-hidden className="hidden h-4 w-px shrink-0 bg-line stack:block" />
          <p title={tagline} className="hidden min-w-0 flex-1 truncate text-caption text-muted stack:block">
            {tagline}
          </p>
        </>
      ) : null}
      {aside ? (
        <div className="ml-auto flex shrink-0 items-center gap-3">{aside}</div>
      ) : null}
    </div>
  );
}
