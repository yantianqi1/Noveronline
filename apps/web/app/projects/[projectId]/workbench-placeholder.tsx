import type { LucideIcon } from "lucide-react";

/**
 * Honest "this workbench is being built" surface.
 *
 * Shown for each of the seven workbenches until its real implementation lands.
 * This is empty-state chrome only — it deliberately shows NO fabricated data,
 * per the no-mock rule. It names the workbench, states what it will do, and
 * keeps the editorial language consistent so the shell feels finished while
 * the domain surfaces are wired up one by one.
 */
export function WorkbenchPlaceholder({
  icon: Icon,
  title,
  tagline,
}: {
  icon: LucideIcon;
  title: string;
  tagline: string;
}) {
  return (
    <div className="flex h-full min-h-[calc(100vh-3.5rem)] flex-col">
      {/* section header */}
      <div className="border-b border-line-soft px-8 py-7">
        <p className="mb-1 text-caption font-medium tracking-label text-muted">
          工作台
        </p>
        <h1 className="font-serif text-display font-semibold leading-tight text-ink">{title}</h1>
        <p className="mt-2 max-w-[520px] text-base leading-relaxed text-muted">{tagline}</p>
      </div>

      {/* empty-state body */}
      <div className="flex flex-1 items-center justify-center px-8 py-16">
        <div className="flex max-w-md flex-col items-center text-center animate-fade-up">
          <span className="grid size-16 place-items-center rounded-modal bg-accent-wash text-accent">
            <Icon className="size-7" aria-hidden />
          </span>
          <h2 className="mt-6 font-serif text-xl font-semibold text-ink">正在搭建</h2>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            这一面工作台还在接入后端能力，很快会在这里完成它的主任务。
          </p>
          <div className="mt-6 flex items-center gap-2 text-caption tracking-label text-muted-soft">
            <span className="h-px w-8 bg-line" />
            <span>墨鱼小说 · 重构进行中</span>
            <span className="h-px w-8 bg-line" />
          </div>
        </div>
      </div>
    </div>
  );
}
